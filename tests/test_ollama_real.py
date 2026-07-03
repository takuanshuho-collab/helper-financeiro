"""
Integração com Ollama REAL (marcador `ollama` — fora do gate bloqueante).

Roda apenas se houver um servidor em localhost:11434 COM ao menos um modelo
instalado; caso contrário, skip com o motivo. O modelo vem de HF_MODEL se
definido; senão, usa o primeiro instalado (`/api/tags`).
Como rodar: `uv run pytest -m ollama -v`.
"""
import json
import os
import urllib.request

import pytest

from agent.agente import analisar, montar_fatos
from agent.config import ConfigAgente
from agent.provider import OllamaProvider
from contracts import AnaliseAgente
from guardrails.conteudo import AVISO_LEGAL


def _modelo_instalado() -> str | None:
    """Nome de um modelo utilizável no Ollama local, ou None (⇒ skip)."""
    try:
        with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=1) as r:
            modelos = [m["name"] for m in json.loads(r.read())["models"]]
    except OSError:
        return None
    if not modelos:
        return None
    preferido = os.getenv("HF_MODEL", "")
    if any(m == preferido or m.startswith(preferido + ":") for m in modelos):
        return preferido
    return modelos[0]


_MODELO = _modelo_instalado()

pytestmark = [
    pytest.mark.ollama,
    pytest.mark.skipif(
        _MODELO is None,
        reason="Ollama sem modelo em localhost:11434 (ex.: `ollama pull qwen2.5:14b`)"),
]


def _cfg() -> ConfigAgente:
    return ConfigAgente(provider="local", cache=False, model=_MODELO or "",
                        timeout_s=int(os.getenv("HF_TIMEOUT", "300")))


def test_provider_real_adere_ao_schema(perfil_atencao):
    """O `format` (JSON Schema) do Ollama deve produzir AnaliseAgente válida.

    Se o modelo emitir algo fora do contrato (ex.: confianca=95 num campo
    0–1), o Pydantic DEVE rejeitar — isso é o contrato funcionando, e conta
    como xfail (limitação do modelo, não defeito do sistema). Modelos ≥7B
    devem passar direto; meça com scripts/bench_schema.py.
    """
    from pydantic import ValidationError

    fatos, _ = montar_fatos(perfil_atencao, extra_mensal=500)
    try:
        analise = OllamaProvider(_cfg()).analisar(fatos)
    except ValidationError as e:
        pytest.xfail(f"modelo {_MODELO} não aderiu ao contrato (rejeitado: {e.error_count()} erro(s))")
    assert isinstance(analise, AnaliseAgente)
    assert 0.0 <= analise.confianca <= 1.0   # imposto pelo contrato (Field ge/le)
    assert analise.sumario_executivo.strip()


def test_pipeline_real_nunca_estoura(perfil_atencao):
    """Contrato P8 fim-a-fim: completo OU degradado com motivo — nunca exceção.

    Degradar aqui é aceitável (o grounding pode reprovar legitimamente um
    modelo fraco); o que este teste garante é o comportamento do SISTEMA.
    """
    resultado = analisar(perfil_atencao, extra_mensal=500, cfg=_cfg())
    assert resultado.modo in ("completo", "degradado")
    assert resultado.aviso_legal == AVISO_LEGAL
    assert resultado.fatos.saldo_devedor_total > 0
    if resultado.modo == "completo":
        assert resultado.guardrails_violados == []
        assert "apoio à decisão" in resultado.analise.sumario_executivo
    else:
        assert resultado.guardrails_violados  # sempre há motivo registrado
