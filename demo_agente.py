"""
Demonstração da camada de IA (offline, FakeProvider).

Mostra o pipeline: core → fatos anonimizados → agente → guardrails → resultado,
com os nomes reais restaurados apenas na exibição local.

Rode com:  python demo_agente.py
"""
from agent.agente import analisar
from agent.config import ConfigAgente
from agent.provider import FakeProvider
from core.models import Divida, PerfilFinanceiro
from guardrails.pii import anonimizar_credores, desanonimizar

perfil = PerfilFinanceiro(
    renda_liquida=5000, despesas_fixas=2200, despesas_variaveis=800,
    dividas=[
        Divida("Cartão Banco A", "Cartão de crédito", 8000, 0.12, 900, 12),
        Divida("CDC Veículo", "CDC (Crédito Direto ao Consumidor)", 20000, 0.025, 700, 36),
        Divida("Consignado Servidor", "Consignado", 6000, 0.018, 350, 20),
    ],
)

cfg = ConfigAgente(provider="fake")
res = analisar(perfil, extra_mensal=500, cfg=cfg, provider=FakeProvider())

# Reconstrói o mapa para desanonimizar a exibição (nomes reais só localmente).
_, mapa = anonimizar_credores([d.credor for d in perfil.dividas])

print(f"MODO: {res.modo}  | guardrails violados: {res.guardrails_violados}\n")
if res.analise:
    a = res.analise
    print("SUMÁRIO:\n", desanonimizar(a.sumario_executivo, mapa), "\n")
    print("DIAGNÓSTICO:\n", desanonimizar(a.diagnostico_interpretado, mapa), "\n")
    print("PRIORIDADES:")
    for p in a.prioridades:
        print(f"  {p.ordem}. {desanonimizar(p.credor_token, mapa)} — "
              f"{desanonimizar(p.justificativa, mapa)}")
    print(f"\nConfiança auto-avaliada: {a.confianca}")
