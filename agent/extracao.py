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
import os
import re
import unicodedata
from dataclasses import dataclass, replace
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


class OpenAICompatExtrator:
    """Extração via endpoint OpenAI-compatible LOCAL (LM Studio/llama.cpp/vLLM).

    Usa `/v1/chat/completions` com `response_format` json_schema (structured
    output). Só é instanciado para endpoints loopback — `obter_extrator` garante
    o H2 (o documento com PII jamais sai da máquina). Sem `strict` de propósito:
    maximiza a compatibilidade entre servidores locais; se a saída não fechar o
    schema, o grafo recupera (1 retry) e degrada para o regex (P8).
    """

    def __init__(self, cfg: ConfigAgente):
        self.cfg = cfg
        self.url = cfg.base_url.rstrip("/") + "/chat/completions"

    def extrair(self, texto: str) -> ExtracaoContrato:
        headers = ({"Authorization": f"Bearer {self.cfg.api_key}"}
                   if self.cfg.api_key else {})
        resposta = _post_json(self.url, {
            "model": self.cfg.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT_EXTRACAO},
                {"role": "user", "content": montar_prompt_extracao(texto)},
            ],
            "temperature": TEMPERATURA_EXTRACAO,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "ExtracaoContrato",
                                "schema": ExtracaoContrato.model_json_schema()},
            },
        }, headers=headers, timeout_s=self.cfg.timeout_s)
        conteudo = resposta["choices"][0]["message"]["content"]
        return ExtracaoContrato.model_validate_json(conteudo)


# Só o Ollama fala a API nativa (`/api/chat`); qualquer outro servidor local
# (LM Studio, llama.cpp, vLLM, ...) fala OpenAI-compatible (`/v1`). Por isso o
# Ollama é o caso EXPLÍCITO e todo o resto cai no dialeto OpenAI — robusto a
# grafias/variações do provider ("openai_compat", "lmstudio", espaços, etc.).
_PROVIDERS_OLLAMA = {"local", "ollama"}


def obter_extrator(cfg: ConfigAgente) -> Extrator:
    """Fábrica. Extração exige endpoint LOCAL (loopback): o documento bruto tem
    PII e nunca pode sair da máquina (H2/ADR-0010). O dialeto segue o provider —
    Ollama (API nativa) ou OpenAI-compatible (LM Studio/llama.cpp/vLLM).

    Mesma precedência da fábrica de provider (ADR-0016 §E, T-1702): com
    `HF_BASE_URL` definido, o servidor do usuário manda (comportamento de
    sempre); sem ele, e com `provider` no dialeto Ollama, o runtime embarcado
    (`llama-server`) é quem responde — e ele fala OpenAI-compatible, não a API
    nativa do Ollama, daí o dialeto mudar junto com o endpoint. Sem
    binário/modelo embarcado, `base_url_runtime_embarcado()` levanta
    `RuntimeLLMIndisponivel` (subclasse de `RuntimeError`); o nó que chama
    esta fábrica (`_no_extrair`) já captura `Exception` e degrada (P8).
    """
    if not cfg.endpoint_local:
        raise RuntimeError(
            f"EXTRACAO_LOCAL_ONLY: extração exige endpoint local (loopback); "
            f"base_url='{cfg.base_url}' é remoto (H2 — o documento contém PII).")
    if cfg.provider.strip().lower() in _PROVIDERS_OLLAMA:
        if "HF_BASE_URL" not in os.environ:
            from .provider import base_url_runtime_embarcado
            return OpenAICompatExtrator(
                replace(cfg, base_url=base_url_runtime_embarcado()))
        return OllamaExtrator(cfg)
    return OpenAICompatExtrator(cfg)


# ------------------------------------------------------------------ verificador
# Reduz a comparação a letras/dígitos/percentual: tolera ruído de FORMATAÇÃO na
# citação — OCR, Markdown do pymupdf4llm (**negrito**, `|` de tabela, `#`) e
# pontuação que o modelo reorganiza (dois-pontos, etc.). Não afrouxa o
# anti-alucinação: o VALOR extraído ainda é conferido contra o trecho cru
# (`_valor_confere_com_trecho`), e a sequência de tokens do trecho continua tendo
# de existir no documento (ADR-0010).
_RE_SO_ESSENCIAL = re.compile(r"[^0-9a-z%\s]")

