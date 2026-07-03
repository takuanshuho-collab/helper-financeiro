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

from pydantic import ValidationError

from contracts import AnaliseAgente, DividaFato, EstrategiaFato, FatosFinanceiros, ResultadoAnalise
from core.diagnostico import resumo_diagnostico
from core.estrategias import comparar_estrategias
from core.models import PerfilFinanceiro
from guardrails.conteudo import AVISO_LEGAL, detectar_conteudo_indevido, garantir_aviso
from guardrails.pii import MapaAnonimizacao, anonimizar_credores, contem_pii
from guardrails.validador_numerico import validar as validar_numeros

from .cache import cache_global
from .config import ConfigAgente, carregar_config
from .provider import LLMProvider, obter_provider

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
    """Ponto de entrada da análise assistida por IA, com guardrails e degradação."""
    cfg = cfg or carregar_config()
    fatos, mapa = montar_fatos(perfil, extra_mensal)

    # P8: modo degradado explícito (ex.: sem LLM disponível).
    if cfg.modo_degradado:
        return _degradado(fatos, ["MODO_DEGRADADO"])

    # H2: provider cloud só recebe payload comprovadamente sem PII.
    if cfg.provider == "openai_compat" and _verificar_pii_pre_envio(fatos, mapa):
        return _degradado(fatos, ["REQ-GRD-002:PII_DETECTADA"])

    # T-205: mesma entrada + mesmo modelo ⇒ reaproveita análise já aprovada.
    chave_cache = cache_global.chave(cfg.provider, cfg.model, fatos)
    analise: AnaliseAgente | None = cache_global.obter(chave_cache) if cfg.cache else None
    veio_do_cache = analise is not None

    if analise is None:
        # Erro de configuração (ex.: cloud sem HF_API_KEY) também degrada — o
        # usuário nunca perde o determinístico por causa do agente (P8).
        try:
            provider = provider or obter_provider(cfg)
        except Exception as e:  # noqa: BLE001
            return _degradado(fatos, [f"ERRO_CONFIG:{type(e).__name__}"])

        # 1) Chamada ao LLM — com 1 (uma) recuperação (REQ-LLM-002).
        #    Falha transitória (rede, timeout) ou saída fora do schema ganham
        #    uma segunda chance; persistindo, degrada.
        motivo_falha = ""
        for _tentativa in (1, 2):
            try:
                candidata = provider.analisar(fatos)
            except ValidationError:
                motivo_falha = "REQ-LLM-002:SCHEMA"
                continue
            except Exception as e:  # noqa: BLE001 — qualquer falha do LLM degrada com segurança
                motivo_falha = f"ERRO_PROVIDER:{type(e).__name__}"
                continue
            if isinstance(candidata, AnaliseAgente):
                analise = candidata
                break
            motivo_falha = "REQ-LLM-002:SCHEMA"

        if analise is None:
            return _degradado(fatos, [motivo_falha or "ERRO_PROVIDER:Desconhecido"])

    violacoes: list[str] = []

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

    # Só análise APROVADA pelos guardrails entra no cache: uma saída ruim
    # nunca fica "grudada" na sessão — a próxima tentativa vai ao LLM de novo.
    if cfg.cache and not veio_do_cache:
        cache_global.guardar(chave_cache, analise)

    return ResultadoAnalise(fatos=fatos, analise=analise, modo="completo",
                            guardrails_violados=[], aviso_legal=AVISO_LEGAL)
