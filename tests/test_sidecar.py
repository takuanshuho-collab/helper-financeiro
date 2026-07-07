"""
Testes de contrato do sidecar (REQ-NF-005 / REQ-SEC-004).

Usam o `TestClient` do FastAPI (sem rede real). Cobrem a autenticação por
token, a validação de entrada e o roundtrip determinístico core <-> JSON,
incluindo os casos de borda (sem dívidas, reserva sem despesas, ordenação).
"""
import base64
import os
import time

from fastapi.testclient import TestClient

from agent.config import ConfigAgente
from agent.provider import FakeProvider
from contracts import AnaliseAgente, FatosFinanceiros
from sidecar.app import app, contexto_analise, contexto_extracao
from sidecar.security import VAR_TOKEN
from tests.test_extracao import CFG_TESTE, DOC_CONTRATO, FakeExtrator

TOKEN = "token-de-teste"
CABECALHO = {"X-HF-Token": TOKEN}
cliente = TestClient(app)

# PDF fantasma: o texto real é injetado via monkeypatch de extrair_texto_pdf_bytes.
PDF_B64 = base64.b64encode(b"%PDF-1.4 fake").decode()


def setup_module(_module):
    os.environ[VAR_TOKEN] = TOKEN


# --- Autenticação (REQ-SEC-004) ----------------------------------------------


def test_health_dispensa_token():
    resposta = cliente.get("/health")
    assert resposta.status_code == 200
    assert resposta.json()["status"] == "ok"


def test_diagnostico_sem_token_401():
    resposta = cliente.post("/diagnostico", json={})
    assert resposta.status_code == 401


def test_diagnostico_token_invalido_401():
    resposta = cliente.post(
        "/diagnostico", json={}, headers={"X-HF-Token": "errado"}
    )
    assert resposta.status_code == 401


# --- Validação de entrada (REQ-NF-005) ---------------------------------------


def test_payload_invalido_422():
    # Dívida sem os campos obrigatórios `credor`/`tipo`.
    payload = {"dividas": [{"saldo_devedor": 100.0}]}
    resposta = cliente.post("/diagnostico", json=payload, headers=CABECALHO)
    assert resposta.status_code == 422


# --- Roundtrip determinístico (REQ-NF-005) -----------------------------------


def test_diagnostico_roundtrip():
    payload = {
        "renda": {"salario_liquido": 5000.0},
        "fixas": {"moradia": 1500.0, "contas_casa": 500.0},
        "variaveis": {"mercado": 800.0},
        "reserva_emergencia": 6000.0,
        "dividas": [
            {
                "credor": "Banco X",
                "tipo": "Cartão de crédito",
                "saldo_devedor": 10000.0,
                "taxa_mensal": 0.09,
                "parcela": 1200.0,
                "parcelas_restantes": 12,
            }
        ],
    }
    resposta = cliente.post("/diagnostico", json=payload, headers=CABECALHO)
    assert resposta.status_code == 200
    dados = resposta.json()

    # Roll-up determinístico no core: despesas = 1500 + 500 + 800 = 2800.
    assert dados["despesas_totais"] == 2800.0
    assert dados["despesas_fixas"] == 2000.0
    assert dados["despesas_variaveis"] == 800.0
    assert dados["total_parcelas"] == 1200.0
    # Comprometimento = 1200 / 5000 = 0,24 → Saudável.
    assert dados["classificacao"] == "Saudável"
    # Cobertura da reserva = 6000 / 2800 ≈ 2,14 meses.
    assert 2.0 < dados["meses_reserva"] < 2.3

    # Campos derivados da dívida foram serializados.
    mais_cara = dados["divida_mais_cara"]
    assert mais_cara["credor"] == "Banco X"
    assert mais_cara["taxa_anual"] > 0
    assert mais_cara["custo_total_restante"] == 1200.0 * 12

    # Estatísticas ponderadas da tela Dívidas (T-804), calculadas no core.
    assert dados["custo_total_ate_quitar"] == 1200.0 * 12
    # Uma única dívida: a média ponderada é a própria taxa.
    assert abs(dados["taxa_media_ponderada"] - 0.09) < 1e-9


