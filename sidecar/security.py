"""
Autenticação do sidecar por token de sessão (REQ-SEC-004).

O launcher gera um token aleatório por execução e o publica apenas para o
processo pai (Electron `main`) via handshake no stdout. Todo request de negócio
precisa apresentá-lo no cabeçalho `X-HF-Token`; sem token válido → 401. O token
vive só na memória do processo — nunca é escrito em disco.
"""
from __future__ import annotations

import os

from fastapi import Header, HTTPException, status

VAR_TOKEN = "HF_SIDECAR_TOKEN"


def exigir_token(x_hf_token: str | None = Header(default=None)) -> None:
    esperado = os.environ.get(VAR_TOKEN)
    if not esperado or x_hf_token != esperado:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="token de sessao ausente ou invalido",
        )
