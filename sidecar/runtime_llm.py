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

import contextlib
import dataclasses
import logging
import os
import re
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from collections import deque
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import NamedTuple

from .job_windows import AncoraProcessos

log = logging.getLogger("helper_financeiro.runtime_llm")

# Variáveis de ambiente (prefixo HF_, como o resto do projeto).
VAR_BINARIO = "HF_LLAMA_SERVER"   # override do caminho do binário llama-server
VAR_MODELO = "HF_LLM_MODELO"      # caminho de um .gguf já instalado no disco
VAR_TESTE_REAL = "HF_LLAMA_REAL"  # liga o teste opt-in com binário/modelo reais
VAR_FLAGS = "HF_LLAMA_FLAGS"      # flags extras do llama-server (ex.: aceleração GPU)

# Sem flags por padrão: o AUTO-FIT do llama.cpp decide o offload a cada boot,
# medindo a VRAM livre daquele instante. LIÇÃO DE CAMPO (2026-07-15, ADR-0022):
# o default antigo `-ngl 99` (forçar TODAS as camadas na GPU Vulkan) foi provado
# ERRADO no build b9966 — o comentário da época afirmava ser "seguro nos dois
# mundos" (offloadaria na GPU e cairia para CPU sem driver), mas com `-ngl`
# explícito o `common_fit_params` ABORTA ("n_gpu_layers already set by user to
# 99, abort") em vez de reduzir, e a alocação estoura com
# `ErrorOutOfDeviceMemory` — o servidor CRASHA em ~5 s (exit 0xC0000005) numa
# GPU-alvo de 4 GB (GTX 1650) que não comporta modelo + KV cache. SEM `-ngl`, o
# mesmo binário/modelo sobem saudáveis (o auto-fit acomoda o que couber e joga o
# resto na CPU). Quem quiser controle explícito escolhe na tela de Configuração
# da IA (`gpu_offload`: `"auto"`/`"cpu"`/N camadas → resolvido abaixo) ou
# sobrepõe TUDO via `HF_LLAMA_FLAGS` (inclusive `HF_LLAMA_FLAGS=""` = CPU puro).
_FLAGS_PADRAO: tuple[str, ...] = ()

# Contexto padrão: 4096 era a config validada na era LM Studio; 8192 (o default
# antigo) estourava a VRAM da GPU-alvo junto com o offload total (ADR-0022).
_CTX_PADRAO = 4096

# Ring buffer do stderr do llama-server: as N últimas linhas ficam SÓ em memória
# (REQ-SEC-001 — nada em disco/log persistente), suficientes para o classificador
# e as métricas do último boot sem reter o log inteiro. 400 (não 200) porque com
# `-lv 4` (ver `_comando_llama_server`) um boot bom do b9966 emite ~203 linhas e
# as métricas de offload/VRAM caem lá pela 141/143 — 200 as perderia num modelo
# maior; 400 dá folga sem custo de memória relevante (medido em campo, ADR-0022).
_MAX_LINHAS_STDERR = 400
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
    """Flags extras do `llama-server`, por precedência (ADR-0022):

    1. `HF_LLAMA_FLAGS` **definida** vence TUDO — inclusive vazia:
       `HF_LLAMA_FLAGS=""` zera as flags (CPU puro). Contrato de override
       intacto: quem seta a env manda no argv inteiro de flags.
    2. `gpu_offload` do `llm.json` (escolha da tela de Configuração da IA):
       `"cpu"` ⇒ `-ngl 0`; int N ⇒ `-ngl N`; `"auto"`/ausente ⇒ SEM `-ngl`
       (deixa o auto-fit do llama.cpp decidir — o fix de campo do ADR-0022).
    3. Default: `_FLAGS_PADRAO` (tupla vazia ⇒ auto-fit).
    """
    env = os.environ if ambiente is None else ambiente
    if VAR_FLAGS in env:
        return tuple(env[VAR_FLAGS].split())
    # Import tardio: `gestor_modelos` importa `encerrar_runtime` deste módulo
    # (ciclo), então cada lado resolve o outro só dentro da função que precisa.
    from .gestor_modelos import gpu_offload_configurado
    offload = gpu_offload_configurado(ambiente)
    if offload is None or offload == "auto":
        return _FLAGS_PADRAO
    if offload == "cpu":
        return ("-ngl", "0")
    return ("-ngl", str(offload))  # int de camadas


