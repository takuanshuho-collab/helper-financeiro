"""
Modelos de dados do programa.

Usamos `dataclasses` — pense nelas como "fichas cadastrais": estruturas simples
que só guardam campos e sabem calcular algumas coisas sobre si mesmas.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict

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


@dataclass
class PerfilFinanceiro:
    renda_liquida: float = 0.0
    despesas_fixas: float = 0.0
    despesas_variaveis: float = 0.0
    reserva_emergencia: float = 0.0
    saldo_fgts: float = 0.0
    dividas: list[Divida] = field(default_factory=list)

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

    def to_dict(self) -> dict:
        return asdict(self)
