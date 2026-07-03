"""Recuperação única do REQ-LLM-002: 1 retry antes de degradar (auditoria F-06)."""
from agent.agente import analisar
from agent.config import ConfigAgente
from agent.provider import FakeProvider


class ProviderFalhaUmaVez:
    """Falha na 1ª chamada e responde bem na 2ª — o retry deve salvar."""

    def __init__(self):
        self.chamadas = 0
        self._bom = FakeProvider()

    def analisar(self, fatos):
        self.chamadas += 1
        if self.chamadas == 1:
            raise TimeoutError("falha transitória")
        return self._bom.analisar(fatos)


class ProviderSchemaUmaVez:
    """Devolve lixo fora do schema na 1ª chamada e adere na 2ª."""

    def __init__(self):
        self.chamadas = 0
        self._bom = FakeProvider()

    def analisar(self, fatos):
        self.chamadas += 1
        if self.chamadas == 1:
            return {"nao": "é AnaliseAgente"}
        return self._bom.analisar(fatos)


class ProviderSempreFalha:
    def __init__(self):
        self.chamadas = 0

    def analisar(self, fatos):
        self.chamadas += 1
        raise RuntimeError("LLM fora do ar")


def test_falha_transitoria_recupera_no_retry(perfil_atencao):
    provider = ProviderFalhaUmaVez()
    res = analisar(perfil_atencao, cfg=ConfigAgente(provider="fake"), provider=provider)
    assert provider.chamadas == 2
    assert res.modo == "completo"
    assert res.guardrails_violados == []


def test_schema_invalido_recupera_no_retry(perfil_atencao):
    provider = ProviderSchemaUmaVez()
    res = analisar(perfil_atencao, cfg=ConfigAgente(provider="fake"), provider=provider)
    assert provider.chamadas == 2
    assert res.modo == "completo"


def test_falha_persistente_degrada_apos_2_tentativas(perfil_atencao):
    provider = ProviderSempreFalha()
    res = analisar(perfil_atencao, cfg=ConfigAgente(provider="fake"), provider=provider)
    assert provider.chamadas == 2          # exatamente 1 retry, nunca mais
    assert res.modo == "degradado"
    assert any("ERRO_PROVIDER" in v for v in res.guardrails_violados)
