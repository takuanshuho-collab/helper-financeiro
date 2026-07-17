"""
Providers reais offline (T-201/T-202, ADR-0005) — Gate A.

Um servidor HTTP local (porta efêmera) simula o Ollama e o endpoint
OpenAI-compatible, então o caminho REAL de rede (urllib, headers, corpo,
parse) é exercitado sem tocar a internet. O T-206 (provider fora do ar)
está em `tests/test_degradacao.py`.
"""
import email.message
import io
import json
import threading
import urllib.error
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from agent.agente import analisar, montar_fatos
from agent.config import ConfigAgente
from agent.provider import FakeProvider, OllamaProvider, OpenAICompatProvider, schema_estrito
from contracts import AnaliseAgente


@dataclass
class EstadoServidor:
    url: str = ""
    resposta: dict = field(default_factory=dict)
    requisicoes: list = field(default_factory=list)


@pytest.fixture
def servidor():
    """Servidor HTTP local: devolve `estado.resposta` e grava cada requisição."""
    estado = EstadoServidor()

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            tamanho = int(self.headers["Content-Length"])
            corpo = json.loads(self.rfile.read(tamanho))
            estado.requisicoes.append({
                "caminho": self.path,
                "corpo": corpo,
                "auth": self.headers.get("Authorization"),
            })
            dados = json.dumps(estado.resposta).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(dados)))
            self.end_headers()
            self.wfile.write(dados)

        def log_message(self, *args):  # silencia o stderr do http.server
            pass

    srv = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    estado.url = f"http://127.0.0.1:{srv.server_port}"
    yield estado
    srv.shutdown()
    srv.server_close()


def _analise_valida_json(perfil) -> str:
    """Uma AnaliseAgente aderente e fundamentada nos fatos (via FakeProvider)."""
    fatos, _ = montar_fatos(perfil)
    return FakeProvider().analisar(fatos).model_dump_json()


# ------------------------------------------------------------- OllamaProvider
def test_ollama_provider_fala_a_api_nativa(servidor, perfil_atencao):
    servidor.resposta = {"message": {"content": _analise_valida_json(perfil_atencao)}}
    cfg = ConfigAgente(provider="local", base_url=servidor.url + "/v1")  # /v1 é normalizado
    fatos, _ = montar_fatos(perfil_atencao)

    analise = OllamaProvider(cfg).analisar(fatos)

    assert analise.confianca == 0.9
    req = servidor.requisicoes[0]
    assert req["caminho"] == "/api/chat"
    assert req["corpo"]["stream"] is False
    # Structured output: o JSON Schema completo vai no `format` (ADR-0005).
    assert req["corpo"]["format"]["properties"].keys() >= {"sumario_executivo", "confianca"}
    # Os FATOS entram delimitados como dado, não instrução (P5/H5).
    assert "<FATOS>" in req["corpo"]["messages"][1]["content"]


def test_ollama_resposta_fora_do_schema_degrada(servidor, perfil_atencao, monkeypatch):
    # HF_BASE_URL definido = usuário apontou o próprio servidor (Ollama): tem
    # precedência sobre o runtime embarcado (ADR-0002/0016 §E).
    monkeypatch.setenv("HF_BASE_URL", servidor.url)
    servidor.resposta = {"message": {"content": '{"nada": "a ver"}'}}
    cfg = ConfigAgente(provider="local", base_url=servidor.url)

    resultado = analisar(perfil_atencao, cfg=cfg)

    assert resultado.modo == "degradado"
    assert "REQ-LLM-002:SCHEMA" in resultado.guardrails_violados
    assert len(servidor.requisicoes) == 2  # 1 tentativa + 1 recuperação


def test_pipeline_completo_com_provider_real(servidor, perfil_atencao, monkeypatch):
    """E2E offline: analisar() → OllamaProvider → HTTP → guardrails → completo."""
    monkeypatch.setenv("HF_BASE_URL", servidor.url)  # servidor do usuário tem precedência
    servidor.resposta = {"message": {"content": _analise_valida_json(perfil_atencao)}}
    cfg = ConfigAgente(provider="local", base_url=servidor.url)

    resultado = analisar(perfil_atencao, cfg=cfg)

    assert resultado.modo == "completo"
    assert resultado.guardrails_violados == []
    assert "apoio à decisão" in resultado.analise.sumario_executivo


