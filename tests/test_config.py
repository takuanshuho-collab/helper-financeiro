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
