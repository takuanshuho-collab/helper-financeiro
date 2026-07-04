"""
Extração Code-First de variáveis de documentos (T-255/T-256, ADR-0006/0007).

O modelo EXTRAI (`capital`, `taxa`, `prazo`, ...), o código VERIFICA e CALCULA,
o usuário CONFIRMA. O LLM nunca faz conta e nunca decide rota.

Duas travas determinísticas contra alucinação de extração:
1. Quote-check — cada campo exige `trecho_fonte` literal presente no documento
   E o valor extraído precisa aparecer no próprio trecho. Sem fonte ⇒ descarte.
2. Checagem cruzada — os campos não são independentes: a parcela recalculada
   via Price(saldo, taxa, n) precisa bater com a parcela extraída.

H2 por construção: extração roda SOMENTE em provider local — documento bruto
(com PII) jamais vai para a nuvem. Fluxo com pausa para confirmação humana
(`interrupt` + checkpointer, ADR-0006): a GUI retoma do checkpoint (M3).
"""
from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass
from math import isclose
from typing import Any, Literal, NotRequired, Protocol, TypedDict
from uuid import uuid4

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.runtime import Runtime
from langgraph.types import Command, interrupt
from pydantic import ValidationError

from contracts import CampoExtraido, ExtracaoContrato, ExtracaoVerificada
from core.calculos import parcela_price

from .config import ConfigAgente, carregar_config
from .grafo import criar_checkpointer
from .prompts import SYSTEM_PROMPT_EXTRACAO, montar_prompt_extracao
from .provider import NUM_CTX, _post_json

log = logging.getLogger("helper_financeiro.extracao")

# Extração quer determinismo, não criatividade.
TEMPERATURA_EXTRACAO = 0.0
# REQ-LLM-002 (mesma régua da análise): no máximo 1 recuperação.
MAX_TENTATIVAS = 2
# Tolerância da checagem cruzada Price: contratos reais embutem IOF/seguros
# na parcela, então divergência pequena é esperada; grande é sinal de erro.
TOLERANCIA_CRUZADA = 0.05


class Extrator(Protocol):
    def extrair(self, texto: str) -> ExtracaoContrato: ...


class OllamaExtrator:
    """Extração via API nativa do Ollama com gramática restrita (ADR-0005)."""

    def __init__(self, cfg: ConfigAgente):
        self.cfg = cfg
        raiz = cfg.base_url.rstrip("/").removesuffix("/v1")
        self.url = f"{raiz}/api/chat"

    def extrair(self, texto: str) -> ExtracaoContrato:
        resposta = _post_json(self.url, {
            "model": self.cfg.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT_EXTRACAO},
                {"role": "user", "content": montar_prompt_extracao(texto)},
            ],
            "stream": False,
            "format": ExtracaoContrato.model_json_schema(),
            "options": {"temperature": TEMPERATURA_EXTRACAO, "num_ctx": NUM_CTX},
        }, headers={}, timeout_s=self.cfg.timeout_s)
        return ExtracaoContrato.model_validate_json(resposta["message"]["content"])


def obter_extrator(cfg: ConfigAgente) -> Extrator:
    """Fábrica. Cloud é RECUSADA: o documento bruto contém PII (H2/REQ-GRD-002)."""
    if cfg.provider == "local":
        return OllamaExtrator(cfg)
    raise RuntimeError(
        f"EXTRACAO_LOCAL_ONLY: extração de documentos exige provider local "
        f"(H2 — o documento bruto contém PII); provider atual: '{cfg.provider}'.")


