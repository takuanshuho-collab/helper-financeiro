"""
Classificação de grupos do extrato por LLM local (ADR-0014, REQ-F-021) — T-1302.

O invariante em teste: a LLM SÓ rotula — e mesmo o rótulo passa por travas
determinísticas (índice existe, campo existe no core, natureza coerente).
Item que viole qualquer trava é descartado; sem LLM, o resultado degrada
para "classificação manual" com o motivo (P8), nunca com exceção.
"""
from agent.classificacao import (
    OllamaClassificador,
    OpenAICompatClassificador,
    classificar_grupos,
    obter_classificador,
)
from agent.config import ConfigAgente
from contracts import ClassificacaoExtrato, ItemClassificado

CFG_TESTE = ConfigAgente(provider="fake", model="fake-model", cache=False)

GRUPOS = [
    ("Salário Acme", "credito"),
    ("Conta de luz Enel", "debito"),
    ("Uber Trip", "debito"),
]


def classificacao_fiel() -> ClassificacaoExtrato:
    return ClassificacaoExtrato(itens=[
        ItemClassificado(indice=0, categoria="renda",
                         campo_pai="salario_liquido"),
        ItemClassificado(indice=1, categoria="fixas", campo_pai="contas_casa"),
        ItemClassificado(indice=2, categoria="fixas", campo_pai="transporte"),
    ])


class FakeClassificador:
    """Classificador determinístico para o harness (nunca toca a rede)."""

    def __init__(self, classificacao: ClassificacaoExtrato | None = None,
                 erro: Exception | None = None):
        self.classificacao = classificacao or classificacao_fiel()
        self.erro = erro
        self.chamadas = 0

    def classificar(self, grupos) -> ClassificacaoExtrato:
        self.chamadas += 1
        if self.erro:
            raise self.erro
        return self.classificacao


def test_classifica_todos_os_grupos_validos():
    resultado = classificar_grupos(GRUPOS, classificador=FakeClassificador())
    assert resultado.por_indice == {
        0: ("renda", "salario_liquido"),
        1: ("fixas", "contas_casa"),
        2: ("fixas", "transporte"),
    }
    assert resultado.descartes == []
    assert resultado.motivos == []


def test_travas_descartam_itens_invalidos():
    # 4 violações distintas; só o item são sobrevive.
    suja = ClassificacaoExtrato(itens=[
        ItemClassificado(indice=9, categoria="fixas", campo_pai="moradia"),
        ItemClassificado(indice=1, categoria="investimentos",
                         campo_pai="acoes"),
        # Crédito (índice 0) classificado como DESPESA: natureza incoerente.
        ItemClassificado(indice=0, categoria="variaveis", campo_pai="lazer"),
        ItemClassificado(indice=2, categoria="fixas", campo_pai="transporte"),
        # Índice repetido: o primeiro rótulo (válido) prevalece.
        ItemClassificado(indice=2, categoria="variaveis", campo_pai="lazer"),
    ])
    resultado = classificar_grupos(
        GRUPOS, classificador=FakeClassificador(suja))
    assert resultado.por_indice == {2: ("fixas", "transporte")}
    assert resultado.descartes == [
        "9:INDICE_INVALIDO",
        "1:CAMPO_INVALIDO:investimentos/acoes",
        "0:NATUREZA:credito",
        "2:INDICE_REPETIDO",
    ]


def test_debito_em_renda_tambem_e_incoerente():
    resultado = classificar_grupos(GRUPOS, classificador=FakeClassificador(
        ClassificacaoExtrato(itens=[
            ItemClassificado(indice=2, categoria="renda",
                             campo_pai="renda_extra"),
        ])))
    assert resultado.por_indice == {}
    assert resultado.descartes == ["2:NATUREZA:debito"]


def test_erro_do_provider_degrada_apos_um_retry():
    # REQ-LLM-002: 2 tentativas no total; depois classificação manual (P8).
    fake = FakeClassificador(erro=ValueError("porta fechada"))
    resultado = classificar_grupos(GRUPOS, classificador=fake)
    assert fake.chamadas == 2
    assert resultado.por_indice == {}
    assert resultado.motivos == ["ERRO_PROVIDER:ValueError"]


def test_sem_grupos_nao_chama_o_modelo():
    fake = FakeClassificador()
    resultado = classificar_grupos([], classificador=fake)
    assert resultado.por_indice == {}
    assert fake.chamadas == 0


def test_fabrica_exige_endpoint_local_h2():
    # Extrato bancário nunca sai da máquina: endpoint remoto é recusado.
    remota = ConfigAgente(provider="openai_compat",
                          base_url="https://api.exemplo.com/v1",
                          api_key="chave")
    resultado = classificar_grupos(GRUPOS, cfg=remota)
    assert resultado.por_indice == {}
    assert resultado.motivos == ["ERRO_CONFIG:RuntimeError"]


def test_fabrica_escolhe_o_dialeto_pelo_provider():
    ollama = ConfigAgente(provider="local",
                          base_url="http://localhost:11434/v1")
    assert isinstance(obter_classificador(ollama), OllamaClassificador)
    lmstudio = ConfigAgente(provider="openai_compat",
                            base_url="http://127.0.0.1:1234/v1")
    assert isinstance(obter_classificador(lmstudio), OpenAICompatClassificador)
