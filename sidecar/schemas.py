"""
Contrato de dados do sidecar (REQ-NF-005).

Modelos Pydantic da fronteira HTTP. O front envia o orçamento por categoria e a
lista de dívidas; o roll-up dos agregados acontece no `core` (ADR-0008), nunca
aqui. Nenhum cálculo financeiro vive neste módulo.
"""
from __future__ import annotations

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
