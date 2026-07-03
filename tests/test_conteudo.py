"""Conteúdo (REQ-GRD-004 / H6 e REQ-GRD-003 / H3)."""
from agent.schemas import AnaliseAgente, PassoNegociacao
from guardrails.conteudo import AVISO_LEGAL, detectar_conteudo_indevido, garantir_aviso


def test_recomendacao_investimento_e_sinalizada():
    analise = AnaliseAgente(
        sumario_executivo="Quite as dívidas caras primeiro.",
        diagnostico_interpretado="Depois, invista em ações para render mais.",
        prioridades=[],
        roteiro_negociacao=[PassoNegociacao(
            credor_token="CREDOR_1", abordagem="reducao",
            argumentos=["Aplique em bitcoin o que sobrar."])],
    )
    violacoes = detectar_conteudo_indevido(analise)
    assert violacoes  # detectou "invista em" e/ou "aplique em"


def test_saida_limpa_nao_gera_violacao():
    analise = AnaliseAgente(
        sumario_executivo="Priorize a dívida mais cara.",
        diagnostico_interpretado="Reduza o custo dos juros negociando.",
        prioridades=[], roteiro_negociacao=[])
    assert detectar_conteudo_indevido(analise) == []


def test_aviso_legal_e_anexado():
    texto = "Análise concluída."
    com_aviso = garantir_aviso(texto)
    assert AVISO_LEGAL in com_aviso
    # Idempotente: não duplica.
    assert garantir_aviso(com_aviso).count("apoio à decisão") == 1
