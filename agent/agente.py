"""
Orquestração do CONSELHEIRO (REQ-LLM-001/002, P8).

Fluxo (docs/PLAN §2, ADR-0006):
  core → montar_fatos (+anonimização) → grafo (LangGraph) → ResultadoAnalise

Desde a Fase 2.5 o pipeline é um StateGraph (`agent/grafo.py`): nós puros,
arestas explícitas e toda falha convergindo para o modo DEGRADADO — devolve os
fatos determinísticos intactos e sinaliza o que falhou. O usuário nunca fica
sem o essencial por causa do LLM.
"""
from __future__ import annotations

import logging

from contracts import DividaFato, EstrategiaFato, FatosFinanceiros, ResultadoAnalise
from core.diagnostico import resumo_diagnostico
from core.estrategias import comparar_estrategias
from core.models import PerfilFinanceiro
from guardrails.conteudo import AVISO_LEGAL
from guardrails.pii import MapaAnonimizacao, anonimizar_credores, contem_pii

from .config import ConfigAgente, carregar_config
from .grafo import executar_analise
from .provider import LLMProvider

log = logging.getLogger("helper_financeiro.agente")


def montar_fatos(perfil: PerfilFinanceiro,
                 extra_mensal: float = 0.0) -> tuple[FatosFinanceiros, MapaAnonimizacao]:
    """Converte o perfil (determinístico) em FatosFinanceiros anonimizados."""
    diag = resumo_diagnostico(perfil)
    comp = comparar_estrategias(perfil, extra_mensal)

    nomes = [d.credor for d in perfil.dividas]
    real_para_token, mapa = anonimizar_credores(nomes)

    dividas = [
        DividaFato(
            token=real_para_token[d.credor],
            tipo=d.tipo,
            saldo_devedor=round(d.saldo_devedor, 2),
            taxa_mensal=round(d.taxa_mensal, 6),
            taxa_anual=round(d.taxa_anual, 6),
            parcela=round(d.parcela, 2),
            parcelas_restantes=d.parcelas_restantes,
        )
        for d in perfil.dividas
    ]

    estrategias = [
        EstrategiaFato(
            metodo=metodo,
            meses=comp[metodo]["meses"],
            juros_pagos=comp[metodo]["juros_pagos"],
            quitavel=comp[metodo]["quitavel"],
            ordem=[real_para_token.get(n, n) for n in comp[metodo]["ordem"]],
        )
        for metodo in ("avalanche", "bola_de_neve")
    ]

    fatos = FatosFinanceiros(
        comprometimento_renda=round(diag["comprometimento_renda"], 4),
        classificacao=diag["classificacao"],
        fluxo_caixa=round(diag["fluxo_caixa"], 2),
        saldo_devedor_total=round(diag["saldo_devedor_total"], 2),
        juros_totais_futuros=round(diag["juros_totais_futuros"], 2),
        dividas=dividas,
        estrategias=estrategias,
        tem_deficit=diag["tem_deficit"],
    )
    return fatos, mapa


def _degradado(fatos: FatosFinanceiros, motivos: list[str]) -> ResultadoAnalise:
    log.warning("Modo degradado. Guardrails/erros: %s", motivos)
    return ResultadoAnalise(fatos=fatos, analise=None, modo="degradado",
                            guardrails_violados=motivos, aviso_legal=AVISO_LEGAL)


def _verificar_pii_pre_envio(fatos: FatosFinanceiros,
                             mapa: MapaAnonimizacao) -> list[str]:
    """Cinto de segurança final do H2: nada com PII sai para provider cloud.

    A anonimização em montar_fatos() já protege por construção; esta checagem
    varre o payload serializado que REALMENTE será enviado, para pegar qualquer
    vazamento futuro (campo novo, refactor descuidado). REQ-GRD-002.
    """
    return contem_pii(fatos.model_dump_json(), mapa)


def analisar(perfil: PerfilFinanceiro, extra_mensal: float = 0.0,
             cfg: ConfigAgente | None = None,
             provider: LLMProvider | None = None) -> ResultadoAnalise:
    """Ponto de entrada da análise assistida por IA, com guardrails e degradação.

    Desde o ADR-0006 a orquestração (cache → LLM com 1 retry → guardrails →
    aprovar/degradar) vive no StateGraph de `agent/grafo.py`; esta função
    prepara os fatos e materializa o resultado — a assinatura e o
    comportamento observável são os mesmos de antes.
    """
    cfg = cfg or carregar_config()
    fatos, mapa = montar_fatos(perfil, extra_mensal)

    # P8: modo degradado explícito (ex.: sem LLM disponível) nem entra no grafo.
    if cfg.modo_degradado:
        return _degradado(fatos, ["MODO_DEGRADADO"])

    return executar_analise(fatos, mapa, cfg, provider)
