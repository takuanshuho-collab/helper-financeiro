"""Privacidade (REQ-GRD-002 / SEC-003): PII é tokenizada e restaurável."""
from agent.agente import montar_fatos
from guardrails.pii import contem_pii, desanonimizar


def test_fatos_nao_contem_nome_real(perfil_atencao):
    fatos, mapa = montar_fatos(perfil_atencao)
    # Nos fatos, credores viram tokens CREDOR_n.
    tokens = {d.token for d in fatos.dividas}
    assert tokens == {"CREDOR_1", "CREDOR_2", "CREDOR_3"}
    # O JSON dos fatos não pode conter os nomes reais.
    import json
    blob = json.dumps(fatos.model_dump(), ensure_ascii=False)
    assert contem_pii(blob, mapa) == []


def test_deteccao_de_vazamento(perfil_atencao):
    _, mapa = montar_fatos(perfil_atencao)
    texto_vazando = "Negocie com Cartão Banco A e informe o CPF 123.456.789-00."
    achados = contem_pii(texto_vazando, mapa)
    assert "Cartão Banco A" in achados
    assert "CPF" in achados


def test_desanonimizar_restaura(perfil_atencao):
    _, mapa = montar_fatos(perfil_atencao)
    texto = "A prioridade é CREDOR_1, depois CREDOR_2."
    restaurado = desanonimizar(texto, mapa)
    assert "Cartão Banco A" in restaurado
    assert "CDC Veículo" in restaurado
