"""Cache local de análises (T-205): acerto, isolamento, LRU e segurança."""
from agent.agente import analisar
from agent.cache import CacheAnalises, cache_global
from agent.config import ConfigAgente
from agent.provider import FakeProvider


class ProviderContador:
    def __init__(self):
        self.chamadas = 0
        self._fake = FakeProvider()

    def analisar(self, fatos):
        self.chamadas += 1
        return self._fake.analisar(fatos)


def test_segunda_analise_igual_nao_chama_o_llm(perfil_atencao):
    provider = ProviderContador()
    cfg = ConfigAgente(provider="fake", cache=True)

    r1 = analisar(perfil_atencao, cfg=cfg, provider=provider)
    r2 = analisar(perfil_atencao, cfg=cfg, provider=provider)

    assert provider.chamadas == 1
    assert r1.modo == r2.modo == "completo"
    assert r2.analise.sumario_executivo == r1.analise.sumario_executivo


def test_fatos_diferentes_nao_compartilham_cache(perfil_atencao, perfil_critico):
    provider = ProviderContador()
    cfg = ConfigAgente(provider="fake", cache=True)

    analisar(perfil_atencao, cfg=cfg, provider=provider)
    analisar(perfil_critico, cfg=cfg, provider=provider)

    assert provider.chamadas == 2


def test_extra_mensal_diferente_muda_os_fatos_e_a_chave(perfil_atencao):
    provider = ProviderContador()
    cfg = ConfigAgente(provider="fake", cache=True)

    analisar(perfil_atencao, extra_mensal=0, cfg=cfg, provider=provider)
    analisar(perfil_atencao, extra_mensal=500, cfg=cfg, provider=provider)

    assert provider.chamadas == 2


def test_cache_desligado_sempre_chama_o_llm(perfil_atencao):
    provider = ProviderContador()
    cfg = ConfigAgente(provider="fake", cache=False)

    analisar(perfil_atencao, cfg=cfg, provider=provider)
    analisar(perfil_atencao, cfg=cfg, provider=provider)

    assert provider.chamadas == 2


def test_analise_reprovada_nao_entra_no_cache(perfil_atencao):
    """Guardrail reprova ⇒ nada é guardado: a próxima tentativa vai ao LLM."""
    from contracts import AnaliseAgente

    class ProviderQueAlucinaContando:
        def __init__(self):
            self.chamadas = 0

        def analisar(self, fatos):
            self.chamadas += 1
            return AnaliseAgente(
                sumario_executivo="Economia garantida de R$ 88.888,00.",
                diagnostico_interpretado="x", prioridades=[], roteiro_negociacao=[])

    provider = ProviderQueAlucinaContando()
    cfg = ConfigAgente(provider="fake", cache=True)

    r1 = analisar(perfil_atencao, cfg=cfg, provider=provider)
    r2 = analisar(perfil_atencao, cfg=cfg, provider=provider)

    assert r1.modo == r2.modo == "degradado"
    # 2 chamadas POR análise (retry com feedback, ADR-0011) e nada no cache:
    # a segunda análise foi de novo ao LLM em vez de reaproveitar a reprovada.
    assert provider.chamadas == 4
    assert len(cache_global) == 0


def test_acerto_devolve_instancia_nova(perfil_atencao):
    """Mutar o resultado de um acerto não pode corromper o cache (aliasing)."""
    provider = ProviderContador()
    cfg = ConfigAgente(provider="fake", cache=True)

    r1 = analisar(perfil_atencao, cfg=cfg, provider=provider)
    r1.analise.sumario_executivo = "MUTADO"
    r2 = analisar(perfil_atencao, cfg=cfg, provider=provider)

    assert r2.analise.sumario_executivo != "MUTADO"


def test_lru_expulsa_o_mais_antigo():
    from agent.agente import montar_fatos
    from core.models import Divida, PerfilFinanceiro

    cache = CacheAnalises(capacidade=2)
    chaves = []
    for saldo in (1000, 2000, 3000):
        perfil = PerfilFinanceiro(
            renda_liquida=5000, despesas_fixas=1000, despesas_variaveis=500,
            dividas=[Divida("Credor", "Cartão de crédito", saldo, 0.05, 200, 12)])
        fatos, _ = montar_fatos(perfil)
        chave = cache.chave("local", "m", fatos)
        cache.guardar(chave, FakeProvider().analisar(fatos))
        chaves.append(chave)

    assert len(cache) == 2
    assert cache.obter(chaves[0]) is None          # o mais antigo saiu
    assert cache.obter(chaves[2]) is not None