# Confusões clássicas de glifo do OCR (ADR-0015), mapeadas para o dígito
# canônico. Aplicadas SÓ dentro de um token numérico (com ao menos um dígito de
# verdade) — nunca em palavras: "6OO,OO" → "600,00", mas "juros"/"bis" ficam
# intactos. É determinístico e simétrico (documento e citação passam pela mesma
# canonicalização), então não afrouxa H1: o número segue tendo de existir e
# bater com o valor extraído.
_GLIFOS_OCR = {"o": "0", "l": "1", "i": "1", "s": "5", "b": "8"}
_RE_TOKEN_NUMERICO = re.compile(r"[0-9olisb][0-9olisb.,]*", re.IGNORECASE)

# Marcação de tipo da pré-anotação (ADR-0015/REQ-F-025). Só o prompt a recebe,
# mas o modelo pode ecoá-la na citação — removemos aqui para o quote-check casar
# contra o documento CRU (sem tags).
_RE_TAG_TIPO = re.compile(r"</?(?:valor|data|percentual)>", re.IGNORECASE)


def _desglifar_numeros(texto: str) -> str:
    def corrige(m: re.Match[str]) -> str:
        token = m.group(0)
        if not any(c.isdigit() for c in token):
            return token  # sem dígito real ⇒ é palavra, não número de OCR
        return "".join(_GLIFOS_OCR.get(c.lower(), c) for c in token)

    return _RE_TOKEN_NUMERICO.sub(corrige, texto)


def _normalizar(texto: str) -> str:
    """Sem tags de tipo, sem acentos, sem ruído de formatação/glifo, colapsado."""
    sem_tags = _RE_TAG_TIPO.sub(" ", texto)
    sem_acentos = "".join(c for c in unicodedata.normalize("NFKD", sem_tags)
                          if not unicodedata.combining(c))
    base = _desglifar_numeros(sem_acentos.casefold())
    so_essencial = _RE_SO_ESSENCIAL.sub(" ", base)
    return re.sub(r"\s+", " ", so_essencial).strip()


_RE_NUMERO = re.compile(r"\d[\d.,]*")


def _numeros_do_trecho(trecho: str) -> list[float]:
    """Números do trecho nas DUAS interpretações (pt-BR 1.234,56 e en 1,234.56).

    Desglifa antes: um valor lido pelo OCR como "6OO,OO" (letra O) volta a
    parsear como 600,00 (ADR-0015).
    """
    numeros: list[float] = []
    for m in _RE_NUMERO.finditer(_desglifar_numeros(trecho)):
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
            log.debug("Falha ao obter extrator (config): %s", type(e).__name__)
            return {"motivos": [f"ERRO_CONFIG:{type(e).__name__}"],
                    "tentativas": MAX_TENTATIVAS}
    tentativas = state.get("tentativas", 0) + 1
    try:
        extracao = ctx.extrator.extrair(state["documento"])
    except ValidationError:
        return {"motivos": ["REQ-LLM-002:SCHEMA"], "tentativas": tentativas}
    except Exception as e:  # noqa: BLE001 — P8 na entrada: falhou ⇒ fallback regex do chamador
        # Só o tipo: `state["documento"]` é o contrato do usuário (PII).
        log.debug("Falha ao extrair do documento: %s", type(e).__name__)
        return {"motivos": [f"ERRO_PROVIDER:{type(e).__name__}"],
                "tentativas": tentativas}
    return {"extracao": extracao.model_dump(), "motivos": [],
            "tentativas": tentativas}


def _no_verificar(state: EstadoExtracao,
                  runtime: Runtime[ContextoExtracao]) -> dict[str, object]:  # noqa: ARG001 — nome exigido p/ injeção do LangGraph (RunnableCallable casa por nome de parâmetro)
    extracao_dump = state.get("extracao")
    assert extracao_dump is not None
    extracao = ExtracaoContrato.model_validate(extracao_dump)
    return {"verificada":
            verificar_extracao(extracao, state["documento"]).model_dump()}


def _no_confirmar(state: EstadoExtracao,
                  runtime: Runtime[ContextoExtracao]) -> dict[str, object]:  # noqa: ARG001 — idem _no_verificar
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
               runtime: Runtime[ContextoExtracao]) -> dict[str, object]:  # noqa: ARG001 — idem _no_verificar
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
    global _grafo  # noqa: PLW0603 — singleton lazy (compilação do grafo não é de graça)
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
