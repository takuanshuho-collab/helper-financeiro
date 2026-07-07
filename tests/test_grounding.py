"""Grounding (REQ-GRD-001 / H1): número órfão na saída do LLM é reprovado."""
from agent.agente import montar_fatos
from contracts import AnaliseAgente, Prioridade
from guardrails.validador_numerico import remover_frases_orfas, validar


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


def test_fato_negativo_citado_sem_sinal_passa(perfil_critico):
    """O token do texto não carrega sinal: "R$ -2.200,00" rende "2.200,00".
    Um fato negativo (fluxo em déficit) citado pelo módulo não é órfão."""
    fatos, _ = montar_fatos(perfil_critico)
    assert fatos.fluxo_caixa < 0
    analise = AnaliseAgente(
        sumario_executivo=(
            f"Faltam R$ {abs(fatos.fluxo_caixa):.2f} por mês no orçamento."),
        diagnostico_interpretado="Déficit exige corte de despesas.",
        prioridades=[], roteiro_negociacao=[],
    )
    assert validar(fatos, analise) == []


def test_redacao_remove_so_as_frases_orfas(perfil_atencao):
    """ADR-0011: a redação corta a FRASE com o número órfão e preserva o resto."""
    fatos, _ = montar_fatos(perfil_atencao, extra_mensal=500)
    comp_pct = round(fatos.comprometimento_renda * 100)
    analise = AnaliseAgente(
        sumario_executivo=(
            f"Comprometimento de {comp_pct}% exige atenção. "
            "Considere renegociar (ex.: R$ 77.777,00 por mês)."),
        diagnostico_interpretado=(
            f"Saldo total de {fatos.saldo_devedor_total:.2f} a controlar."),
        prioridades=[Prioridade(ordem=1, credor_token="CREDOR_1",
                                justificativa="Reduza um valor tipo 555,55 aqui.")],
        roteiro_negociacao=[],
        alertas_risco=["Sem número nenhum, fica.", "Alerta com 888,88 inventado."],
    )
    limpa = remover_frases_orfas(fatos, analise)
    assert "77.777" not in limpa.sumario_executivo
    assert f"{comp_pct}%" in limpa.sumario_executivo       # frase boa preservada
    assert limpa.diagnostico_interpretado                  # intacto
    assert limpa.prioridades[0].justificativa == ""        # 100% órfã ⇒ vazia
    assert limpa.alertas_risco == ["Sem número nenhum, fica."]
    assert validar(fatos, limpa) == []                     # H1 pós-redação