def test_diagnostico_sem_dividas():
    payload = {
        "renda": {"salario_liquido": 4000.0},
        "fixas": {"moradia": 1000.0},
    }
    resposta = cliente.post("/diagnostico", json=payload, headers=CABECALHO)
    assert resposta.status_code == 200
    dados = resposta.json()

    assert dados["divida_mais_cara"] is None
    assert dados["ranking"] == []
    assert dados["saldo_devedor_total"] == 0.0
    assert dados["total_parcelas"] == 0.0
    assert dados["classificacao"] == "Saudável"


def test_meses_reserva_nulo_sem_despesas():
    # Sem despesas informadas, a cobertura em meses não tem significado.
    payload = {"renda": {"salario_liquido": 3000.0}, "reserva_emergencia": 5000.0}
    resposta = cliente.post("/diagnostico", json=payload, headers=CABECALHO)
    assert resposta.status_code == 200
    assert resposta.json()["meses_reserva"] is None


def test_ranking_ordena_por_taxa():
    payload = {
        "renda": {"salario_liquido": 9000.0},
        "dividas": [
            {
                "credor": "Consignado",
                "tipo": "Consignado",
                "saldo_devedor": 6000.0,
                "taxa_mensal": 0.018,
                "parcela": 350.0,
                "parcelas_restantes": 20,
            },
            {
                "credor": "Cartão",
                "tipo": "Cartão de crédito",
                "saldo_devedor": 8000.0,
                "taxa_mensal": 0.12,
                "parcela": 900.0,
                "parcelas_restantes": 12,
            },
        ],
    }
    resposta = cliente.post("/diagnostico", json=payload, headers=CABECALHO)
    assert resposta.status_code == 200
    dados = resposta.json()

    # Avalanche: a mais cara (0,12) vem primeiro.
    assert dados["divida_mais_cara"]["credor"] == "Cartão"
    assert [d["credor"] for d in dados["ranking"]] == ["Cartão", "Consignado"]


# --- Estratégias (avalanche vs. bola de neve) --------------------------------


def test_estrategias_sem_token_401():
    resposta = cliente.post("/estrategias", json={"perfil": {}})
    assert resposta.status_code == 401


def test_estrategias_compara_metodos():
    payload = {
        "perfil": {
            "renda": {"salario_liquido": 5000.0},
            "dividas": [
                {
                    "credor": "Cartão",
                    "tipo": "Cartão de crédito",
                    "saldo_devedor": 3000.0,
                    "taxa_mensal": 0.12,
                    "parcela": 600.0,
                    "parcelas_restantes": 8,
                },
                {
                    "credor": "Consignado",
                    "tipo": "Consignado",
                    "saldo_devedor": 5000.0,
                    "taxa_mensal": 0.018,
                    "parcela": 300.0,
                    "parcelas_restantes": 20,
                },
            ],
        },
        "extra": 200.0,
    }
    resposta = cliente.post("/estrategias", json=payload, headers=CABECALHO)
    assert resposta.status_code == 200
    dados = resposta.json()

    assert set(dados) == {"avalanche", "bola_de_neve"}
    # Avalanche ataca a mais cara primeiro (Cartão, 12% a.m.).
    assert dados["avalanche"]["ordem"][0] == "Cartão"
    assert dados["avalanche"]["quitavel"] is True
    assert dados["avalanche"]["meses"] is not None


# --- Contrato PDF: extração local + interrupt→resume (REQ-F-014) --------------


def test_contrato_sem_token_401():
    resposta = cliente.post("/contrato/extrair", json={"pdf_base64": PDF_B64})
    assert resposta.status_code == 401


def test_contrato_base64_invalido_422():
    cliente.app.dependency_overrides[contexto_extracao] = lambda: (CFG_TESTE, FakeExtrator())
    try:
        resposta = cliente.post(
            "/contrato/extrair", json={"pdf_base64": "nao-e-base64!!"}, headers=CABECALHO
        )
        assert resposta.status_code == 422
    finally:
        cliente.app.dependency_overrides.clear()


