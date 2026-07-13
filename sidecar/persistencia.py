"""
Persistência local do estado do usuário (ADR-0012, REQ-F-018).

Um único arquivo SQLite gerido pelo sidecar — a GUI nunca toca o banco. O
arquivo fica no perfil do usuário (`%APPDATA%\\HelperFinanceiro\\dados.db`),
fora do repositório e fora de logs (REQ-SEC-001); o mapa de anonimização
continua existindo apenas em memória (REQ-SEC-003) — nada daqui vai ao LLM.

Conexão única + `threading.Lock` (o FastAPI atende em múltiplas threads), mesmo
padrão do `_JOBS_IA`. A tabela `esquema` versiona o banco para migrações
futuras; `rubrica` já nasce com a coluna `mes` (NULL = orçamento vivo) para o
histórico mensal entrar sem migração dolorosa.

## Cofre cifrado (ADR-0016 §B, REQ-SEC-006) — T-1602

O contêiner do banco passa a ser **SQLCipher** (AES-256): o `Repositorio` recebe
a **DEK** (32 bytes, vinda do `auth.py`/T-1601) e a aplica por `PRAGMA key` antes
de qualquer consulta. Detalhes de projeto (decididos na ADR):

- **Raw key, sem KDF interno.** O PRAGMA usa a DEK como blob literal
  (`x'<64 hex>'`), o que PULA o PBKDF2 interno do SQLCipher: o KDF forte já é o
  Argon2id do cofre (T-1601) — empilhar dois KDFs só custaria latência. A DEK só
  aparece na montagem local do PRAGMA/ATTACH; **nunca** em log, repr ou exceção.
- **Sanidade pós-key.** Com chave errada o SQLCipher não falha no `PRAGMA key`,
  só na PRIMEIRA leitura — por isso, logo após aplicar a chave, fazemos um
  `SELECT count(*) FROM sqlite_master`; a falha vira `ChaveInvalida` (sem vazar
  a chave), não um erro obscuro lá na frente.
- **`dek=None` é transitório.** Mantém o comportamento antigo (sqlite3 da stdlib,
  banco em claro): existe para o `app.py` seguir funcionando até o T-1603 ligar a
  sessão do cofre, e para a migração conseguir LER o banco antigo em claro. O
  T-1603 remove esse uso em produção.
- **Migração atômica** (`migrar_para_cofre`): o schema lógico não muda
  (`VERSAO_ESQUEMA` continua 1), muda o contêiner. Exportamos o `dados.db` em
  claro para um `.novo` cifrado (`sqlcipher_export`), **verificamos** (integridade
  + contagem de linhas) ANTES de tocar no original e só então trocamos por
  `os.replace` (atômico). Qualquer falha antes disso remove o `.novo` e deixa o
  original intacto — o usuário nunca perde dados no meio do caminho.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import sqlcipher3  # driver do banco cifrado (ADR-0016 §B); em claro seguimos no sqlite3

VERSAO_ESQUEMA = 1

# Seções do orçamento que aceitam rubricas (ADR-0012: saldos ficam de fora).
CATEGORIAS_RUBRICA = ("renda", "fixas", "variaveis")

# Header mágico do SQLite em claro (16 bytes). O contêiner SQLCipher começa com
# bytes aleatórios (o sal), então a presença deste header detecta "ainda em claro".
_HEADER_SQLITE_CLARO = b"SQLite format 3\x00"

# Tabelas conferidas na verificação da migração (contagem de linhas por tabela).
_TABELAS_MIGRACAO = ("esquema", "estado", "rubrica")

_DDL_V1 = """
CREATE TABLE IF NOT EXISTS esquema (
    versao INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS estado (
    chave         TEXT PRIMARY KEY,
    json          TEXT NOT NULL,
    atualizado_em TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS rubrica (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    categoria TEXT NOT NULL CHECK (categoria IN ('renda', 'fixas', 'variaveis')),
    campo_pai TEXT NOT NULL,
    nome      TEXT NOT NULL,
    valor     REAL NOT NULL DEFAULT 0,
    ordem     INTEGER NOT NULL DEFAULT 0,
    mes       TEXT
);
CREATE INDEX IF NOT EXISTS idx_rubrica_campo ON rubrica (categoria, campo_pai);
"""


# --------------------------------------------------------------- exceções
class ChaveInvalida(Exception):
    """A DEK não abre o cofre (chave errada ou arquivo corrompido).

    A mensagem NUNCA contém a chave nem sua representação hex (REQ-SEC-001).
    """


class ErroMigracao(RuntimeError):
    """A migração para o cofre falhou na verificação; o original em claro é preservado."""


# --------------------------------------------------------- helpers de cofre
# INVARIANTE DE SEGURANÇA (C-21, REQ-SEC-001/006): nenhuma exceção que atravesse
# este módulo pode carregar a statement SQL que embute a DEK — nem no texto, nem
# na cadeia `__cause__`/`__context__`. A chave só aparece inline no `PRAGMA key`/
# `ATTACH ... KEY` montados aqui; se uma dessas execuções explodir, a exceção
# original (cujos `args` podem ecoar a statement com o hex) é SEVERADA e trocada
# por um erro de mensagem fixa. Severar de verdade exige levantar o erro limpo
# FORA do `except` que capturou a original: `raise ... from None` apenas SUPRIME
# o contexto na impressão, mas `__context__` continua apontando para a exceção
# com o hex. Isso é o cinto: a política do cofre (T-1603, revalidada no portão do
# C-21) é NÃO filtrar o stderr do SQLCipher globalmente — logo a defesa tem de
# nascer na fonte, aqui, antes que qualquer traceback chegue ao stderr que o
# Electron ecoa (`main.ts`).
def _blob_key(dek: bytes) -> str:
    """Representa a DEK como blob literal SQL `x'<hex>'` — raw key, sem KDF interno.

    Usada apenas para montar o `PRAGMA key`/`ATTACH ... KEY` localmente; o valor
    é efêmero e nunca vai a log, repr ou exceção (ADR-0016 §B, REQ-SEC-006).
    """
    return f"x'{dek.hex()}'"


def _conectar(caminho: Path, dek: bytes | None) -> sqlite3.Connection:
    """Abre a conexão do repositório: em claro (`dek=None`) ou cifrada (SQLCipher).

    Com DEK: aplica a raw key e faz uma leitura de sanidade — o SQLCipher só
    acusa chave errada na PRIMEIRA leitura, não no `PRAGMA key` —, traduzindo a
    falha em `ChaveInvalida` (sem vazar a chave). `check_same_thread=False`: quem
    serializa o acesso é o lock do `Repositorio`, não o driver.
    """
    if dek is None:
        con = sqlite3.connect(str(caminho), check_same_thread=False)
        con.row_factory = sqlite3.Row
        return con
    cifrada = sqlcipher3.connect(str(caminho), check_same_thread=False)
    cifrada.row_factory = sqlcipher3.Row
    # O `PRAGMA key` (que embute o hex da DEK) e a leitura de sanidade compartilham
    # o MESMO tratamento: chave errada só falha na PRIMEIRA leitura, mas um erro no
    # próprio `PRAGMA key` — ou um traceback que ecoe a statement — carregaria o hex.
    # Capturamos `Exception` (largo de propósito: a fonte do erro não importa, o que
    # importa é que NADA derivado da chave escape) e trocamos por `ChaveInvalida` de
    # mensagem fixa. A exceção limpa é criada aqui mas LEVANTADA FORA do `except`
    # (ver abaixo): `raise ... from None` só SUPRIME o contexto — o `__context__`
    # ainda apontaria para a exceção original com o hex; levantar sem um `except`
    # ativo nasce com `__context__ = None`, severando o vínculo de verdade.
    erro_de_chave: ChaveInvalida | None = None
    try:
        cifrada.execute(f'PRAGMA key = "{_blob_key(dek)}"')
        cifrada.execute("SELECT count(*) FROM sqlite_master").fetchone()
    except Exception:
        cifrada.close()
        erro_de_chave = ChaveInvalida("Não foi possível abrir o cofre com a chave fornecida.")
    if erro_de_chave is not None:
        raise erro_de_chave
    # sqlcipher3.Connection espelha a DBAPI do sqlite3; o cast diz "mesma interface".
    return cast("sqlite3.Connection", cifrada)


def arquivo_em_claro(caminho: Path) -> bool:
    """`True` se o arquivo é um SQLite em claro (header mágico); `False` se cifrado.

    Arquivo inexistente → `False` (nada a migrar). Determinístico: o SQLCipher
    embaralha o começo do arquivo, então a ausência do header basta.
    """
    caminho = Path(caminho)
    if not caminho.exists():
        return False
    with caminho.open("rb") as f:
        return f.read(len(_HEADER_SQLITE_CLARO)) == _HEADER_SQLITE_CLARO


def _contar_linhas_claro(caminho: Path) -> dict[str, int]:
    """Contagem de linhas por tabela do banco EM CLARO (referência da verificação)."""
    con = sqlite3.connect(str(caminho))
    try:
        return {t: con.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
                for t in _TABELAS_MIGRACAO}
    finally:
        con.close()


def _exportar_para_cofre(origem: Path, destino: Path, dek: bytes) -> None:
    """Copia o banco em claro `origem` para o cofre cifrado `destino` (`sqlcipher_export`).

    Abre a origem em claro COM o driver sqlcipher3 (sem key), anexa o `destino`
    com a DEK e usa `sqlcipher_export` — o jeito canônico e íntegro de recifrar.
    O caminho do destino é passado como parâmetro ligado (escapa a barra/aspas do
    Windows); a KEY é inline porque um blob literal (`x'...'`) não pode vir por
    bind sem o SQLCipher tratá-lo como passphrase (o que reintroduziria o KDF).
    `isolation_level=None` (autocommit): `sqlcipher_export` gere sua transação.
    """
    con = sqlcipher3.connect(str(origem), isolation_level=None)
    try:
        # Só o ATTACH embute a chave (destino vai por bind; a KEY é inline). Mesma
        # invariante do `_conectar`: se explodir, a statement com o hex não pode
        # subir. Trocamos por `ErroMigracao` (erro apropriado deste fluxo) criada no
        # `except` e LEVANTADA fora dele, para `__context__` nascer None e severar a
        # exceção original que ecoaria a statement (não só suprimi-la como `from None`).
        erro_attach: ErroMigracao | None = None
        try:
            con.execute(f'ATTACH DATABASE ? AS cofre KEY "{_blob_key(dek)}"', (str(destino),))
        except Exception:
            erro_attach = ErroMigracao("Falha ao anexar o cofre cifrado para exportação.")
        if erro_attach is not None:
            raise erro_attach
        con.execute("SELECT sqlcipher_export('cofre')").fetchall()
        # Preserva o user_version (não usado hoje — versionamos pela tabela
        # `esquema` — mas copiar é barato e à prova de futuro).
        uv = con.execute("PRAGMA user_version").fetchone()[0]
        con.execute(f"PRAGMA cofre.user_version = {int(uv)}")
        con.execute("DETACH DATABASE cofre")
    finally:
        con.close()


def _verificar_cofre(destino: Path, dek: bytes, contagens_esperadas: dict[str, int]) -> None:
    """Confere o cofre recém-exportado ANTES de qualquer remoção do original.

    Reabre `destino` com a DEK (chave errada ⇒ `ChaveInvalida`), roda
    `PRAGMA integrity_check` e compara a contagem de linhas por tabela com a do
    original. Qualquer divergência levanta `ErroMigracao` — o chamador então
    descarta o `.novo` e mantém o banco em claro intacto. Função nomeada de
    propósito: os testes de atomicidade a substituem (monkeypatch) para simular
    falha de verificação sem corromper nada de verdade.
    """
    con = _conectar(destino, dek)
    try:
        integridade = con.execute("PRAGMA integrity_check").fetchone()[0]
        if integridade != "ok":
            raise ErroMigracao(f"integridade do cofre falhou: {integridade}")
        for tabela, esperado in contagens_esperadas.items():
            atual = con.execute(f"SELECT count(*) FROM {tabela}").fetchone()[0]
            if atual != esperado:
                raise ErroMigracao(
                    f"contagem de '{tabela}' divergiu após a migração "
                    f"({atual} != {esperado})"
                )
    finally:
        con.close()


def migrar_para_cofre(caminho: Path, dek: bytes) -> None:
    """Migra o `dados.db` em claro para o cofre cifrado, de forma ATÔMICA (REQ-SEC-006).

    Idempotente: se o arquivo não existe ou já está cifrado, é no-op. Caso
    contrário exporta para `<caminho>.novo`, verifica (integridade + contagens) e
    só então faz `os.replace` — troca atômica que apaga o arquivo em claro. Falha
    em QUALQUER etapa anterior remove o `.novo` (se existir) e deixa o original
    intacto; a exceção sobe para o chamador (T-1603) decidir o que exibir. O nome
    do arquivo não muda — muda só o contêiner (`caminho_banco()` intocado).
    """
    caminho = Path(caminho)
    if not arquivo_em_claro(caminho):
        return
    novo = caminho.with_name(caminho.name + ".novo")
    try:
        if novo.exists():
            novo.unlink()
        contagens = _contar_linhas_claro(caminho)
        _exportar_para_cofre(caminho, novo, dek)
        _verificar_cofre(novo, dek, contagens)
    except BaseException:
        # Nunca deixa lixo cifrado meio-pronto ao lado do original.
        if novo.exists():
            novo.unlink()
        raise
    os.replace(novo, caminho)


def caminho_banco(ambiente: Mapping[str, str] | None = None) -> Path:
    """Resolve o caminho do banco: `HF_DB_PATH` (testes/E2E) > perfil do usuário."""
    env = os.environ if ambiente is None else ambiente
    forcado = env.get("HF_DB_PATH", "").strip()
    if forcado:
        return Path(forcado)
    appdata = env.get("APPDATA", "").strip()
    base = Path(appdata) / "HelperFinanceiro" if appdata else Path.home() / ".helper_financeiro"
    return base / "dados.db"


class Repositorio:
    """Fachada única de acesso ao banco (thread-safe por lock)."""

    def __init__(self, caminho: Path | None = None, dek: bytes | None = None) -> None:
        """Abre o banco e aplica a migração de SCHEMA (`_migrar`). Com `dek`, o
        contêiner é SQLCipher (ADR-0016 §B) — a migração de CONTÊINER é
        `migrar_para_cofre`, chamada pelo T-1603 ANTES de instanciar isto.

        `dek=None` é transitório: mantém o banco em claro (sqlite3 da stdlib) para
        o `app.py` funcionar até o T-1603 ligar a sessão do cofre — e para a
        migração conseguir ler o banco antigo. Em produção o T-1603 sempre passa a
        DEK. Chave errada no modo cifrado levanta `ChaveInvalida` já na abertura.
        """
        self._caminho = caminho if caminho is not None else caminho_banco()
        self._caminho.parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False: o lock (e não o driver) serializa o acesso.
        self._conn = _conectar(self._caminho, dek)
        self._lock = threading.Lock()
        self._migrar()

    @property
    def caminho(self) -> Path:
        return self._caminho

    # ---------------------------------------------------------- migração
    def versao_esquema(self) -> int:
        with self._lock:
            return self._versao_sem_lock()

    def _versao_sem_lock(self) -> int:
        tem_tabela = self._conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'esquema'"
        ).fetchone()
        if not tem_tabela:
            return 0
        linha = self._conn.execute("SELECT versao FROM esquema").fetchone()
        return int(linha["versao"]) if linha else 0

    def _migrar(self) -> None:
        with self._lock, self._conn:
            versao = self._versao_sem_lock()
            if versao > VERSAO_ESQUEMA:
                raise RuntimeError(
                    f"Banco criado por versão mais nova (esquema {versao} > "
                    f"{VERSAO_ESQUEMA}). Atualize o Helper Financeiro."
                )
            if versao < 1:
                self._conn.executescript(_DDL_V1)
                self._conn.execute("DELETE FROM esquema")
                self._conn.execute(
                    "INSERT INTO esquema (versao) VALUES (?)", (VERSAO_ESQUEMA,)
                )

    # ------------------------------------------------------------- estado
    def salvar_estado(self, chave: str, dados: dict) -> None:
        """Grava (ou substitui) um documento JSON de estado — ex.: o perfil."""
        agora = datetime.now(UTC).isoformat()
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO estado (chave, json, atualizado_em) VALUES (?, ?, ?) "
                "ON CONFLICT (chave) DO UPDATE SET json = excluded.json, "
                "atualizado_em = excluded.atualizado_em",
                (chave, json.dumps(dados, ensure_ascii=False), agora),
            )

    def carregar_estado(self, chave: str) -> dict | None:
        with self._lock:
            linha = self._conn.execute(
                "SELECT json FROM estado WHERE chave = ?", (chave,)
            ).fetchone()
        if linha is None:
            return None
        dados = json.loads(linha["json"])
        if not isinstance(dados, dict):
            return None  # conteúdo inesperado: melhor "sem estado" que quebrar
        return dados

    # ------------------------------------------------------------ rubricas
    # CRUD dos lançamentos do orçamento (T-1103, REQ-F-017). `mes` fica NULL
    # no orçamento vivo (v2.4); o filtro já existe para o histórico futuro.
    def listar_rubricas(self) -> list[dict]:
        with self._lock:
            linhas = self._conn.execute(
                "SELECT id, categoria, campo_pai, nome, valor, ordem FROM rubrica "
                "WHERE mes IS NULL ORDER BY categoria, campo_pai, ordem, id"
            ).fetchall()
        return [dict(linha) for linha in linhas]

    def criar_rubrica(self, categoria: str, campo_pai: str, nome: str,
                      valor: float = 0.0, ordem: int = 0,
                      mes: str | None = None) -> dict:
        """Insere um lançamento; `mes` NULL = orçamento vivo (padrão).

        `mes` preenchido entra numa competência arquivada — a importação de
        CSV (ADR-0014) acrescenta rubricas direto no snapshot.
        """
        with self._lock, self._conn:
            cursor = self._conn.execute(
                "INSERT INTO rubrica (categoria, campo_pai, nome, valor, ordem, mes) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (categoria, campo_pai, nome, valor, ordem, mes),
            )
        return {"id": cursor.lastrowid, "categoria": categoria,
                "campo_pai": campo_pai, "nome": nome, "valor": valor,
                "ordem": ordem}

    def atualizar_rubrica(self, rubrica_id: int, nome: str, valor: float,
                          ordem: int | None = None) -> dict | None:
        """Edita nome/valor (e ordem, se enviada); None se o id não existe.

        Categoria/campo_pai são a ANCORAGEM da rubrica — não mudam numa
        edição; mover de grupo é remover + criar (decisão de simplicidade).
        """
        with self._lock, self._conn:
            linha = self._conn.execute(
                "SELECT id, categoria, campo_pai, ordem FROM rubrica WHERE id = ?",
                (rubrica_id,),
            ).fetchone()
            if linha is None:
                return None
            ordem_final = linha["ordem"] if ordem is None else ordem
            self._conn.execute(
                "UPDATE rubrica SET nome = ?, valor = ?, ordem = ? WHERE id = ?",
                (nome, valor, ordem_final, rubrica_id),
            )
        return {"id": rubrica_id, "categoria": linha["categoria"],
                "campo_pai": linha["campo_pai"], "nome": nome, "valor": valor,
                "ordem": ordem_final}

    def remover_rubrica(self, rubrica_id: int) -> bool:
        with self._lock, self._conn:
            cursor = self._conn.execute(
                "DELETE FROM rubrica WHERE id = ?", (rubrica_id,)
            )
        return cursor.rowcount > 0

    # ------------------------------------------- histórico mensal (T-1201)
    # Snapshot da competência 'AAAA-MM' (ADR-0013): o perfil vai para a
    # chave `perfil:AAAA-MM` e as rubricas vivas são COPIADAS com o mês.
    # Arquivar de novo a mesma competência substitui o snapshot.
    def arquivar_mes(self, mes: str, perfil: dict) -> None:
        agora = datetime.now(UTC).isoformat()
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO estado (chave, json, atualizado_em) VALUES (?, ?, ?) "
                "ON CONFLICT (chave) DO UPDATE SET json = excluded.json, "
                "atualizado_em = excluded.atualizado_em",
                (f"perfil:{mes}", json.dumps(perfil, ensure_ascii=False), agora),
            )
            self._conn.execute("DELETE FROM rubrica WHERE mes = ?", (mes,))
            self._conn.execute(
                "INSERT INTO rubrica (categoria, campo_pai, nome, valor, ordem, mes) "
                "SELECT categoria, campo_pai, nome, valor, ordem, ? "
                "FROM rubrica WHERE mes IS NULL",
                (mes,),
            )

    def listar_meses(self) -> list[str]:
        with self._lock:
            linhas = self._conn.execute(
                "SELECT chave FROM estado WHERE chave LIKE 'perfil:%' "
                "ORDER BY chave"
            ).fetchall()
        return [linha["chave"].removeprefix("perfil:") for linha in linhas]

    def carregar_mes(self, mes: str) -> dict | None:
        return self.carregar_estado(f"perfil:{mes}")

    def salvar_perfil_do_mes(self, mes: str, perfil: dict) -> None:
        """Grava/substitui só o perfil do snapshot (sem tocar nas rubricas).

        Usado pela importação de CSV (ADR-0014) para recalcular o snapshot
        depois de acrescentar rubricas à competência.
        """
        self.salvar_estado(f"perfil:{mes}", perfil)

    def rubricas_do_mes(self, mes: str) -> list[dict]:
        with self._lock:
            linhas = self._conn.execute(
                "SELECT id, categoria, campo_pai, nome, valor, ordem "
                "FROM rubrica WHERE mes = ? "
                "ORDER BY categoria, campo_pai, ordem, id",
                (mes,),
            ).fetchall()
        return [dict(linha) for linha in linhas]

    # -------------------------------------------------------------- ciclo
    def fechar(self) -> None:
        with self._lock:
            self._conn.close()
