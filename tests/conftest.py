"""Fixtures do harness (casos-ouro). Ver docs/HARNESS §2."""
import pytest

from agent.cache import cache_global
from core.models import Divida, PerfilFinanceiro


@pytest.fixture(autouse=True)
def _cache_limpo():
    """Isola os testes do cache de análises (T-205): sem estado entre eles."""
    cache_global.limpar()
    yield
    cache_global.limpar()


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
def perfil_saudavel():
    return PerfilFinanceiro(
        renda_liquida=8000, despesas_fixas=3000, despesas_variaveis=1200,
        reserva_emergencia=15000, saldo_fgts=20000,
        dividas=[
            Divida("Financiamento Casa", "Financiamento", 120000, 0.009, 1100, 180),
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
