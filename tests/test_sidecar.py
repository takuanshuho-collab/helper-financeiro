"""
Testes de contrato do sidecar (REQ-NF-005 / REQ-SEC-004).

Usam o `TestClient` do FastAPI (sem rede real). Cobrem a autenticação por
token, a validação de entrada e o roundtrip determinístico core <-> JSON,
incluindo os casos de borda (sem dívidas, reserva sem despesas, ordenação).
"""
import os

from fastapi.testclient import TestClient

from sidecar.app import app
from sidecar.security import VAR_TOKEN

TOKEN = "token-de-teste"
CABECALHO = {"X-HF-Token": TOKEN}
cliente = TestClient(app)


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