def test_contrato_extrair_ia_com_citacao_e_confirma(monkeypatch):
    """Caminho feliz: IA local extrai com citação, pausa e retoma (ADR-0006)."""
    fake = FakeExtrator()
    cliente.app.dependency_overrides[contexto_extracao] = lambda: (CFG_TESTE, fake)
    monkeypatch.setattr("sidecar.app.extrair_texto_pdf_bytes", lambda _b: DOC_CONTRATO)
    try:
        resp = cliente.post(
            "/contrato/extrair",
            json={"pdf_base64": PDF_B64, "nome": "contrato.pdf"},
            headers=CABECALHO,
        )
        assert resp.status_code == 200
        dados = resp.json()
        assert dados["modo"] == "ia"
        assert dados["thread_id"]
        assert dados["descartados"] == []

        campos = {c["chave"]: c for c in dados["campos"]}
        assert {"credor", "saldo", "taxa", "parcela", "restantes"} <= set(campos)
        # Valor no formato do formulário + citação verbatim do documento.
        assert campos["saldo"]["valor"] == "10000,00"
        assert "10.000,00" in campos["saldo"]["fonte"]
        assert campos["taxa"]["valor"] == "2,00"  # fração 0.02 → 2,00%

        # interrupt→resume: a confirmação retoma o grafo pausado.
        resp2 = cliente.post(
            "/contrato/confirmar",
            json={"thread_id": dados["thread_id"], "confirmacao": {"saldo": "10000,00"}},
            headers=CABECALHO,
        )
        assert resp2.status_code == 200
        assert resp2.json()["ok"] is True
        assert fake.chamadas == 1
    finally:
        cliente.app.dependency_overrides.clear()


def test_contrato_extrair_fallback_classico(monkeypatch):
    """IA local indisponível ⇒ extração clássica por regex, sem citação."""
    fake = FakeExtrator(erro=ValueError("sem llm local"))
    cliente.app.dependency_overrides[contexto_extracao] = lambda: (CFG_TESTE, fake)
    monkeypatch.setattr("sidecar.app.extrair_texto_pdf_bytes", lambda _b: DOC_CONTRATO)
    try:
        resp = cliente.post(
            "/contrato/extrair", json={"pdf_base64": PDF_B64}, headers=CABECALHO
        )
        assert resp.status_code == 200
        dados = resp.json()
        assert dados["modo"] == "classico"
        assert dados["thread_id"] is None
        chaves = {c["chave"] for c in dados["campos"]}
        # O regex acha taxa e parcelas no DOC; nenhum campo traz citação.
        assert {"taxa", "restantes"} <= chaves
        assert all(c["fonte"] == "" for c in dados["campos"])
        # Diagnóstico: o motivo da queda e o alvo efetivo da LLM (ADR-0010).
        assert "ERRO_PROVIDER:ValueError" in dados["motivos"]
        assert dados["llm"]["endpoint_local"] is True
        assert "1234" not in dados["llm"]["base_url"]  # CFG_TESTE usa o default
    finally:
        cliente.app.dependency_overrides.clear()


def test_fusao_classica_completa_campos_da_ia():
    """LLM pequena devolve null em campos presentes no doc ⇒ resgate sem LLM."""
    from sidecar.app import _fundir_com_classico

    campos = {
        "credor": {"valor": "Banco X", "trecho_fonte": "Credor: Banco X",
                   "confianca": 0.9},
        "tipo": None,
        "saldo_devedor": None,
        "taxa_mensal": {"valor": 0.0142, "trecho_fonte": "1,42% ao mês",
                        "confianca": 0.9},
        "parcela": {"valor": 899.47, "trecho_fonte": "96x de R$ 899,47",
                    "confianca": 0.9},
        "parcelas_restantes": None,
    }
    texto = ("Contrato de empréstimo consignado\n"
             "Total financiado Período de pagamento\n"
             "R$ 46.533,20 Agosto/2026 a Julho/2034\n")
    fundido = _fundir_com_classico(campos, texto)

    # `restantes` derivado do trecho já citado (e verificado) da parcela.
    assert fundido["parcelas_restantes"]["valor"] == 96
    assert fundido["parcelas_restantes"]["trecho_fonte"] == "96x de R$ 899,47"
    # `saldo` e `tipo` resgatados pelo regex clássico (sem citação).
    assert fundido["saldo_devedor"]["valor"] == 46533.20
    assert fundido["saldo_devedor"]["trecho_fonte"] == ""
    assert fundido["tipo"]["valor"] == "Consignado"
    # O que a IA achou nunca é sobrescrito.
    assert fundido["parcela"]["valor"] == 899.47
    assert fundido["credor"]["valor"] == "Banco X"