# ------------------------------------------------------- OpenAICompatProvider
def test_openai_compat_envia_chave_e_schema_estrito(servidor, perfil_atencao):
    servidor.resposta = {
        "choices": [{"message": {"content": _analise_valida_json(perfil_atencao)}}]}
    cfg = ConfigAgente(provider="openai_compat", base_url=servidor.url + "/v1",
                       api_key="chave-teste")
    fatos, _ = montar_fatos(perfil_atencao)

    analise = OpenAICompatProvider(cfg).analisar(fatos)

    assert analise.prioridades  # parse do choices[0].message.content funcionou
    req = servidor.requisicoes[0]
    assert req["caminho"] == "/v1/chat/completions"
    assert req["auth"] == "Bearer chave-teste"
    rf = req["corpo"]["response_format"]
    assert rf["type"] == "json_schema"
    assert rf["json_schema"]["strict"] is True


def test_openai_compat_remoto_sem_chave_degrada_sem_excecao(perfil_atencao, monkeypatch):
    """Endpoint REMOTO sem chave degrada limpo (SEC-002); o determinístico sobrevive."""
    monkeypatch.delenv("HF_API_KEY", raising=False)
    cfg = ConfigAgente(provider="openai_compat", base_url="https://api.openai.com/v1")

    resultado = analisar(perfil_atencao, cfg=cfg)

    assert resultado.modo == "degradado"
    assert resultado.guardrails_violados == ["ERRO_CONFIG:RuntimeError"]
    assert resultado.fatos.saldo_devedor_total > 0  # o determinístico sobrevive


def test_openai_compat_local_dispensa_chave(perfil_atencao, monkeypatch):
    """Servidor local (loopback, ex.: LM Studio) não exige chave (ADR-0010)."""
    monkeypatch.delenv("HF_API_KEY", raising=False)
    cfg = ConfigAgente(provider="openai_compat", base_url="http://localhost:1234/v1")
    # Não deve levantar por falta de chave; a URL é montada normalmente.
    prov = OpenAICompatProvider(cfg)
    assert prov.url == "http://localhost:1234/v1/chat/completions"


def test_schema_estrito_endurece_todos_os_objetos():
    """Modo strict OpenAI: additionalProperties=false e required completo em cada nó."""
    schema = schema_estrito()

    def verificar(no):
        if isinstance(no, dict):
            if no.get("type") == "object" and "properties" in no:
                assert no["additionalProperties"] is False
                assert set(no["required"]) == set(no["properties"].keys())
            for valor in no.values():
                verificar(valor)
        elif isinstance(no, list):
            for item in no:
                verificar(item)

    verificar(schema)
    assert "$defs" in schema  # os modelos aninhados (Prioridade etc.) estão lá


# ------------------------- Fallback de gramática do llama-server (T-2505)
# Corpo REAL do 400 capturado na aceitação de campo de 2026-07-16 (phi-3.5,
# builds b9966/b10043): o `llama-server` recusa a gramática do json_schema
# estrito por bug do llama.cpp com o tokenizer (issues #12597/#21017/#23677).
CORPO_400_GRAMATICA = json.dumps({"error": {
    "code": 400,
    "message": ("Failed to initialize samplers: Unexpected empty grammar "
                "stack after accepting piece: | (29989)"),
    "type": "invalid_request_error",
}})


def _http_error(codigo: int, corpo: str) -> urllib.error.HTTPError:
    """Constrói um HTTPError legível (com `.read()`) como o urllib levantaria."""
    return urllib.error.HTTPError(
        "http://127.0.0.1:1234/v1/chat/completions", codigo, "erro",
        email.message.Message(), io.BytesIO(corpo.encode("utf-8")))


class _PostFake:
    """Substitui `agent.provider._post_json`: para cada chamada, ou levanta a
    exceção enfileirada, ou devolve o dict enfileirado. Grava os payloads."""

    def __init__(self, acoes: list) -> None:
        self.acoes = list(acoes)
        self.payloads: list[dict] = []

    def __call__(self, url, payload, headers, timeout_s):  # noqa: ANN001, ARG002
        self.payloads.append(payload)
        acao = self.acoes.pop(0)
        if isinstance(acao, BaseException):
            raise acao
        return acao


def _resposta_openai(perfil) -> dict:
    return {"choices": [{"message": {"content": _analise_valida_json(perfil)}}]}


def _provider_local() -> OpenAICompatProvider:
    return OpenAICompatProvider(ConfigAgente(
        provider="openai_compat", base_url="http://localhost:1234/v1"))


