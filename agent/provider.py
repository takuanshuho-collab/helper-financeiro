"""
Providers de LLM (REQ-LLM-003/004, ADR-0002, ADR-0005).

Interface única `LLMProvider.analisar(fatos) -> AnaliseAgente`. Implementações:
  - FakeProvider        : determinístico, SEM rede — usado pelo harness (M1).
  - OllamaProvider      : local-first via API nativa do Ollama (T-201).
  - OpenAICompatProvider: nuvem via endpoint OpenAI-compatible (T-202).

Trocar de provider não muda nada acima desta camada (o pipeline de guardrails
é o mesmo). É a "tomada padrão": o aparelho não sabe de qual usina vem a luz.

Structured output (ADR-0005): sem SDK nem framework — o POST é feito com a
stdlib e a resposta é validada com Pydantic. Erros de rede e de schema SOBEM;
recuperar (1 retry) ou degradar é decisão do orquestrador (REQ-LLM-002/P8).
"""
from __future__ import annotations

import copy
import json
import logging
import urllib.request
from typing import Any, Protocol

from contracts import AnaliseAgente, FatosFinanceiros, PassoNegociacao, Prioridade
from core.utils import formatar_brl

from .config import ConfigAgente
from .prompts import SYSTEM_PROMPT, montar_prompt_usuario

log = logging.getLogger("helper_financeiro.provider")

# Baixa temperatura: aderência ao schema e aos fatos vale mais que criatividade.
TEMPERATURA = 0.2
# Os FATOS serializados crescem com o nº de dívidas; o padrão de 2048 tokens
# de contexto do Ollama truncaria carteiras grandes.
NUM_CTX = 8192


class LLMProvider(Protocol):
    def analisar(self, fatos: FatosFinanceiros) -> AnaliseAgente: ...


# --------------------------------------------------------------- FakeProvider
class FakeProvider:
    """Provider determinístico para testes: monta uma análise coerente com os
    fatos usando SOMENTE números que vieram deles (respeita H1 por construção).
    """

    def analisar(self, fatos: FatosFinanceiros) -> AnaliseAgente:
        comp_pct = round(fatos.comprometimento_renda * 100)
        aval = next((e for e in fatos.estrategias if e.metodo == "avalanche"), None)

        prioridades = []
        # Ordena por taxa mensal desc (mais cara primeiro) — narrativa de avalanche
        for i, d in enumerate(sorted(fatos.dividas,
                                     key=lambda x: x.taxa_mensal, reverse=True), 1):
            prioridades.append(Prioridade(
                ordem=i, credor_token=d.token,
                justificativa=(f"{d.token} tem custo de "
                               f"{round(d.taxa_mensal*100, 2)}% ao mês, "
                               "entre os mais altos da carteira."),
            ))

        roteiro = []
        for d in sorted(fatos.dividas, key=lambda x: x.taxa_mensal, reverse=True):
            roteiro.append(PassoNegociacao(
                credor_token=d.token,
                abordagem="portabilidade" if d.taxa_mensal > 0.03 else "reducao",
                argumentos=[
                    f"Saldo devedor informado de {formatar_brl(d.saldo_devedor)}.",
                    "Histórico de pagamento e intenção de manter o contrato.",
                ],
                concessoes_possiveis=["Quitação à vista se houver desconto relevante."],
            ))

        meses_txt = (f"{aval.meses} meses" if aval and aval.quitavel
                     else "prazo a definir")
        return AnaliseAgente(
            sumario_executivo=(
                f"O comprometimento de renda de {comp_pct}% coloca o orçamento em "
                f"zona de '{fatos.classificacao}'. A prioridade é atacar a dívida "
                "mais cara primeiro (estratégia avalanche)."
            ),
            diagnostico_interpretado=(
                f"Com saldo devedor total de {formatar_brl(fatos.saldo_devedor_total)} e "
                f"fluxo de caixa de {formatar_brl(fatos.fluxo_caixa)}, o foco deve ser reduzir "
                f"o custo dos juros. Pela avalanche, a quitação ocorre em {meses_txt}."
            ),
            prioridades=prioridades,
            roteiro_negociacao=roteiro,
            alertas_risco=(["Fluxo de caixa negativo: cortar despesas é urgente."]
                           if fatos.tem_deficit else []),
            confianca=0.9,
        )


