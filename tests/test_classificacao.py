"""
Classificação de grupos do extrato por LLM local (ADR-0014, REQ-F-021) — T-1302.

O invariante em teste: a LLM SÓ rotula — e mesmo o rótulo passa por travas
determinísticas (índice existe, campo existe no core, natureza coerente).
Item que viole qualquer trava é descartado; sem LLM, o resultado degrada
para "classificação manual" com o motivo (P8), nunca com exceção.
"""
from pydantic import ValidationError

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


def test_modo_degradado_pula_o_llm_sem_tentar_rede():
    # HF_MODO_DEGRADADO=1 (P8 explícito): direto para a classificação manual.
    cfg = ConfigAgente(provider="local", modo_degradado=True)
    resultado = classificar_grupos(GRUPOS, cfg=cfg)
    assert resultado.por_indice == {}
    assert resultado.motivos == ["HF_MODO_DEGRADADO"]


def test_fabrica_exige_endpoint_local_h2():
    # Extrato bancário nunca sai da máquina: endpoint remoto é recusado.
    remota = ConfigAgente(provider="openai_compat",
                          base_url="https://api.exemplo.com/v1",
                          api_key="chave")
    resultado = classificar_grupos(GRUPOS, cfg=remota)
    assert resultado.por_indice == {}
    assert resultado.motivos == ["ERRO_CONFIG:RuntimeError"]


def test_fabrica_escolhe_o_dialeto_pelo_provider(monkeypatch):
    # HF_BASE_URL fixado: servidor do usuário (Ollama de verdade), não o
    # runtime embarcado — que, sem HF_BASE_URL, assumiria o dialeto
    # OpenAI-compatible mesmo com provider="local" (T-1702, ADR-0016 §E).
    monkeypatch.setenv("HF_BASE_URL", "http://localhost:11434/v1")
    ollama = ConfigAgente(provider="local",
                          base_url="http://localhost:11434/v1")
    assert isinstance(obter_classificador(ollama), OllamaClassificador)
    lmstudio = ConfigAgente(provider="openai_compat",
                            base_url="http://127.0.0.1:1234/v1")
    assert isinstance(obter_classificador(lmstudio), OpenAICompatClassificador)


def test_fabrica_sem_hf_base_url_cai_no_runtime_embarcado(monkeypatch):
    """Sem HF_BASE_URL, provider="local" usa o runtime embarcado — que fala
    OpenAI-compatible (llama-server), não a API nativa do Ollama (T-1702)."""
    from agent import provider as provider_mod

    monkeypatch.delenv("HF_BASE_URL", raising=False)
    monkeypatch.setattr(provider_mod, "base_url_runtime_embarcado",
                        lambda: "http://127.0.0.1:5599/v1")
    classificador = obter_classificador(ConfigAgente(provider="local"))
    assert isinstance(classificador, OpenAICompatClassificador)
    assert classificador.url == "http://127.0.0.1:5599/v1/chat/completions"


def _validation_error() -> ValidationError:
    """Gera um ValidationError real (não um mock) — mesmo tipo que
    `model_validate_json` levanta quando a LLM devolve algo fora do schema."""
    try:
        ItemClassificado(indice="não-é-índice", categoria=1, campo_pai=None)
    except ValidationError as e:
        return e
    raise AssertionError("esperava ValidationError")


def test_resposta_fora_do_schema_degrada_apos_esgotar_as_tentativas():
    # C-33: as duas tentativas (REQ-LLM-002) devolvem algo não-parseável ⇒
    # degradação para classificação manual com o motivo do schema, sem itens.
    fake = FakeClassificador(erro=_validation_error())
    resultado = classificar_grupos(GRUPOS, classificador=fake)
    assert fake.chamadas == 2
    assert resultado.por_indice == {}
    assert resultado.descartes == []
    assert resultado.motivos == ["REQ-LLM-002:SCHEMA"]


def test_resposta_fora_do_schema_recupera_na_segunda_tentativa():
    # A primeira resposta não bate o schema; a segunda (retry) é válida —
    # REQ-LLM-002 permite 1 recuperação, e o resultado final não carrega motivo.
    class FakeComRecuperacao:
        def __init__(self):
            self.chamadas = 0

        def classificar(self, grupos):
            self.chamadas += 1
            if self.chamadas == 1:
                raise _validation_error()
            return classificacao_fiel()

    fake = FakeComRecuperacao()
    resultado = classificar_grupos(GRUPOS, classificador=fake)
    assert fake.chamadas == 2
    assert resultado.por_indice == {
        0: ("renda", "salario_liquido"),
        1: ("fixas", "contas_casa"),
        2: ("fixas", "transporte"),
    }
    assert resultado.motivos == []


def test_openai_compat_classificador_sem_api_key_nao_envia_authorization(monkeypatch):
    # Sem api_key configurada, o header Authorization não deve ser enviado
    # (servidor local sem autenticação — caso comum de LM Studio/llama-server).
    capturado = {}

    def fake_post_json(url, payload, *, headers, timeout_s):
        capturado["headers"] = headers
        return {"choices": [{"message": {
            "content": classificacao_fiel().model_dump_json()}}]}

    monkeypatch.setattr("agent.classificacao._post_json", fake_post_json)
    cfg = ConfigAgente(provider="openai_compat",
                       base_url="http://127.0.0.1:1234/v1", api_key=None)
    resultado = OpenAICompatClassificador(cfg).classificar(GRUPOS)
    assert capturado["headers"] == {}
    assert resultado == classificacao_fiel()


def test_openai_compat_classificador_com_api_key_envia_bearer(monkeypatch):
    capturado = {}

    def fake_post_json(url, payload, *, headers, timeout_s):
        capturado["headers"] = headers
        return {"choices": [{"message": {
            "content": classificacao_fiel().model_dump_json()}}]}

    monkeypatch.setattr("agent.classificacao._post_json", fake_post_json)
    cfg = ConfigAgente(provider="openai_compat",
                       base_url="http://127.0.0.1:1234/v1", api_key="chave-x")
    OpenAICompatClassificador(cfg).classificar(GRUPOS)
    assert capturado["headers"] == {"Authorization": "Bearer chave-x"}


def test_ollama_classificador_usa_api_nativa_e_parseia_message_content(monkeypatch):
    # Dialeto nativo do Ollama: content vem em resposta["message"]["content"],
    # diferente do dialeto OpenAI-compatible (resposta["choices"][0][...]).
    def fake_post_json(url, payload, *, headers, timeout_s):
        assert url.endswith("/api/chat")
        return {"message": {"content": classificacao_fiel().model_dump_json()}}

    monkeypatch.setattr("agent.classificacao._post_json", fake_post_json)
    cfg = ConfigAgente(provider="local", base_url="http://localhost:11434/v1")
    resultado = OllamaClassificador(cfg).classificar(GRUPOS)
    assert resultado == classificacao_fiel()
