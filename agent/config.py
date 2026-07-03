"""
Configuração do agente. Segredos vêm de variáveis de ambiente (REQ-SEC-002).

Nenhuma chave de API é escrita em código. O padrão é local-first (Ollama).
"""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class ConfigAgente:
    # "local" (Ollama) | "openai_compat" | "fake"
    provider: str = os.getenv("HF_PROVIDER", "local")
    base_url: str = os.getenv("HF_BASE_URL", "http://localhost:11434/v1")
    model: str = os.getenv("HF_MODEL", "qwen2.5:14b")
    api_key: str = os.getenv("HF_API_KEY", "")  # nunca hardcode
    # Se True, pula o LLM e entrega só o determinístico (P8).
    modo_degradado: bool = os.getenv("HF_MODO_DEGRADADO", "0") == "1"
    timeout_s: int = int(os.getenv("HF_TIMEOUT", "60"))


def carregar_config() -> ConfigAgente:
    return ConfigAgente()
