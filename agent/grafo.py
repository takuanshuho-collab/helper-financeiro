"""
Grafo de orquestração do CONSELHEIRO (ADR-0006, T-252).

O fluxo é RÍGIDO: o LangGraph liga nós que são funções Python puras; o LLM não
decide rota nenhuma (Code-First — o modelo aparece só nas pontas). Toda aresta
de falha converge para `degradar`, que preserva o determinístico (P8).

    verificar_pii → consultar_cache → chamar_llm ⇄ (1 retry) → validar_guardrails
                          ↘ (hit) ─────────────────────────────↗        ↓
                                                        aprovar | degradar

A recuperação única do REQ-LLM-002 cobre falha de chamada/schema E reprovação
de guardrail: `validar_guardrails` devolve para `chamar_llm` (com o feedback
dos números órfãos) enquanto houver orçamento — teto global de MAX_TENTATIVAS
chamadas ao LLM por análise. Esgotado o retry só com NUMEROS_FABRICADOS, o nó
`sanear` (ADR-0011) remove deterministicamente as frases com números órfãos e
revalida; se o que sobra continua fundamentado, aprova — senão, degrada.

O que fica FORA do estado (e portanto fora de qualquer checkpoint): o mapa de
anonimização (REQ-SEC-003: só memória), a config e o provider — todos viajam
no `Runtime.context`, que o LangGraph não serializa.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Literal, NotRequired, TypedDict
from uuid import uuid4

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.runtime import Runtime
from pydantic import ValidationError

from contracts import AnaliseAgente, FatosFinanceiros, ResultadoAnalise
from guardrails.conteudo import AVISO_LEGAL, detectar_conteudo_indevido, garantir_aviso
from guardrails.pii import MapaAnonimizacao, contem_pii
from guardrails.validador_numerico import remover_frases_orfas
from guardrails.validador_numerico import validar as validar_numeros

from .cache import cache_global
from .config import ConfigAgente
from .provider import LLMProvider, obter_provider

log = logging.getLogger("helper_financeiro.grafo")

# REQ-LLM-002: no máximo 1 recuperação ⇒ 2 tentativas no total.
MAX_TENTATIVAS = 2

# Higiene de checkpoint (M4): o estado carrega apenas dicts/primitivos
# (model_dump) — o checkpointer nunca serializa objetos Pydantic. Como cinto
# extra, os tipos de `contracts` ficam registrados na allowlist do msgpack:
# se algum voltar a entrar no estado, é desserializado explicitamente em vez
# de virar aviso (e, em versões futuras do LangGraph, bloqueio).
_TIPOS_PERMITIDOS_CHECKPOINT = [
    ("contracts.schemas", nome) for nome in (
        "AnaliseAgente", "CampoExtraido", "CampoTextoExtraido", "DividaFato",
        "EstrategiaFato", "ExtracaoContrato", "ExtracaoVerificada",
        "FatosFinanceiros", "PassoNegociacao", "Prioridade",
    )
]


def criar_checkpointer() -> InMemorySaver:
    """InMemorySaver com serializador de allowlist explícita (só memória)."""
    return InMemorySaver(serde=JsonPlusSerializer(
        allowed_msgpack_modules=_TIPOS_PERMITIDOS_CHECKPOINT))


class EstadoAnalise(TypedDict):
    """Estado que trafega pelo grafo. Só dicts/primitivos, sem PII.

    `fatos` e `analise` são `model_dump()` de FatosFinanceiros/AnaliseAgente;
    os nós revalidam com `model_validate` quando precisam do objeto.
    """
    fatos: dict[str, Any]
    analise: NotRequired[dict[str, Any] | None]
    motivos: NotRequired[list[str]]
    veio_do_cache: NotRequired[bool]
    tentativas: NotRequired[int]
    modo: NotRequired[str]
    # Feedback do guardrail para a recuperação única (ex.: números órfãos).
    correcao: NotRequired[str | None]
    # A redação determinística (sanear) roda no máximo uma vez.
    saneado: NotRequired[bool]


def _fatos_de(state: EstadoAnalise) -> FatosFinanceiros:
    return FatosFinanceiros.model_validate(state["fatos"])


@dataclass
class ContextoAnalise:
    """Dependências de execução — NUNCA entram em checkpoint (REQ-SEC-003)."""
    cfg: ConfigAgente
    mapa: MapaAnonimizacao
    provider: LLMProvider | None = None


# ------------------------------------------------------------------- nós
def verificar_pii(state: EstadoAnalise,
                  runtime: Runtime[ContextoAnalise]) -> dict[str, object]:
    """Cinto de segurança final do H2: nada com PII sai para provider cloud.

    A anonimização em montar_fatos() já protege por construção; esta checagem
    varre o payload serializado que REALMENTE será enviado (REQ-GRD-002). Só
    incide quando o endpoint é REMOTO (não-loopback): um LLM local recebe fatos
    na própria máquina, sem sair para a nuvem (ADR-0010).
    """
    cfg = runtime.context.cfg
    if not cfg.endpoint_local and contem_pii(
            _fatos_de(state).model_dump_json(), runtime.context.mapa):
        return {"motivos": ["REQ-GRD-002:PII_DETECTADA"]}
    return {}


def consultar_cache(state: EstadoAnalise,
                    runtime: Runtime[ContextoAnalise]) -> dict[str, object]:
    """T-205: mesma entrada + mesmo modelo ⇒ reaproveita análise já aprovada."""
    cfg = runtime.context.cfg
    if not cfg.cache:
        return {"veio_do_cache": False}
    chave = cache_global.chave(cfg.provider, cfg.model, _fatos_de(state))
    analise = cache_global.obter(chave)
    return {"analise": analise.model_dump() if analise else None,
            "veio_do_cache": analise is not None}


def chamar_llm(state: EstadoAnalise,
               runtime: Runtime[ContextoAnalise]) -> dict[str, object]:
    """Uma tentativa de chamada ao provider (ADR-0005). O retry é aresta do grafo."""
    ctx = runtime.context
    if ctx.provider is None:
        # Erro de configuração (ex.: cloud sem HF_API_KEY) degrada direto,
        # sem consumir retry — o usuário nunca perde o determinístico (P8).
        try:
            ctx.provider = obter_provider(ctx.cfg)
        except Exception as e:  # noqa: BLE001
            return {"motivos": [f"ERRO_CONFIG:{type(e).__name__}"],
                    "tentativas": MAX_TENTATIVAS}

    tentativas = state.get("tentativas", 0) + 1
    correcao = state.get("correcao")
    try:
        # No retry pós-guardrail, providers que suportam recebem o feedback
        # com os números órfãos — muito mais eficaz que reamostrar às cegas.
        if correcao and hasattr(ctx.provider, "analisar_com_correcao"):
            candidata = ctx.provider.analisar_com_correcao(
                _fatos_de(state), correcao)
        else:
            candidata = ctx.provider.analisar(_fatos_de(state))
    except ValidationError:
        return {"motivos": ["REQ-LLM-002:SCHEMA"], "tentativas": tentativas}
    except Exception as e:  # noqa: BLE001 — qualquer falha do LLM degrada com segurança
        return {"motivos": [f"ERRO_PROVIDER:{type(e).__name__}"],
                "tentativas": tentativas}
    if not isinstance(candidata, AnaliseAgente):
        return {"motivos": ["REQ-LLM-002:SCHEMA"], "tentativas": tentativas}
    return {"analise": candidata.model_dump(), "motivos": [],
            "correcao": None, "tentativas": tentativas}


def validar_guardrails(state: EstadoAnalise,
                       runtime: Runtime[ContextoAnalise]) -> dict[str, object]:
    """H1 (números fabricados) + H6 (conteúdo indevido) — as travas críticas."""
    analise_dump = state.get("analise")
    assert analise_dump is not None  # rota garante: só chega aqui com análise
    analise = AnaliseAgente.model_validate(analise_dump)
    violacoes: list[str] = []
    correcao = None
    if orfaos := validar_numeros(_fatos_de(state), analise):
        violacoes.append("REQ-GRD-001:NUMEROS_FABRICADOS")
        unicos = ", ".join(f"{o:g}" for o in dict.fromkeys(orfaos))
        correcao = (
            "ATENÇÃO: sua análise citou números que NÃO existem nos FATOS: "
            f"{unicos}. Refaça a análise citando SOMENTE números copiados "
            "literalmente dos FATOS; onde citaria qualquer outro número "
            "(exemplos, faixas, estimativas), escreva a ideia SEM número."
        )
    if detectar_conteudo_indevido(analise):
        violacoes.append("REQ-GRD-004:CONTEUDO_INDEVIDO")
    return {"motivos": violacoes, "correcao": correcao}


def aprovar(state: EstadoAnalise,
            runtime: Runtime[ContextoAnalise]) -> dict[str, object]:
    """Garante o aviso legal (H3) e guarda no cache só o que foi APROVADO."""
    cfg = runtime.context.cfg
    analise_dump = state.get("analise")
    assert analise_dump is not None
    analise = AnaliseAgente.model_validate(analise_dump)
    analise.sumario_executivo = garantir_aviso(analise.sumario_executivo)
    if cfg.cache and not state.get("veio_do_cache", False):
        chave = cache_global.chave(cfg.provider, cfg.model, _fatos_de(state))
        cache_global.guardar(chave, analise)
    return {"analise": analise.model_dump(), "modo": "completo"}


def sanear(state: EstadoAnalise,
           runtime: Runtime[ContextoAnalise]) -> dict[str, object]:
    """Último recurso antes de degradar (ADR-0011): redação determinística.

    Remove as FRASES com números órfãos e revalida. Se o que sobra continua
    limpo e com sumário/diagnóstico não vazios, a análise segue para aprovação;
    caso contrário, mantém os motivos e degrada. Só roda para NUMEROS_FABRICADOS
    (conteúdo indevido nunca é 'consertado' por corte de frase).
    """
    analise_dump = state.get("analise")
    assert analise_dump is not None
    fatos = _fatos_de(state)
    limpa = remover_frases_orfas(fatos, AnaliseAgente.model_validate(analise_dump))
    if (limpa.sumario_executivo and limpa.diagnostico_interpretado
            and not validar_numeros(fatos, limpa)):
        log.info("Análise saneada: frases com números órfãos removidas.")
        return {"analise": limpa.model_dump(), "motivos": [], "saneado": True}
    return {"saneado": True}  # não sobrou análise fundamentada ⇒ degradar


def degradar(state: EstadoAnalise,
             runtime: Runtime[ContextoAnalise]) -> dict[str, object]:
    """P8: entrega o determinístico intacto, com os motivos registrados."""
    motivos = state.get("motivos") or ["ERRO_PROVIDER:Desconhecido"]
    log.warning("Modo degradado. Guardrails/erros: %s", motivos)
    return {"analise": None, "modo": "degradado", "motivos": motivos}


# ------------------------------------------------------------------- rotas
def _rota_pos_pii(state: EstadoAnalise) -> Literal["degradar", "consultar_cache"]:
    return "degradar" if state.get("motivos") else "consultar_cache"


def _rota_pos_cache(state: EstadoAnalise) -> Literal["validar_guardrails", "chamar_llm"]:
    return "validar_guardrails" if state.get("analise") is not None else "chamar_llm"


def _rota_pos_llm(state: EstadoAnalise) -> Literal["validar_guardrails", "chamar_llm", "degradar"]:
    if state.get("analise") is not None:
        return "validar_guardrails"
    if state.get("tentativas", 0) >= MAX_TENTATIVAS:
        return "degradar"
    return "chamar_llm"  # REQ-LLM-002: exatamente 1 recuperação


def _rota_pos_guardrails(
    state: EstadoAnalise,
) -> Literal["aprovar", "chamar_llm", "sanear", "degradar"]:
    motivos = state.get("motivos") or []
    if not motivos:
        return "aprovar"
    # Guardrail reprovou (ex.: número fabricado): a recuperação única do
    # REQ-LLM-002 também vale aqui — o retry leva o feedback com os órfãos.
    # O teto continua MAX_TENTATIVAS chamadas ao LLM (P8).
    if state.get("tentativas", 0) < MAX_TENTATIVAS:
        return "chamar_llm"
    # Esgotou o retry SÓ com números fabricados: redação determinística
    # (ADR-0011) antes de jogar a análise fora. Conteúdo indevido não passa.
    if motivos == ["REQ-GRD-001:NUMEROS_FABRICADOS"] and not state.get("saneado"):
        return "sanear"
    return "degradar"


def _rota_pos_sanear(state: EstadoAnalise) -> Literal["aprovar", "degradar"]:
    return "degradar" if state.get("motivos") else "aprovar"


# ------------------------------------------------------------------- grafo
GrafoAnalise = CompiledStateGraph[EstadoAnalise, ContextoAnalise, EstadoAnalise, EstadoAnalise]


def _construir() -> GrafoAnalise:
    g = StateGraph(EstadoAnalise, context_schema=ContextoAnalise)
    g.add_node("verificar_pii", verificar_pii)
    g.add_node("consultar_cache", consultar_cache)
    g.add_node("chamar_llm", chamar_llm)
    g.add_node("validar_guardrails", validar_guardrails)
    g.add_node("sanear", sanear)
    g.add_node("aprovar", aprovar)
    g.add_node("degradar", degradar)

    g.add_edge(START, "verificar_pii")
    g.add_conditional_edges("verificar_pii", _rota_pos_pii)
    g.add_conditional_edges("consultar_cache", _rota_pos_cache)
    g.add_conditional_edges("chamar_llm", _rota_pos_llm)
    g.add_conditional_edges("validar_guardrails", _rota_pos_guardrails)
    g.add_conditional_edges("sanear", _rota_pos_sanear)
    g.add_edge("aprovar", END)
    g.add_edge("degradar", END)
    # InMemorySaver: estado por thread_id só na memória do processo. Persistir
    # em disco exige as condições do ADR-0006 (pós-anonimização + opt-in).
    return g.compile(checkpointer=criar_checkpointer())


_grafo: GrafoAnalise | None = None


def grafo_analise() -> GrafoAnalise:
    """Grafo compilado (singleton — a compilação não é de graça)."""
    global _grafo
    if _grafo is None:
        _grafo = _construir()
    return _grafo


def executar_analise(fatos: FatosFinanceiros, mapa: MapaAnonimizacao,
                     cfg: ConfigAgente, provider: LLMProvider | None = None,
                     thread_id: str | None = None) -> ResultadoAnalise:
    """Invoca o grafo e materializa o `ResultadoAnalise` da aplicação."""
    estado = grafo_analise().invoke(
        {"fatos": fatos.model_dump()},
        config={"configurable": {"thread_id": thread_id or str(uuid4())}},
        context=ContextoAnalise(cfg=cfg, mapa=mapa, provider=provider),
    )
    modo = estado.get("modo", "degradado")
    analise_dump = estado.get("analise")
    return ResultadoAnalise(
        fatos=fatos,
        analise=AnaliseAgente.model_validate(analise_dump)
        if modo == "completo" and analise_dump is not None else None,
        modo=modo,
        guardrails_violados=estado.get("motivos", []) if modo == "degradado" else [],
        aviso_legal=AVISO_LEGAL,
    )
