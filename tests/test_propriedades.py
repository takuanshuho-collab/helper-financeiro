"""Propriedades matemáticas do core (Hypothesis; auditoria F-12).

Em vez de casos fixos, verificamos INVARIANTES que valem para qualquer
combinação plausível de (principal, taxa, prazo) — é onde mora a confiança
de uma calculadora financeira.
"""
from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from core.calculos import (
    parcela_price,
    saldo_devedor_price,
    taxa_anual_para_mensal,
    taxa_implicita,
    taxa_mensal_para_anual,
)

# Faixas realistas para o domínio: dívidas de R$ 100 a R$ 1 mi,
# taxas de 0% a 20% a.m., prazos de 1 a 360 meses.
pv_st = st.floats(min_value=100, max_value=1_000_000)
taxa_st = st.floats(min_value=0.0, max_value=0.20)
n_st = st.integers(min_value=1, max_value=360)


@given(pv=pv_st, i=taxa_st, n=n_st)
def test_total_pago_nunca_menor_que_principal(pv, i, n):
    """Com juros ≥ 0, a soma das parcelas cobre ao menos o principal."""
    total = parcela_price(pv, i, n) * n
    assert total >= pv * (1 - 1e-9)


@given(pv=pv_st, i=taxa_st, n=n_st)
def test_saldo_zera_ao_pagar_todas_as_parcelas(pv, i, n):
    assert saldo_devedor_price(pv, i, n, n) == 0.0


@given(pv=pv_st, i=taxa_st, n=n_st, dados=st.data())
def test_saldo_devedor_decresce_com_parcelas_pagas(pv, i, n, dados):
    k = dados.draw(st.integers(min_value=0, max_value=n - 1), label="k")
    saldo_k = saldo_devedor_price(pv, i, n, k)
    saldo_k1 = saldo_devedor_price(pv, i, n, k + 1)
    assert saldo_k1 <= saldo_k + 1e-6


@given(pv=pv_st, i=st.floats(min_value=0.001, max_value=0.20), n=n_st)
def test_taxa_implicita_inverte_parcela_price(pv, i, n):
    """taxa_implicita(pv, PMT(pv, i, n), n) ≈ i — bisseção converge."""
    pmt = parcela_price(pv, i, n)
    recuperada = taxa_implicita(pv, pmt, n)
    assert recuperada is not None
    assert abs(recuperada - i) < 1e-6


@given(i=taxa_st)
def test_conversao_mensal_anual_e_inversa(i):
    assert abs(taxa_anual_para_mensal(taxa_mensal_para_anual(i)) - i) < 1e-12


@given(pv=pv_st, n=n_st)
def test_sem_juros_parcela_e_divisao_simples(pv, n):
    assert abs(parcela_price(pv, 0.0, n) - pv / n) < 1e-9
