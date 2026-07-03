"""Núcleo determinístico (REQ-F-001..003)."""
from core.calculos import (parcela_price, taxa_implicita, calcular_cet_anual,
                           taxa_mensal_para_anual)
from core.diagnostico import resumo_diagnostico, classificar_saude
from core.estrategias import comparar_estrategias


def test_parcela_price_valor_conhecido():
    # 10.000 a 2% a.m. em 24x ≈ 528,71
    assert round(parcela_price(10000, 0.02, 24), 2) == 528.71


def test_taxa_implicita_recupera_taxa():
    pmt = parcela_price(10000, 0.02, 24)
    assert abs(taxa_implicita(10000, pmt, 24) - 0.02) < 1e-4


def test_cet_maior_que_nominal_com_tarifa():
    pmt = parcela_price(10000, 0.02, 24)
    cet = calcular_cet_anual(9800, pmt, 24)   # R$200 de tarifa embutida
    assert cet > taxa_mensal_para_anual(0.02)


def test_classificacao_por_faixa():
    assert classificar_saude(0.25)[0] == "Saudável"
    assert classificar_saude(0.39)[0] == "Atenção"
    assert classificar_saude(0.60)[0] == "Crítico"


def test_avalanche_paga_menos_juros_que_bola_de_neve(perfil_atencao):
    comp = comparar_estrategias(perfil_atencao, extra_mensal=500)
    assert comp["avalanche"]["quitavel"]
    assert comp["bola_de_neve"]["quitavel"]
    assert comp["avalanche"]["juros_pagos"] <= comp["bola_de_neve"]["juros_pagos"]


def test_diagnostico_consistente(perfil_atencao):
    diag = resumo_diagnostico(perfil_atencao)
    assert diag["saldo_devedor_total"] == 34000
    assert diag["classificacao"] == "Atenção"
