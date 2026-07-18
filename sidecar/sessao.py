"""
Estado da sessão do cofre no sidecar (ADR-0016 §C; REQ-SEC-005) — T-1603.

O token por execução (`sidecar/security.py`, REQ-SEC-004) autentica o
*processo* Electron; esta sessão autentica o *usuário* — os dois convivem em
TODA rota de negócio (`X-HF-Token` sempre, mais o gate `exigir_cofre` do
`app.py`, que fala com esta sessão).

## Modo de transição (onboarding → cofre)

Enquanto NENHUM cofre estiver cadastrado (`Cofre.esta_cadastrado() is
False`), os endpoints de negócio funcionam como antes do T-1603: `Repositorio`
legado em claro (`dek=None`), sem exigir login — é a "janela de onboarding".
Os dados nessa janela já estavam em claro antes desta task (T-1601/1602
deram a fundação, mas não migraram nada sozinhas), então não há regressão.
Assim que existir um cofre cadastrado (`POST /auth/cadastrar`), a janela
fecha: TODO endpoint de negócio passa a responder `423 Locked` até
`POST /auth/login` (ou `/auth/recuperar`) abrir a sessão. O T-1604 força o
onboarding na GUI (assistente de cadastro antes de qualquer tela de negócio).

## Auto-lock preguiçoso

Sem timer em background (mais simples e testável): a cada acesso ao
repositório ativo (`repositorio_ativo`), se `agora() - ultimo_uso` passar de
`HF_AUTO_LOCK_MIN` minutos (padrão 15; `0` desliga), a sessão bloqueia ANTES
de atender — a chamada de negócio em curso recebe `423`, nunca os dados. O
relógio é injetável (`agora`, padrão `time.monotonic`) para os testes
avançarem sem `sleep`. Consultar `status()` NÃO conta como atividade (não
atualiza `ultimo_uso`) — só o uso de negócio de verdade adia o auto-lock.

## Concorrência

Um único `threading.Lock` serializa TUDO nesta classe (cadastro, login,
recuperação, troca de senha, bloqueio, acesso ao repositório): o `Cofre` de
`auth.py` não tem lock próprio e o FastAPI atende em múltiplas threads (mesmo
racional do `Repositorio` em `persistencia.py`, T-1602). Isso inclui o custo
do Argon2id/TOTP — aceitável num app desktop de usuário único; o que importa é
nunca deixar duas requisições mexerem no `auth.json`/DEK ao mesmo tempo.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import TYPE_CHECKING

from agent.grafo import armar_checkpointer_duravel, desarmar_checkpointer_duravel

from .auth import Cofre, ResultadoCadastro
from .checkpoint_cofre import abrir_saver_cofre, fechar_saver_cofre
from .gestor_modelos import retomar_analises_configurado
from .persistencia import ChaveInvalida, Repositorio, caminho_banco, migrar_para_cofre

if TYPE_CHECKING:
    from langgraph.checkpoint.sqlite import SqliteSaver

log = logging.getLogger("helper_financeiro.sessao")

VAR_AUTO_LOCK_MIN = "HF_AUTO_LOCK_MIN"
_AUTO_LOCK_MIN_PADRAO = 15.0


class SessaoBloqueada(Exception):
    """A sessão está bloqueada (ou nunca foi aberta) — o `app.py` vira `423`."""


def _minutos_auto_lock(ambiente: Mapping[str, str] | None = None) -> float:
    """Lê `HF_AUTO_LOCK_MIN` (minutos); `0` desliga; ausente/vazio = padrão."""
    env = os.environ if ambiente is None else ambiente
    bruto = env.get(VAR_AUTO_LOCK_MIN, "").strip()
    if not bruto:
        return _AUTO_LOCK_MIN_PADRAO
    try:
        return float(bruto)
    except ValueError:
        return _AUTO_LOCK_MIN_PADRAO


class SessaoCofre:
    """Estado bloqueado/desbloqueado do cofre para um `auth.json`/`dados.db`.

    Guarda o `Cofre` (metadados de autenticação), a DEK (só em memória
    enquanto aberto — extensão do REQ-SEC-003), o `Repositorio` ativo e o
    instante do último uso de negócio. `cofre`/`caminho_db`/`agora`/
    `auto_lock_min` são injetáveis para os testes rodarem isolados e sem
    `sleep`.
    """

    def __init__(
        self,
        *,
        cofre: Cofre | None = None,
        caminho_db: Path | None = None,
        agora: Callable[[], float] = time.monotonic,
        auto_lock_min: float | None = None,
        ao_bloquear: Callable[[], None] | None = None,
        retomar_analises: Callable[[], bool] | None = None,
    ) -> None:
        self._lock = threading.Lock()
        self._cofre = cofre if cofre is not None else Cofre()
        self._caminho_db = caminho_db
        self._agora = agora
        self._auto_lock_min = (
            _minutos_auto_lock() if auto_lock_min is None else auto_lock_min
        )
        self._dek: bytes | None = None
        self._repo: Repositorio | None = None
        # Checkpoint durável do grafo (ADR-0023, T-2601): a 2ª conexão SQLCipher
        # do saver vive enquanto a sessão está aberta. `retomar_analises` é o
        # toggle (default = `retomar_analises_configurado`, do `llm.json`),
        # injetável para os testes fixarem liga/desliga sem tocar o `llm.json`.
        self._saver_cofre: SqliteSaver | None = None
        self._retomar_analises = (
            retomar_analises if retomar_analises is not None
            else retomar_analises_configurado
        )
        self._ultimo_uso: float = agora()
        # Gancho disparado quando a sessão SAI do estado desbloqueado (bloqueio
        # manual OU auto-lock). O `app.py` o usa para descartar `_JOBS_IA`: a
        # seção da análise sênior guarda credores DESANONIMIZADOS (REQ-SEC-003) e
        # essa PII não pode sobreviver à janela desbloqueada do cofre (C-04).
        # Atributo público para o `app.py` armá-lo sem acoplar a camada de
        # sessão à de negócio.
        self.ao_bloquear = ao_bloquear

    @property
    def cofre(self) -> Cofre:
        return self._cofre

    def _caminho_banco(self) -> Path:
        return self._caminho_db if self._caminho_db is not None else caminho_banco()

    # ------------------------------------------------------------- status
    def status(self) -> dict:
        """`{cadastrado, desbloqueado, aguarde_s}` — o front decide a tela."""
        with self._lock:
            self._autolock_sem_lock()
            cadastrado = self._cofre.esta_cadastrado()
            return {
                "cadastrado": cadastrado,
                "desbloqueado": self._dek is not None,
                "aguarde_s": self._cofre.segundos_de_espera() if cadastrado else 0.0,
            }

    # ----------------------------------------------------------- cadastro
    def cadastrar(self, senha: str) -> ResultadoCadastro:
        """Cria o cofre e migra o banco NA HORA (o dado sai do claro já no
        cadastro); a sessão continua bloqueada — o primeiro `login` confirma
        que o autenticador TOTP foi configurado de verdade (ADR-0016 §D).

        Propaga `CofreJaCadastrado`/`SenhaFraca` do `Cofre.cadastrar` sem
        tradução — o `app.py` decide o código HTTP.
        """
        with self._lock:
            resultado = self._cofre.cadastrar(senha)
            # A janela de onboarding fecha aqui: descarta um repositório
            # legado eventualmente já aberto (algum endpoint de negócio pode
            # ter rodado antes do cadastro) ANTES de migrar o arquivo — o
            # SQLite em claro não pode ter conexão presa quando o exportamos.
            self._fechar_repo_sem_lock()
            migrar_para_cofre(self._caminho_banco(), resultado.dek)
            return resultado

    # ---------------------------------------------------------- desbloqueio
    def login(self, senha: str, codigo_totp: str) -> None:
        """Abre a sessão com senha + TOTP (`Cofre.desbloquear`).

        Propaga `SenhaIncorreta`/`TotpIncorreto`/`AguardeCofre`/
        `CofreNaoCadastrado` sem tradução.
        """
        with self._lock:
            dek = self._cofre.desbloquear(senha, codigo_totp)
            self._abrir_com_dek_sem_lock(dek)

    def recuperar(self, codigo_recuperacao: str, nova_senha: str) -> None:
        """Abre a sessão por um código de recuperação e redefine a senha
        (`Cofre.recuperar`) — o código É o fator de posse, TOTP não é exigido
        aqui (decisão da ADR-0016 §A: perder senha não perde os dados
        enquanto restar um código)."""
        with self._lock:
            dek = self._cofre.recuperar(codigo_recuperacao, nova_senha)
            self._abrir_com_dek_sem_lock(dek)

    def trocar_senha(self, senha_atual: str, codigo_totp: str, nova_senha: str) -> None:
        """Troca a senha; exige sessão desbloqueada (`SessaoBloqueada`) e os
        2 fatores atuais — `Cofre.trocar_senha` os confere de novo."""
        with self._lock:
            if self._dek is None:
                raise SessaoBloqueada("cofre bloqueado")
            self._cofre.trocar_senha(senha_atual, codigo_totp, nova_senha)
            self._ultimo_uso = self._agora()

    def _abrir_com_dek_sem_lock(self, dek: bytes) -> None:
        caminho = self._caminho_banco()
        # Idempotente: cobre o upgrade de quem cadastrou numa versão que
        # ainda não migrava no cadastro (T-1601/1602 nasceram isoladas).
        migrar_para_cofre(caminho, dek)
        try:
            repo = Repositorio(caminho, dek=dek)
        except ChaveInvalida:
            # Decisão (T-1603, lembrete nº 2 do TASKS): NÃO filtramos o
            # stderr do SQLCipher globalmente. Chave errada é praticamente
            # impossível aqui — a DEK acabou de sair do envelope que a
            # própria senha+TOTP (ou o código de recuperação) já validaram
            # (`Cofre.desbloquear`/`recuperar`); `ChaveInvalida` neste ponto
            # só pode ser corrupção real do arquivo cifrado. Filtrar o
            # stderr esconderia esse erro legítimo — deixamos a exceção
            # subir para o `app.py` decidir o que exibir (500 genérico, sem
            # a chave).
            raise
        self._fechar_repo_sem_lock()
        self._desarmar_checkpoint_duravel_sem_lock()
        self._dek = dek
        self._repo = repo
        self._ultimo_uso = self._agora()
        # Durabilidade do grafo (ADR-0023): tenta ligar o checkpoint no cofre
        # recém-aberto. Plano C está DENTRO do helper — qualquer falha degrada
        # para memória sem impedir a abertura da sessão.
        self._armar_checkpoint_duravel_sem_lock(caminho, dek)

    # --------------------------------------------------- checkpoint durável
    def _armar_checkpoint_duravel_sem_lock(self, caminho: Path, dek: bytes) -> None:
        """Plano C (degradação segura, ADR-0023): com o toggle ligado, abre a 2ª
        conexão SQLCipher e arma o checkpointer durável do grafo; QUALQUER falha
        (toggle à parte) cai para checkpoint em memória com `log.warning` — a
        sessão NUNCA falha por causa disto, e a análise nunca fica pior que hoje.
        """
        if not self._retomar_analises():
            return
        try:
            saver = abrir_saver_cofre(caminho, dek)
            armar_checkpointer_duravel(saver)
            self._saver_cofre = saver
        except Exception:  # noqa: BLE001 — checkpoint durável é opcional (P8); sessão segue
            log.warning("Checkpoint durável indisponível nesta sessão; seguindo "
                        "com checkpoint só em memória (ADR-0023, plano C).")

    def _desarmar_checkpoint_duravel_sem_lock(self) -> None:
        """Desarma o checkpointer durável e consolida/fecha a 2ª conexão — rodado
        ANTES de zerar a DEK no bloqueio/fechamento. Best-effort e idempotente
        (sem saver armado ⇒ no-op)."""
        if self._saver_cofre is None:
            return
        desarmar_checkpointer_duravel()
        fechar_saver_cofre(self._saver_cofre)
        self._saver_cofre = None

    # -------------------------------------------------------------- bloqueio
    def bloquear(self) -> None:
        """Bloqueio manual — idempotente (bloquear já bloqueado é no-op).

        Fecha o `Repositorio` cifrado (conexão) e descarta a referência da
        DEK. Zeroização real de bytes em Python é best-effort — não
        inventamos isso aqui; descartar a referência basta (mesmo racional
        do mapa de anonimização, REQ-SEC-003).
        """
        with self._lock:
            self._descartar_dek_sem_lock()

    def _descartar_dek_sem_lock(self) -> None:
        """Ponto ÚNICO de saída do estado desbloqueado: fecha o repositório
        cifrado, descarta a referência da DEK e — só quando havia mesmo uma
        sessão aberta — dispara `ao_bloquear`. Bloqueio manual e auto-lock
        passam ambos por aqui, então o gancho cobre os dois sem duplicação; o
        guard `estava_desbloqueada` mantém o bloqueio idempotente (bloquear já
        bloqueado não redispara o gancho)."""
        estava_desbloqueada = self._dek is not None
        # Desarma o checkpoint durável ANTES de zerar a DEK (ADR-0023): consolida
        # o WAL e fecha a 2ª conexão enquanto a chave ainda vale.
        self._desarmar_checkpoint_duravel_sem_lock()
        self._fechar_repo_sem_lock()
        self._dek = None
        if estava_desbloqueada and self.ao_bloquear is not None:
            self.ao_bloquear()

    def _fechar_repo_sem_lock(self) -> None:
        if self._repo is not None:
            self._repo.fechar()
            self._repo = None

    # ------------------------------------------------------------ negócio
    def repositorio_ativo(self) -> Repositorio:
        """Repositório da requisição de negócio corrente.

        Janela de onboarding (cofre não cadastrado): repositório legado em
        claro, criado sob demanda e reusado — mesmo padrão do singleton
        `_REPO` que existia em `app.py` antes desta task. Com cofre
        cadastrado: exige sessão desbloqueada, senão `SessaoBloqueada` (vira
        `423` no `app.py`). Toda chamada aqui é "atividade de negócio": só
        ela atualiza `ultimo_uso` — `status()` não conta, para o auto-lock
        refletir INATIVIDADE de verdade.
        """
        with self._lock:
            self._autolock_sem_lock()
            if self._cofre.esta_cadastrado():
                if self._dek is None or self._repo is None:
                    raise SessaoBloqueada("cofre bloqueado")
                self._ultimo_uso = self._agora()
                return self._repo
            if self._repo is None:
                self._repo = Repositorio(self._caminho_banco(), dek=None)
            self._ultimo_uso = self._agora()
            return self._repo

    def _autolock_sem_lock(self) -> None:
        if self._dek is None or self._auto_lock_min <= 0:
            return
        limite_s = self._auto_lock_min * 60.0
        if self._agora() - self._ultimo_uso > limite_s:
            self._descartar_dek_sem_lock()

    # ---------------------------------------------------------------- ciclo
    def fechar(self) -> None:
        """Fecha o repositório ativo — shutdown do sidecar / teardown de teste."""
        with self._lock:
            self._desarmar_checkpoint_duravel_sem_lock()
            self._fechar_repo_sem_lock()


# ----------------------------------------------------------------- singleton
_SESSAO: SessaoCofre | None = None


def sessao() -> SessaoCofre:
    """Sessão única do processo (sobrescrita nos testes via
    `dependency_overrides` no `app.py` — não pelo reset abaixo).

    Criada sob demanda, mesmo padrão do antigo singleton `_REPO`: lê
    `HF_AUTO_LOCK_MIN` uma vez, na primeira chamada.
    """
    global _SESSAO  # noqa: PLW0603 — singleton lazy
    if _SESSAO is None:
        _SESSAO = SessaoCofre()
    return _SESSAO


def resetar_sessao() -> None:
    """Descarta o singleton do processo (fecha o repositório ativo antes).

    Só para os poucos testes que exercitam o singleton de produção em vez de
    `dependency_overrides` — a maioria isola via override, como o
    `Repositorio` sempre fez.
    """
    global _SESSAO  # noqa: PLW0603 — singleton lazy
    if _SESSAO is not None:
        _SESSAO.fechar()
    _SESSAO = None
