"""
Testes de contrato do sidecar (REQ-NF-005 / REQ-SEC-004).

Usam o `TestClient` do FastAPI (sem rede real). Cobrem liveness, a exigência do
token de sessão e o roundtrip determinístico core <-> JSON.
"""
import os

from fastapi.testclient import TestClient

from sidecar.app import app
from sidecar.security import VAR_TOKEN

TOKEN = "token-de-teste"
cliente = TestClient(app)


def setup_module(_module):
    os.environ[VAR_TOKEN] = TOKEN


def test_health_dispensa_token():
    resposta = cliente.get("/health")
    assert resposta.status_code == 200
    assert resposta.json()["status"] == "ok"


def test_diagnostico_exige_token():
    resposta = cliente.post("/diagnostico", json={})
    assert resposta.status_code == 401


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
    resposta = cliente.post(
        "/diagnostico", json=payload, headers={"X-HF-Token": TOKEN}
    )
    assert resposta.status_code == 200
    dados = resposta.json()

    # Roll-up determinístico no core: despesas = 1500 + 500 + 800 = 2800.
    assert dados["despesas_totais"] == 2800.0
    assert dados["total_parcelas"] == 1200.0
    # Comprometimento = 1200 / 5000 = 0,24 → Saudável.
    assert dados["classificacao"] == "Saudável"
    assert dados["divida_mais_cara"]["credor"] == "Banco X"
    # Cobertura da reserva = 6000 / 2800 ≈ 2,14 meses.
    assert 2.0 < dados["meses_reserva"] < 2.3
