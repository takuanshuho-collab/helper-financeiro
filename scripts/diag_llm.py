"""Diagnóstico rápido do LLM local de extração (ADR-0010).

Isola o elo sidecar↔servidor local (LM Studio/Ollama) do Electron: lê a config
efetiva do ambiente, monta o extrator e roda UMA extração — no contrato de teste
embutido OU num PDF real que você passar — imprimindo os campos extraídos, quais
sobrevivem ao quote-check e o que foi descartado (o mesmo caminho do app).

Uso (PowerShell, na raiz do projeto), apontando para o seu LM Studio:

    $env:HF_PROVIDER = 'openai_compat'
    $env:HF_BASE_URL = 'http://localhost:1234/v1'
    $env:HF_MODEL    = '<id do modelo carregado no LM Studio>'
    $env:HF_TIMEOUT  = '300'
    .venv\\Scripts\\python.exe scripts\\diag_llm.py                    # doc de teste
    .venv\\Scripts\\python.exe scripts\\diag_llm.py "C:\\caminho\\contrato.pdf"  # PDF real
"""
from __future__ import annotations

import sys
from pathlib import Path

# Rodar o script direto põe scripts/ no sys.path, não a raiz — corrige aqui.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.config import ConfigAgente, carregar_config  # noqa: E402
from agent.extracao import obter_extrator, verificar_extracao  # noqa: E402

DOC = (
    "CONTRATO DE EMPRESTIMO PESSOAL\n"
    "Credor: Banco Teste S.A.\n"
    "Saldo devedor atual: R$ 10.000,00\n"
    "Taxa de juros: 2,00% ao mes\n"
    "Prazo remanescente: 12 parcelas\n"
    "Valor da parcela mensal: R$ 945,60\n"
)


def _documento(cfg: ConfigAgente, pdf: str | None) -> str:
    """Reproduz o preparo do sidecar: texto plano p/ a LLM, com truncagem/retrieval."""
    if not pdf:
        return DOC
    from core.extrator_pdf import extrair_texto_pdf_bytes  # noqa: E402
    from sidecar.app import _contexto_seguro  # noqa: E402

    dados = Path(pdf).read_bytes()
    plano = extrair_texto_pdf_bytes(dados)
    return _contexto_seguro(plano, cfg)


def main() -> None:
    cfg = carregar_config()
    pdf = sys.argv[1] if len(sys.argv) > 1 else None
    print("provider      :", cfg.provider)
    print("base_url      :", cfg.base_url)
    print("model         :", cfg.model)
    print("endpoint_local:", cfg.endpoint_local)
    print("-" * 44)

    try:
        documento = _documento(cfg, pdf)
    except Exception as e:  # noqa: BLE001
        print("leitura do PDF FALHOU:", type(e).__name__, "-", e)
        return
    print("documento     :", f"{pdf} ({len(documento)} chars)" if pdf else "doc de teste")

    try:
        extrator = obter_extrator(cfg)
    except Exception as e:  # noqa: BLE001
        print("obter_extrator FALHOU:", type(e).__name__, "-", e)
        return
    print("extrator      :", type(extrator).__name__)
    print("chamando o modelo local... (pode levar alguns segundos)")

    try:
        bruto = extrator.extrair(documento)
    except Exception as e:  # noqa: BLE001
        print("extrair FALHOU:", type(e).__name__, "-", e)
        return

    verificada = verificar_extracao(bruto, documento)
    confirmados = [k for k, v in verificada.extracao.model_dump().items() if v is not None]
    print("-" * 44)
    print("campos confirmados :", confirmados or "(nenhum)")
    print("descartados        :", verificada.descartados or "(nenhum)")
    print("inconsistencias    :", verificada.inconsistencias or "(nenhuma)")
    print("-" * 44)
    print("bruto do modelo:")
    print(bruto.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
