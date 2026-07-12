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

- **Dois locks: START serializado, estado com lock CURTO.** O boot do modelo
  leva dezenas de segundos (carrega ~2 GB); prender um único lock por todo esse
  tempo congelaria `ativo()` (pollado por `GET /llm/status`) e `encerrar()`
  (`POST /llm/modelo`) — a UI de Configuração da IA travava (C-12, ADR-0017
  §M19). Agora `_lock_start` serializa só as tentativas de START entre si
  (duas threads não sobem o servidor ao mesmo tempo), enquanto `_lock_estado` é
  um lock CURTO que só protege leitura/escrita dos campos de estado
  (`_proc`/`_porta`/`_invalidada`) — nunca é retido durante o poll de saúde nem
  durante o `terminate/wait`. `encerrar()` sinaliza o cancelamento do boot em
  curso por um `threading.Event` e mata o processo FORA do lock.

- **Instância invalidada não ressobe (C-03).** Quando a troca de modelo
  (`definir_modelo_ativo` → `encerrar_runtime`) derruba o runtime, a instância
  que outra thread já obteve fica OBSOLETA (cfg do modelo antigo). `encerrar()`
  marca a instância como invalidada; `base_url()` numa instância invalidada
  NÃO reinicia o servidor — levanta `RuntimeLLMInvalidado` — para não ressuscitar
  o modelo antigo e deixar dois `llama-server` no ar. O chokepoint
  `agent.provider.base_url_runtime_embarcado` intercepta essa exceção e re-obtém
  a instância ATUAL (já com o modelo novo) uma única vez.

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

from .job_windows import AncoraProcessos

log = logging.getLogger("helper_financeiro.runtime_llm")

# Variáveis de ambiente (prefixo HF_, como o resto do projeto).
VAR_BINARIO = "HF_LLAMA_SERVER"   # override do caminho do binário llama-server
VAR_MODELO = "HF_LLM_MODELO"      # caminho de um .gguf já instalado no disco
VAR_TESTE_REAL = "HF_LLAMA_REAL"  # liga o teste opt-in com binário/modelo reais
VAR_FLAGS = "HF_LLAMA_FLAGS"      # flags extras do llama-server (ex.: aceleração GPU)

# Aceleração GPU por padrão (T-1703). O binário empacotado é o build **Vulkan**
# do llama.cpp (ver scripts/preparar_llama.py): `-ngl 99` manda offload de TODAS
# as camadas para a GPU Vulkan. Racional da calibragem para a GPU-alvo (4 GB de
# VRAM) com os modelos do catálogo (Q4, ~1,1–2,4 GB): os dois modelos leves
# (1.5B/2B) cabem inteiros na VRAM; o build Vulkan também carrega os backends de
# CPU, então numa máquina SEM GPU/driver Vulkan o `-ngl` não tem para onde
# offloadar e o servidor roda em CPU — o default é seguro nos dois mundos. Quem
# tiver VRAM apertada (ex.: o modelo de 3,8 B numa placa muito cheia) sobrepõe
# via `HF_LLAMA_FLAGS` (inclusive `HF_LLAMA_FLAGS=""` para forçar CPU puro).
_FLAGS_PADRAO: tuple[str, ...] = ("-ngl", "99")

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


class RuntimeLLMInvalidado(RuntimeLLMIndisponivel):
    """Instância cujo `encerrar()` já rodou (troca de modelo/shutdown): subir o
    `llama-server` aqui ressuscitaria o modelo ANTIGO e deixaria dois servidores
    no ar (C-03).

    É subclasse de `RuntimeLLMIndisponivel` de propósito: quem NÃO sabe re-obter
    a instância (qualquer chamador ingênuo) ainda degrada com um motivo textual
    (P8), preservando o contrato. Quem sabe — o chokepoint
    `agent.provider.base_url_runtime_embarcado` — a intercepta especificamente e
    re-obtém a instância atual (já com o modelo novo) uma única vez."""


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
    """Resolve o `.gguf` do modelo: parâmetro explícito > `HF_LLM_MODELO` >
    `llm.json` (T-1702, escolha do usuário na tela de Configuração da IA) >
    ausente.

    Sem modelo configurado (ou apontando para arquivo inexistente) devolve
    `None` — o runtime NÃO inicia e o chamador degrada (P8). Import tardio de
    `sidecar.gestor_modelos`: esse módulo importa `encerrar_runtime` daqui
    (para reiniciar o runtime quando o usuário troca o modelo ativo), então o
    import a nível de módulo criaria um ciclo — cada lado resolve o outro só
    dentro da função que precisa dele.
    """
    env = os.environ if ambiente is None else ambiente
    bruto = str(modelo).strip() if modelo is not None else env.get(VAR_MODELO, "").strip()
    if not bruto:
        from .gestor_modelos import modelo_ativo
        bruto = modelo_ativo(ambiente) or ""
    if not bruto:
        return None
    caminho = Path(bruto)
    if not caminho.is_file():
        log.warning("Modelo GGUF configurado não encontrado — runtime indisponível.")
        return None
    return caminho


