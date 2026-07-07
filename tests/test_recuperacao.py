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


class ProviderAlucinaUmaVez:
    """Fabrica um número na 1ª chamada e volta aos fatos na 2ª (caso real do
    ministral-3b: "90% do fluxo", "ex.: 24 meses" — nada disso nos FATOS)."""

    def __init__(self):
        self.chamadas = 0
        self._bom = FakeProvider()

    def analisar(self, fatos):
        self.chamadas += 1
        analise = self._bom.analisar(fatos)
        if self.chamadas == 1:
            analise.sumario_executivo = "Economia estimada de R$ 88.888,00."
        return analise


class ProviderSempreAlucina:
    def __init__(self):
        self.chamadas = 0
        self._bom = FakeProvider()

    def analisar(self, fatos):
        self.chamadas += 1
        analise = self._bom.analisar(fatos)
        analise.sumario_executivo = "Economia estimada de R$ 88.888,00."
        return analise


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


class ProviderQueOuveCorrecao:
    """Alucina na 1ª; se receber o feedback do guardrail, devolve limpa."""

    def __init__(self):
        self.chamadas = 0
        self.correcoes: list[str] = []
        self._bom = FakeProvider()

    def analisar(self, fatos):
        self.chamadas += 1
        analise = self._bom.analisar(fatos)
        analise.sumario_executivo = "Economia estimada de R$ 88.888,00."
        return analise

    def analisar_com_correcao(self, fatos, correcao):
        self.chamadas += 1
        self.correcoes.append(correcao)
        return self._bom.analisar(fatos)


def test_retry_envia_feedback_com_os_numeros_orfaos(perfil_atencao):
    """O retry pós-guardrail NOMEIA os números fabricados ao provider."""
    provider = ProviderQueOuveCorrecao()
    cfg = ConfigAgente(provider="fake", cache=False)
    res = analisar(perfil_atencao, cfg=cfg, provider=provider)
    assert res.modo == "completo"
    assert provider.chamadas == 2
    assert len(provider.correcoes) == 1
    assert "88888" in provider.correcoes[0]  # o órfão é citado no feedback


def test_alucinacao_recupera_no_retry(perfil_atencao):
    """Guardrail reprovado também gasta a recuperação única (REQ-LLM-002):
    com temperatura > 0, a 2ª amostra costuma vir fundamentada nos fatos."""
    provider = ProviderAlucinaUmaVez()
    cfg = ConfigAgente(provider="fake", cache=False)
    res = analisar(perfil_atencao, cfg=cfg, provider=provider)
    assert provider.chamadas == 2
    assert res.modo == "completo"
    assert res.guardrails_violados == []


def test_alucinacao_persistente_degrada_apos_2_tentativas(perfil_atencao):
    """Sumário 100% fabricado: a redação não deixa nada de pé ⇒ degrada."""
    provider = ProviderSempreAlucina()
    cfg = ConfigAgente(provider="fake", cache=False)
    res = analisar(perfil_atencao, cfg=cfg, provider=provider)
    assert provider.chamadas == 2          # o teto de chamadas não muda
    assert res.modo == "degradado"
    assert "REQ-GRD-001:NUMEROS_FABRICADOS" in res.guardrails_violados


class ProviderComExemploFabricado:
    """Análise fundamentada + UMA frase acessória inventada (persistente)."""

    def __init__(self):
        self.chamadas = 0
        self._bom = FakeProvider()

    def analisar(self, fatos):
        self.chamadas += 1
        analise = self._bom.analisar(fatos)
        analise.diagnostico_interpretado += (
            " Considere renegociar (ex.: R$ 77.777,00 por mês).")
        return analise


def test_sanear_remove_a_frase_orfa_e_aprova(perfil_atencao):
    """ADR-0011: esgotado o retry, a redação determinística salva a análise —
    a frase com número fabricado some e o conteúdo fundamentado é aprovado."""
    provider = ProviderComExemploFabricado()
    cfg = ConfigAgente(provider="fake", cache=False)
    res = analisar(perfil_atencao, cfg=cfg, provider=provider)
    assert provider.chamadas == 2          # retry gastou; sanear resolveu
    assert res.modo == "completo"
    assert res.analise is not None
    assert "77.777" not in res.analise.diagnostico_interpretado
    assert res.analise.diagnostico_interpretado  # o resto sobreviveu
