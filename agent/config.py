"""
Configuração do agente. Segredos vêm de variáveis de ambiente (REQ-SEC-002).

Nenhuma chave de API é escrita em código. O padrão é local-first (Ollama).
Os `default_factory` garantem que o ambiente é lido a CADA instanciação —
mudar HF_PROVIDER depois do import tem efeito (auditoria F-11).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass
class ConfigAgente:
    # "local" (Ollama) | "openai_compat" | "fake"
    provider: str = field(default_factory=lambda: os.getenv("HF_PROVIDER", "local"))
    base_url: str = field(
        default_factory=lambda: os.getenv("HF_BASE_URL", "http://localhost:11434/v1"))
    model: str = field(default_factory=lambda: os.getenv("HF_MODEL", "qwen2.5:14b"))
    api_key: str = field(default_factory=lambda: os.getenv("HF_API_KEY", ""))  # nunca hardcode
    # Se True, pula o LLM e entrega só o determinístico (P8).
    modo_degradado: bool = field(
        default_factory=lambda: os.getenv("HF_MODO_DEGRADADO", "0") == "1")
    timeout_s: int = field(default_factory=lambda: int(os.getenv("HF_TIMEOUT", "60")))


def carregar_config() -> ConfigAgente:
    return ConfigAgente()
