"""
Contratos de dados (Pydantic v2) — a fronteira entre o determinístico e o LLM.

Ver docs/SPEC.md §6. Estes modelos são a "alfândega": só passa o que está
tipado. O LLM recebe `FatosFinanceiros` e devolve `AnaliseAgente`.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


# ----------------------------- Entrada do agente (só números + tokens) --------
class DividaFato(BaseModel):
    token: str                       # "CREDOR_1" (anonimizado)
    tipo: str
    saldo_devedor: float
    taxa_mensal: float               # decimal (0.02 = 2%)
    taxa_anual: float
    parcela: float
    parcelas_restantes: int


class EstrategiaFato(BaseModel):
    metodo: str                      # "avalanche" | "bola_de_neve"
    meses: int | None
    juros_pagos: float
    quitavel: bool
    ordem: list[str]                 # lista de tokens


class FatosFinanceiros(BaseModel):
    comprometimento_renda: float
    classificacao: str
    fluxo_caixa: float
    saldo_devedor_total: float
    juros_totais_futuros: float
    dividas: list[DividaFato]
    estrategias: list[EstrategiaFato]
    tem_deficit: bool


# ----------------------------- Saída do agente (texto + estrutura) ------------
class Prioridade(BaseModel):
    ordem: int
    credor_token: str
    justificativa: str


class PassoNegociacao(BaseModel):
    credor_token: str
    abordagem: str                   # "quitacao" | "portabilidade" | "reducao"
    argumentos: list[str]
    concessoes_possiveis: list[str] = Field(default_factory=list)


class AnaliseAgente(BaseModel):
    sumario_executivo: str
    diagnostico_interpretado: str
    prioridades: list[Prioridade]
    roteiro_negociacao: list[PassoNegociacao]
    alertas_risco: list[str] = Field(default_factory=list)
    # Fração 0.0–1.0 IMPOSTA pelo contrato: modelo real (qwen2.5:0.5b) devolveu
    # 95.0 (estilo percentual) e passava — a SPEC §6.2 sempre exigiu 0–1.
    confianca: float = Field(default=0.0, ge=0.0, le=1.0)


# ----------------------------- Resultado consumido pela aplicação -------------
class ResultadoAnalise(BaseModel):
    fatos: FatosFinanceiros
    analise: AnaliseAgente | None    # None em modo degradado
    modo: str                        # "completo" | "degradado"
    guardrails_violados: list[str] = Field(default_factory=list)
    aviso_legal: str = ""
