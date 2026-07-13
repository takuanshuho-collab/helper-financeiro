"""
Persistência local em SQLite (ADR-0012, REQ-F-018) — T-1101.

O banco é um arquivo no perfil do usuário gerido só pelo sidecar; aqui
validamos a resolução do caminho, a migração versionada e o roundtrip do
estado (documentos JSON), incluindo reabertura (dados sobrevivem entre
sessões) e acesso concorrente (o sidecar atende em múltiplas threads).
"""
from __future__ import annotations

import secrets
import sqlite3
import threading
import traceback
from pathlib import Path

import pytest
import sqlcipher3

from sidecar import persistencia
from sidecar.persistencia import (
    VERSAO_ESQUEMA,
    ChaveInvalida,
    ErroMigracao,
    Repositorio,
    arquivo_em_claro,
    caminho_banco,
    migrar_para_cofre,
)

# DEK fixa do teste (nunca vai a %APPDATA% real — sempre sob tmp_path).
_DEK = secrets.token_bytes(32)
_HEADER_CLARO = b"SQLite format 3\x00"


# ------------------------------------------------------- caminho do banco
def test_hf_db_path_tem_precedencia():
    env = {"HF_DB_PATH": r"C:\tmp\teste.db", "APPDATA": r"C:\Users\x\AppData\Roaming"}
    assert caminho_banco(env) == Path(r"C:\tmp\teste.db")


def test_appdata_e_o_padrao_no_windows():
    env = {"APPDATA": r"C:\Users\x\AppData\Roaming"}
    esperado = Path(r"C:\Users\x\AppData\Roaming") / "HelperFinanceiro" / "dados.db"
    assert caminho_banco(env) == esperado


def test_sem_appdata_cai_na_home():
    caminho = caminho_banco({})
    assert caminho == Path.home() / ".helper_financeiro" / "dados.db"


# ------------------------------------------------------- migração/schema
def test_banco_novo_fica_na_versao_atual(tmp_path):
    repo = Repositorio(tmp_path / "dados.db")
    assert repo.versao_esquema() == VERSAO_ESQUEMA
    repo.fechar()


