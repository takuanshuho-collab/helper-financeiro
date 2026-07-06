"""M3 (T-301/T-302/T-305) — adaptação para exibição local.

Valida a fronteira da desanonimização (tokens só viram nomes reais na
exibição, REQ-SEC-003), a formatação do painel da GUI (incluindo o estado
degradado, T-304) e a conversão do payload da extração para o formulário
da aba Dívidas (tela de confirmação, T-305).
"""
from __future__ import annotations

from agent.exibicao import (
    ROTULO_IA,
    campos_para_formulario,
    formatar_secao_ia,
    mapear_tipo_divida,
    preparar_exibicao,
)
from contracts import (
    AnaliseAgente,
    CampoExtraido,
    CampoTextoExtraido,
    ExtracaoContrato,
    FatosFinanceiros,
    PassoNegociacao,
    Prioridade,
    ResultadoAnalise,
)
from guardrails.pii import anonimizar_credores

AVISO = "Este conteúdo é apoio à decisão, não aconselhamento financeiro."


def _fatos() -> FatosFinanceiros:
    return FatosFinanceiros(
        comprometimento_renda=0.39, classificacao="ATENÇÃO", fluxo_caixa=350.0,
        saldo_devedor_total=34000.0, juros_totais_futuros=9000.0,
        dividas=[], estrategias=[], tem_deficit=False,
    )


def _analise_com_tokens() -> AnaliseAgente:
    return AnaliseAgente(
        sumario_executivo="CREDOR_1 é a dívida mais cara da carteira.",
        diagnostico_interpretado="Priorize CREDOR_1 antes de CREDOR_2.",
        prioridades=[
            Prioridade(ordem=2, credor_token="CREDOR_2", justificativa="taxa menor"),
            Prioridade(ordem=1, credor_token="CREDOR_1", justificativa="maior taxa da carteira"),
        ],
        roteiro_negociacao=[
            PassoNegociacao(credor_token="CREDOR_1", abordagem="quitacao",
                            argumentos=["CREDOR_1 costuma aceitar desconto à vista"],
                            concessoes_possiveis=["parcelar a entrada"]),
        ],
        alertas_risco=["Evite contratar crédito novo no CREDOR_2."],
        confianca=0.9,
    )


def _resultado_completo() -> ResultadoAnalise:
    return ResultadoAnalise(fatos=_fatos(), analise=_analise_com_tokens(),
                            modo="completo", aviso_legal=AVISO)


def test_preparar_exibicao_restaura_nomes_reais():
    _, mapa = anonimizar_credores(["Banco Alfa", "Financeira Beta"])
    secao = preparar_exibicao(_resultado_completo(), mapa)

    assert secao.modo == "completo"
    assert "Banco Alfa" in secao.sumario
    assert "Banco Alfa" in secao.diagnostico and "Financeira Beta" in secao.diagnostico
    # Prioridades ordenadas pela ordem declarada, já com o nome real.
    assert secao.prioridades[0].startswith("1. Banco Alfa")
    assert secao.prioridades[1].startswith("2. Financeira Beta")
    # Abordagem traduzida para rótulo legível; argumentos desanonimizados.
    assert secao.roteiro[0].credor == "Banco Alfa"
    assert secao.roteiro[0].abordagem == "Quitação à vista"
    assert "Banco Alfa" in secao.roteiro[0].argumentos[0]
    assert secao.confianca == 0.9
    assert secao.aviso_legal == AVISO


def test_formatar_secao_ia_sem_tokens_e_com_rotulo():
    _, mapa = anonimizar_credores(["Banco Alfa", "Financeira Beta"])
    texto = formatar_secao_ia(preparar_exibicao(_resultado_completo(), mapa))

    assert "CREDOR_" not in texto            # nenhum token vaza para a tela
    assert ROTULO_IA in texto                # T-302/P2: rótulo explícito
    assert "SUMÁRIO EXECUTIVO" in texto
    assert "ROTEIRO DE NEGOCIAÇÃO" in texto
    assert "90%" in texto                    # confiança auto-avaliada
    assert AVISO in texto                    # H3: aviso legal presente


