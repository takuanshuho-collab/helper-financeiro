"""Telemetria local opt-in (T-1002, REQ-SEC-004): tracing nunca vaza p/ nuvem."""
from agent.telemetria import (
    VAR_ENDPOINT,
    VAR_OPTIN,
    VARS_TRACING,
    configurar_telemetria,
)


def test_sem_optin_forca_tracing_desligado():
    """Caso de segurança central: LANGSMITH_TRACING=true perdido no ambiente
    é SOBRESCRITO para false quando não há opt-in explícito."""
    env = {"LANGSMITH_TRACING": "true", "LANGCHAIN_TRACING_V2": "true"}
    assert configurar_telemetria(env) is False
    assert all(env[v] == "false" for v in VARS_TRACING)


def test_optin_com_endpoint_loopback_liga():
    env = {VAR_OPTIN: "1", VAR_ENDPOINT: "http://127.0.0.1:1984"}
    assert configurar_telemetria(env) is True
    assert all(env[v] == "true" for v in VARS_TRACING)


def test_optin_com_endpoint_remoto_e_ignorado():
    """Opt-in não basta: endpoint de nuvem (api.smith.langchain.com) desliga."""
    env = {VAR_OPTIN: "1", VAR_ENDPOINT: "https://api.smith.langchain.com"}
    assert configurar_telemetria(env) is False
    assert all(env[v] == "false" for v in VARS_TRACING)


def test_optin_sem_endpoint_e_ignorado():
    """Sem endpoint explícito, o default do SDK seria a nuvem — desliga."""
    env = {VAR_OPTIN: "1"}
    assert configurar_telemetria(env) is False
    assert all(env[v] == "false" for v in VARS_TRACING)


def test_localhost_e_ipv6_loopback_contam_como_local():
    for endpoint in ("http://localhost:1984", "http://[::1]:1984"):
        env = {VAR_OPTIN: "1", VAR_ENDPOINT: endpoint}
        assert configurar_telemetria(env) is True, endpoint
