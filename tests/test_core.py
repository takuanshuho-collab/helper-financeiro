"""Núcleo determinístico (REQ-F-001..003)."""
import dataclasses

from core.calculos import calcular_cet_anual, parcela_price, taxa_implicita, taxa_mensal_para_anual
from core.diagnostico import classificar_saude, resumo_diagnostico, taxa_media_ponderada
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


def test_classificacao_dois_eixos_deficit_nunca_e_saudavel():
    """T-2606 (achado da aceitação de campo do v2.15): parcelas baixas com
    DÉFICIT mensal não podem sair "Saudável" — o caso real de campo tinha
    falta de R$ 2.159,47/mês e o dashboard dizia Saudável. FALHAVA antes."""
    # Renda 6000, parcelas 900 (15%, eixo-parcelas Saudável), déficit 2159.47
    # = 36% da renda (> 10%) ⇒ o eixo do fluxo puxa para Crítico.
    rotulo, explicacao = classificar_saude(0.15, -2159.47, 6000.0)
    assert rotulo == "Crítico"
    assert "vermelho" in explicacao

    # Déficit pequeno (≤ 10% da renda) ⇒ Atenção, nunca Saudável.
    assert classificar_saude(0.15, -300.0, 6000.0)[0] == "Atenção"

    # Superávit ⇒ o eixo das parcelas continua mandando (regra clássica).
    assert classificar_saude(0.15, 1500.0, 6000.0)[0] == "Saudável"
    assert classificar_saude(0.60, 1500.0, 6000.0)[0] == "Crítico"

    # Renda zero gastando dinheiro ⇒ Crítico direto (sem denominador).
    assert classificar_saude(0.0, -100.0, 0.0)[0] == "Crítico"

    # Empate num nível ruim ⇒ explicação combinada (cita os DOIS motivos).
    rotulo, explicacao = classificar_saude(0.40, -300.0, 6000.0)
    assert rotulo == "Atenção"
    assert "parcelas" in explicacao and "vermelho" in explicacao


def test_resumo_diagnostico_reflete_o_deficit(perfil_atencao):
    """O rótulo do resumo (dashboard/relatório/LLM) usa os dois eixos."""
    perfil_deficit = dataclasses.replace(
        perfil_atencao,
        despesas_variaveis=perfil_atencao.despesas_variaveis + 5000)
    diag = resumo_diagnostico(perfil_deficit)
    assert diag["tem_deficit"] is True
    assert diag["classificacao"] != "Saudável"


def test_avalanche_paga_menos_juros_que_bola_de_neve(perfil_atencao):
    comp = comparar_estrategias(perfil_atencao, extra_mensal=500)
    assert comp["avalanche"]["quitavel"]
    assert comp["bola_de_neve"]["quitavel"]
    assert comp["avalanche"]["juros_pagos"] <= comp["bola_de_neve"]["juros_pagos"]


def test_diagnostico_consistente(perfil_atencao):
    diag = resumo_diagnostico(perfil_atencao)
    assert diag["saldo_devedor_total"] == 34000
    assert diag["classificacao"] == "Atenção"


def test_taxa_media_ponderada_pelo_saldo(perfil_atencao):
    # (0,12*8000 + 0,025*20000 + 0,018*6000) / 34000 = 1568 / 34000 ≈ 0,046118
    assert abs(taxa_media_ponderada(perfil_atencao) - 1568 / 34000) < 1e-9
    # Dívida grande e barata puxa a média para baixo da mais cara (12% a.m.).
    assert taxa_media_ponderada(perfil_atencao) < 0.12


def test_taxa_media_ponderada_sem_dividas():
    from core.models import PerfilFinanceiro

    assert taxa_media_ponderada(PerfilFinanceiro()) == 0.0


def test_diagnostico_estatisticas_de_dividas(perfil_atencao):
    diag = resumo_diagnostico(perfil_atencao)
    # Custo até quitar = soma das parcelas restantes: 900*12 + 700*36 + 350*20.
    assert diag["custo_total_ate_quitar"] == 900 * 12 + 700 * 36 + 350 * 20
    assert abs(diag["taxa_media_ponderada"] - 1568 / 34000) < 1e-9
