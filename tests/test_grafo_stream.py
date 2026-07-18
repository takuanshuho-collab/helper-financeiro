"""
Caminho de streaming do grafo (ADR-0023, T-2603).

`executar_analise(ao_evento=...)` roda o grafo por `.stream()` síncrono emitindo
fase (por nó) + progresso (contador), e materializa um `ResultadoAnalise`
IDÊNTICO ao do `.invoke()` (mesmo fake, dois caminhos). Retomada/higiene do
T-2601/T-2602 valem igual no caminho stream. Tudo offline com `FakeProvider`.
"""
from __future__ import annotations

import pytest

from agent.agente import montar_fatos
from agent.config import ConfigAgente
from agent.grafo import desarmar_checkpointer_duravel, executar_analise
from agent.provider import FakeProvider
from core.models import Divida, PerfilFinanceiro

CFG_FAKE = ConfigAgente(provider="fake", cache=False)


@pytest.fixture(autouse=True)
def _reset_proxy():
    desarmar_checkpointer_duravel()
    yield
    desarmar_checkpointer_duravel()


def _perfil() -> PerfilFinanceiro:
    return PerfilFinanceiro(
        renda_liquida=5000, despesas_fixas=2200, despesas_variaveis=800,
        reserva_emergencia=0, saldo_fgts=3000,
        dividas=[Divida("Banco Z", "Cartão de crédito", 8000, 0.12, 900, 12)],
    )


def test_stream_emite_fases_na_ordem_e_resultado_identico():
    """As fases saem na ordem dos nós e o `ResultadoAnalise` do caminho stream é
    materializado IDÊNTICO ao do `.invoke()` (fatos/análise/modo/guardrails)."""
    cfg = CFG_FAKE

    # Caminho .invoke() (ao_evento=None).
    fatos_a, mapa_a = montar_fatos(_perfil())
    r_invoke = executar_analise(fatos_a, mapa_a, cfg, FakeProvider())

    # Caminho .stream() (ao_evento coletando eventos).
    eventos: list[tuple[str, dict]] = []
    fatos_b, mapa_b = montar_fatos(_perfil())
    r_stream = executar_analise(
        fatos_b, mapa_b, cfg, FakeProvider(),
        ao_evento=lambda tipo, dados: eventos.append((tipo, dados)))

    # ResultadoAnalise idêntico (o thread_id é efêmero/uuid ⇒ comparo o resto).
    assert r_stream.modo == r_invoke.modo == "completo"
    assert r_stream.analise == r_invoke.analise
    assert r_stream.guardrails_violados == r_invoke.guardrails_violados
    assert r_stream.fatos == r_invoke.fatos

    fases = [d["no"] for t, d in eventos if t == "fase"]
    # Ordem dos nós até a aprovação (FakeProvider gera análise válida).
    assert fases[:3] == ["verificar_pii", "consultar_cache", "chamar_llm"]
    assert fases[-1] == "aprovar"
    assert "validar_guardrails" in fases


def test_stream_erro_de_provider_degrada_e_ainda_emite_fases():
    """Falha do provider no caminho stream degrada com segurança (P8) — e as
    fases até o ponto de falha continuam saindo (o stream não some no erro)."""
    class _ProviderErro:
        def analisar(self, fatos):  # noqa: ANN001, ANN202
            raise RuntimeError("llm fora do ar")

    eventos: list[tuple[str, dict]] = []
    fatos, mapa = montar_fatos(_perfil())
    res = executar_analise(
        fatos, mapa, CFG_FAKE, _ProviderErro(),
        ao_evento=lambda tipo, dados: eventos.append((tipo, dados)))

    assert res.modo == "degradado"
    fases = [d["no"] for t, d in eventos if t == "fase"]
    assert "chamar_llm" in fases
    assert "degradar" in fases