def test_migracao_cria_tabelas_estado_e_rubrica(tmp_path):
    repo = Repositorio(tmp_path / "dados.db")
    repo.fechar()
    con = sqlite3.connect(tmp_path / "dados.db")
    tabelas = {
        linha[0]
        for linha in con.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    con.close()
    assert {"esquema", "estado", "rubrica"} <= tabelas


def test_reabrir_banco_e_idempotente(tmp_path):
    caminho = tmp_path / "dados.db"
    repo = Repositorio(caminho)
    repo.salvar_estado("perfil", {"reserva_emergencia": 1000.0})
    repo.fechar()

    repo2 = Repositorio(caminho)  # nova "sessão": migração não pode destruir nada
    assert repo2.versao_esquema() == VERSAO_ESQUEMA
    assert repo2.carregar_estado("perfil") == {"reserva_emergencia": 1000.0}
    repo2.fechar()


def test_banco_de_versao_mais_nova_e_recusado(tmp_path):
    caminho = tmp_path / "dados.db"
    repo = Repositorio(caminho)
    repo.fechar()
    con = sqlite3.connect(caminho)
    with con:
        con.execute("UPDATE esquema SET versao = ?", (VERSAO_ESQUEMA + 1,))
    con.close()

    with pytest.raises(RuntimeError, match="versão mais nova"):
        Repositorio(caminho)


def test_diretorio_do_banco_e_criado(tmp_path):
    caminho = tmp_path / "HelperFinanceiro" / "dados.db"  # pasta não existe ainda
    repo = Repositorio(caminho)
    assert caminho.exists()
    repo.fechar()


# --------------------------------------------------------------- estado
def test_roundtrip_do_estado(tmp_path):
    repo = Repositorio(tmp_path / "dados.db")
    perfil = {
        "renda": {"salario_liquido": 4200.0},
        "fixas": {"contas_casa": 480.5},
        "dividas": [{"credor": "Banco São João", "saldo_devedor": 12000.0}],
    }
    repo.salvar_estado("perfil", perfil)
    assert repo.carregar_estado("perfil") == perfil
    repo.fechar()


def test_salvar_de_novo_sobrescreve(tmp_path):
    repo = Repositorio(tmp_path / "dados.db")
    repo.salvar_estado("perfil", {"v": 1})
    repo.salvar_estado("perfil", {"v": 2})
    assert repo.carregar_estado("perfil") == {"v": 2}
    repo.fechar()


def test_estado_inexistente_devolve_none(tmp_path):
    repo = Repositorio(tmp_path / "dados.db")
    assert repo.carregar_estado("perfil") is None
    repo.fechar()


def test_acentos_sobrevivem_ao_roundtrip(tmp_path):
    repo = Repositorio(tmp_path / "dados.db")
    repo.salvar_estado("perfil", {"credor": "Crédito & Cia — São Paulo"})
    carregado = repo.carregar_estado("perfil")
    assert carregado is not None
    assert carregado["credor"] == "Crédito & Cia — São Paulo"
    repo.fechar()


# -------------------------------------------------- rubricas (CRUD, T-1103)
def test_rubrica_crud_roundtrip(tmp_path):
    repo = Repositorio(tmp_path / "dados.db")
    criada = repo.criar_rubrica("fixas", "contas_casa", "Conta de luz", 180.0)
    assert criada["id"] is not None

    listadas = repo.listar_rubricas()
    assert listadas == [criada]

    editada = repo.atualizar_rubrica(criada["id"], "Luz + taxa", 195.5)
    assert editada is not None
    assert editada["valor"] == 195.5
    # A ancoragem não muda numa edição.
    assert editada["categoria"] == "fixas"
    assert editada["campo_pai"] == "contas_casa"

    assert repo.remover_rubrica(criada["id"]) is True
    assert repo.listar_rubricas() == []
    repo.fechar()


def test_rubrica_ordenacao_por_grupo_e_ordem(tmp_path):
    repo = Repositorio(tmp_path / "dados.db")
    repo.criar_rubrica("variaveis", "mercado", "Feira", 100.0, ordem=1)
    repo.criar_rubrica("fixas", "contas_casa", "Internet", 120.0, ordem=2)
    repo.criar_rubrica("fixas", "contas_casa", "Luz", 180.0, ordem=1)
    nomes = [r["nome"] for r in repo.listar_rubricas()]
    assert nomes == ["Luz", "Internet", "Feira"]
    repo.fechar()


def test_rubrica_id_desconhecido(tmp_path):
    repo = Repositorio(tmp_path / "dados.db")
    assert repo.atualizar_rubrica(999, "X", 1.0) is None
    assert repo.remover_rubrica(999) is False
    repo.fechar()


def test_rubrica_com_mes_fica_fora_do_orcamento_vivo(tmp_path):
    # A coluna `mes` existe para o histórico mensal futuro (ADR-0012): o
    # orçamento vivo lista só as linhas com mes NULL.
    repo = Repositorio(tmp_path / "dados.db")
    repo.criar_rubrica("fixas", "contas_casa", "Luz", 180.0)
    with repo._conn:  # simula uma linha de snapshot mensal (v2.5)
        repo._conn.execute(
            "INSERT INTO rubrica (categoria, campo_pai, nome, valor, mes) "
            "VALUES ('fixas', 'contas_casa', 'Luz de julho', 170.0, '2026-07')"
        )
    assert [r["nome"] for r in repo.listar_rubricas()] == ["Luz"]
    repo.fechar()


# ---------------------------------------- histórico mensal (T-1201, ADR-0013)
def test_arquivar_mes_grava_perfil_e_copia_rubricas(tmp_path):
    repo = Repositorio(tmp_path / "dados.db")
    repo.criar_rubrica("fixas", "contas_casa", "Luz", 180.0)
    perfil = {"fixas": {"contas_casa": 180.0}}

    repo.arquivar_mes("2026-07", perfil)

    assert repo.listar_meses() == ["2026-07"]
    assert repo.carregar_mes("2026-07") == perfil
    snapshot = repo.rubricas_do_mes("2026-07")
    assert [r["nome"] for r in snapshot] == ["Luz"]
    # As rubricas VIVAS continuam lá (o snapshot é cópia, não movimentação).
    assert [r["nome"] for r in repo.listar_rubricas()] == ["Luz"]
    repo.fechar()


def test_arquivar_de_novo_substitui_o_snapshot(tmp_path):
    repo = Repositorio(tmp_path / "dados.db")
    repo.criar_rubrica("fixas", "contas_casa", "Luz", 180.0)
    repo.arquivar_mes("2026-07", {"v": 1})

    # O orçamento vivo muda e o mês é arquivado de novo.
    repo.criar_rubrica("fixas", "contas_casa", "Internet", 120.0)
    repo.arquivar_mes("2026-07", {"v": 2})

    assert repo.carregar_mes("2026-07") == {"v": 2}
    assert [r["nome"] for r in repo.rubricas_do_mes("2026-07")] == [
        "Luz", "Internet"]
    assert repo.listar_meses() == ["2026-07"]  # sem duplicar a competência
    repo.fechar()


def test_snapshot_nao_vaza_para_o_orcamento_vivo(tmp_path):
    repo = Repositorio(tmp_path / "dados.db")
    repo.criar_rubrica("fixas", "contas_casa", "Luz", 180.0)
    repo.arquivar_mes("2026-06", {})
    # Editar o vivo depois do arquivamento não toca o snapshot...
    rid = repo.listar_rubricas()[0]["id"]
    repo.atualizar_rubrica(rid, "Luz", 200.0)
    assert repo.rubricas_do_mes("2026-06")[0]["valor"] == 180.0
    # ...e o snapshot não aparece no vivo.
    assert len(repo.listar_rubricas()) == 1
    repo.fechar()


def test_mes_sem_snapshot(tmp_path):
    repo = Repositorio(tmp_path / "dados.db")
    assert repo.listar_meses() == []
    assert repo.carregar_mes("2026-01") is None
    assert repo.rubricas_do_mes("2026-01") == []
    repo.fechar()


def test_criar_rubrica_direto_na_competencia(tmp_path):
    # Importação de CSV (ADR-0014): a rubrica nasce no snapshot, não no vivo.
    repo = Repositorio(tmp_path / "dados.db")
    repo.criar_rubrica("variaveis", "mercado", "Mercado Bom Preço", 800.87,
                       mes="2026-06")
    assert repo.listar_rubricas() == []
    assert [r["nome"] for r in repo.rubricas_do_mes("2026-06")] == [
        "Mercado Bom Preço"]

    repo.salvar_perfil_do_mes("2026-06", {"v": 1})
    assert repo.carregar_mes("2026-06") == {"v": 1}
    assert repo.listar_meses() == ["2026-06"]
    repo.fechar()


def test_escritas_concorrentes_nao_se_corrompem(tmp_path):
    repo = Repositorio(tmp_path / "dados.db")

    def gravar(i: int) -> None:
        repo.salvar_estado(f"chave_{i}", {"i": i})

    threads = [threading.Thread(target=gravar, args=(i,)) for i in range(16)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    for i in range(16):
        assert repo.carregar_estado(f"chave_{i}") == {"i": i}
    repo.fechar()


# ---------------------------------------------- cofre cifrado (T-1602, ADR-0016 §B)
def _popular(repo: Repositorio) -> None:
    """Grava um pouco de tudo (perfil, dívidas embutidas, rubricas) para os asserts."""
    repo.salvar_estado("perfil", {
        "renda": {"salario_liquido": 4200.0},
        "dividas": [{"credor": "Banco São João", "saldo_devedor": 12000.0}],
    })
    repo.criar_rubrica("fixas", "contas_casa", "Conta de luz", 180.0)
    repo.criar_rubrica("variaveis", "mercado", "Feira do produtor", 95.5)


def test_cofre_roundtrip_com_dek(tmp_path):
    caminho = tmp_path / "dados.db"
    repo = Repositorio(caminho, dek=_DEK)
    _popular(repo)
    repo.fechar()

    # Reabre com a MESMA DEK: tudo volta igual (dados sobrevivem à sessão).
    repo2 = Repositorio(caminho, dek=_DEK)
    assert repo2.versao_esquema() == VERSAO_ESQUEMA
    perfil = repo2.carregar_estado("perfil")
    assert perfil is not None
    assert perfil["dividas"][0]["credor"] == "Banco São João"
    assert [r["nome"] for r in repo2.listar_rubricas()] == ["Conta de luz", "Feira do produtor"]
    repo2.fechar()


def test_cofre_dek_errada_levanta_excecao_tipada(tmp_path):
    caminho = tmp_path / "dados.db"
    repo = Repositorio(caminho, dek=_DEK)
    _popular(repo)
    repo.fechar()

    outra = secrets.token_bytes(32)
    with pytest.raises(ChaveInvalida) as exc:
        Repositorio(caminho, dek=outra)
    # A mensagem NUNCA pode conter a chave (nem certa nem errada) — REQ-SEC-001.
    texto = str(exc.value)
    assert _DEK.hex() not in texto
    assert outra.hex() not in texto


def test_cofre_arquivo_nao_esta_em_claro(tmp_path):
    caminho = tmp_path / "dados.db"
    repo = Repositorio(caminho, dek=_DEK)
    repo.criar_rubrica("fixas", "contas_casa", "Rubrica Secreta Xyz", 180.0)
    repo.fechar()

    bruto = caminho.read_bytes()
    assert not bruto.startswith(_HEADER_CLARO)              # contêiner cifrado
    assert b"Rubrica Secreta Xyz" not in bruto              # dado não em claro
    assert b"contas_casa" not in bruto


def test_arquivo_em_claro_detecta_os_tres_casos(tmp_path):
    # 1) banco stdlib em claro → True
    claro = tmp_path / "claro.db"
    repo_claro = Repositorio(claro, dek=None)
    repo_claro.fechar()
    assert arquivo_em_claro(claro) is True

    # 2) cofre cifrado → False
    cofre = tmp_path / "cofre.db"
    repo_cofre = Repositorio(cofre, dek=_DEK)
    repo_cofre.fechar()
    assert arquivo_em_claro(cofre) is False

    # 3) inexistente → False
    assert arquivo_em_claro(tmp_path / "nao_existe.db") is False


def test_migracao_converte_banco_em_claro(tmp_path):
    caminho = tmp_path / "dados.db"
    # Popula o banco EM CLARO (caminho dek=None), como um dados.db pré-v2.8.
    repo = Repositorio(caminho, dek=None)
    _popular(repo)
    repo.fechar()
    assert arquivo_em_claro(caminho) is True

    migrar_para_cofre(caminho, _DEK)

    # Depois: cifrado, sem sobra de `.novo`, e os dados abrem com a DEK.
    assert arquivo_em_claro(caminho) is False
    assert not (tmp_path / "dados.db.novo").exists()
    repo2 = Repositorio(caminho, dek=_DEK)
    perfil = repo2.carregar_estado("perfil")
    assert perfil is not None
    assert perfil["renda"]["salario_liquido"] == 4200.0
    assert [r["nome"] for r in repo2.listar_rubricas()] == ["Conta de luz", "Feira do produtor"]
    repo2.fechar()


def test_migracao_e_idempotente(tmp_path):
    caminho = tmp_path / "dados.db"
    repo = Repositorio(caminho, dek=None)
    _popular(repo)
    repo.fechar()

    migrar_para_cofre(caminho, _DEK)          # migra de fato
    antes = caminho.read_bytes()
    migrar_para_cofre(caminho, _DEK)          # já cifrado → no-op
    assert caminho.read_bytes() == antes      # não mexeu no arquivo

    # Caminho inexistente → no-op silencioso (não cria nada).
    inexistente = tmp_path / "fantasma.db"
    migrar_para_cofre(inexistente, _DEK)
    assert not inexistente.exists()


def test_migracao_falha_na_verificacao_preserva_original(tmp_path, monkeypatch):
    caminho = tmp_path / "dados.db"
    repo = Repositorio(caminho, dek=None)
    _popular(repo)
    repo.fechar()
    original = caminho.read_bytes()

    # Simula falha na etapa de verificação (ex.: integridade/contagem).
    def _boom(*_a, **_k):
        raise ErroMigracao("verificação simulada falhou")

    monkeypatch.setattr(persistencia, "_verificar_cofre", _boom)
    with pytest.raises(ErroMigracao):
        migrar_para_cofre(caminho, _DEK)

    # O original em claro permanece intacto e legível; nenhum `.novo` sobra.
    assert caminho.read_bytes() == original
    assert arquivo_em_claro(caminho) is True
    assert not (tmp_path / "dados.db.novo").exists()
    repo2 = Repositorio(caminho, dek=None)
    assert repo2.carregar_estado("perfil") is not None
    repo2.fechar()


# ------------------------- blindagem da DEK na statement SQL (C-21, T-1908)
# A DEK é interpolada inline no `PRAGMA key`/`ATTACH ... KEY` (raw key, sem KDF —
# ADR-0016 §B). Se uma dessas execuções explodir ecoando a statement, o hex do
# segredo-mestre poderia subir no traceback → stderr → terminal (o `main.ts` ecoa
# o stderr do sidecar sem scrub; a política do T-1603 de NÃO filtrar é mantida —
# por isso a defesa nasce na fonte). Estes testes provam que NENHUMA exceção que
# sai do módulo carrega o hex — nem no texto, nem na cadeia `__cause__`/
# `__context__`. Antes da correção (execuções sem try/except) eles FALHAM.

# DEK fixa e reconhecível para estes testes (hex 000102…1f) — facilita ver o
# vazamento se um dia reaparecer no output do pytest.
_DEK_C21 = bytes(range(32))


class _ConexaoQueEcoaAStatement:
    """Conexão SQLCipher FALSA cujo `execute` explode ECOANDO a statement.

    É o pior caso do C-21: se o hex da DEK aparece no SQL (o `PRAGMA key`/
    `ATTACH` com a chave inline), levanta um erro cuja mensagem contém a própria
    statement — exatamente o traceback que, sem a blindagem, chegaria ao stderr
    com o segredo dentro. As demais statements não são exercidas neste cenário.
    """

    def __init__(self, *_a, **_k) -> None:
        self.row_factory = None

    def execute(self, sql, *_params):
        if _DEK_C21.hex() in sql:
            raise sqlcipher3.Error(f'near "{sql}": syntax error')
        return self

    def fetchone(self):
        return None

    def fetchall(self):
        return []

    def close(self) -> None:
        pass


def _texto_de_toda_a_cadeia(exc: BaseException) -> str:
    """str/repr/args de `exc` e de TODA a sua cadeia (`__cause__` e `__context__`,
    recursivamente). Varre o grafo bruto: uma correção de vazamento tem de deixar
    o hex ausente em QUALQUER nó da cadeia, não só suprimido na impressão."""
    partes: list[str] = []
    vistos: set[int] = set()
    pilha: list[BaseException | None] = [exc]
    while pilha:
        atual = pilha.pop()
        if atual is None or id(atual) in vistos:
            continue
        vistos.add(id(atual))
        partes.append(str(atual))
        partes.append(repr(atual))
        partes.extend(repr(a) for a in atual.args)
        pilha.append(atual.__cause__)
        pilha.append(atual.__context__)
    return "\n".join(partes)


def _assert_sem_hex_da_dek(exc: BaseException) -> None:
    hexdek = _DEK_C21.hex()
    # 1) Nada em str/repr/args de toda a cadeia de exceções.
    assert hexdek not in _texto_de_toda_a_cadeia(exc)
    # 2) E — o vetor real do C-21 — nada no traceback formatado que iria ao stderr.
    formatado = "".join(
        traceback.format_exception(type(exc), exc, exc.__traceback__)
    )
    assert hexdek not in formatado


def test_pragma_key_que_explode_nao_vaza_a_dek(tmp_path, monkeypatch):
    # Força o `PRAGMA key`/sanidade a explodir ecoando a statement com o hex.
    monkeypatch.setattr(
        persistencia.sqlcipher3, "connect",
        lambda *a, **k: _ConexaoQueEcoaAStatement(),
    )
    with pytest.raises(ChaveInvalida) as exc:
        persistencia._conectar(tmp_path / "dados.db", _DEK_C21)
    _assert_sem_hex_da_dek(exc.value)
    # A exceção que sai é a tipada, com mensagem fixa (não a statement crua).
    assert "cofre" in str(exc.value).lower()


def test_attach_que_explode_nao_vaza_a_dek(tmp_path, monkeypatch):
    # Força o `ATTACH ... KEY` da exportação a explodir ecoando o hex.
    monkeypatch.setattr(
        persistencia.sqlcipher3, "connect",
        lambda *a, **k: _ConexaoQueEcoaAStatement(),
    )
    with pytest.raises(ErroMigracao) as exc:
        persistencia._exportar_para_cofre(
            tmp_path / "claro.db", tmp_path / "cofre.db", _DEK_C21
        )
    _assert_sem_hex_da_dek(exc.value)
    assert "cofre" in str(exc.value).lower()
