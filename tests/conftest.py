"""Fixtures do harness (casos-ouro). Ver docs/HARNESS §2."""
import pytest

from core.models import Divida, PerfilFinanceiro


@pytest.fixture
def perfil_atencao():
    return PerfilFinanceiro(
        renda_liquida=5000, despesas_fixas=2200, despesas_variaveis=800,
        reserva_emergencia=0, saldo_fgts=3000,
        dividas=[
            Divida("Cartão Banco A", "Cartão de crédito", 8000, 0.12, 900, 12),
            Divida("CDC Veículo", "CDC (Crédito Direto ao Consumidor)", 20000, 0.025, 700, 36),
            Divida("Consignado Servidor", "Consignado", 6000, 0.018, 350, 20),
        ],
    )


@pytest.fixture
def perfil_critico():
    return PerfilFinanceiro(
        renda_liquida=3000, despesas_fixas=2000, despesas_variaveis=900,
        dividas=[
            Divida("Cheque Especial", "Cheque especial", 5000, 0.08, 1200, 6),
            Divida("Cartão X", "Cartão de crédito", 9000, 0.14, 1100, 10),
        ],
    )
