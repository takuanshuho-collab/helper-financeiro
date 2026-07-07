"""
Launcher do sidecar (REQ-SEC-004).

Reserva uma porta efêmera em `127.0.0.1`, gera o token de sessão, publica o
handshake `{"port": ..., "token": ...}` numa única linha do stdout (para o
processo pai Electron `main` ler) e sobe o uvicorn. Rodar com:

    python -m sidecar
"""
from __future__ import annotations

import json
import os
import secrets
import socket
import sys

import uvicorn

from agent.telemetria import configurar_telemetria

from .app import app
from .security import VAR_TOKEN


def _porta_efemera() -> int:
    """Pergunta ao SO uma porta livre em loopback e a devolve."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def main() -> None:
    # Antes de qualquer import do grafo processar env: tracing só liga com
    # opt-in + endpoint loopback; senão é forçado a "false" (REQ-SEC-004).
    configurar_telemetria()

    port = _porta_efemera()
    token = secrets.token_urlsafe(32)
    os.environ[VAR_TOKEN] = token

    # Handshake para o processo pai: uma linha JSON, com flush imediato.
    sys.stdout.write(json.dumps({"port": port, "token": token}) + "\n")
    sys.stdout.flush()

    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
