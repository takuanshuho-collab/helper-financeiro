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
import threading
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, Literal, NotRequired, TypedDict
from uuid import uuid4

from langgraph.checkpoint.base import BaseCheckpointSaver, RunnableConfig
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

# Prefixo do thread_id determinístico da análise sênior (ADR-0023): thread_id =
# "analise:" + assinatura SHA-256 dos fatos (a MESMA chave do cache T-205). A
# poda de higiene identifica os threads da análise por este prefixo.
PREFIXO_THREAD_ANALISE = "analise:"


def serde_checkpoint() -> JsonPlusSerializer:
    """Serializador com allowlist explícita — o MESMO nos dois modos (memória e
    cofre durável). Exposto para o `sidecar/checkpoint_cofre` passar a serde
    idêntica ao `SqliteSaver`, de modo que a fronteira de tipos permitidos seja
    única (ADR-0023 §T-2601)."""
    return JsonPlusSerializer(allowed_msgpack_modules=_TIPOS_PERMITIDOS_CHECKPOINT)


class CheckpointerChaveavel(BaseCheckpointSaver[Any]):
    """Proxy que delega a um checkpointer interno TROCÁVEL em runtime (ADR-0023).

    O grafo é singleton, compilado UMA vez com este proxy. Trocar o *delegate*
    (memória ↔ cofre durável) sem recompilar o grafo é o que permite ligar a
    durabilidade quando o cofre abre e voltar à memória quando ele bloqueia.
    O delegate default é um `InMemorySaver` com a allowlist atual — comportamento
    idêntico ao de antes desta task.

    Duas invariantes de resiliência (P8, revisão G2):
    - **Escrita não-fatal:** falha do delegate durável em `put`/`put_writes` vira
      `log.warning` + no-op naquele passo — a análise NUNCA aborta por causa do
      checkpoint. A mensagem é conservadora (só o nome da operação): mesmo que o
      SQL do saver não carregue a DEK, não ecoamos exceção nenhuma.
    - **Leitura não-fatal:** falha em `get_tuple`/`list` é tratada como "sem
      checkpoint" (None/vazio), então a retomada simplesmente roda do zero.

    A troca do delegate acontece sob um lock CURTO; as leituras do delegate
    tiram um retrato atômico da referência (garantido pelo GIL) e chamam fora do
    lock, para não segurar o lock durante I/O de disco.
    """

    def __init__(self) -> None:
        super().__init__(serde=serde_checkpoint())
        self._delegate: BaseCheckpointSaver[Any] = InMemorySaver(serde=serde_checkpoint())
        self._troca_lock = threading.Lock()

    def _atual(self) -> BaseCheckpointSaver[Any]:
        # Leitura atômica da referência (GIL) — retrato do delegate corrente.
        return self._delegate

    def armar(self, saver: BaseCheckpointSaver[Any]) -> None:
        with self._troca_lock:
            self._delegate = saver

    def desarmar(self) -> None:
        # Volta para um InMemorySaver NOVO: o estado de memória de uma sessão
        # bloqueada não pode vazar para a próxima (ADR-0023).
        with self._troca_lock:
            self._delegate = InMemorySaver(serde=serde_checkpoint())

    def _aviso_nao_fatal(self, operacao: str) -> None:
        log.warning(
            "Checkpoint durável falhou em '%s'; seguindo sem checkpoint neste "
            "passo (degradação segura, ADR-0023/P8).", operacao)

    # ---- escrita (não-fatal) ----
    def put(self, config: Any, checkpoint: Any, metadata: Any,
            new_versions: Any) -> Any:
        try:
            return self._atual().put(config, checkpoint, metadata, new_versions)
        except Exception:  # noqa: BLE001 — a análise nunca aborta pelo checkpoint (G2)
            self._aviso_nao_fatal("put")
            return config

    def put_writes(self, config: Any, writes: Any, task_id: str,
                   task_path: str = "") -> None:
        try:
            self._atual().put_writes(config, writes, task_id, task_path)
        except Exception:  # noqa: BLE001
            self._aviso_nao_fatal("put_writes")

    async def aput(self, config: Any, checkpoint: Any, metadata: Any,
                   new_versions: Any) -> Any:
        try:
            return await self._atual().aput(config, checkpoint, metadata, new_versions)
        except Exception:  # noqa: BLE001
            self._aviso_nao_fatal("aput")
            return config

    async def aput_writes(self, config: Any, writes: Any, task_id: str,
                          task_path: str = "") -> None:
        try:
            await self._atual().aput_writes(config, writes, task_id, task_path)
        except Exception:  # noqa: BLE001
            self._aviso_nao_fatal("aput_writes")

    # ---- leitura (não-fatal ⇒ "sem checkpoint") ----
    def get_tuple(self, config: Any) -> Any:
        try:
            return self._atual().get_tuple(config)
        except Exception:  # noqa: BLE001
            self._aviso_nao_fatal("get_tuple")
            return None

    def list(self, config: Any, *, filter: Any = None,  # noqa: A002 — nome da assinatura da base
             before: Any = None, limit: Any = None) -> Iterator[Any]:
        try:
            yield from self._atual().list(
                config, filter=filter, before=before, limit=limit)
        except Exception:  # noqa: BLE001
            self._aviso_nao_fatal("list")

    async def aget_tuple(self, config: Any) -> Any:
        try:
            return await self._atual().aget_tuple(config)
        except Exception:  # noqa: BLE001
            self._aviso_nao_fatal("aget_tuple")
            return None

    async def alist(self, config: Any, *, filter: Any = None,  # noqa: A002
                    before: Any = None, limit: Any = None) -> Any:
        try:
            async for item in self._atual().alist(
                    config, filter=filter, before=before, limit=limit):
                yield item
        except Exception:  # noqa: BLE001
            self._aviso_nao_fatal("alist")

    # ---- utilitários delegados (não gravam estado) ----
    def get_next_version(self, current: Any, channel: Any = None) -> Any:
        return self._atual().get_next_version(current, channel)

    def delete_thread(self, thread_id: str) -> None:
        # Delegado direto: a higiene/poda que chama isto já é best-effort no
        # chamador (envolvido em try/except), então aqui não mascaramos o erro.
        self._atual().delete_thread(thread_id)

    def with_allowlist(self, extra_allowlist: Any) -> BaseCheckpointSaver[Any]:
        # Preserva a IDENTIDADE do proxy (o grafo compilado guarda esta
        # instância; um clone quebraria a troca de delegate). A allowlist do
        # msgpack já viaja na nossa serde; sob a config atual do LangGraph o
        # reforço estrito está desligado, então devolver `self` mantém o
        # comportamento idêntico ao de hoje (ADR-0023).
        return self


