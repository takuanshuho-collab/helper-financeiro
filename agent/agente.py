"""
Orquestração do CONSELHEIRO (REQ-LLM-001/002, P8).

Fluxo (docs/PLAN §2):
  core → montar_fatos (+anonimização) → provider → guardrails → ResultadoAnalise

Se qualquer etapa da IA falhar, cai em MODO DEGRADADO: devolve os fatos
determinísticos intactos e sinaliza o que falhou. O usuário nunca fica sem o
essencial por causa do LLM.
"""
from __future__ import annotations

import logging

from core.diagnostico import resumo_diagnostico
from core.estrategias import comparar_estrategias
from core.models import PerfilFinanceiro
from guardrails.conteudo import AVISO_LEGAL, detectar_conteudo_indevido, garantir_aviso
from guardrails.pii import MapaAnonimizacao, anonimizar_credores
from guardrails.validador_numerico import validar as validar_numeros

from .config import ConfigAgente, carregar_config
from .provider import LLMProvider, obter_provider
from .schemas import AnaliseAgente, DividaFato, EstrategiaFato, FatosFinanceiros, ResultadoAnalise

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


def analisar(perfil: PerfilFinanceiro, extra_mensal: float = 0.0,
             cfg: ConfigAgente | None = None,
             provider: LLMProvider | None = None) -> ResultadoAnalise:
    """Ponto de entrada da análise assistida por IA, com guardrails e degradação."""
    cfg = cfg or carregar_config()
    fatos, mapa = montar_fatos(perfil, extra_mensal)

    # P8: modo degradado explícito (ex.: sem LLM disponível).
    if cfg.modo_degradado:
        return _degradado(fatos, ["MODO_DEGRADADO"])

    provider = provider or obter_provider(cfg)

    # 1) Chamada ao LLM
    try:
        analise = provider.analisar(fatos)
    except Exception as e:  # noqa: BLE001 — qualquer falha do LLM degrada com segurança
        return _degradado(fatos, [f"ERRO_PROVIDER:{type(e).__name__}"])

    violacoes: list[str] = []

    # 2) Schema (defensivo: garante o tipo esperado)
    if not isinstance(analise, AnaliseAgente):
        return _degradado(fatos, ["REQ-LLM-002:SCHEMA"])

    # 3) Consistência numérica (H1) — a trava crítica
    orfaos = validar_numeros(fatos, analise)
    if orfaos:
        violacoes.append("REQ-GRD-001:NUMEROS_FABRICADOS")

    # 4) Conteúdo indevido (H6)
    if detectar_conteudo_indevido(analise):
        violacoes.append("REQ-GRD-004:CONTEUDO_INDEVIDO")

    # Violação de guardrail crítico ⇒ degrada (não entrega saída suspeita).
    if violacoes:
        return _degradado(fatos, violacoes)

    # 5) Aviso legal (H3) garantido no sumário.
    analise.sumario_executivo = garantir_aviso(analise.sumario_executivo)

    return ResultadoAnalise(fatos=fatos, analise=analise, modo="completo",
                            guardrails_violados=[], aviso_legal=AVISO_LEGAL)