def resolver_ctx_size(ambiente: Mapping[str, str] | None = None) -> int:
    """Contexto efetivo: `ctx_size` do `llm.json` substitui o `-c` default.

    (Não há env dedicada: quem usa `HF_LLAMA_FLAGS` pode acrescentar `-c N` lá,
    e o llama.cpp b9966 aplica o "último `-c` vence" — ver ADR-0022, tabela de
    riscos.) Valor ausente/inválido no `llm.json` cai no `_CTX_PADRAO`.
    """
    from .gestor_modelos import ctx_size_configurado
    valor = ctx_size_configurado(ambiente)
    return valor if valor is not None else _CTX_PADRAO


# ------------------------------------------------ diagnóstico do boot do runtime
class MotivoFalhaGPU(StrEnum):
    """Motivo tipado de uma falha de boot na GPU (ADR-0022).

    `StrEnum` de propósito: serializa direto no JSON dos endpoints (T-2502) e
    compara com string nos testes. `GENERICO` é o fallback que SEMPRE existe —
    um padrão de erro ainda não catalogado nunca vira exceção, só perde
    especificidade (as fixtures crescem quando surgir caso novo)."""

    GPU_SEM_MEMORIA = "GPU_SEM_MEMORIA"    # ErrorOutOfDeviceMemory (VRAM estourou)
    GPU_FIT_ABORTADO = "GPU_FIT_ABORTADO"  # common_fit_params: failed to fit params
    GENERICO = "GENERICO"                  # qualquer outra falha


@dataclass
class MetricasBoot:
    """Métricas do último boot BOM (cada campo é best-effort: ausente ⇒ `None`,
    nunca exceção — o formato varia por build do llama.cpp).

    Offload/VRAM/contexto saem do stderr do boot (`extrair_metricas`); o
    dispositivo e a VRAM total/livre vêm do `--list-devices` (`listar_dispositivos`),
    porque o b9966 NÃO imprime linha de dispositivo no stderr em nenhuma
    verbosidade testada em campo (ADR-0022)."""

    camadas_offload: int | None = None    # camadas jogadas na GPU
    camadas_total: int | None = None      # total de camadas do modelo
    vram_bytes: int | None = None         # VRAM alocada pelo buffer do modelo
    ctx_efetivo: int | None = None        # n_ctx_slot efetivo do servidor
    dispositivo: str | None = None        # nome do 1º dispositivo (--list-devices)
    vram_total_bytes: int | None = None   # VRAM total do dispositivo
    vram_livre_bytes: int | None = None   # VRAM livre no momento da enumeração


@dataclass
class BootInfo:
    """Resultado consultável do último boot (sob o lock de estado).

    `modo`: `"nunca_subiu"` (nunca subiu com sucesso) | `"gpu"` (offload > 0) |
    `"cpu_configurado"` (a config pediu CPU puro) | `"cpu_fallback"` (a GPU
    falhou e a retentativa em CPU salvou o boot). `motivo_fallback` só é
    preenchido quando houve falha de GPU (fallback ou boot que não subiu)."""

    modo: str = "nunca_subiu"
    motivo_fallback: MotivoFalhaGPU | None = None
    metricas: MetricasBoot = field(default_factory=MetricasBoot)


# Padrões dos motivos de falha, na ORDEM de prioridade: o crash real de campo
# emite AS DUAS linhas (o auto-fit avisa "failed to fit" e segue, e a alocação é
# que estoura com OOM) — a falta de VRAM é a causa decisiva e a que dispara a
# dica de reduzir contexto (T-2502), então vem primeiro.
_PADROES_FALHA: tuple[tuple[str, MotivoFalhaGPU], ...] = (
    ("erroroutofdevicememory", MotivoFalhaGPU.GPU_SEM_MEMORIA),
    ("failed to fit params", MotivoFalhaGPU.GPU_FIT_ABORTADO),
)


