"""Config lê o ambiente em tempo de execução, não no import (auditoria F-11)."""
from agent.config import carregar_config


def test_env_lida_a_cada_carregamento(monkeypatch):
    monkeypatch.setenv("HF_PROVIDER", "openai_compat")
    monkeypatch.setenv("HF_MODEL", "modelo-teste")
    cfg = carregar_config()
    assert cfg.provider == "openai_compat"
    assert cfg.model == "modelo-teste"

    monkeypatch.setenv("HF_PROVIDER", "local")
    assert carregar_config().provider == "local"   # mudança pós-import tem efeito


def test_defaults_local_first(monkeypatch):
    for var in ("HF_PROVIDER", "HF_BASE_URL", "HF_MODEL", "HF_API_KEY",
                "HF_MODO_DEGRADADO", "HF_TIMEOUT"):
        monkeypatch.delenv(var, raising=False)
    cfg = carregar_config()
    assert cfg.provider == "local"                 # LGPD: local-first por padrão
    assert "localhost" in cfg.base_url
    assert cfg.api_key == ""                       # nunca chave hardcoded
    assert cfg.modo_degradado is False


def test_modo_degradado_por_env(monkeypatch):
    monkeypatch.setenv("HF_MODO_DEGRADADO", "1")
    assert carregar_config().modo_degradado is True


def test_endpoint_local_distingue_loopback_de_nuvem():
    """A invariante do H2 é o endpoint (loopback), não o nome do provider (ADR-0010)."""
    from agent.config import ConfigAgente

    local = ("http://localhost:11434/v1", "http://127.0.0.1:1234/v1",
             "http://127.0.0.5:8080")
    for url in local:
        assert ConfigAgente(base_url=url).endpoint_local is True

    remoto = ("https://api.openai.com/v1", "http://10.0.0.9:1234/v1",
              "https://meu-servidor.com/v1")
    for url in remoto:
        assert ConfigAgente(base_url=url).endpoint_local is False
