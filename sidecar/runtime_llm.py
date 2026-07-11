"""
Runtime LLM embarcado: gerência do processo `llama-server` (ADR-0016 §E, REQ-F-027).

Elimina a obrigatoriedade de Ollama/LM Studio: o próprio programa carrega um
`llama-server` (llama.cpp — OpenAI-compatible) em **loopback + porta efêmera**,
espera o health, serve as chamadas do `OpenAICompatProvider` (sem mudança de
contrato) e encerra no shutdown do sidecar. É o "padrão de fábrica"; o caminho
do usuário com servidor próprio (`HF_BASE_URL`) continua tendo precedência —
essa decisão fica na fábrica do provider (`agent/provider.py`), não aqui.

## Porquês de projeto

- **Só loopback (REQ-NF-007).** O servidor escuta em `127.0.0.1` e recebe uma
  **porta efêmera** (mesma disciplina do próprio sidecar em `sidecar/__main__`):
  nada é exposto para fora da máquina. Nenhum download acontece aqui — o
  catálogo/instalação do modelo é o T-1702; sem binário ou sem modelo, o
  runtime fica **indisponível** com motivo claro e o chamador degrada (P8).

- **Start preguiçoso + auto-recuperação.** Só sobe quando alguém precisa
  (`base_url()`), e se o processo tiver morrido entre chamadas, a próxima
  reinicia — o custo de carregar ~2 GB de pesos não pode ser pago no boot do
  app nem repetido à toa.

- **Lock único.** Um `threading.Lock` serializa start/stop/detecção de morte:
  o sidecar (FastAPI) atende em múltiplas threads e duas delas não podem tentar
  subir o servidor ao mesmo tempo (mesmo racional do lock único de
  `sidecar/sessao.py` e do `Repositorio`).

- **Relógio/health injetáveis.** `agora`, `dormir`, `verificar_saude` e
  `montar_comando` entram pelo construtor para os testes exercitarem
  start/readiness/shutdown/restart com um processo FALSO, sem binário real e
  sem dormir de verdade.

## Convenção de empacotamento (para o T-1703)

O binário viaja como *extraResource* do Electron. A convenção que este módulo
resolve — e que o T-1703 deve honrar ao empacotar — é, **relativa ao
executável congelado**:

    <dir do executável>/resources/llama/llama-server(.exe)

Em desenvolvimento (não congelado), procura o mesmo caminho relativo à raiz do
repositório. O override explícito `HF_LLAMA_SERVER` (caminho absoluto do
binário) vence a convenção — útil para dev e para builds alternativos.
"""
from __future__ import annotations

import logging
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger("helper_financeiro.runtime_llm")

# Variáveis de ambiente (prefixo HF_, como o resto do projeto).
VAR_BINARIO = "HF_LLAMA_SERVER"   # override do caminho do binário llama-server
VAR_MODELO = "HF_LLM_MODELO"      # caminho de um .gguf já instalado no disco
VAR_TESTE_REAL = "HF_LLAMA_REAL"  # liga o teste opt-in com binário/modelo reais

# Contexto padrão: acompanha o NUM_CTX do provider (fatos crescem com a carteira).
_CTX_PADRAO = 8192
# Health check: modelos de 2 GB podem levar dezenas de segundos p/ carregar em CPU.
_TIMEOUT_HEALTH_PADRAO_S = 60.0
_INTERVALO_POLL_PADRAO_S = 0.25
# Prazo do encerramento gentil antes do kill (SIGKILL/TerminateProcess).
_PRAZO_ENCERRAR_PADRAO_S = 5.0

_HOST_LOOPBACK = "127.0.0.1"


class RuntimeLLMIndisponivel(RuntimeError):
    """Runtime embarcado ausente ou que não ficou saudável — o chamador degrada
    (P8). O motivo é textual e SEM PII (só caminhos/estado), seguro para virar
    `ERRO_CONFIG:RuntimeLLMIndisponivel` no grafo e uma instrução na GUI
    ("instale um modelo em Configurações")."""


# ------------------------------------------------------------ resolução de caminhos
def _nome_binario() -> str:
    """Nome do executável por plataforma (`.exe` no Windows)."""
    return "llama-server.exe" if os.name == "nt" else "llama-server"