# ------------------------------------------------------------------ verificador
def _normalizar(texto: str) -> str:
    """Espaços colapsados, sem acentos, casefold — comparação tolerante a OCR."""
    sem_acentos = "".join(c for c in unicodedata.normalize("NFKD", texto)
                          if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", sem_acentos).strip().casefold()


_RE_NUMERO = re.compile(r"\d[\d.,]*")


def _numeros_do_trecho(trecho: str) -> list[float]:
    """Números do trecho nas DUAS interpretações (pt-BR 1.234,56 e en 1,234.56)."""
    numeros: list[float] = []
    for m in _RE_NUMERO.finditer(trecho):
        bruto = m.group(0).strip(".,")
        for candidato in (bruto.replace(".", "").replace(",", "."),
                          bruto.replace(",", "")):
            try:
                numeros.append(float(candidato))
            except ValueError:
                continue
    return numeros


def _valor_confere_com_trecho(campo: CampoExtraido) -> bool:
    """O valor extraído precisa aparecer no próprio trecho citado.

    Aceita a forma percentual (trecho "2,50% a.m." ⇔ valor 0.025): a conversão
    fração↔percentual é legítima e exigida pelo prompt de extração.
    """
    for x in _numeros_do_trecho(campo.trecho_fonte):
        for forma in (campo.valor, campo.valor * 100):
            if isclose(x, forma, rel_tol=1e-4, abs_tol=0.005):
                return True
    return False


def verificar_extracao(extracao: ExtracaoContrato, documento: str) -> ExtracaoVerificada:
    """Travas determinísticas: quote-check por campo + checagem cruzada Price."""
    doc_norm = _normalizar(documento)
    campos = dict(extracao)
    descartados: list[str] = []

    for nome, campo in list(campos.items()):
        if campo is None:
            continue
        if _normalizar(campo.trecho_fonte) not in doc_norm:
            campos[nome] = None
            descartados.append(f"{nome}:SEM_FONTE")
        elif isinstance(campo, CampoExtraido) and not _valor_confere_com_trecho(campo):
            campos[nome] = None
            descartados.append(f"{nome}:VALOR_DIVERGE_DA_FONTE")

    limpa = ExtracaoContrato(**campos)

    inconsistencias: list[str] = []
    saldo, taxa = limpa.saldo_devedor, limpa.taxa_mensal
    parcela, n = limpa.parcela, limpa.parcelas_restantes
    if saldo and taxa and parcela and n and taxa.valor > 0 and n.valor >= 1:
        pmt = parcela_price(saldo.valor, taxa.valor, int(n.valor))
        if parcela.valor > 0 and abs(pmt - parcela.valor) / parcela.valor > TOLERANCIA_CRUZADA:
            inconsistencias.append("CRUZADA_PRICE:parcela")

    if descartados or inconsistencias:
        log.warning("Verificação da extração: descartados=%s inconsistencias=%s",
                    descartados, inconsistencias)
    return ExtracaoVerificada(extracao=limpa, descartados=descartados,
                              inconsistencias=inconsistencias)


# ------------------------------------------------------------------ grafo
class EstadoExtracao(TypedDict):
    """Estado do fluxo de extração. O documento fica só na memória do processo.

    `extracao` e `verificada` são `model_dump()` (higiene de checkpoint, M4):
    o checkpointer só serializa dicts/primitivos, nunca objetos Pydantic.
    """
    documento: str
    extracao: NotRequired[dict[str, Any] | None]
    verificada: NotRequired[dict[str, Any] | None]
    confirmada: NotRequired[dict[str, Any] | None]
    motivos: NotRequired[list[str]]
    tentativas: NotRequired[int]


@dataclass
class ContextoExtracao:
    cfg: ConfigAgente
    extrator: Extrator | None = None


def _no_extrair(state: EstadoExtracao,
                runtime: Runtime[ContextoExtracao]) -> dict[str, object]:
    ctx = runtime.context
    if ctx.extrator is None:
        try:
            ctx.extrator = obter_extrator(ctx.cfg)
        except Exception as e:  # noqa: BLE001
            return {"motivos": [f"ERRO_CONFIG:{type(e).__name__}"],
                    "tentativas": MAX_TENTATIVAS}
    tentativas = state.get("tentativas", 0) + 1
    try:
        extracao = ctx.extrator.extrair(state["documento"])
    except ValidationError:
        return {"motivos": ["REQ-LLM-002:SCHEMA"], "tentativas": tentativas}
    except Exception as e:  # noqa: BLE001 — P8 na entrada: falhou ⇒ fallback regex do chamador
        return {"motivos": [f"ERRO_PROVIDER:{type(e).__name__}"],
                "tentativas": tentativas}
    return {"extracao": extracao.model_dump(), "motivos": [],
            "tentativas": tentativas}


def _no_verificar(state: EstadoExtracao,
                  runtime: Runtime[ContextoExtracao]) -> dict[str, object]:
    extracao_dump = state.get("extracao")
    assert extracao_dump is not None
    extracao = ExtracaoContrato.model_validate(extracao_dump)
    return {"verificada":
            verificar_extracao(extracao, state["documento"]).model_dump()}


def _no_confirmar(state: EstadoExtracao,
                  runtime: Runtime[ContextoExtracao]) -> dict[str, object]:
    """Pausa o grafo até o humano conferir (interrupt + checkpointer, ADR-0006).

    O payload é o que a GUI (M3) mostra pré-preenchido — mesmo fluxo "confira
    antes de adicionar" da aba Contrato PDF. O `resume` devolve os campos
    confirmados (possivelmente editados) pelo usuário.
    """
    verificada = state.get("verificada")
    assert verificada is not None
    resposta = interrupt({
        "campos": verificada["extracao"],
        "descartados": verificada["descartados"],
        "inconsistencias": verificada["inconsistencias"],
    })
    return {"confirmada": resposta}


def _no_falhar(state: EstadoExtracao,
               runtime: Runtime[ContextoExtracao]) -> dict[str, object]:
    """P8 na entrada: extração indisponível ⇒ chamador cai no extrator regex."""
    motivos = state.get("motivos") or ["ERRO_PROVIDER:Desconhecido"]
    log.warning("Extração degradada: %s", motivos)
    return {"extracao": None, "verificada": None, "confirmada": None,
            "motivos": motivos}


def _rota_pos_extrair(state: EstadoExtracao) -> Literal["verificar", "extrair", "falhar"]:
    if state.get("extracao") is not None:
        return "verificar"
    if state.get("tentativas", 0) >= MAX_TENTATIVAS:
        return "falhar"
    return "extrair"


GrafoExtracao = CompiledStateGraph[EstadoExtracao, ContextoExtracao, EstadoExtracao, EstadoExtracao]


def _construir() -> GrafoExtracao:
    g = StateGraph(EstadoExtracao, context_schema=ContextoExtracao)
    g.add_node("extrair", _no_extrair)
    g.add_node("verificar", _no_verificar)
    g.add_node("confirmar", _no_confirmar)
    g.add_node("falhar", _no_falhar)

    g.add_edge(START, "extrair")
    g.add_conditional_edges("extrair", _rota_pos_extrair)
    g.add_edge("verificar", "confirmar")
    g.add_edge("confirmar", END)
    g.add_edge("falhar", END)
    return g.compile(checkpointer=criar_checkpointer())


_grafo: GrafoExtracao | None = None


def grafo_extracao() -> GrafoExtracao:
    global _grafo
    if _grafo is None:
        _grafo = _construir()
    return _grafo


# ------------------------------------------------------------------ API de alto nível
def iniciar_extracao(texto: str, cfg: ConfigAgente | None = None,
                     extrator: Extrator | None = None,
                     thread_id: str | None = None) -> tuple[str, dict[str, Any]]:
    """Roda o fluxo até a pausa de confirmação (ou até falhar).

    Devolve `(thread_id, estado)`. Se o grafo pausou, `estado["__interrupt__"]`
    carrega o payload para a GUI; retome com `confirmar_extracao`.
    """
    cfg = cfg or carregar_config()
    tid = thread_id or str(uuid4())
    estado: dict[str, Any] = grafo_extracao().invoke(
        {"documento": texto},
        config={"configurable": {"thread_id": tid}},
        context=ContextoExtracao(cfg=cfg, extrator=extrator),
    )
    return tid, estado


def confirmar_extracao(thread_id: str, confirmacao: dict[str, Any],
                       cfg: ConfigAgente | None = None,
                       extrator: Extrator | None = None) -> dict[str, Any]:
    """Retoma o grafo pausado com os campos confirmados/editados pelo usuário."""
    cfg = cfg or carregar_config()
    estado: dict[str, Any] = grafo_extracao().invoke(
        Command(resume=confirmacao),
        config={"configurable": {"thread_id": thread_id}},
        context=ContextoExtracao(cfg=cfg, extrator=extrator),
    )
    return estado
