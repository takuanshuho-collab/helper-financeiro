"""Degradação segura (P8/REQ-LLM-002) e pipeline completo (FakeProvider)."""
from agent.agente import analisar
from agent.config import ConfigAgente
from agent.provider import FakeProvider


class ProviderQueFalha:
    def analisar(self, fatos):
        raise RuntimeError("LLM indisponível")


class ProviderQueAlucina:
    def analisar(self, fatos):
        from contracts import AnaliseAgente
        return AnaliseAgente(
            sumario_executivo="Economia garantida de R$ 88.888,00.",
            diagnostico_interpretado="x", prioridades=[], roteiro_negociacao=[])


def test_pipeline_completo_com_fake(perfil_atencao):
    cfg = ConfigAgente(provider="fake")
    res = analisar(perfil_atencao, extra_mensal=500, cfg=cfg, provider=FakeProvider())
    assert res.modo == "completo"
    assert res.analise is not None
    assert res.guardrails_violados == []
    # Aviso legal presente (H3).
    assert "apoio à decisão" in res.analise.sumario_executivo


def test_provider_indisponivel_degrada(perfil_atencao):
    cfg = ConfigAgente(provider="fake")
    res = analisar(perfil_atencao, cfg=cfg, provider=ProviderQueFalha())
    assert res.modo == "degradado"
    assert res.analise is None
    assert res.fatos is not None                      # determinístico intacto
    assert any("ERRO_PROVIDER" in v for v in res.guardrails_violados)


def test_alucinacao_numerica_degrada(perfil_atencao):
    cfg = ConfigAgente(provider="fake")
    res = analisar(perfil_atencao, cfg=cfg, provider=ProviderQueAlucina())
    assert res.modo == "degradado"
    assert "REQ-GRD-001:NUMEROS_FABRICADOS" in res.guardrails_violados


def test_modo_degradado_explicito(perfil_atencao):
    cfg = ConfigAgente(provider="fake", modo_degradado=True)
    res = analisar(perfil_atencao, cfg=cfg)
    assert res.modo == "degradado"
    assert res.guardrails_violados == ["MODO_DEGRADADO"]


def test_provider_offline_real_degrada(perfil_atencao, monkeypatch):
    """T-206: OllamaProvider DE VERDADE contra porta local fechada.

    Diferente dos fakes acima, aqui o caminho real de rede (urllib) falha com
    conexão recusada — e o usuário ainda recebe o determinístico, sem exceção.
    A porta 9 (discard) não tem listener; a recusa é imediata, sem internet.

    `HF_BASE_URL` definido = servidor do usuário (Ollama) tem precedência sobre
    o runtime embarcado (ADR-0016 §E); é o `OllamaProvider` que falha na rede.
    """
    monkeypatch.setenv("HF_BASE_URL", "http://127.0.0.1:9")
    cfg = ConfigAgente(provider="local", base_url="http://127.0.0.1:9", timeout_s=2)
    res = analisar(perfil_atencao, cfg=cfg)
    assert res.modo == "degradado"
    assert res.analise is None
    assert res.guardrails_violados[0].startswith("ERRO_PROVIDER:")
    assert res.fatos.saldo_devedor_total > 0          # determinístico intacto
