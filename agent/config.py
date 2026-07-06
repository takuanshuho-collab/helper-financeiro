"""
Configuração do agente. Segredos vêm de variáveis de ambiente (REQ-SEC-002).

Nenhuma chave de API é escrita em código. O padrão é local-first (Ollama).
Os `default_factory` garantem que o ambiente é lido a CADA instanciação —
mudar HF_PROVIDER depois do import tem efeito (auditoria F-11).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from urllib.parse import urlparse


@dataclass
class ConfigAgente:
    # "local" (Ollama) | "openai_compat" (nuvem OU servidor local, ex.: LM Studio)
    # | "fake". O que separa local de nuvem é o ENDPOINT (loopback), não o nome —
    # ver `endpoint_local` e ADR-0010.
    provider: str = field(default_factory=lambda: os.getenv("HF_PROVIDER", "local"))
    base_url: str = field(
        default_factory=lambda: os.getenv("HF_BASE_URL", "http://localhost:11434/v1"))
    # Padrão dimensionado para a GPU-alvo (4 GB de VRAM): 3B roda 100% na GPU.
    # ATENÇÃO à licença (ADR-0006): qwen2.5:3b é Qwen Research License (não
    # comercial); para uso comercial, HF_MODEL=qwen3:4b (Apache 2.0).
    model: str = field(default_factory=lambda: os.getenv("HF_MODEL", "qwen2.5:3b"))
    api_key: str = field(default_factory=lambda: os.getenv("HF_API_KEY", ""))  # nunca hardcode
    # Se True, pula o LLM e entrega só o determinístico (P8).
    modo_degradado: bool = field(
        default_factory=lambda: os.getenv("HF_MODO_DEGRADADO", "0") == "1")
    timeout_s: int = field(default_factory=lambda: int(os.getenv("HF_TIMEOUT", "60")))
    # Cache em memória de análises aprovadas (T-205): mesma entrada → sem nova
    # chamada ao LLM. Desligue com HF_CACHE=0.
    cache: bool = field(default_factory=lambda: os.getenv("HF_CACHE", "1") == "1")

    @property
    def endpoint_local(self) -> bool:
        """True se `base_url` aponta para a própria máquina (loopback).

        É a invariante real do H2 (ADR-0010): o documento/os fatos só saem da
        máquina quando o endpoint é remoto. Um LM Studio em `localhost:1234` é
        local; `https://api.openai.com` é nuvem — independente do nome do
        provider.
        """
        host = (urlparse(self.base_url).hostname or "").lower()
        return host in {"localhost", "::1"} or host.startswith("127.")


def carregar_config() -> ConfigAgente:
    return ConfigAgente()
