"""
Bancada de aderência de schema por modelo (auditoria M2, ADR-0005).

Compara modelos do Ollama local (ex.: 7B vs 14B) em 3 métricas por chamada:
  - schema   : a resposta valida como `AnaliseAgente`?
  - grounding: nenhum número fabricado (REQ-GRD-001)?
  - conteúdo : sem recomendação de investimento (REQ-GRD-004)?

Uso:
  uv run python scripts/bench_schema.py --modelos qwen2.5:7b qwen2.5:14b --n 5

Fora do CI (exige Ollama e demora minutos); o resultado orienta a escolha do
HF_MODEL padrão.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # noqa: E402 — script avulso

from agent.agente import montar_fatos  # noqa: E402
from agent.config import ConfigAgente  # noqa: E402
from agent.provider import OllamaProvider  # noqa: E402
from core.models import Divida, PerfilFinanceiro  # noqa: E402
from guardrails.conteudo import detectar_conteudo_indevido  # noqa: E402
from guardrails.validador_numerico import validar as validar_numeros  # noqa: E402

# Mesmo caso-ouro do harness (PERFIL_ATENCAO, docs/HARNESS §2).
PERFIL = PerfilFinanceiro(
    renda_liquida=5000, despesas_fixas=2200, despesas_variaveis=800,
    reserva_emergencia=0, saldo_fgts=3000,
    dividas=[
        Divida("Cartão Banco A", "Cartão de crédito", 8000, 0.12, 900, 12),
        Divida("CDC Veículo", "CDC (Crédito Direto ao Consumidor)", 20000, 0.025, 700, 36),
        Divida("Consignado Servidor", "Consignado", 6000, 0.018, 350, 20),
    ],
)


def avaliar_modelo(modelo: str, n: int, timeout_s: int) -> dict[str, float]:
    cfg = ConfigAgente(provider="local", model=modelo, timeout_s=timeout_s, cache=False)
    provider = OllamaProvider(cfg)
    fatos, _ = montar_fatos(PERFIL, extra_mensal=500)

    schema_ok = grounding_ok = conteudo_ok = 0
    latencias: list[float] = []
    for i in range(1, n + 1):
        inicio = time.perf_counter()
        try:
            analise = provider.analisar(fatos)
        except Exception as e:  # noqa: BLE001 — no bench, falha é dado, não erro
            print(f"  [{modelo}] chamada {i}/{n}: FALHA de schema/rede ({type(e).__name__})")
            latencias.append(time.perf_counter() - inicio)
            continue
        latencias.append(time.perf_counter() - inicio)
        schema_ok += 1
        grounding_ok += 0 if validar_numeros(fatos, analise) else 1
        conteudo_ok += 0 if detectar_conteudo_indevido(analise) else 1
        print(f"  [{modelo}] chamada {i}/{n}: ok em {latencias[-1]:.1f}s")

    return {
        "schema": schema_ok / n,
        "grounding": grounding_ok / n,
        "conteudo": conteudo_ok / n,
        "latencia_media_s": sum(latencias) / len(latencias) if latencias else 0.0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Bancada de aderência de schema por modelo (Ollama local).")
    parser.add_argument("--modelos", nargs="+", default=["qwen2.5:7b", "qwen2.5:14b"])
    parser.add_argument("--n", type=int, default=5, help="chamadas por modelo")
    parser.add_argument("--timeout", type=int, default=300)
    args = parser.parse_args()

    resultados: dict[str, dict[str, float]] = {}
    for modelo in args.modelos:
        print(f"\n=== {modelo} ===")
        resultados[modelo] = avaliar_modelo(modelo, args.n, args.timeout)

    print(f"\n{'modelo':<20} {'schema':>8} {'grounding':>10} {'conteúdo':>9} {'latência':>9}")
    for modelo, r in resultados.items():
        print(f"{modelo:<20} {r['schema']:>7.0%} {r['grounding']:>9.0%} "
              f"{r['conteudo']:>8.0%} {r['latencia_media_s']:>8.1f}s")
    print("\ngrounding/conteúdo são % das N chamadas (falha de schema conta como reprova).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
