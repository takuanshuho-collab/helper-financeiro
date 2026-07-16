"""
Contratos de dados (Pydantic v2) — a fronteira entre o determinístico e o LLM.

Ver docs/SPEC.md §6. Estes modelos são a "alfândega": só passa o que está
tipado. O LLM recebe `FatosFinanceiros` e devolve `AnaliseAgente`.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


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


# ------------------- Classificação de extrato CSV (ADR-0014) ------------------
# O modelo SÓ ROTULA: recebe os grupos numerados (nomes de estabelecimento,
# sem valores) e devolve `índice → campo do orçamento`. Nenhum número passa
# por aqui — valores e contagens vêm do parser determinístico (H1).
class ItemClassificado(BaseModel):
    indice: int                      # posição do grupo na lista enviada
    categoria: str                   # 'renda' | 'fixas' | 'variaveis'
    campo_pai: str                   # ex.: 'contas_casa'


class ClassificacaoExtrato(BaseModel):
    """Rótulos sugeridos pela LLM; itens inválidos são descartados no código."""
    itens: list[ItemClassificado] = Field(default_factory=list)


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


# --------------------------- Runtime LLM configurável (ADR-0022, T-2502) ------
# Contratos da tela "Configurações da IA" (ajustes avançados) e do painel do
# último boot — endereço estável para o sidecar E a GUI, mesmo racional do
# resto desta camada (ADR-0004): a GUI nunca reimplementa a regra da dica,
# só renderiza o que o backend já decidiu (REQ-NF-005).
OrigemConfigLLM = Literal["padrao", "tela", "env"]


class ConfigLLMEfetiva(BaseModel):
    """Valores efetivos de `ctx_size`/`gpu_offload` + a origem de cada um.

    Origem `env` quando `HF_LLAMA_FLAGS` está definida (vence tudo — a GUI
    desabilita os controles nesse caso); `tela` quando veio do `llm.json`
    (escolha salva na tela); `padrao` caso contrário.
    """
    ctx_size: int
    ctx_size_origem: OrigemConfigLLM
    gpu_offload: str | int
    gpu_offload_origem: OrigemConfigLLM


class MetricasBootOut(BaseModel):
    """Espelho de `runtime_llm.MetricasBoot` — cada campo best-effort (`None`
    quando o formato do build do llama.cpp não emitiu o dado)."""
    camadas_offload: int | None = None
    camadas_total: int | None = None
    vram_bytes: int | None = None
    ctx_efetivo: int | None = None
    dispositivo: str | None = None
    vram_total_bytes: int | None = None
    vram_livre_bytes: int | None = None


class BootInfoOut(BaseModel):
    """Espelho de `runtime_llm.BootInfo` — diagnóstico do último boot.

    `modo`: `"nunca_subiu"` | `"gpu"` | `"cpu_configurado"` | `"cpu_fallback"`.
    """
    modo: str = "nunca_subiu"
    motivo_fallback: str | None = None
    metricas: MetricasBootOut = Field(default_factory=MetricasBootOut)


class ConfigLLMOut(BaseModel):
    """Resposta de `GET /llm/config` (e de `PUT /llm/config` após persistir)."""
    config: ConfigLLMEfetiva
    boot_info: BootInfoOut
    dica: str | None = None
    dica_ctx_sugerido: int | None = None  # botão "Aplicar sugestão" (T-2503)


class ConfigLLMIn(BaseModel):
    """Corpo de `PUT /llm/config`: ambos os campos são opcionais — só valida
    (e persiste) o que vier. `ctx_size` fechado nos 3 degraus da escada;
    `gpu_offload` é `"auto"` | `"cpu"` | um inteiro de camadas (1..999)."""
    ctx_size: Literal[2048, 4096, 8192] | None = None
    gpu_offload: str | int | None = None

    # `mode="before"`: precisa rodar ANTES da coerção do Pydantic para `int`
    # (que aceitaria `True`/`False` como 1/0 — bool é subclasse de int em
    # Python — e o `isinstance(v, bool)` abaixo já veria só o inteiro coagido).
    @field_validator("gpu_offload", mode="before")
    @classmethod
    def _validar_gpu_offload(cls, v: str | int | None) -> str | int | None:
        if v is None:
            return v
        if isinstance(v, bool):  # bool é int em Python — rejeita explicitamente
            raise ValueError("gpu_offload inválido")
        if isinstance(v, str):
            if v not in ("auto", "cpu"):
                raise ValueError("gpu_offload deve ser 'auto', 'cpu' ou um inteiro (1-999)")
            return v
        if isinstance(v, int):
            if not (1 <= v <= 999):
                raise ValueError("gpu_offload inteiro deve estar entre 1 e 999")
            return v
        raise ValueError("gpu_offload inválido")