def classificar_falha(linhas: Sequence[str]) -> MotivoFalhaGPU:
    """Classifica um boot que falhou a partir das linhas de stderr capturadas.

    Função PURA e testável (entrada = sequência de linhas). Tolerante a linhas
    vazias/lixo: se nenhum padrão conhecido casar, devolve `GENERICO`."""
    texto = "\n".join(linhas).lower()
    for agulha, motivo in _PADROES_FALHA:
        if agulha in texto:
            return motivo
    return MotivoFalhaGPU.GENERICO


# Regexes das métricas do boot bom. Todas opcionais: o que não casar fica `None`
# (o formato das linhas varia por build do llama.cpp — o parser nunca pode
# levantar por um campo ausente).
_RE_CTX_SLOT = re.compile(r"n_ctx_slot\s*=\s*(\d+)")
_RE_OFFLOAD = re.compile(r"offloaded\s+(\d+)\s*/\s*(\d+)\s+layers")
# VRAM: ANCORADA em `VulkanN` (dígito). Em `-lv 4` o load faz dois passes e há
# várias linhas casando `model buffer size` — a de dry-run `Vulkan0 ... 0.00 MiB`,
# a `CPU_Mapped ... 2281 MiB` e a REAL `Vulkan0 ... 358.41 MiB`. A âncora exclui
# `CPU_Mapped` e `Vulkan_Host` (sem dígito) e pegamos a ÚLTIMA ocorrência (o
# valor real vem depois do dry-run zerado). Ver ADR-0022 (evidência de campo).
_RE_VRAM_VULKAN_MIB = re.compile(r"Vulkan\d+ model buffer size\s*=\s*([\d.]+)\s*MiB")


def extrair_metricas(linhas: Sequence[str]) -> MetricasBoot:
    """Extrai offload, VRAM alocada e contexto de um boot BOM do stderr
    (best-effort, nunca levanta).

    Cada métrica é buscada de forma independente; um campo cujo padrão não
    aparece nas linhas (build diferente, log truncado) fica `None`. O nome do
    dispositivo e a VRAM total/livre NÃO saem daqui (o b9966 não os imprime no
    stderr) — vêm do `--list-devices` via `listar_dispositivos`."""
    texto = "\n".join(linhas)
    m = MetricasBoot()
    if achou := _RE_CTX_SLOT.search(texto):
        m.ctx_efetivo = int(achou.group(1))
    if achou := _RE_OFFLOAD.search(texto):
        m.camadas_offload = int(achou.group(1))
        m.camadas_total = int(achou.group(2))
    if valores := _RE_VRAM_VULKAN_MIB.findall(texto):
        m.vram_bytes = int(round(float(valores[-1]) * 1024 * 1024))  # última: a real
    return m


class DispositivoGPU(NamedTuple):
    """Um dispositivo reportado pelo `llama-server --list-devices`."""

    nome: str
    vram_total_mib: int
    vram_livre_mib: int


# Linha do `--list-devices`: "  Vulkan0: NVIDIA GeForce GTX 1650 (4149 MiB, 3535 MiB free)"
_RE_DISPOSITIVO_LISTA = re.compile(
    r"^\s*\S+:\s*(.+?)\s*\((\d+)\s*MiB,\s*(\d+)\s*MiB\s+free\)\s*$", re.MULTILINE)


def _parsear_dispositivos(texto: str) -> list[DispositivoGPU]:
    """Parser PURO da saída do `--list-devices` → lista de `DispositivoGPU`.

    Tolerante: linhas que não casam (cabeçalho `Available devices:`, lixo) são
    ignoradas; texto sem dispositivos ⇒ lista vazia, nunca exceção."""
    return [
        DispositivoGPU(nome.strip(), int(total), int(livre))
        for nome, total, livre in _RE_DISPOSITIVO_LISTA.findall(texto)
    ]


# Cache dos dispositivos por caminho do binário: `--list-devices` é estável para
# um binário e não queremos re-executá-lo a cada boot (C-14-like).
_CACHE_DISPOSITIVOS: dict[str, list[DispositivoGPU]] = {}
_CACHE_DISPOSITIVOS_LOCK = threading.Lock()


