"""
Contratos de dados (Pydantic v2) — camada sem dependências internas.

`agent/` e `guardrails/` dependem daqui; nunca um do outro (PLAN §1, ADR-0004).
"""
from .schemas import (
    AnaliseAgente,
    CampoExtraido,
    CampoTextoExtraido,
    ClassificacaoExtrato,
    DividaFato,
    EstrategiaFato,
    ExtracaoContrato,
    ExtracaoVerificada,
    FatosFinanceiros,
    ItemClassificado,
    PassoNegociacao,
    PassoRoteiroIA,
    Prioridade,
    ResultadoAnalise,
    SecaoIA,
)

__all__ = [
    "AnaliseAgente",
    "CampoExtraido",
    "CampoTextoExtraido",
    "ClassificacaoExtrato",
    "DividaFato",
    "EstrategiaFato",
    "ExtracaoContrato",
    "ExtracaoVerificada",
    "FatosFinanceiros",
    "ItemClassificado",
    "PassoNegociacao",
    "PassoRoteiroIA",
    "Prioridade",
    "ResultadoAnalise",
    "SecaoIA",
]
