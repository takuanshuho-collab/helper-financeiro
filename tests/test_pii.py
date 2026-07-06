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


# --- Cinto de segurança final pré-cloud (H2, auditoria F-07) -----------------

def test_verificacao_pre_envio_aprova_fatos_limpos(perfil_atencao):
    from agent.agente import _verificar_pii_pre_envio
    fatos, mapa = montar_fatos(perfil_atencao)
    assert _verificar_pii_pre_envio(fatos, mapa) == []


def test_verificacao_pre_envio_pega_vazamento(perfil_atencao):
    from agent.agente import _verificar_pii_pre_envio
    fatos, mapa = montar_fatos(perfil_atencao)
    # Simula um refactor descuidado que deixou nome real escapar num campo.
    fatos.dividas[0].tipo = "Cartão de crédito (Cartão Banco A)"
    assert "Cartão Banco A" in _verificar_pii_pre_envio(fatos, mapa)


def test_provider_cloud_degrada_se_pii_no_payload(perfil_atencao, monkeypatch):
    """Orquestração: com provider cloud e PII no payload, NUNCA chama o LLM."""
    import agent.agente as agente_mod
    from agent.config import ConfigAgente

    fatos, mapa = montar_fatos(perfil_atencao)
    fatos.dividas[0].tipo = "Cartão de crédito (Cartão Banco A)"  # vazamento forjado
    monkeypatch.setattr(agente_mod, "montar_fatos", lambda *a, **k: (fatos, mapa))

    class ProviderQueNaoPodeSerChamado:
        def analisar(self, fatos):
            raise AssertionError("payload com PII chegou ao provider cloud")

    # Endpoint REMOTO (nuvem): a checagem de PII incide (ADR-0010).
    cfg = ConfigAgente(provider="openai_compat", base_url="https://api.openai.com/v1")
    res = agente_mod.analisar(perfil_atencao, cfg=cfg,
                              provider=ProviderQueNaoPodeSerChamado())
    assert res.modo == "degradado"
    assert "REQ-GRD-002:PII_DETECTADA" in res.guardrails_violados