def test_contexto_trunca_para_openai_compat_local():
    """LM Studio (sem embeddings): trunca o documento em vez de tentar /api/embed."""
    from agent.config import ConfigAgente
    from sidecar.app import LIMITE_EXTRACAO_LLM, _contexto_seguro

    longo = "x" * (LIMITE_EXTRACAO_LLM + 500)
    cfg = ConfigAgente(provider="openai_compat", base_url="http://localhost:1234/v1")
    assert _contexto_seguro(longo, cfg) == longo[:LIMITE_EXTRACAO_LLM]


# --- Tela Análise: pacote determinístico (T-902, REQ-F-015) -------------------

PERFIL_ANALISE = {
    "renda": {"salario_liquido": 6000.0},
    "fixas": {"moradia": 1500.0},
    "dividas": [
        {
            "credor": "Cartão Banco João da Silva",
            "tipo": "Cartão de crédito",
            "saldo_devedor": 4000.0,
            "taxa_mensal": 0.12,
            "parcela": 800.0,
            "parcelas_restantes": 10,
        },
        {
            "credor": "Consignado Maria Pereira",
            "tipo": "Consignado",
            "saldo_devedor": 6000.0,
            "taxa_mensal": 0.015,
            "parcela": 350.0,
            "parcelas_restantes": 20,
        },
    ],
}


def test_analise_sem_token_401():
    resposta = cliente.post("/analise", json={"perfil": {}})
    assert resposta.status_code == 401


def test_analise_pacote_deterministico():
    payload = {"perfil": PERFIL_ANALISE, "extra": 300.0, "taxa_alvo": 0.018}
    resposta = cliente.post("/analise", json=payload, headers=CABECALHO)
    assert resposta.status_code == 200
    dados = resposta.json()

    # Estratégias recalculadas com o extra; avalanche nunca paga mais juros.
    ava = dados["estrategias"]["avalanche"]
    bola = dados["estrategias"]["bola_de_neve"]
    assert ava["quitavel"] and bola["quitavel"]
    assert dados["economia_avalanche"] == round(
        bola["juros_pagos"] - ava["juros_pagos"], 2)
    assert dados["economia_avalanche"] >= 0

    # Portabilidade: só o cartão (12% a.m.) supera a taxa-alvo de 1,8% a.m.
    ops = dados["oportunidades"]
    assert [o["credor"] for o in ops] == ["Cartão Banco João da Silva"]
    assert ops[0]["taxa_mensal"] == 0.12
    assert ops[0]["parcelas_restantes"] == 10
    assert ops[0]["economia_mensal"] > 0
    assert dados["economia_total_portabilidade"] == ops[0]["economia_total"]

    assert dados["recomendacoes"]  # regras do core sempre orientam algo


def test_analise_taxa_alvo_alta_sem_oportunidades():
    payload = {"perfil": PERFIL_ANALISE, "taxa_alvo": 0.20}
    resposta = cliente.post("/analise", json=payload, headers=CABECALHO)
    assert resposta.status_code == 200
    dados = resposta.json()
    assert dados["oportunidades"] == []
    assert dados["economia_total_portabilidade"] == 0.0


# --- Análise sênior: job assíncrono + fronteira cloud (H2/SEC-003) -------------


class ProviderEspiao:
    """Grava o payload que REALMENTE chegaria ao LLM (a fronteira cloud)."""

    def __init__(self, erro: Exception | None = None):
        self.payloads: list[str] = []
        self._fake = FakeProvider()
        self._erro = erro

    def analisar(self, fatos: FatosFinanceiros) -> AnaliseAgente:
        self.payloads.append(fatos.model_dump_json())
        if self._erro:
            raise self._erro
        return self._fake.analisar(fatos)


def _esperar_job(job_id: str, timeout_s: float = 5.0) -> dict:
    """Faz poll até o job sair de `rodando` (o teste roda com FakeProvider)."""
    fim = time.monotonic() + timeout_s
    while time.monotonic() < fim:
        resp = cliente.get(f"/analise/ia/{job_id}", headers=CABECALHO)
        assert resp.status_code == 200
        dados = resp.json()
        if dados["status"] != "rodando":
            return dados
        time.sleep(0.05)
    raise AssertionError("job da IA não terminou no tempo do teste")