def test_fallback_gramatica_recupera_com_json_object(perfil_atencao, monkeypatch):
    """400 de gramática na 1ª ⇒ reenvia com json_object + schema no prompt."""
    fake = _PostFake([_http_error(400, CORPO_400_GRAMATICA),
                      _resposta_openai(perfil_atencao)])
    monkeypatch.setattr("agent.provider._post_json", fake)
    fatos, _ = montar_fatos(perfil_atencao)

    analise = _provider_local().analisar(fatos)

    assert isinstance(analise, AnaliseAgente)
    assert len(fake.payloads) == 2
    assert fake.payloads[0]["response_format"]["type"] == "json_schema"
    # A 2ª requisição troca para json_object e injeta o schema na última msg.
    assert fake.payloads[1]["response_format"] == {"type": "json_object"}
    ultima = fake.payloads[1]["messages"][-1]
    assert ultima["role"] == "user"
    assert json.dumps(schema_estrito()) in ultima["content"]
    # Sem a gramática restringindo a amostragem, a aderência ao schema depende
    # do modelo — temperatura ZERO no fallback (medição de campo 2026-07-17:
    # 0.2 ⇒ 1/3 análises válidas; 0.0 ⇒ 4/4). O caminho forte mantém 0.2.
    assert fake.payloads[1]["temperature"] == 0.0
    assert fake.payloads[0]["temperature"] == 0.2


def test_fallback_gramatica_nas_duas_propaga(perfil_atencao, monkeypatch):
    """Recusa de gramática nas duas tentativas ⇒ o HTTPError da 2ª sobe (P8)."""
    fake = _PostFake([_http_error(400, CORPO_400_GRAMATICA),
                      _http_error(400, CORPO_400_GRAMATICA)])
    monkeypatch.setattr("agent.provider._post_json", fake)
    fatos, _ = montar_fatos(perfil_atencao)

    with pytest.raises(urllib.error.HTTPError):
        _provider_local().analisar(fatos)
    assert len(fake.payloads) == 2


def test_400_de_outro_corpo_propaga_sem_fallback(perfil_atencao, monkeypatch):
    """400 que NÃO é recusa de gramática sobe direto, sem 2ª chamada."""
    corpo = json.dumps({"error": {"message": "context length exceeded"}})
    fake = _PostFake([_http_error(400, corpo)])
    monkeypatch.setattr("agent.provider._post_json", fake)
    fatos, _ = montar_fatos(perfil_atencao)

    with pytest.raises(urllib.error.HTTPError):
        _provider_local().analisar(fatos)
    assert len(fake.payloads) == 1  # uma única chamada


def test_500_propaga_sem_fallback(perfil_atencao, monkeypatch):
    """Erro de servidor (500) sobe direto, sem fallback."""
    fake = _PostFake([_http_error(500, "boom")])
    monkeypatch.setattr("agent.provider._post_json", fake)
    fatos, _ = montar_fatos(perfil_atencao)

    with pytest.raises(urllib.error.HTTPError):
        _provider_local().analisar(fatos)
    assert len(fake.payloads) == 1


def test_memoizacao_segunda_analise_vai_direto_ao_fallback(perfil_atencao, monkeypatch):
    """Após a 1ª recusa, a MESMA instância pula o json_schema (1 requisição)."""
    fake = _PostFake([_http_error(400, CORPO_400_GRAMATICA),
                      _resposta_openai(perfil_atencao),   # fallback da 1ª análise
                      _resposta_openai(perfil_atencao)])  # 2ª análise: direto
    monkeypatch.setattr("agent.provider._post_json", fake)
    fatos, _ = montar_fatos(perfil_atencao)
    prov = _provider_local()

    prov.analisar(fatos)
    assert len(fake.payloads) == 2  # 1ª análise: schema (400) + fallback

    prov.analisar(fatos)
    assert len(fake.payloads) == 3  # 2ª análise: uma só, já no fallback
    assert fake.payloads[2]["response_format"] == {"type": "json_object"}


def test_fallback_preserva_correcao_do_guardrail(perfil_atencao, monkeypatch):
    """No fallback, a correção do retry-correção vem ANTES do schema injetado."""
    fake = _PostFake([_http_error(400, CORPO_400_GRAMATICA),
                      _resposta_openai(perfil_atencao)])
    monkeypatch.setattr("agent.provider._post_json", fake)
    fatos, _ = montar_fatos(perfil_atencao)

    _provider_local().analisar_com_correcao(fatos, "CORRECAO_NUMEROS_ORFAOS")

    conteudos = [m["content"] for m in fake.payloads[1]["messages"]]
    assert any("CORRECAO_NUMEROS_ORFAOS" in c for c in conteudos)
    # O schema segue como ÚLTIMA mensagem, depois da correção.
    assert json.dumps(schema_estrito()) in conteudos[-1]