def resolver_flags(ambiente: Mapping[str, str] | None = None) -> tuple[str, ...]:
    """Flags extras do `llama-server`: `HF_LLAMA_FLAGS` (split por espaços) ou o
    default de aceleração (`_FLAGS_PADRAO`).

    A env **definida** vence — inclusive vazia: `HF_LLAMA_FLAGS=""` zera as flags
    (força CPU puro, útil se o offload Vulkan falhar). Não definida ⇒ default.
    """
    env = os.environ if ambiente is None else ambiente
    if VAR_FLAGS not in env:
        return _FLAGS_PADRAO
    return tuple(env[VAR_FLAGS].split())


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
        # `_lock_start` serializa TENTATIVAS de subir o servidor; `_lock_estado`
        # é um lock CURTO só para ler/escrever os campos de estado — nunca é
        # retido durante o boot/health nem durante o terminate (C-12).
        self._lock_start = threading.Lock()
        self._lock_estado = threading.Lock()
        self._montar_comando = montar_comando or self._comando_llama_server
        self._agora = agora
        self._dormir = dormir
        self._verificar_saude = verificar_saude
        self._proc: subprocess.Popen[bytes] | None = None
        self._porta: int | None = None
        # Marca de instância obsoleta após `encerrar()` (C-03): `base_url()`
        # recusa reiniciar em vez de ressuscitar o modelo antigo.
        self._invalidada = False
        # Evento para interromper o poll de saúde de um boot em curso quando
        # `encerrar()` chega no meio (fica não-`None` só durante um boot).
        self._cancelar_boot: threading.Event | None = None
        # Rede de segurança do Windows (C-02): ancora o `llama-server` a um Job
        # Object com KILL_ON_JOB_CLOSE, para que a morte DURA do sidecar
        # (TerminateProcess, que não roda o lifespan) não deixe o neto órfão.
        # No-op fora do Windows; toda falha degrada sem piorar o atual (P8).
        self._ancora = AncoraProcessos()

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
        """`True` se há um processo vivo (não encerrou/morreu).

        Responde sob o lock CURTO de estado — nunca fica atrás do boot do
        modelo (C-12): durante o boot o processo já está no ar (registrado
        antes do poll de saúde), então devolve `True` imediatamente.
        """
        with self._lock_estado:
            return self._processo_vivo_sem_lock()

    def _processo_vivo_sem_lock(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    # -------------------------------------------------------- endpoint/uso
    def base_url(self) -> str:
        """Garante o servidor no ar e devolve o endpoint OpenAI-compat (`…/v1`).

        Levanta `RuntimeLLMIndisponivel` se faltar binário/modelo ou se o
        servidor não ficar saudável no prazo; `RuntimeLLMInvalidado` (subclasse)
        se a instância já foi encerrada por uma troca de modelo/shutdown — nunca
        deixa o chamador sem um motivo textual para degradar (P8).
        """
        # Caminho rápido: já no ar → devolve o endpoint sob o lock CURTO, sem
        # tocar em `_lock_start` (que pode estar retido por um boot em curso).
        with self._lock_estado:
            self._garantir_disponivel_sem_lock()
            if self._processo_vivo_sem_lock():
                return self._endpoint_sem_lock()
        # Precisa (re)subir: só o START serializa entre si. A ordem de aquisição
        # é sempre `_lock_start` → `_lock_estado` (nunca o inverso) — sem deadlock
        # com `ativo()`/`encerrar()`, que só pegam `_lock_estado`.
        with self._lock_start:
            with self._lock_estado:
                self._garantir_disponivel_sem_lock()
                if self._processo_vivo_sem_lock():
                    return self._endpoint_sem_lock()  # outra thread já subiu
            self._iniciar()
            with self._lock_estado:
                # Reconfere ANTES de ler a porta: um `encerrar()` que corra
                # entre o fim do boot e este return já zerou `_porta` — sem a
                # guarda, devolveríamos a URL malformada `http://…:None/v1`;
                # com ela, `RuntimeLLMInvalidado` aciona o retry do chokepoint.
                self._garantir_disponivel_sem_lock()
                return self._endpoint_sem_lock()

    def _endpoint_sem_lock(self) -> str:
        return f"http://{self._cfg.host}:{self._porta}/v1"

    def _garantir_disponivel_sem_lock(self) -> None:
        """Traduz instância obsoleta / ausência de binário/modelo em exceção.

        A invalidação vem primeiro: uma instância encerrada não deve nem tentar
        resolver binário/modelo — o chokepoint re-obtém a instância atual.
        """
        if self._invalidada:
            raise RuntimeLLMInvalidado(
                "RUNTIME_ENCERRADO: instância encerrada por troca de modelo ou "
                "shutdown — re-obtenha o runtime atual")
        if self._cfg.binario is None:
            raise RuntimeLLMIndisponivel(
                "BINARIO_AUSENTE: llama-server não encontrado (defina HF_LLAMA_SERVER "
                "ou empacote em resources/llama/)")
        if self._cfg.modelo is None:
            raise RuntimeLLMIndisponivel(
                "MODELO_AUSENTE: nenhum modelo GGUF instalado (aponte HF_LLM_MODELO "
                "ou instale um modelo em Configurações)")

    def _iniciar(self) -> None:
        """Sobe o processo numa porta efêmera e espera o health, SEM segurar o
        lock de estado durante o poll (C-12).

        Chamado só sob `_lock_start` (starts serializados). O boot registra o
        processo no estado ANTES de esperar a saúde, para que `ativo()` o veja e
        que um `encerrar()` concorrente possa matá-lo — se `encerrar()` chega no
        meio, o processo que subia TEM de morrer (aqui ou no ramo de limpeza),
        nunca fica órfão (também coberto pela âncora do Job Object, C-02).
        """
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
        # Ancora ao Job Object ANTES de esperar a saúde: se o sidecar morrer
        # duro durante o boot do modelo, o SO ainda aniquila este processo.
        self._ancora.anexar(proc)
        cancelar = threading.Event()
        invalidado_no_start = False
        with self._lock_estado:
            if self._invalidada:
                # `encerrar()` correu ANTES de registrarmos: não deixe órfão.
                invalidado_no_start = True
            else:
                self._proc = proc
                self._porta = porta
                self._cancelar_boot = cancelar
        if invalidado_no_start:
            self._matar_direto(proc, _PRAZO_ENCERRAR_PADRAO_S)
            raise RuntimeLLMInvalidado(
                "RUNTIME_ENCERRADO: instância encerrada durante o start")

        ok = self._esperar_saude(porta, proc, cancelar)

        encerrado_no_boot = False
        with self._lock_estado:
            if self._proc is not proc or self._invalidada:
                # `encerrar()` correu DURANTE o boot (já zerou `_proc` e/ou pediu
                # cancelamento). O processo deste boot não é mais o oficial.
                encerrado_no_boot = True
            else:
                self._cancelar_boot = None
                if not ok:
                    self._proc = None
                    self._porta = None
        if encerrado_no_boot:
            self._matar_direto(proc, _PRAZO_ENCERRAR_PADRAO_S)  # idempotente
            raise RuntimeLLMInvalidado(
                "RUNTIME_ENCERRADO: instância encerrada durante o boot")
        if not ok:
            self._matar_direto(proc, _PRAZO_ENCERRAR_PADRAO_S)
            raise RuntimeLLMIndisponivel(
                f"HEALTH_TIMEOUT: llama-server não respondeu /health em "
                f"{self._cfg.timeout_health_s:.0f}s")

    def _esperar_saude(
        self, porta: int, proc: subprocess.Popen[bytes], cancelar: threading.Event
    ) -> bool:
        """Poll do `/health` até 200, cancelamento ou timeout (relógio injetável).

        Roda SEM o lock de estado; recebe o `proc` deste boot por parâmetro (não
        lê `self._proc`) e observa o `cancelar` para abortar na hora quando um
        `encerrar()` concorrente pede a parada.
        """
        url = f"http://{self._cfg.host}:{porta}/health"
        limite = self._agora() + self._cfg.timeout_health_s
        while self._agora() < limite:
            if cancelar.is_set():
                return False
            # Se o processo já morreu (ex.: modelo corrompido), não adianta esperar.
            if proc.poll() is not None:
                return False
            if self._verificar_saude(url):
                return True
            self._dormir(self._cfg.intervalo_poll_s)
        return False

    # ------------------------------------------------------------ shutdown
    def encerrar(self, prazo_s: float = _PRAZO_ENCERRAR_PADRAO_S) -> None:
        """Encerra o servidor e INVALIDA a instância (não ressobe, C-03).

        Sob o lock CURTO só marca a invalidação, captura o processo e sinaliza o
        cancelamento de um boot em curso; o `terminate/wait` (que pode custar até
        o prazo) roda FORA do lock, para não prender `ativo()`/status (C-12).
        """
        with self._lock_estado:
            self._invalidada = True
            proc = self._proc
            self._proc = None
            self._porta = None
            if self._cancelar_boot is not None:
                self._cancelar_boot.set()
        self._matar_direto(proc, prazo_s)

    def _matar_direto(
        self, proc: subprocess.Popen[bytes] | None, prazo_s: float
    ) -> None:
        """Encerra `proc`: terminate gentil e, esgotado o prazo, kill.

        Opera sobre a referência recebida (não sobre `self._proc`) e é
        idempotente — chamável fora de qualquer lock e mais de uma vez sobre o
        mesmo processo.
        """
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
                ConfigRuntime(
                    binario=resolver_binario_llama(),
                    modelo=resolver_modelo(),
                    flags_extra=resolver_flags(),
                )
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