def test_analise_ia_job_completo_e_anonimizacao_da_fronteira():
    """H2/SEC-003: nomes reais NUNCA cruzam a fronteira do provider; a
    desanonimização acontece só na seção devolvida à tela (exibição local)."""
    espiao = ProviderEspiao()
    cfg = ConfigAgente(provider="fake", cache=False)
    cliente.app.dependency_overrides[contexto_analise] = lambda: (cfg, espiao)
    try:
        resp = cliente.post("/analise/ia",
                            json={"perfil": PERFIL_ANALISE, "extra": 300.0},
                            headers=CABECALHO)
        assert resp.status_code == 200
        dados = _esperar_job(resp.json()["job_id"])

        # O payload enviado ao LLM só tem tokens — nenhum credor real, nenhum CPF.
        assert len(espiao.payloads) == 1
        payload_llm = espiao.payloads[0]
        assert "CREDOR_1" in payload_llm and "CREDOR_2" in payload_llm
        assert "João" not in payload_llm
        assert "Maria" not in payload_llm

        # A seção exibida ao usuário volta com os nomes reais restaurados.
        assert dados["status"] == "pronto"
        secao = dados["secao"]
        assert secao["modo"] == "completo"
        texto_secao = str(secao)
        assert "Cartão Banco João da Silva" in texto_secao
        assert "CREDOR_1" not in texto_secao
        assert secao["aviso_legal"]
    finally:
        cliente.app.dependency_overrides.clear()


def test_analise_ia_provider_falho_degrada_sem_500():
    """P8: falha do LLM degrada para o determinístico — o job nunca vira 500."""
    espiao = ProviderEspiao(erro=ValueError("llm fora do ar"))
    cfg = ConfigAgente(provider="fake", cache=False)
    cliente.app.dependency_overrides[contexto_analise] = lambda: (cfg, espiao)
    try:
        resp = cliente.post("/analise/ia", json={"perfil": PERFIL_ANALISE},
                            headers=CABECALHO)
        dados = _esperar_job(resp.json()["job_id"])
        assert dados["status"] == "pronto"
        assert dados["secao"]["modo"] == "degradado"
        assert dados["secao"]["motivos"]  # diz por que degradou
    finally:
        cliente.app.dependency_overrides.clear()


def test_analise_ia_job_desconhecido_404():
    resp = cliente.get("/analise/ia/nao-existe", headers=CABECALHO)
    assert resp.status_code == 404


# --- Exportações .xlsx/.docx (T-902) ------------------------------------------


def test_exportar_planilha_e_relatorio(tmp_path):
    xlsx = tmp_path / "diagnostico.xlsx"
    resp = cliente.post(
        "/exportar/planilha",
        json={"perfil": PERFIL_ANALISE, "caminho": str(xlsx),
              "extra": 300.0, "taxa_alvo": 0.018},
        headers=CABECALHO,
    )
    assert resp.status_code == 200
    assert resp.json()["caminho"] == str(xlsx)
    assert xlsx.stat().st_size > 0

    docx = tmp_path / "relatorio.docx"
    secao_ia = {"modo": "completo", "sumario": "Resumo de teste.",
                "diagnostico": "Diagnóstico de teste.", "confianca": 0.8,
                "aviso_legal": "Conteúdo assistido por IA."}
    resp = cliente.post(
        "/exportar/relatorio",
        json={"perfil": PERFIL_ANALISE, "caminho": str(docx),
              "nome_usuario": "Fulano", "secao_ia": secao_ia},
        headers=CABECALHO,
    )
    assert resp.status_code == 200
    assert docx.stat().st_size > 0


def test_exportar_caminho_invalido_400():
    resp = cliente.post(
        "/exportar/planilha",
        json={"perfil": PERFIL_ANALISE,
              "caminho": "Z:/pasta/que/nao/existe/x.xlsx"},
        headers=CABECALHO,
    )
    assert resp.status_code == 400
    assert "salvar" in resp.json()["detail"]


def test_contrato_pdf_sem_texto(monkeypatch):
    """PDF escaneado (sem texto) ⇒ aviso, sem consultar o modelo."""
    monkeypatch.setattr("sidecar.app.extrair_texto_pdf_bytes", lambda _b: "   ")
    resp = cliente.post(
        "/contrato/extrair", json={"pdf_base64": PDF_B64}, headers=CABECALHO
    )
    assert resp.status_code == 200
    dados = resp.json()
    assert dados["modo"] == "vazio"
    assert dados["aviso"]
    assert dados["campos"] == []
