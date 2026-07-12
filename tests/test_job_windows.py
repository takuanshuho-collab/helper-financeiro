"""
Job Object do Windows como rede de segurança contra `llama-server` órfão
(C-02, ADR-0017 §M19) — Gate A (offline, sem binário real).

O teste que FALHARIA ANTES da correção é `test_fechar_job_mata_processo_anexado`:
sem a ancoragem ao Job Object, fechar o handle do "pai" não afeta o filho e ele
sobrevive (exatamente o órfão do T-1704). O par de controle
`test_sem_job_processo_sobrevive` prova que quem mata é o job — não o simples
fim do teste.

Específico do Windows (`JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`); pulado nos demais
SOs, onde `AncoraProcessos` é um no-op deliberado. O que só o smoke manual do
pacote cobre (T-1911): a morte por `TerminateProcess` do sidecar REAL fechando o
handle sozinho — aqui fechamos o handle explicitamente com `fechar()`, que
exercita o MESMO mecanismo do SO (KILL_ON_JOB_CLOSE) que a morte dura dispara.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time

import pytest

from sidecar.job_windows import AncoraProcessos

pytestmark = pytest.mark.skipif(
    os.name != "nt", reason="Job Object é específico do Windows"
)


def _dummy() -> subprocess.Popen[bytes]:
    """Processo que sobrevive por conta própria (dorme 30 s) — só morre se algo
    de fora o matar. Análogo ao `cmd /c pause` do brief, mas portável e sem TTY."""
    return subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])


def _vivo(proc: subprocess.Popen[bytes]) -> bool:
    return proc.poll() is None


def test_fechar_job_mata_processo_anexado() -> None:
    """Anexado ao job, fechar o handle (o que o SO faz na morte do sidecar)
    aniquila o filho — a rede de segurança que elimina o órfão."""
    ancora = AncoraProcessos()
    proc = _dummy()
    try:
        assert ancora.anexar(proc) is True
        assert _vivo(proc)
        ancora.fechar()  # simula o SO fechando o handle na morte do sidecar
        proc.wait(timeout=5)
        assert not _vivo(proc)
    finally:
        if _vivo(proc):
            proc.kill()
            proc.wait()


def test_sem_job_processo_sobrevive() -> None:
    """Controle: um processo NÃO anexado sobrevive a `fechar()` — prova que a
    morte no teste anterior vem do job, não do fim do processo de teste. É o
    comportamento de ANTES da correção (órfão)."""
    proc = _dummy()
    try:
        ancora = AncoraProcessos()  # nunca anexa `proc`
        ancora.fechar()
        time.sleep(0.5)
        assert _vivo(proc)
    finally:
        proc.kill()
        proc.wait()


def test_anexar_e_idempotente_reusa_o_mesmo_job() -> None:
    """Dois processos anexados à MESMA âncora caem no mesmo job; fechar mata os
    dois (reinício do llama-server reatribui ao job existente)."""
    ancora = AncoraProcessos()
    p1, p2 = _dummy(), _dummy()
    try:
        assert ancora.anexar(p1) is True
        assert ancora.anexar(p2) is True
        ancora.fechar()
        p1.wait(timeout=5)
        p2.wait(timeout=5)
        assert not _vivo(p1) and not _vivo(p2)
    finally:
        for p in (p1, p2):
            if _vivo(p):
                p.kill()
                p.wait()