def _base_pacote() -> Path:
    """Diretório-base para procurar o binário empacotado.

    Congelado (PyInstaller): a pasta do executável — é ao lado dele que o
    *extraResource* do Electron deposita `resources/`. Em desenvolvimento: a
    raiz do repositório (dois níveis acima deste arquivo: `sidecar/..`)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def resolver_binario_llama(ambiente: Mapping[str, str] | None = None) -> Path | None:
    """Resolve o caminho do `llama-server`: override por env > pacote > ausente.

    - `HF_LLAMA_SERVER` definido: usa esse caminho SE existir; se apontar para
      algo inexistente, devolve `None` (escolha explícita e errada do usuário
      não deve cair silenciosamente no binário do pacote — melhor sinalizar
      indisponível e degradar com motivo).
    - Sem override: `<base>/resources/llama/llama-server(.exe)` se existir.
    - Nada encontrado: `None` ⇒ runtime indisponível.
    """
    env = os.environ if ambiente is None else ambiente
    override = env.get(VAR_BINARIO, "").strip()
    if override:
        caminho = Path(override)
        if caminho.is_file():
            return caminho
        log.warning("%s aponta para binário inexistente — runtime indisponível.", VAR_BINARIO)
        return None
    empacotado = _base_pacote() / "resources" / "llama" / _nome_binario()
    return empacotado if empacotado.is_file() else None


def resolver_modelo(
    ambiente: Mapping[str, str] | None = None, modelo: str | os.PathLike[str] | None = None
) -> Path | None:
    """Resolve o `.gguf` do modelo: parâmetro explícito > `HF_LLM_MODELO` > ausente.

    Sem modelo configurado (ou apontando para arquivo inexistente) devolve
    `None` — o runtime NÃO inicia e o chamador degrada (P8). O catálogo/download
    é o T-1702; aqui só se APONTA um arquivo já presente no disco.
    """
    env = os.environ if ambiente is None else ambiente
    bruto = str(modelo).strip() if modelo is not None else env.get(VAR_MODELO, "").strip()
    if not bruto:
        return None
    caminho = Path(bruto)
    if not caminho.is_file():
        log.warning("Modelo GGUF configurado não encontrado — runtime indisponível.")
        return None
    return caminho


def _porta_livre(host: str = _HOST_LOOPBACK) -> int:
    """Pergunta ao SO uma porta livre em loopback (bind 0) e a devolve.

    Há uma janela TOCTOU entre fechar o socket e o `llama-server` fazer o bind
    — a mesma aceita conscientemente pelo `sidecar/__main__` para o próprio
    sidecar; num app desktop de usuário único é irrelevante.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((host, 0))
        return int(s.getsockname()[1])


def _saude_ok(url_health: str, timeout_s: float = 2.0) -> bool:
    """`True` se o `GET /health` responde 200 (`llama-server` pronto).

    Enquanto carrega o modelo o servidor responde 503; qualquer erro de conexão
    (ainda não subiu) também conta como "não pronto". Nunca levanta.
    """
    try:
        # URL sempre loopback montada por nós (host/porta controlados) — sem SSRF.
        with urllib.request.urlopen(url_health, timeout=timeout_s) as resp:
            return 200 <= resp.status < 300
    except (urllib.error.URLError, OSError):
        return False


@dataclass
class ConfigRuntime:
    """Parâmetros de execução do `llama-server` (tudo injetável para teste)."""

    binario: Path | None
    modelo: Path | None
    host: str = _HOST_LOOPBACK
    ctx_size: int = _CTX_PADRAO
    timeout_health_s: float = _TIMEOUT_HEALTH_PADRAO_S
    intervalo_poll_s: float = _INTERVALO_POLL_PADRAO_S
    # Flags extras (ex.: `-ngl N` p/ camadas na GPU Vulkan) — o T-1703 calibra
    # conforme o build empacotado; o default fica só no CPU, portável.
    flags_extra: tuple[str, ...] = field(default_factory=tuple)


