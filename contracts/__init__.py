"""
Contratos de dados (Pydantic v2) — camada sem dependências internas.

`agent/` e `guardrails/` dependem daqui; nunca um do outro (PLAN §1, ADR-0004).
"""
from .schemas import (
    AnaliseAgente,
    DividaFato,
    EstrategiaFato,
    FatosFinanceiros,
    PassoNegociacao,
    Prioridade,
    ResultadoAnalise,
)

__all__ = [
    "AnaliseAgente",
    "DividaFato",
    "EstrategiaFato",
    "FatosFinanceiros",
    "PassoNegociacao",
    "Prioridade",
    "ResultadoAnalise",
]
