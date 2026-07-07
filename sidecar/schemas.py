"""
Contrato de dados do sidecar (REQ-NF-005).

Modelos Pydantic da fronteira HTTP. O front envia o orçamento por categoria e a
lista de dívidas; o roll-up dos agregados acontece no `core` (ADR-0008), nunca
aqui. Nenhum cálculo financeiro vive neste módulo.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class DividaIn(BaseModel):
    credor: str
    tipo: str
    saldo_devedor: float = 0.0
    taxa_mensal: float = 0.0
    parcela: float = 0.0
    parcelas_restantes: int = 0
    garantia: str = ""
    em_atraso: bool = False
    dias_atraso: int = 0
    cet_anual: float | None = None


class RendaIn(BaseModel):
    salario_liquido: float = 0.0
    renda_extra: float = 0.0
    outras_rendas: float = 0.0


class FixasIn(BaseModel):
    moradia: float = 0.0
    contas_casa: float = 0.0
    transporte: float = 0.0
    saude: float = 0.0
    educacao: float = 0.0
    assinaturas: float = 0.0
    outras_fixas: float = 0.0


class VariaveisIn(BaseModel):
    mercado: float = 0.0
    lazer: float = 0.0
    vestuario: float = 0.0
    imprevistos: float = 0.0
    outras_variaveis: float = 0.0


class PerfilIn(BaseModel):
    """Orçamento por categoria + dívidas — a entrada do diagnóstico."""

    renda: RendaIn = Field(default_factory=RendaIn)
    fixas: FixasIn = Field(default_factory=FixasIn)
    variaveis: VariaveisIn = Field(default_factory=VariaveisIn)
    reserva_emergencia: float = 0.0
    saldo_fgts: float = 0.0
    dividas: list[DividaIn] = Field(default_factory=list)


class EstrategiasIn(BaseModel):
    """Perfil + pagamento extra mensal para simular a quitação."""

    perfil: PerfilIn
    extra: float = 0.0


class AnaliseIn(BaseModel):
    """Perfil + parâmetros da tela Análise (REQ-F-015).

    `extra` alimenta a simulação de quitação; `taxa_alvo` (fração mensal,
    0.018 = 1,8% a.m.) filtra as oportunidades de portabilidade.
    """

    perfil: PerfilIn
    extra: float = 0.0
    taxa_alvo: float = 0.018


class AnaliseIaIn(BaseModel):
    """Disparo do job assíncrono da análise sênior (IA, sob guardrails)."""

    perfil: PerfilIn
    extra: float = 0.0


class ExportarPlanilhaIn(BaseModel):
    """Exportação .xlsx: o caminho vem do diálogo de salvar do Electron."""

    perfil: PerfilIn
    caminho: str
    extra: float = 0.0
    taxa_alvo: float = 0.018


class ExportarRelatorioIn(ExportarPlanilhaIn):
    """Exportação .docx; `secao_ia` é a última análise sênior (opcional)."""

    nome_usuario: str = ""
    secao_ia: dict[str, Any] | None = None


class CartaIn(BaseModel):
    """Carta ao credor (REQ-F-016): dívida + tipo + campos contextuais.

    `valor_proposto` só vale para quitação; `banco_concorrente`/`taxa_
    concorrente_mensal` (fração, 0.018 = 1,8% a.m.) só para portabilidade.
    Nome/CPF ficam na loopback e no arquivo local — nunca vão à nuvem (H2).
    """

    divida: DividaIn
    tipo: str = "quitacao"  # "quitacao" | "portabilidade" | "reducao"
    valor_proposto: float | None = None
    banco_concorrente: str = ""
    taxa_concorrente_mensal: float | None = None
    nome_usuario: str = ""
    cpf: str = ""
    contrato: str = ""


class ExportarCartaIn(CartaIn):
    """Exportação da carta .docx no caminho escolhido no diálogo do Electron."""

    caminho: str


class ContratoIn(BaseModel):
    """PDF de contrato (base64) para extração LOCAL dos campos (REQ-F-014).

    O binário viaja só na loopback; o sidecar o decodifica em memória, extrai o
    texto e roda a extração local — nada é persistido em disco nem vai à nuvem.
    """

    pdf_base64: str
    nome: str = ""


class ConfirmarContratoIn(BaseModel):
    """Retomada do grafo de extração pausado (interrupt→resume, ADR-0006)."""

    thread_id: str
    confirmacao: dict[str, Any] = Field(default_factory=dict)
