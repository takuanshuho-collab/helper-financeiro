"""
Persistência local do estado do usuário (ADR-0012, REQ-F-018).

Um único arquivo SQLite gerido pelo sidecar — a GUI nunca toca o banco. O
arquivo fica no perfil do usuário (`%APPDATA%\\HelperFinanceiro\\dados.db`),
fora do repositório e fora de logs (REQ-SEC-001); o mapa de anonimização
continua existindo apenas em memória (REQ-SEC-003) — nada daqui vai ao LLM.

`sqlite3` da stdlib, conexão única + `threading.Lock` (o FastAPI atende em
múltiplas threads), mesmo padrão do `_JOBS_IA`. A tabela `esquema` versiona o
banco para migrações futuras; `rubrica` já nasce com a coluna `mes`
(NULL = orçamento vivo) para o histórico mensal entrar sem migração dolorosa.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path

VERSAO_ESQUEMA = 1

# Seções do orçamento que aceitam rubricas (ADR-0012: saldos ficam de fora).
CATEGORIAS_RUBRICA = ("renda", "fixas", "variaveis")

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

    def __init__(self, caminho: Path | None = None) -> None:
        self._caminho = caminho if caminho is not None else caminho_banco()
        self._caminho.parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False: o lock (e não o sqlite) serializa o acesso.
        self._conn = sqlite3.connect(str(self._caminho), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
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

    # -------------------------------------------------------------- ciclo
    def fechar(self) -> None:
        with self._lock:
            self._conn.close()