def test_exibicao_degradada_mostra_motivos():
    """T-304: em modo degradado a seção vira um indicador claro, sem narrativa."""
    _, mapa = anonimizar_credores(["Banco Alfa"])
    res = ResultadoAnalise(fatos=_fatos(), analise=None, modo="degradado",
                           guardrails_violados=["ERRO_PROVIDER:URLError"],
                           aviso_legal=AVISO)
    secao = preparar_exibicao(res, mapa)
    texto = formatar_secao_ia(secao)

    assert secao.modo == "degradado"
    assert secao.motivos == ["ERRO_PROVIDER:URLError"]
    assert "MODO DEGRADADO" in texto
    assert "ERRO_PROVIDER:URLError" in texto
    assert "fonte oficial" in texto          # aponta o determinístico como oficial


# ---------------------------------------------------- extração → formulário
def _payload_extracao() -> dict:
    return ExtracaoContrato(
        credor=CampoTextoExtraido(valor="Banco Alfa S.A.",
                                  trecho_fonte="Banco Alfa S.A.", confianca=0.9),
        tipo=CampoTextoExtraido(valor="empréstimo consignado",
                                trecho_fonte="empréstimo consignado", confianca=0.8),
        saldo_devedor=CampoExtraido(valor=10000.0, trecho_fonte="R$ 10.000,00",
                                    confianca=0.95),
        taxa_mensal=CampoExtraido(valor=0.02, trecho_fonte="2,00% a.m.", confianca=0.9),
        parcela=CampoExtraido(valor=945.6, trecho_fonte="R$ 945,60", confianca=0.9),
        parcelas_restantes=CampoExtraido(valor=12, trecho_fonte="12 parcelas",
                                         confianca=0.9),
    ).model_dump()


def test_campos_para_formulario_formata_para_o_formulario():
    form = campos_para_formulario(_payload_extracao())

    assert form["credor"]["valor"] == "Banco Alfa S.A."
    assert form["tipo"]["valor"] == "Consignado"        # texto livre → lista fechada
    assert form["saldo"]["valor"] == "10000,00"          # vírgula decimal
    assert form["taxa"]["valor"] == "2,00"               # fração 0.02 → 2,00 (%)
    assert form["parcela"]["valor"] == "945,60"
    assert form["restantes"]["valor"] == "12"
    # A citação e a confiança acompanham cada campo (tela de confirmação).
    assert form["saldo"]["fonte"] == "R$ 10.000,00"
    assert form["taxa"]["confianca"] == "90%"


def test_campos_ausentes_sao_omitidos():
    assert campos_para_formulario(ExtracaoContrato().model_dump()) == {}


def test_tipo_classifica_pelo_trecho_quando_contradiz_o_valor():
    """O trecho é literal do doc (quote-check); a paráfrase do modelo pode
    contradizê-lo — caso real: valor "pessoal" com trecho "consignado"."""
    form = campos_para_formulario({
        "tipo": {"valor": "empréstimo pessoal",
                 "trecho_fonte": "Contrato de empréstimo consignado",
                 "confianca": 0.0},
    })
    assert form["tipo"]["valor"] == "Consignado"


def test_tipo_usa_o_valor_quando_o_trecho_nao_classifica():
    form = campos_para_formulario({
        "tipo": {"valor": "cartão de crédito",
                 "trecho_fonte": "modalidade rotativa", "confianca": 0.0},
    })
    assert form["tipo"]["valor"] == "Cartão de crédito"


def test_mapear_tipo_divida():
    assert mapear_tipo_divida("empréstimo consignado privado") == "Consignado"
    assert mapear_tipo_divida("CDC veicular") == "CDC (Crédito Direto ao Consumidor)"
    assert mapear_tipo_divida("cartão de crédito rotativo") == "Cartão de crédito"
    assert mapear_tipo_divida("cheque especial") == "Cheque especial"
    assert mapear_tipo_divida("financiamento imobiliário") == "Financiamento"
    assert mapear_tipo_divida("empréstimo pessoal") == "Empréstimo pessoal"
    assert mapear_tipo_divida("hipoteca") == "Outro"
    assert mapear_tipo_divida(None) == "Outro"
