"""
Telemetria LangSmith LOCAL e opt-in (T-1002, REQ-SEC-004).

O LangGraph/LangChain liga o tracing por variáveis de ambiente
(`LANGSMITH_TRACING`), e o destino padrão é a NUVEM da LangSmith — um
`LANGSMITH_TRACING=true` esquecido no ambiente mandaria prompts e traces para
terceiros. Este módulo inverte o padrão: o tracing só liga com opt-in
explícito (`HF_TELEMETRIA=1`) E endpoint self-hosted em loopback
(`LANGSMITH_ENDPOINT`); em QUALQUER outra combinação as variáveis de tracing
são forçadas para "false" antes de o grafo carregar.

Mesmo com os fatos anonimizados (CREDOR_n, REQ-GRD-002), traces carregam
prompts/respostas inteiros — nada disso deve sair da máquina (H2).
"""
from __future__ import annotations

import logging
import os
from collections.abc import MutableMapping
from urllib.parse import urlparse

log = logging.getLogger("helper_financeiro.telemetria")

VAR_OPTIN = "HF_TELEMETRIA"           # "1" liga (opt-in explícito)
VAR_ENDPOINT = "LANGSMITH_ENDPOINT"   # obrigatório: self-hosted em loopback

# As duas gerações da flag de tracing (LangSmith atual e LangChain legado).
VARS_TRACING = ("LANGSMITH_TRACING", "LANGCHAIN_TRACING_V2")


def _endpoint_local(url: str) -> bool:
    """Mesma invariante do H2 (ADR-0010): local é o ENDPOINT, não o nome."""
    host = (urlparse(url).hostname or "").lower()
    return host in {"localhost", "::1"} or host.startswith("127.")


def configurar_telemetria(
    ambiente: MutableMapping[str, str] = os.environ,
) -> bool:
    """Aplica a política de telemetria no ambiente. Devolve True se ligou.

    Liga somente com `HF_TELEMETRIA=1` E `LANGSMITH_ENDPOINT` em loopback.
    Nos demais casos (sem opt-in, endpoint ausente ou remoto), força as
    flags de tracing para "false" — inclusive sobrescrevendo um
    `LANGSMITH_TRACING=true` pré-existente no ambiente.
    """
    optin = ambiente.get(VAR_OPTIN, "0") == "1"
    endpoint = ambiente.get(VAR_ENDPOINT, "")

    if optin and endpoint and _endpoint_local(endpoint):
        for var in VARS_TRACING:
            ambiente[var] = "true"
        log.info("Telemetria LangSmith LOCAL ligada (endpoint %s).", endpoint)
        return True

    if optin:
        log.warning(
            "HF_TELEMETRIA=1 ignorado: LANGSMITH_ENDPOINT %r não é loopback "
            "— telemetria DESLIGADA (REQ-SEC-004/H2).",
            endpoint,
        )
    for var in VARS_TRACING:
        ambiente[var] = "false"
    return False
