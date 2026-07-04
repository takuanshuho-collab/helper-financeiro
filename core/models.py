"""
Modelos de dados do programa.

Usamos `dataclasses` — pense nelas como "fichas cadastrais": estruturas simples
que só guardam campos e sabem calcular algumas coisas sobre si mesmas.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

# Tipos de dívida reconhecidos. O tipo influencia a estratégia:
# consignado costuma ser barato; cartão/cheque especial, caros.
TIPOS_DIVIDA = [
    "CDC (Crédito Direto ao Consumidor)",
    "Consignado",
    "Cartão de crédito",
    "Cheque especial",
    "Financiamento",
    "Empréstimo pessoal",
    "Outro",
]


@dataclass
class Divida:
    credor: str
    tipo: str
    saldo_devedor: float          # quanto ainda se deve (principal + juros futuros embutidos)
    taxa_mensal: float            # decimal, ex.: 0.02 para 2% a.m.
    parcela: float                # valor da parcela mensal
    parcelas_restantes: int
    garantia: str = ""            # ex.: "alienação fiduciária do veículo", "folha de pagamento"
    em_atraso: bool = False
    dias_atraso: int = 0
    cet_anual: float | None = None  # se conhecido a partir do contrato

    @property
    def taxa_anual(self) -> float:
        """Converte a taxa mensal para anual equivalente (juros compostos)."""
        return (1 + self.taxa_mensal) ** 12 - 1

    @property
    def custo_total_restante(self) -> float:
        """Total que ainda será pago até o fim (soma das parcelas restantes)."""
        return self.parcela * self.parcelas_restantes

    @property
    def juros_restantes(self) -> float:
        """Parte das parcelas futuras que é juro (gordura), não amortização."""
        return max(self.custo_total_restante - self.saldo_devedor, 0.0)


# --- Orçamento detalhado (ADR-0008, REQ-F-006) -----------------------------
# O usuário informa POR CATEGORIA; os agregados do PerfilFinanceiro são sempre
# derivados por soma (roll-up determinístico) — nunca digitados em separado.


@dataclass
class ComposicaoRenda:
    """Renda líquida mensal, aberta por origem."""

    salario_liquido: float = 0.0   # salário/benefício principal, já descontado
    renda_extra: float = 0.0       # bicos, freelas, trabalho autônomo
    outras_rendas: float = 0.0     # aluguel recebido, pensão, auxílios

    @property
    def total(self) -> float:
        return self.salario_liquido + self.renda_extra + self.outras_rendas


@dataclass
class DespesasFixas:
    """Despesas que se repetem todo mês com valor previsível."""

    moradia: float = 0.0           # aluguel, condomínio, IPTU mensalizado
    contas_casa: float = 0.0       # luz, água, gás, internet, telefone
    transporte: float = 0.0        # combustível, transporte público, seguro
    saude: float = 0.0             # plano de saúde, remédios contínuos
    educacao: float = 0.0          # escola, faculdade, cursos
    assinaturas: float = 0.0       # streaming, apps, academia
    outras_fixas: float = 0.0

    @property
    def total(self) -> float:
        return (self.moradia + self.contas_casa + self.transporte + self.saude
                + self.educacao + self.assinaturas + self.outras_fixas)


@dataclass
class DespesasVariaveis:
    """Despesas que flutuam mês a mês (use a média dos últimos meses)."""

    mercado: float = 0.0           # supermercado, feira, padaria
    lazer: float = 0.0             # restaurantes, delivery, passeios
    vestuario: float = 0.0         # roupas, calçados, cuidados pessoais
    imprevistos: float = 0.0       # consertos, presentes, eventualidades
    outras_variaveis: float = 0.0

    @property
    def total(self) -> float:
        return (self.mercado + self.lazer + self.vestuario
                + self.imprevistos + self.outras_variaveis)


@dataclass
class PerfilFinanceiro:
    renda_liquida: float = 0.0
    despesas_fixas: float = 0.0
    despesas_variaveis: float = 0.0
    reserva_emergencia: float = 0.0
    saldo_fgts: float = 0.0
    dividas: list[Divida] = field(default_factory=list)
    # Detalhamento opcional de origem (preenchido por `com_orcamento`); os
    # campos agregados acima continuam sendo a fonte usada nos cálculos.
    renda_detalhada: ComposicaoRenda | None = None
    fixas_detalhadas: DespesasFixas | None = None
    variaveis_detalhadas: DespesasVariaveis | None = None

    @classmethod
    def com_orcamento(
        cls,
        renda: ComposicaoRenda,
        fixas: DespesasFixas,
        variaveis: DespesasVariaveis,
        reserva_emergencia: float = 0.0,
        saldo_fgts: float = 0.0,
        dividas: list[Divida] | None = None,
    ) -> PerfilFinanceiro:
        """Monta o perfil a partir do orçamento por categoria (roll-up)."""
        return cls(
            renda_liquida=renda.total,
            despesas_fixas=fixas.total,
            despesas_variaveis=variaveis.total,
            reserva_emergencia=reserva_emergencia,
            saldo_fgts=saldo_fgts,
            dividas=dividas or [],
            renda_detalhada=renda,
            fixas_detalhadas=fixas,
            variaveis_detalhadas=variaveis,
        )

    # --- Totais e indicadores ---
    @property
    def total_parcelas(self) -> float:
        return sum(d.parcela for d in self.dividas)

    @property
    def saldo_devedor_total(self) -> float:
        return sum(d.saldo_devedor for d in self.dividas)

    @property
    def despesas_totais(self) -> float:
        return self.despesas_fixas + self.despesas_variaveis

    @property
    def comprometimento_renda(self) -> float:
        """Fração da renda comprometida com parcelas de dívida (0.0 a 1.0+)."""
        if self.renda_liquida <= 0:
            return 0.0
        return self.total_parcelas / self.renda_liquida

    @property
    def fluxo_caixa(self) -> float:
        """Sobra (ou déficit) mensal após despesas e parcelas."""
        return self.renda_liquida - self.despesas_totais - self.total_parcelas

    @property
    def meses_reserva(self) -> float | None:
        """Quantos meses de despesas totais a reserva cobre (REQ-F-007).

        Retorna None quando as despesas totais são zero — sem despesas
        informadas, a cobertura em meses não tem significado.
        """
        if self.despesas_totais <= 0:
            return None
        return self.reserva_emergencia / self.despesas_totais

    def to_dict(self) -> dict:
        return asdict(self)