class RuntimeLLM:
    """Ciclo de vida de um `llama-server` embarcado, thread-safe.

    Uso: `base_url()` sobe o servidor sob demanda (se preciso) e devolve o
    endpoint OpenAI-compatible loopback; `encerrar()` derruba no shutdown.
    """

    def __init__(
        self,
        cfg: ConfigRuntime,
        *,
        montar_comando: Callable[[int], list[str]] | None = None,
        agora: Callable[[], float] = time.monotonic,
        dormir: Callable[[float], None] = time.sleep,
        verificar_saude: Callable[[str], bool] = _saude_ok,
    ) -> None:
        self._cfg = cfg
        self._lock = threading.Lock()
        self._montar_comando = montar_comando or self._comando_llama_server
        self._agora = agora
        self._dormir = dormir
        self._verificar_saude = verificar_saude
        self._proc: subprocess.Popen[bytes] | None = None
        self._porta: int | None = None

    # -------------------------------------------------------------- comando
    def _comando_llama_server(self, porta: int) -> list[str]:
        """Argv padrão do `llama-server`: modelo, loopback, porta e contexto.

        Mantido mínimo e portável (CPU). O binário/modelo já foram validados
        (não-`None`) por quem chama; os asserts abaixo são só para o type
        checker.
        """
        assert self._cfg.binario is not None and self._cfg.modelo is not None
        return [
            str(self._cfg.binario),
            "-m", str(self._cfg.modelo),
            "--host", self._cfg.host,
            "--port", str(porta),
            "-c", str(self._cfg.ctx_size),
            *self._cfg.flags_extra,
        ]

    # ------------------------------------------------------------- estado
    def ativo(self) -> bool:
        """`True` se há um processo vivo (não encerrou/morreu)."""
        with self._lock:
            return self._processo_vivo_sem_lock()

    def _processo_vivo_sem_lock(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    # -------------------------------------------------------- endpoint/uso
    def base_url(self) -> str:
        """Garante o servidor no ar e devolve o endpoint OpenAI-compat (`…/v1`).

        Levanta `RuntimeLLMIndisponivel` se faltar binário/modelo ou se o
        servidor não ficar saudável no prazo — nunca deixa o chamador sem um
        motivo textual para degradar (P8).
        """
        with self._lock:
            self._garantir_indisponibilidade_sem_lock()
            if not self._processo_vivo_sem_lock():
                self._iniciar_sem_lock()
            return f"http://{self._cfg.host}:{self._porta}/v1"

    def _garantir_indisponibilidade_sem_lock(self) -> None:
        """Traduz a ausência de binário/modelo em `RuntimeLLMIndisponivel`."""
        if self._cfg.binario is None:
            raise RuntimeLLMIndisponivel(
                "BINARIO_AUSENTE: llama-server não encontrado (defina HF_LLAMA_SERVER "
                "ou empacote em resources/llama/)")
        if self._cfg.modelo is None:
            raise RuntimeLLMIndisponivel(
                "MODELO_AUSENTE: nenhum modelo GGUF instalado (aponte HF_LLM_MODELO "
                "ou instale um modelo em Configurações)")

    def _iniciar_sem_lock(self) -> None:
        """Sobe o processo numa porta efêmera e espera o health; limpa se falhar."""
        porta = _porta_livre(self._cfg.host)
        comando = self._montar_comando(porta)
        log.info("Iniciando llama-server em %s:%d", self._cfg.host, porta)
        # stdout/stderr descartados: o servidor loga infos do modelo que não
        # queremos nos nossos logs (REQ-SEC-001 é sobre PII, mas manter quieto
        # é a política do app). Sem shell, argv em lista e binário resolvido
        # por nós (sem injeção).
        proc = subprocess.Popen(
            comando, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        self._proc = proc
        self._porta = porta
        if not self._esperar_saude_sem_lock(porta):
            self._encerrar_processo_sem_lock(_PRAZO_ENCERRAR_PADRAO_S)
            raise RuntimeLLMIndisponivel(
                f"HEALTH_TIMEOUT: llama-server não respondeu /health em "
                f"{self._cfg.timeout_health_s:.0f}s")

    def _esperar_saude_sem_lock(self, porta: int) -> bool:
        """Poll do `/health` até 200 ou estourar o timeout (relógio injetável)."""
        url = f"http://{self._cfg.host}:{porta}/health"
        limite = self._agora() + self._cfg.timeout_health_s
        while self._agora() < limite:
            # Se o processo já morreu (ex.: modelo corrompido), não adianta esperar.
            if not self._processo_vivo_sem_lock():
                return False
            if self._verificar_saude(url):
                return True
            self._dormir(self._cfg.intervalo_poll_s)
        return False

    # ------------------------------------------------------------ shutdown
    def encerrar(self, prazo_s: float = _PRAZO_ENCERRAR_PADRAO_S) -> None:
        """Encerra o servidor: terminate gentil e, esgotado o prazo, kill."""
        with self._lock:
            self._encerrar_processo_sem_lock(prazo_s)

    def _encerrar_processo_sem_lock(self, prazo_s: float) -> None:
        proc = self._proc
        self._proc = None
        self._porta = None
        if proc is None or proc.poll() is not None:
            return
        proc.terminate()
        try:
            proc.wait(timeout=prazo_s)
        except subprocess.TimeoutExpired:
            log.warning("llama-server não encerrou em %.1fs — kill.", prazo_s)
            proc.kill()
            proc.wait()


# ----------------------------------------------------------------- singleton
_RUNTIME: RuntimeLLM | None = None
_LOCK_SINGLETON = threading.Lock()


def runtime_embarcado() -> RuntimeLLM:
    """Runtime único do processo (criado sob demanda).

    Resolve binário/modelo do ambiente na primeira chamada. Mesmo sem binário
    ou modelo, devolve uma instância — é `base_url()` que levanta
    `RuntimeLLMIndisponivel` com o motivo, mantendo um ponto único de decisão.
    """
    global _RUNTIME
    with _LOCK_SINGLETON:
        if _RUNTIME is None:
            _RUNTIME = RuntimeLLM(
                ConfigRuntime(binario=resolver_binario_llama(), modelo=resolver_modelo())
            )
        return _RUNTIME


def encerrar_runtime() -> None:
    """Derruba o runtime único e descarta a referência.

    A ser chamado no shutdown do sidecar (o T-1702 liga isto no ciclo de vida
    do `app.py`, fora do perímetro desta task).
    """
    global _RUNTIME
    with _LOCK_SINGLETON:
        if _RUNTIME is not None:
            _RUNTIME.encerrar()
            _RUNTIME = None
