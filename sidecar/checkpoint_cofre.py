"""
2ª conexão SQLCipher dedicada ao checkpoint durável do grafo (ADR-0023, T-2601).

O checkpoint durável do LangGraph vive DENTRO do `dados.db` cifrado — nenhum byte
de estado em claro fora do cofre (REQ-SEC-001). O `SqliteSaver` tem lock interno
próprio (`self.lock`), então NÃO pode compartilhar a conexão do `Repositorio`
(dois locks independentes sobre a mesma conexão: o commit de um encerraria a
transação do outro — Plano A descartado no spike). A solução é uma SEGUNDA
conexão `sqlcipher3` ao MESMO arquivo, aberta com a MESMA DEK, com
`busy_timeout` nas duas pontas + WAL — provado no spike (grafo real gravou/leu
checkpoint no banco cifrado sob escrita concorrente do auto-save do repo, 0
`database is locked`).

Consequência do `SqliteSaver.setup()`: ele força `PRAGMA journal_mode=WAL` no
`dados.db` inteiro (hardcoded no pacote; conversão aprovada pelo mantenedor). Por
isso `fechar_saver_cofre` roda `wal_checkpoint(TRUNCATE)` antes de fechar — os
dados voltam ao arquivo principal e os satélites `-wal`/`-shm` esvaziam, deixando
o cofre íntegro para o próximo login/backup.

## Invariante anti-vazamento (C-21, REQ-SEC-001/006)

Igual ao `persistencia._conectar`: o `PRAGMA key` embute o hex da DEK; chave
errada só falha na PRIMEIRA leitura. Capturamos `Exception` (largo de propósito),
fechamos a conexão e trocamos por `ChaveInvalida` de mensagem fixa — CRIADA no
`except` mas LEVANTADA FORA dele, para o `__context__` nascer `None` e severar de
verdade o vínculo com a exceção original (que poderia ecoar a statement com o
hex). `raise ... from None` só suprimiria a impressão, não o `__context__`.
"""
from __future__ import annotations

import contextlib
import logging
import sqlite3
from pathlib import Path
from typing import cast

import sqlcipher3  # 2ª conexão ao mesmo cofre cifrado (ADR-0016 §B)
from langgraph.checkpoint.sqlite import SqliteSaver

from agent.grafo import serde_checkpoint

from .persistencia import ChaveInvalida, _blob_key

log = logging.getLogger("helper_financeiro.checkpoint_cofre")

# `busy_timeout` (ms) aplicado à conexão do saver (e à do Repositorio): sob WAL,
# uma escrita concorrente encontra a outra e ESPERA em vez de estourar
# `database is locked` na hora (ADR-0023/spike). 5 s cobre com folga a janela de
# um `put` de checkpoint contra o auto-save de 600 ms do repo (T-1102).
BUSY_TIMEOUT_MS = 5000


def abrir_saver_cofre(caminho: Path, dek: bytes) -> SqliteSaver:
    """Abre a 2ª conexão SQLCipher e devolve um `SqliteSaver` pronto (setup feito).

    Mesma DEK e mesmo `dados.db` do `Repositorio`; `check_same_thread=False`
    porque o job da análise roda em thread pool (quem serializa é o lock interno
    do próprio `SqliteSaver`). A serde é a MESMA allowlist do modo memória
    (`serde_checkpoint`), então a fronteira de tipos permitidos é única. Chave
    errada/arquivo corrompido ⇒ `ChaveInvalida` (sem vazar a chave); o chamador
    (sessão) trata como Plano C e segue sem durável.
    """
    con = sqlcipher3.connect(str(caminho), check_same_thread=False)
    # `PRAGMA key` (embute o hex), `busy_timeout` e a leitura de sanidade
    # compartilham o MESMO tratamento anti-vazamento — ver o cabeçalho do módulo.
    erro_de_chave: ChaveInvalida | None = None
    try:
        con.execute(f'PRAGMA key = "{_blob_key(dek)}"')
        con.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
        con.execute("SELECT count(*) FROM sqlite_master").fetchone()
    except Exception:  # noqa: BLE001 — a fonte do erro não importa; nada derivado da chave escapa
        con.close()
        erro_de_chave = ChaveInvalida(
            "Não foi possível abrir o cofre do checkpoint com a chave fornecida.")
    if erro_de_chave is not None:
        raise erro_de_chave
    # sqlcipher3.Connection espelha a DBAPI do sqlite3 (mesmo cast do
    # `persistencia._conectar`): o SqliteSaver só usa a interface DBAPI padrão.
    saver = SqliteSaver(cast("sqlite3.Connection", con), serde=serde_checkpoint())
    # Idempotente. Cria `checkpoints`/`writes` no cofre cifrado e força WAL no
    # `dados.db` (conversão aprovada — ver cabeçalho). Roda DEPOIS da migração
    # da ADR-0016 (que acontece antes de existir qualquer checkpoint).
    saver.setup()
    return saver


def fechar_saver_cofre(saver: SqliteSaver) -> None:
    """Consolida o WAL (`wal_checkpoint(TRUNCATE)`) e fecha a conexão do saver.

    Best-effort: rodado no bloqueio/fechamento do cofre, ANTES de zerar a DEK.
    Trazer os dados do `-wal` de volta ao arquivo principal deixa o cofre num
    estado limpo (sem satélites pendurados) para o próximo login/backup. Falha
    aqui não é fatal — pior caso, o `-wal` é consolidado no próximo `open`.
    """
    con = getattr(saver, "conn", None)
    if con is None:
        return
    try:
        con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    except Exception:  # noqa: BLE001 — consolidação do WAL é best-effort
        log.warning("wal_checkpoint(TRUNCATE) do checkpoint falhou no "
                    "fechamento (best-effort, ADR-0023).")
    with contextlib.suppress(Exception):  # fechar conexão já em erro não derruba o bloqueio
        con.close()
