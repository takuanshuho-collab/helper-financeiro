"""Diagnóstico rápido do LLM local de extração (ADR-0010).

Isola o elo sidecar↔servidor local (LM Studio/Ollama) do Electron: lê a config
efetiva do ambiente, monta o extrator e faz UMA extração de teste, imprimindo o
resultado ou o erro exato.

Uso (PowerShell, na raiz do projeto), apontando para o seu LM Studio:

    $env:HF_PROVIDER = 'openai_compat'
    $env:HF_BASE_URL = 'http://localhost:1234/v1'
    $env:HF_MODEL    = '<id do modelo carregado no LM Studio>'
    .venv\\Scripts\\python.exe scripts\\diag_llm.py
"""
from __future__ import annotations

import sys
from pathlib import Path

# Rodar o script direto põe scripts/ no sys.path, não a raiz — corrige aqui.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.config import carregar_config  # noqa: E402
from agent.extracao import obter_extrator  # noqa: E402

DOC = (
    "CONTRATO DE EMPRESTIMO PESSOAL\n"
    "Credor: Banco Teste S.A.\n"
    "Saldo devedor atual: R$ 10.000,00\n"
    "Taxa de juros: 2,00% ao mes\n"
    "Prazo remanescente: 12 parcelas\n"
    "Valor da parcela mensal: R$ 945,60\n"
)


def main() -> None:
    cfg = carregar_config()
    print("provider      :", cfg.provider)
    print("base_url      :", cfg.base_url)
    print("model         :", cfg.model)
    print("endpoint_local:", cfg.endpoint_local)
    print("tem_api_key   :", bool(cfg.api_key))
    print("-" * 44)

    try:
        extrator = obter_extrator(cfg)
    except Exception as e:  # noqa: BLE001 — queremos o erro exato, não o traceback
        print("obter_extrator FALHOU:", type(e).__name__, "-", e)
        return
    print("extrator      :", type(extrator).__name__)
    print("chamando o modelo local... (pode levar alguns segundos)")

    try:
        resultado = extrator.extrair(DOC)
    except Exception as e:  # noqa: BLE001 — mostra a causa (conexão, modelo, schema)
        print("extrair FALHOU:", type(e).__name__, "-", e)
        return
    print("OK — extração assistida funcionou:")
    print(resultado.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
