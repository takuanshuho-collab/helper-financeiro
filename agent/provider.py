"""
Providers de LLM (REQ-LLM-003/004, ADR-0002).

Interface única `LLMProvider.analisar(fatos) -> AnaliseAgente`. Implementações:
  - FakeProvider        : determinístico, SEM rede — usado pelo harness (M1).
  - OllamaProvider      : local-first (M2, stub aqui).
  - OpenAICompatProvider: nuvem via env (M2, stub aqui).

Trocar de provider não muda nada acima desta camada (o pipeline de guardrails
é o mesmo). É a "tomada padrão": o aparelho não sabe de qual usina vem a luz.
"""
from __future__ import annotations

from typing import Protocol

from contracts import AnaliseAgente, FatosFinanceiros, PassoNegociacao, Prioridade
from core.utils import formatar_brl

from .config import ConfigAgente


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
class OllamaProvider:
    """Local-first via Ollama (endpoint OpenAI-compatible). Stub — ver T-201."""

    def __init__(self, cfg: ConfigAgente):
        self.cfg = cfg

    def analisar(self, fatos: FatosFinanceiros) -> AnaliseAgente:
        # M2: usar cliente OpenAI-compatible apontando para cfg.base_url e,
        # de preferência, `instructor` para forçar a saída no schema AnaliseAgente.
        #   from openai import OpenAI
        #   client = OpenAI(base_url=self.cfg.base_url, api_key="ollama")
        #   ... structured output ...
        raise NotImplementedError("OllamaProvider será implementado na task T-201.")


class OpenAICompatProvider:
    """Nuvem via endpoint OpenAI-compatible. Chave via env. Stub — ver T-202."""

    def __init__(self, cfg: ConfigAgente):
        self.cfg = cfg

    def analisar(self, fatos: FatosFinanceiros) -> AnaliseAgente:
        raise NotImplementedError("OpenAICompatProvider será implementado na task T-202.")


def obter_provider(cfg: ConfigAgente) -> LLMProvider:
    """Fábrica: escolhe o provider conforme a configuração."""
    if cfg.provider == "fake":
        return FakeProvider()
    if cfg.provider == "local":
        return OllamaProvider(cfg)
    if cfg.provider == "openai_compat":
        return OpenAICompatProvider(cfg)
    raise ValueError(f"Provider desconhecido: {cfg.provider}")