def listar_dispositivos(binario: Path) -> list[DispositivoGPU]:
    """Enumera os dispositivos do `llama-server` via `--list-devices` (rápido, não
    carrega modelo), com tolerância TOTAL: qualquer falha (binário inválido,
    timeout, saída inesperada) ⇒ lista vazia, nunca exceção — o painel degrada
    para "dispositivo desconhecido", não quebra o boot. Resultado cacheado por
    caminho do binário."""
    chave = str(binario)
    with _CACHE_DISPOSITIVOS_LOCK:
        if chave in _CACHE_DISPOSITIVOS:
            return _CACHE_DISPOSITIVOS[chave]
    dispositivos: list[DispositivoGPU] = []
    try:
        # argv em lista, binário resolvido por nós (sem shell, sem injeção).
        res = subprocess.run(
            [chave, "--list-devices"],
            capture_output=True, timeout=10.0, check=False,
        )
        saida = res.stdout.decode("utf-8", errors="replace")
        saida += "\n" + res.stderr.decode("utf-8", errors="replace")
        dispositivos = _parsear_dispositivos(saida)
    except (OSError, subprocess.SubprocessError):
        dispositivos = []
    with _CACHE_DISPOSITIVOS_LOCK:
        _CACHE_DISPOSITIVOS[chave] = dispositivos
    return dispositivos


