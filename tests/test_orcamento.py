"""
Testes do orçamento detalhado do perfil (M5 / ADR-0008).

Cobre REQ-F-006 (itemização por categoria com roll-up determinístico) e
REQ-F-007 (cobertura da reserva de emergência em meses de despesas).
"""
from hypothesis import given
from hypothesis import strategies as st

from core.models import (
    ComposicaoRenda,
    DespesasFixas,
    DespesasVariaveis,
    Divida,
    PerfilFinanceiro,
)

VALOR = st.floats(min_value=0, max_value=1_000_000, allow_nan=False,
                  allow_infinity=False)


def _divida(parcela: float = 500.0) -> Divida:
    return Divida(credor="Banco A", tipo="Cartão de crédito",
                  saldo_devedor=5_000.0, taxa_mensal=0.12,
                  parcela=parcela, parcelas_restantes=10)


def test_totais_das_categorias():
    renda = ComposicaoRenda(salario_liquido=3_800.0, renda_extra=550.0,
                            outras_rendas=200.0)
    fixas = DespesasFixas(moradia=1_200.0, contas_casa=460.0, transporte=350.0,
                          saude=300.0, educacao=250.0, assinaturas=90.0,
                          outras_fixas=50.0)
    variaveis = DespesasVariaveis(mercado=700.0, lazer=200.0, vestuario=100.0,
                                  imprevistos=80.0, outras_variaveis=20.0)
    assert renda.total == 4_550.0
    assert fixas.total == 2_700.0
    assert variaveis.total == 1_100.0


def test_com_orcamento_faz_rollup_dos_agregados():
    perfil = PerfilFinanceiro.com_orcamento(
        renda=ComposicaoRenda(salario_liquido=4_000.0, renda_extra=350.0),
        fixas=DespesasFixas(moradia=1_500.0, contas_casa=400.0),
        variaveis=DespesasVariaveis(mercado=800.0, lazer=150.0),
        reserva_emergencia=2_000.0,
        saldo_fgts=6_000.0,
        dividas=[_divida()],
    )
    assert perfil.renda_liquida == 4_350.0
    assert perfil.despesas_fixas == 1_900.0
    assert perfil.despesas_variaveis == 950.0
    assert perfil.despesas_totais == 2_850.0
    assert perfil.reserva_emergencia == 2_000.0
    assert perfil.saldo_fgts == 6_000.0
    # Indicadores existentes continuam funcionando sobre os agregados.
    assert perfil.fluxo_caixa == 4_350.0 - 2_850.0 - 500.0
    assert perfil.renda_detalhada is not None
    assert perfil.renda_detalhada.salario_liquido == 4_000.0


def test_com_orcamento_sem_dividas_usa_lista_vazia():
    perfil = PerfilFinanceiro.com_orcamento(
        renda=ComposicaoRenda(), fixas=DespesasFixas(),
        variaveis=DespesasVariaveis())
    assert perfil.dividas == []
    assert perfil.renda_liquida == 0.0


def test_meses_reserva_cobre_despesas():
    perfil = PerfilFinanceiro(despesas_fixas=1_500.0, despesas_variaveis=500.0,
                              reserva_emergencia=6_000.0)
    assert perfil.meses_reserva == 3.0


def test_meses_reserva_sem_despesas_e_none():
    assert PerfilFinanceiro(reserva_emergencia=1_000.0).meses_reserva is None


def test_meses_reserva_zerada_e_zero():
    perfil = PerfilFinanceiro(despesas_fixas=1_000.0, reserva_emergencia=0.0)
    assert perfil.meses_reserva == 0.0


def test_to_dict_inclui_detalhamento():
    perfil = PerfilFinanceiro.com_orcamento(
        renda=ComposicaoRenda(salario_liquido=3_000.0),
        fixas=DespesasFixas(moradia=900.0),
        variaveis=DespesasVariaveis(mercado=600.0))
    dump = perfil.to_dict()
    assert dump["renda_detalhada"]["salario_liquido"] == 3_000.0
    assert dump["fixas_detalhadas"]["moradia"] == 900.0
    assert dump["variaveis_detalhadas"]["mercado"] == 600.0


def test_perfil_sem_detalhamento_continua_compativel():
    """Retrocompatibilidade: construção direta pelos agregados segue valendo."""
    perfil = PerfilFinanceiro(renda_liquida=4_000.0, despesas_fixas=2_000.0)
    assert perfil.renda_detalhada is None
    assert perfil.to_dict()["renda_detalhada"] is None


@given(salario=VALOR, extra=VALOR, outras=VALOR)
def test_propriedade_rollup_renda_e_soma_exata(salario, extra, outras):
    renda = ComposicaoRenda(salario_liquido=salario, renda_extra=extra,
                            outras_rendas=outras)
    perfil = PerfilFinanceiro.com_orcamento(
        renda=renda, fixas=DespesasFixas(), variaveis=DespesasVariaveis())
    assert perfil.renda_liquida == renda.total == salario + extra + outras