# --------------------------------------------------------- Providers reais (M2)
def _post_json(url: str, payload: dict[str, Any],
               headers: dict[str, str], timeout_s: int) -> dict[str, Any]:
    """POST JSON → JSON com a stdlib (ADR-0005). Erros de rede/HTTP sobem."""
    corpo = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=corpo, method="POST",
        headers={"Content-Type": "application/json", **headers})
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        dados: dict[str, Any] = json.loads(resp.read().decode("utf-8"))
    return dados


def _mensagens(fatos: FatosFinanceiros) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": montar_prompt_usuario(fatos)},
    ]


def schema_estrito() -> dict[str, Any]:
    """Schema do `AnaliseAgente` endurecido para o modo strict OpenAI.

    O strict exige `additionalProperties: false` e todos os campos em
    `required` em CADA objeto — o Pydantic não emite isso por padrão.
    """
    schema: dict[str, Any] = copy.deepcopy(AnaliseAgente.model_json_schema())

    def endurecer(no: Any) -> None:
        if isinstance(no, dict):
            if no.get("type") == "object" and "properties" in no:
                no["additionalProperties"] = False
                no["required"] = list(no["properties"].keys())
            for valor in no.values():
                endurecer(valor)
        elif isinstance(no, list):
            for item in no:
                endurecer(item)

    endurecer(schema)
    return schema


class OllamaProvider:
    """Local-first via API nativa do Ollama (T-201, REQ-LLM-003/004).

    Usa `/api/chat` com `format` = JSON Schema do `AnaliseAgente`: o servidor
    restringe a gramática de amostragem, então a aderência ao schema é por
    construção — a forma mais forte disponível (ADR-0005).
    """

    def __init__(self, cfg: ConfigAgente):
        self.cfg = cfg
        # Aceita tanto a raiz ("http://localhost:11434") quanto a forma
        # OpenAI-compat ("…/v1") no HF_BASE_URL — a API nativa fica na raiz.
        raiz = cfg.base_url.rstrip("/").removesuffix("/v1")
        self.url = f"{raiz}/api/chat"
        if "localhost" not in raiz and "127.0.0.1" not in raiz:
            log.warning("Provider 'local' apontando para host remoto (%s) — "
                        "verifique o REQ-LLM-004 (sem tráfego externo).", raiz)

    def analisar(self, fatos: FatosFinanceiros) -> AnaliseAgente:
        resposta = _post_json(self.url, {
            "model": self.cfg.model,
            "messages": _mensagens(fatos),
            "stream": False,
            "format": AnaliseAgente.model_json_schema(),
            "options": {"temperature": TEMPERATURA, "num_ctx": NUM_CTX},
        }, headers={}, timeout_s=self.cfg.timeout_s)
        return AnaliseAgente.model_validate_json(resposta["message"]["content"])


class OpenAICompatProvider:
    """Nuvem via endpoint OpenAI-compatible (T-202). Chave SÓ via env (SEC-002)."""

    def __init__(self, cfg: ConfigAgente):
        if not cfg.api_key:
            raise RuntimeError(
                "HF_API_KEY ausente: o provider cloud exige chave via variável "
                "de ambiente (REQ-SEC-002).")
        self.cfg = cfg
        self.url = cfg.base_url.rstrip("/") + "/chat/completions"

    def analisar(self, fatos: FatosFinanceiros) -> AnaliseAgente:
        resposta = _post_json(self.url, {
            "model": self.cfg.model,
            "messages": _mensagens(fatos),
            "temperature": TEMPERATURA,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "AnaliseAgente", "strict": True,
                                "schema": schema_estrito()},
            },
        }, headers={"Authorization": f"Bearer {self.cfg.api_key}"},
            timeout_s=self.cfg.timeout_s)
        conteudo = resposta["choices"][0]["message"]["content"]
        return AnaliseAgente.model_validate_json(conteudo)


def obter_provider(cfg: ConfigAgente) -> LLMProvider:
    """Fábrica: escolhe o provider conforme a configuração."""
    if cfg.provider == "fake":
        return FakeProvider()
    if cfg.provider == "local":
        return OllamaProvider(cfg)
    if cfg.provider == "openai_compat":
        return OpenAICompatProvider(cfg)
    raise ValueError(f"Provider desconhecido: {cfg.provider}")