def _e_cpu_puro(flags: Sequence[str]) -> bool:
    """`True` se as flags já forçam CPU puro (`-ngl 0`) — nesse caso não há
    retentativa em CPU a fazer (já é o destino do retry)."""
    for i, tok in enumerate(flags):
        if tok == "-ngl" and i + 1 < len(flags) and flags[i + 1] == "0":
            return True
    return False


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
    # Flags extras resolvidas por `resolver_flags` (env > `gpu_offload` do
    # llm.json > default). O default é VAZIO: o auto-fit do llama.cpp decide o
    # offload (fix de campo do ADR-0022; ver `_FLAGS_PADRAO`).
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
        # Override transitório das flags durante a retentativa em CPU puro
        # (`-ngl 0`): `_comando_llama_server` o consulta em vez de
        # `cfg.flags_extra` enquanto o retry está em curso; `None` fora dele.
        self._flags_boot: tuple[str, ...] | None = None
        # Diagnóstico do último boot (item consultável por `boot_info()`) e as
        # linhas de stderr do último boot — INTERNAS (não expostas no BootInfo),
        # usadas para classificar a falha e extrair métricas.
        self._boot_info = BootInfo()
        self._linhas_ultimo_boot: list[str] = []
        # Rede de segurança do Windows (C-02): ancora o `llama-server` a um Job
        # Object com KILL_ON_JOB_CLOSE, para que a morte DURA do sidecar
        # (TerminateProcess, que não roda o lifespan) não deixe o neto órfão.
        # No-op fora do Windows; toda falha degrada sem piorar o atual (P8).
        self._ancora = AncoraProcessos()

    # -------------------------------------------------------------- comando
    def _comando_llama_server(self, porta: int) -> list[str]:
        """Argv do `llama-server`: modelo, loopback, porta, contexto e flags.

        `-lv 4` (verbosidade) é OBRIGATÓRIO no argv base: na verbosidade padrão
        (3) o b9966 NÃO emite as linhas de offload/VRAM que alimentam o painel do
        último boot (medido em campo — um boot bom sai com só 7 linhas de srv);
        com `-lv 4` o mesmo boot emite ~203 linhas incluindo
        `offloaded X/Y layers to GPU` e `VulkanN model buffer size = ... MiB`.
        Fica no 4 de propósito: `-lv 5` explode para ~1000 linhas de debug por
        request (ruído e risco de reter conteúdo de request no buffer). Vem ANTES
        de `flags` para que `HF_LLAMA_FLAGS` possa sobrepô-lo (último `-lv` vence).

        As flags saem de `_flags_boot` quando um retry em CPU está em curso
        (`-ngl 0`), senão de `cfg.flags_extra` (resolvidas por `resolver_flags`).
        O binário/modelo já foram validados (não-`None`) por quem chama; os
        asserts abaixo são só para o type checker.
        """
        assert self._cfg.binario is not None and self._cfg.modelo is not None
        flags = self._cfg.flags_extra if self._flags_boot is None else self._flags_boot
        return [
            str(self._cfg.binario),
            "-m", str(self._cfg.modelo),
            "--host", self._cfg.host,
            "--port", str(porta),
            "-c", str(self._cfg.ctx_size),
            "-lv", "4",
            *flags,
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
            self._iniciar_com_retry()
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
        # stdout descartado; stderr vai para um PIPE lido por uma thread daemon
        # que alimenta um ring buffer SÓ em memória (REQ-SEC-001 — nada em
        # disco): é a matéria-prima do classificador de falha e das métricas do
        # último boot, e ler o pipe evita que o servidor bloqueie se logar
        # muito. Sem shell, argv em lista e binário resolvido por nós (sem
        # injeção).
        proc = subprocess.Popen(
            comando, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE
        )
        buffer: deque[str] = deque(maxlen=_MAX_LINHAS_STDERR)
        leitor = threading.Thread(
            target=self._drenar_stderr, args=(proc, buffer), daemon=True)
        leitor.start()
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
            self._snapshot_stderr(buffer, leitor)
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
            self._snapshot_stderr(buffer, leitor)
            raise RuntimeLLMInvalidado(
                "RUNTIME_ENCERRADO: instância encerrada durante o boot")
        if not ok:
            self._matar_direto(proc, _PRAZO_ENCERRAR_PADRAO_S)
            # Processo morto ⇒ stderr em EOF: aguarda a leitora fechar para
            # capturar TODAS as linhas antes de classificar a falha.
            self._snapshot_stderr(buffer, leitor, aguardar=True)
            raise RuntimeLLMIndisponivel(
                f"HEALTH_TIMEOUT: llama-server não respondeu /health em "
                f"{self._cfg.timeout_health_s:.0f}s")
        # Boot bom: captura o snapshot para extrair métricas (as linhas de load
        # já foram emitidas antes do /health responder 200).
        self._snapshot_stderr(buffer, leitor)

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

    # -------------------------------------------------- captura de stderr
    def _drenar_stderr(
        self, proc: subprocess.Popen[bytes], buffer: deque[str]
    ) -> None:
        """Lê o stderr do `proc` linha a linha para o ring buffer (thread daemon).

        Nunca bloqueia o boot: roda numa thread própria e o health poll não
        depende dela. `readline` retorna `b""` no EOF (processo morto) e a thread
        encerra; um stream fechado no meio (kill) apenas termina a leitura. Nada
        é logado nem escrito em disco (REQ-SEC-001) — só o buffer em memória.
        """
        stream = proc.stderr
        if stream is None:
            return
        try:
            for linha in iter(stream.readline, b""):
                buffer.append(linha.decode("utf-8", errors="replace").rstrip("\r\n"))
        except (ValueError, OSError):
            pass  # stream fechado durante a leitura (proc morto) — encerra quieto
        finally:
            with contextlib.suppress(OSError):
                stream.close()

    def _snapshot_stderr(
        self, buffer: deque[str], leitor: threading.Thread, aguardar: bool = False
    ) -> None:
        """Congela as linhas de stderr do boot corrente em `_linhas_ultimo_boot`.

        `aguardar=True` dá um tempo curto para a leitora esvaziar o pipe antes do
        snapshot (usado quando o processo já morreu e queremos TODAS as linhas
        para classificar a falha); num boot bom o snapshot é imediato.
        """
        if aguardar:
            leitor.join(timeout=1.0)
        self._linhas_ultimo_boot = list(buffer)

    # ------------------------------------------------------- boot + retry
    def _iniciar_com_retry(self) -> None:
        """Sobe o servidor e, se a GPU falhar, faz UMA retentativa em CPU puro.

        Envolve `_iniciar()` (que faz uma tentativa) com a política do ADR-0022:
        se o boot falha (processo morre ou health estoura) e a config NÃO era CPU
        puro, tenta de novo uma única vez com `-ngl 0` antes de degradar — sem
        loop, sem segunda retentativa. `RuntimeLLMInvalidado` (troca de
        modelo/shutdown) nunca é retentada: é propagada de imediato. Em todos os
        caminhos o `boot_info` fica atualizado sob o lock de estado.
        """
        config_cpu = _e_cpu_puro(self._cfg.flags_extra)
        try:
            self._iniciar()
        except RuntimeLLMInvalidado:
            raise
        except RuntimeLLMIndisponivel:
            motivo = classificar_falha(self._linhas_ultimo_boot)
            if config_cpu:
                # Já era CPU puro: a retentativa em CPU não mudaria nada.
                self._registrar_boot_falho(motivo)
                raise
            # Retentativa única em CPU puro (`-ngl 0`).
            self._flags_boot = ("-ngl", "0")
            try:
                self._iniciar()
            except RuntimeLLMInvalidado:
                raise
            except RuntimeLLMIndisponivel:
                self._registrar_boot_falho(classificar_falha(self._linhas_ultimo_boot))
                raise
            finally:
                self._flags_boot = None
            # A retentativa salvou o boot: modo cpu_fallback com o motivo da GPU.
            self._registrar_boot_ok(foi_fallback=True, config_cpu=False, motivo=motivo)
            return
        # Primeira tentativa subiu.
        self._registrar_boot_ok(foi_fallback=False, config_cpu=config_cpu, motivo=None)

    def _registrar_boot_ok(
        self, *, foi_fallback: bool, config_cpu: bool, motivo: MotivoFalhaGPU | None
    ) -> None:
        """Grava o `boot_info` de um boot bem-sucedido sob o lock de estado."""
        metricas = extrair_metricas(self._linhas_ultimo_boot)
        # O stderr não traz o nome do dispositivo (b9966): completa com o 1º
        # dispositivo do `--list-devices` (cacheado, tolerante). Fora do lock: é
        # um subprocesso que pode custar até o timeout curto.
        if metricas.dispositivo is None and self._cfg.binario is not None:
            dispositivos = listar_dispositivos(self._cfg.binario)
            if dispositivos:
                d = dispositivos[0]
                metricas.dispositivo = d.nome
                metricas.vram_total_bytes = d.vram_total_mib * 1024 * 1024
                metricas.vram_livre_bytes = d.vram_livre_mib * 1024 * 1024
        if foi_fallback:
            modo = "cpu_fallback"
        elif config_cpu:
            modo = "cpu_configurado"
        else:
            # Config auto/GPU que subiu de primeira. `gpu` é o rótulo quando há
            # offload (>0); sem métricas de offload (build que não emite as
            # linhas), assume `gpu` — a GUI mostra o offload real quando existe.
            modo = "gpu"
        with self._lock_estado:
            self._boot_info = BootInfo(modo=modo, motivo_fallback=motivo, metricas=metricas)

    def _registrar_boot_falho(self, motivo: MotivoFalhaGPU) -> None:
        """Grava o `boot_info` de um boot que não subiu (modo `nunca_subiu` com o
        motivo tipado disponível para a GUI/endpoints)."""
        with self._lock_estado:
            self._boot_info = BootInfo(modo="nunca_subiu", motivo_fallback=motivo)

    def boot_info(self) -> BootInfo:
        """Diagnóstico do último boot (cópia, sob o lock CURTO de estado).

        Devolve uma cópia para o chamador não mexer no estado interno; as linhas
        cruas de stderr NÃO são expostas (ficam internas — REQ-SEC-001)."""
        with self._lock_estado:
            info = self._boot_info
            return dataclasses.replace(
                info, metricas=dataclasses.replace(info.metricas))

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
    global _RUNTIME  # noqa: PLW0603 — singleton lazy sob lock
    with _LOCK_SINGLETON:
        if _RUNTIME is None:
            _RUNTIME = RuntimeLLM(
                ConfigRuntime(
                    binario=resolver_binario_llama(),
                    modelo=resolver_modelo(),
                    ctx_size=resolver_ctx_size(),
                    flags_extra=resolver_flags(),
                )
            )
        return _RUNTIME


def encerrar_runtime() -> None:
    """Derruba o runtime único e descarta a referência.

    A ser chamado no shutdown do sidecar (o T-1702 liga isto no ciclo de vida
    do `app.py`, fora do perímetro desta task).
    """
    global _RUNTIME  # noqa: PLW0603 — singleton lazy sob lock
    with _LOCK_SINGLETON:
        if _RUNTIME is not None:
            _RUNTIME.encerrar()
            _RUNTIME = None
