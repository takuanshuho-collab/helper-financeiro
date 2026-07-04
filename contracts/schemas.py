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


# ----------------------------- Extração Code-First (Fase 2.5) -----------------
# O modelo EXTRAI variáveis de documentos (contrato/extrato); o código verifica
# e calcula. Cada campo exige a citação verbatim de onde saiu: valor sem fonte
# verificável é descartado pelo verificador (espelho do H1 na entrada).
class CampoExtraido(BaseModel):
    valor: float
    trecho_fonte: str                # citação literal do documento
    confianca: float = Field(default=0.0, ge=0.0, le=1.0)


class CampoTextoExtraido(BaseModel):
    valor: str
    trecho_fonte: str
    confianca: float = Field(default=0.0, ge=0.0, le=1.0)


class ExtracaoContrato(BaseModel):
    """Variáveis financeiras extraídas de um documento. Campos ausentes = None."""
    credor: CampoTextoExtraido | None = None
    tipo: CampoTextoExtraido | None = None       # "emprestimo", "financiamento"...
    saldo_devedor: CampoExtraido | None = None   # R$
    taxa_mensal: CampoExtraido | None = None     # FRAÇÃO (0.025 = 2,5% a.m.)
    parcela: CampoExtraido | None = None         # R$
    parcelas_restantes: CampoExtraido | None = None


class ExtracaoVerificada(BaseModel):
    """Saída do verificador determinístico (quote-check + checagem cruzada)."""
    extracao: ExtracaoContrato       # campos sem fonte verificável já removidos
    descartados: list[str] = Field(default_factory=list)      # "saldo_devedor:SEM_FONTE"
    inconsistencias: list[str] = Field(default_factory=list)  # "CRUZADA_PRICE:parcela"


# ----------------------------- Exibição local (M3) ----------------------------
# Estrutura pronta para as cascas (GUI e .docx) renderizarem a seção de IA.
# Aqui os nomes REAIS já foram restaurados: a desanonimização acontece só na
# fronteira da exibição local (REQ-SEC-003) — nada disto volta ao LLM/nuvem.
class PassoRoteiroIA(BaseModel):
    credor: str                      # nome real (restaurado do token)
    abordagem: str                   # rótulo legível ("Quitação à vista", ...)
    argumentos: list[str] = Field(default_factory=list)
    concessoes: list[str] = Field(default_factory=list)


class SecaoIA(BaseModel):
    """Seção "Análise do Agente (IA)" pronta para exibição (T-301/T-302)."""
    modo: str                        # "completo" | "degradado"
    motivos: list[str] = Field(default_factory=list)   # por que degradou (P8)
    sumario: str = ""
    diagnostico: str = ""
    prioridades: list[str] = Field(default_factory=list)   # já com "1. Credor — ..."
    roteiro: list[PassoRoteiroIA] = Field(default_factory=list)
    alertas: list[str] = Field(default_factory=list)
    confianca: float = 0.0
    aviso_legal: str = ""
