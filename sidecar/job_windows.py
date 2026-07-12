"""
Ancoragem de processos-filho ao ciclo de vida do sidecar via Job Object do
Windows (C-02, ADR-0017 §M19).

## O porquê

No Windows, a morte DURA do sidecar — o `sidecar.kill()` do Electron, que é um
`TerminateProcess`, disparado em quit/relaunch/crash — não entrega sinal algum
ao Python: o lifespan do FastAPI (`sidecar/app.py`) NÃO roda, logo
`encerrar_runtime()` não executa e o `llama-server` (neto) fica **órfão**,
segurando RAM/VRAM e o handle do `.gguf` (foi o EBUSY observado no rebuild do
T-1704). O encerramento gracioso (`terminate→wait→kill` em `runtime_llm.py`)
cobre o caminho feliz, mas não a morte dura.

A rede de segurança que cobre TODO caminho de morte é um **Job Object** com
`JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`: atribuímos o `llama-server` a um job cujo
handle o SIDECAR mantém aberto. Quando o processo do sidecar termina por
qualquer via, o SO fecha todos os seus handles; ao fechar o último handle do
job, o SO aniquila os processos ainda atribuídos. É garantia do SO, não do
nosso código de shutdown.

## Disciplina de segurança (P8)

- **No-op limpo fora do Windows.** Outros SOs não têm Job Object; a lacuna
  coberta aqui é específica do `TerminateProcess`. `anexar()` devolve `False` e
  nada acontece.
- **Fallback silencioso.** Qualquer falha de API (criar job, atribuir processo)
  vira `log.warning` e segue — o filho continua vivo, apenas sem a rede de
  segurança. O comportamento atual NUNCA pode PIORAR por causa do job: na pior
  hipótese ficamos exatamente como antes (órfão possível), nunca com o filho
  morto indevidamente.
- **Criação preguiçosa.** O job só é criado na primeira `anexar()` — runtimes
  que nunca sobem o `llama-server` não gastam um handle de job.
"""
from __future__ import annotations

import ctypes
import logging
import os
import subprocess

log = logging.getLogger("helper_financeiro.job_windows")

_EH_WINDOWS = os.name == "nt"

# Índice da classe de informação estendida e a flag que mata a árvore ao fechar
# o job (winnt.h). Só usados no ramo Windows.
_JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
_JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000


def _criar_job() -> int | None:
    """Cria um Job Object com `KILL_ON_JOB_CLOSE` e devolve o handle (int).

    Devolve `None` se qualquer passo da API do Windows falhar — o chamador
    degrada para "sem rede de segurança" (P8), nunca levanta.
    """
    from ctypes import wintypes

    class _BASIC_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", wintypes.LARGE_INTEGER),
            ("PerJobUserTimeLimit", wintypes.LARGE_INTEGER),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class _IO_COUNTERS(ctypes.Structure):
        _fields_ = [
            ("ReadOperationCount", ctypes.c_ulonglong),
            ("WriteOperationCount", ctypes.c_ulonglong),
            ("OtherOperationCount", ctypes.c_ulonglong),
            ("ReadTransferCount", ctypes.c_ulonglong),
            ("WriteTransferCount", ctypes.c_ulonglong),
            ("OtherTransferCount", ctypes.c_ulonglong),
        ]

    class _EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", _BASIC_LIMIT_INFORMATION),
            ("IoInfo", _IO_COUNTERS),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateJobObjectW.restype = wintypes.HANDLE
    k32.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
    k32.SetInformationJobObject.restype = wintypes.BOOL
    k32.SetInformationJobObject.argtypes = [
        wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD,
    ]
    k32.CloseHandle.restype = wintypes.BOOL
    k32.CloseHandle.argtypes = [wintypes.HANDLE]

    job = k32.CreateJobObjectW(None, None)
    if not job:
        log.warning("CreateJobObjectW falhou (erro %d) — sem rede de segurança do job.",
                    ctypes.get_last_error())
        return None

    info = _EXTENDED_LIMIT_INFORMATION()
    info.BasicLimitInformation.LimitFlags = _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    ok = k32.SetInformationJobObject(
        job, _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
        ctypes.byref(info), ctypes.sizeof(info),
    )
    if not ok:
        log.warning("SetInformationJobObject falhou (erro %d) — job descartado.",
                    ctypes.get_last_error())
        k32.CloseHandle(job)
        return None
    return int(job)


def _atribuir(job: int, proc: subprocess.Popen[bytes]) -> bool:
    """Atribui `proc` ao job. `True` se atribuído; `False` (com log) se falhar."""
    from ctypes import wintypes

    handle = getattr(proc, "_handle", None)
    if handle is None:  # sem handle nativo (não deveria ocorrer no Windows)
        return False
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.AssignProcessToJobObject.restype = wintypes.BOOL
    k32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    if not k32.AssignProcessToJobObject(wintypes.HANDLE(job), wintypes.HANDLE(int(handle))):
        log.warning("AssignProcessToJobObject falhou (erro %d) — filho sem rede de segurança.",
                    ctypes.get_last_error())
        return False
    return True


def _fechar(job: int) -> None:
    """Fecha o handle do job. Com `KILL_ON_JOB_CLOSE`, isto mata os processos
    ainda atribuídos AGORA — usado no encerramento explícito e nos testes; na
    morte real do sidecar é o SO que fecha o handle sozinho."""
    from ctypes import wintypes

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CloseHandle.restype = wintypes.BOOL
    k32.CloseHandle.argtypes = [wintypes.HANDLE]
    k32.CloseHandle(wintypes.HANDLE(job))


class AncoraProcessos:
    """Mantém um Job Object aberto e a ele atribui os processos-filho.

    Uma instância por `RuntimeLLM`: o job é criado na primeira `anexar()` e
    reusado nas subsequentes (reinício do `llama-server` sob demanda reatribui
    ao mesmo job). Fora do Windows a instância é inerte.
    """

    def __init__(self) -> None:
        self._job: int | None = None
        self._tentou = False

    def anexar(self, proc: subprocess.Popen[bytes]) -> bool:
        """Atribui `proc` ao job de segurança. `True` só quando de fato anexou.

        Nunca levanta: fora do Windows, ou se a criação/atribuição do job
        falhar, devolve `False` e o processo segue vivo sem a rede de segurança.
        """
        if not _EH_WINDOWS:
            return False
        if self._job is None and not self._tentou:
            self._tentou = True
            self._job = _criar_job()
        if self._job is None:
            return False
        return _atribuir(self._job, proc)

    def fechar(self) -> None:
        """Fecha o handle do job (mata os processos atribuídos, via
        `KILL_ON_JOB_CLOSE`). Idempotente e inócuo fora do Windows."""
        if self._job is not None:
            _fechar(self._job)
            self._job = None
