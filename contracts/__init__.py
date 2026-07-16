"""
Contratos de dados (Pydantic v2) — camada sem dependências internas.

`agent/` e `guardrails/` dependem daqui; nunca um do outro (PLAN §1, ADR-0004).
"""
from .schemas import (
    AnaliseAgente,
    BootInfoOut,
    CampoExtraido,
    CampoTextoExtraido,
    ClassificacaoExtrato,
    ConfigLLMEfetiva,
    ConfigLLMIn,
    ConfigLLMOut,
    DividaFato,
    EstrategiaFato,
    ExtracaoContrato,
    ExtracaoVerificada,
    FatosFinanceiros,
    ItemClassificado,
    MetricasBootOut,
    OrigemConfigLLM,
    PassoNegociacao,
    PassoRoteiroIA,
    Prioridade,
    ResultadoAnalise,
    SecaoIA,
)

__all__ = [
    "AnaliseAgente",
    "BootInfoOut",
    "CampoExtraido",
    "CampoTextoExtraido",
    "ClassificacaoExtrato",
    "ConfigLLMEfetiva",
    "ConfigLLMIn",
    "ConfigLLMOut",
    "DividaFato",
    "EstrategiaFato",
    "ExtracaoContrato",
    "ExtracaoVerificada",
    "FatosFinanceiros",
    "ItemClassificado",
    "MetricasBootOut",
    "OrigemConfigLLM",
    "PassoNegociacao",
    "PassoRoteiroIA",
    "Prioridade",
    "ResultadoAnalise",
    "SecaoIA",
]