# Proxy singleton compartilhado pelos DOIS grafos (análise e extração): ambos
# compilam com esta mesma instância, então armar/desarmar cobre os dois de uma
# vez (a extração ganha durabilidade de graça — ADR-0023, premissa 2).
_checkpointer: CheckpointerChaveavel | None = None


def criar_checkpointer() -> CheckpointerChaveavel:
    """Proxy chaveável singleton (allowlist explícita; memória por default)."""
    global _checkpointer  # noqa: PLW0603 — singleton lazy
    if _checkpointer is None:
        _checkpointer = CheckpointerChaveavel()
    return _checkpointer


def armar_checkpointer_duravel(saver: BaseCheckpointSaver[Any]) -> None:
    """Liga a durabilidade: o proxy passa a delegar ao `saver` (cofre cifrado)."""
    criar_checkpointer().armar(saver)


def desarmar_checkpointer_duravel() -> None:
    """Desliga a durabilidade: volta ao `InMemorySaver` NOVO (nada vaza entre
    sessões). Chamado no bloqueio/fechamento do cofre, ANTES de zerar a DEK."""
    criar_checkpointer().desarmar()


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
            log.debug("Falha ao obter provider (config): %s", type(e).__name__)
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
        # Só o tipo: `_fatos_de(state)` carrega dados financeiros do usuário.
        log.debug("Falha ao chamar o provider de análise: %s", type(e).__name__)
        return {"motivos": [f"ERRO_PROVIDER:{type(e).__name__}"],
                "tentativas": tentativas}
    if not isinstance(candidata, AnaliseAgente):
        return {"motivos": ["REQ-LLM-002:SCHEMA"], "tentativas": tentativas}
    return {"analise": candidata.model_dump(), "motivos": [],
            "correcao": None, "tentativas": tentativas}


def validar_guardrails(state: EstadoAnalise,
                       runtime: Runtime[ContextoAnalise]) -> dict[str, object]:  # noqa: ARG001 — nome exigido p/ injeção do LangGraph (RunnableCallable casa por nome de parâmetro)
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
           runtime: Runtime[ContextoAnalise]) -> dict[str, object]:  # noqa: ARG001 — idem validar_guardrails
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
             runtime: Runtime[ContextoAnalise]) -> dict[str, object]:  # noqa: ARG001 — idem validar_guardrails
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
    global _grafo  # noqa: PLW0603 — singleton lazy
    if _grafo is None:
        _grafo = _construir()
    return _grafo


def thread_id_analise(cfg: ConfigAgente, fatos: FatosFinanceiros) -> str:
    """thread_id determinístico = `analise:` + assinatura SHA-256 dos fatos.

    Fonte ÚNICA da chave: reusa `cache_global.chave` (a mesma do cache T-205), de
    modo que checkpoint e cache concordem na identidade dos dados — retomar só faz
    sentido para os MESMOS fatos/modelo; dados diferentes ⇒ thread diferente
    (ADR-0023). Calculada sobre `fatos` JÁ anonimizados (mesmo ponto do nó
    `consultar_cache`)."""
    return PREFIXO_THREAD_ANALISE + cache_global.chave(cfg.provider, cfg.model, fatos)


