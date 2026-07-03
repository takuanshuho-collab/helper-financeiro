"""Grounding (REQ-GRD-001 / H1): número órfão na saída do LLM é reprovado."""
from agent.agente import montar_fatos
from agent.schemas import AnaliseAgente, Prioridade
from guardrails.validador_numerico import validar


def test_saida_coerente_passa(perfil_atencao):
    fatos, _ = montar_fatos(perfil_atencao, extra_mensal=500)
    # Análise que cita apenas números presentes nos fatos.
    comp_pct = round(fatos.comprometimento_renda * 100)
    analise = AnaliseAgente(
        sumario_executivo=f"Comprometimento de {comp_pct}% exige atenção.",
        diagnostico_interpretado=(
            f"Saldo total de {fatos.saldo_devedor_total:.2f} a controlar."),
        prioridades=[Prioridade(ordem=1, credor_token="CREDOR_1",
                                justificativa="Custo de 12.0% ao mês, o mais alto.")],
        roteiro_negociacao=[],
    )
    assert validar(fatos, analise) == []   # nenhum número órfão


def test_numero_fabricado_reprova(perfil_atencao):
    fatos, _ = montar_fatos(perfil_atencao, extra_mensal=500)
    analise = AnaliseAgente(
        sumario_executivo="Você pode economizar R$ 99.999,00 imediatamente.",
        diagnostico_interpretado="Projeção otimista.",
        prioridades=[],
        roteiro_negociacao=[],
    )
    orfaos = validar(fatos, analise)
    assert 99999.0 in orfaos            # a cifra inventada é detectada
