"""
Providers reais offline (T-201/T-202, ADR-0005) — Gate A.

Um servidor HTTP local (porta efêmera) simula o Ollama e o endpoint
OpenAI-compatible, então o caminho REAL de rede (urllib, headers, corpo,
parse) é exercitado sem tocar a internet. O T-206 (provider fora do ar)
está em `tests/test_degradacao.py`.
"""
import json
import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from agent.agente import analisar, montar_fatos
from agent.config import ConfigAgente
from agent.provider import FakeProvider, OllamaProvider, OpenAICompatProvider, schema_estrito


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