def apagar_thread_analise(thread_id: str) -> None:
    """Apaga o checkpoint de um thread de análise (higiene do sucesso, best-effort).

    Ponto de deleção isolado de propósito: o T-2602 vai chamá-lo DEPOIS de
    persistir a `SecaoIA` (ordem "persistir-antes-de-apagar"); se a deleção
    falhar, o thread completo vira órfão inócuo, podado no próximo início."""
    try:
        criar_checkpointer().delete_thread(thread_id)
    except Exception:  # noqa: BLE001 — deleção é best-effort; órfão é podado depois
        log.warning("Falha ao apagar o checkpoint da análise concluída; "
                    "será podado no próximo início (ADR-0023).")


def podar_threads_analise(thread_id_atual: str) -> None:
    """Máx. 1 thread de análise por vez: ao iniciar um thread novo, apaga todo
    thread de análise de assinatura DIFERENTE (inacabado órfão ou completo que
    escapou da deleção). Consequência documentada (revisão S2): começar a análise
    de dados diferentes ANTES de repetir a interrompida descarta esta última.
    Best-effort — falha de checkpoint nunca atrapalha a análise (P8)."""
    cp = criar_checkpointer()
    try:
        alvos = {
            tid for tup in cp.list(None)
            if (tid := tup.config.get("configurable", {}).get("thread_id"))
            and tid.startswith(PREFIXO_THREAD_ANALISE) and tid != thread_id_atual
        }
        for tid in alvos:
            cp.delete_thread(tid)
    except Exception:  # noqa: BLE001
        log.warning("Poda de threads de análise falhou; seguindo (ADR-0023).")


def _entrada_da_retomada(grafo: GrafoAnalise, config: RunnableConfig, tid: str,
                         entrada_fresca: EstadoAnalise) -> EstadoAnalise | None:
    """Decide, para um thread com retomada ligada, se INVOCA do zero ou RETOMA.

    Regra da revisão S5 — retomada só de thread INACABADO: estado existe e
    `.next` não-vazio ⇒ retoma (input `None`, o LangGraph continua do nó
    pendente); estado existe mas completo (`.next` vazio) ⇒ apaga (nunca serve
    resultado velho) e roda do zero; sem estado ⇒ roda do zero."""
    podar_threads_analise(tid)
    try:
        snap = grafo.get_state(config)
    except Exception:  # noqa: BLE001 — leitura de checkpoint é não-fatal
        return entrada_fresca
    if snap.created_at is None:
        return entrada_fresca  # nenhum checkpoint para este thread
    if snap.next:
        return None  # inacabado: retoma do nó pendente
    apagar_thread_analise(tid)  # completo órfão: apaga e roda do zero
    return entrada_fresca


def executar_analise(fatos: FatosFinanceiros, mapa: MapaAnonimizacao,
                     cfg: ConfigAgente, provider: LLMProvider | None = None,
                     thread_id: str | None = None,
                     retomar: bool = False,
                     apagar_no_fim: bool = True) -> ResultadoAnalise:
    """Invoca o grafo e materializa o `ResultadoAnalise` da aplicação.

    `retomar=True` (opt-in do job da análise): usa o thread_id determinístico
    (assinatura dos fatos), retoma um thread inacabado do checkpoint durável e,
    ao terminar (aprovado OU degradado — ambos são fim legítimo), apaga o thread
    (higiene) — A MENOS que `apagar_no_fim=False` (T-2602, ADR-0023): o job da
    análise sênior precisa persistir a `SecaoIA` ANTES de apagar o checkpoint
    (ordem "persistir-antes-de-apagar" — crash entre os dois deixa um thread
    completo órfão, inócuo, podado no próximo início), então ele mesmo chama
    `apagar_thread_analise` depois de gravar. Os chamadores existentes não
    passam nenhum dos dois parâmetros ⇒ semântica antiga intacta (thread
    efêmero por `uuid4`, sem poda/retomada/apagar)."""
    grafo = grafo_analise()
    tid = thread_id or (thread_id_analise(cfg, fatos) if retomar else str(uuid4()))
    config: RunnableConfig = {"configurable": {"thread_id": tid}}
    entrada_fresca: EstadoAnalise = {"fatos": fatos.model_dump()}
    entrada: EstadoAnalise | None = entrada_fresca
    if retomar:
        entrada = _entrada_da_retomada(grafo, config, tid, entrada_fresca)
    estado = grafo.invoke(
        entrada, config=config,
        context=ContextoAnalise(cfg=cfg, mapa=mapa, provider=provider),
    )
    if retomar and apagar_no_fim:
        apagar_thread_analise(tid)  # fim legítimo ⇒ higiene (T-2602 reordena)
    modo = estado.get("modo", "degradado")
    analise_dump = estado.get("analise")
    return ResultadoAnalise(
        fatos=fatos,
        analise=AnaliseAgente.model_validate(analise_dump)
        if modo == "completo" and analise_dump is not None else None,
        modo=modo,
        guardrails_violados=estado.get("motivos", []) if modo == "degradado" else [],
        aviso_legal=AVISO_LEGAL,
        # T-2602: exposto para o job usar como assinatura persistida (fonte
        # ÚNICA de `thread_id_analise`, nunca recalculada fora daqui) e para
        # apagar o checkpoint DEPOIS de persistir, quando `apagar_no_fim=False`.
        thread_id=tid,
    )
