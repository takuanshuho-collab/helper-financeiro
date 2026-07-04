# ADR-0006 — LangGraph como orquestrador do pipeline do agente

- **Status:** Aceita · **Data:** 2026-07-04
- **Relacionada a:** REQ-LLM-001/002, REQ-SEC-003, P8, T-251/T-252, ADR-0005
- **Supersede parcialmente:** ADR-0005 (apenas a camada de orquestração; a
  camada de chamada ao LLM permanece como decidida lá)

## Contexto

A Fase 2.5 adiciona ao pipeline duas capacidades que o loop manual de
`agent/agente.py` não comporta bem:

1. **Extração Code-First de documentos** (contratos/extratos): o fluxo ganha
   nós novos (ingestão → extração → verificação → **confirmação humana** →
   cálculo → narrativa) e a confirmação humana exige **pausar e retomar** a
   execução com estado preservado.
2. **Persistência de estado (memória de sessão)**: retomar uma análise do
   ponto em que parou, por `thread_id`.

Implementar pausa/retomada e checkpoints à mão é exatamente o tipo de
infraestrutura que não é diferencial do produto. O LangGraph oferece
`StateGraph` (fluxo rígido e explícito), `interrupt()` (human-in-the-loop) e
checkpointers plugáveis — e os nós são **funções Python puras**, sem exigir
os wrappers de LLM do LangChain.

## Decisão

**LangGraph orquestra; os providers do ADR-0005 continuam fazendo a chamada.**

- `agent/grafo.py` define o `StateGraph` com o fluxo rígido:
  `anonimizar → cache → chamar_llm → validar → aprovar | degradar`
  (e, com documento anexado: `extrair → verificar → confirmar (interrupt)`
  antes do cálculo determinístico).
- Cada nó é uma função pura sobre `EstadoAnalise` (TypedDict). Os nós de LLM
  chamam `OllamaProvider`/`OpenAICompatProvider` (stdlib + structured output
  nativo) — o ADR-0005 permanece válido nessa camada.
- A recuperação de schema (REQ-LLM-002: exatamente **1** retry com feedback)
  vira **aresta condicional explícita** `validar_schema → chamar_llm`, não
  `RetryPolicy` — ela é semântica, não transitória, e o contrato "1
  recuperação" precisa continuar visível e testável.
- **Checkpointer padrão: `InMemorySaver`** (memória do processo), com
  `thread_id` por sessão. Persistir em disco (`langgraph-checkpoint-sqlite`)
  fica **adiado e condicionado ao REQ-SEC-003**: só estado pós-anonimização e
  com opt-in explícito do usuário — LGPD manda aqui.
- O que o modelo decide continua sendo **nada**: o grafo é fixo, o LLM aparece
  só nos nós de extração e narrativa (Code-First). Sem tool-calling/ReAct —
  modelos de 3B são pouco confiáveis orquestrando ferramentas e o fluxo do
  produto é fixo por definição.

## Consequências

- P8 inalterado: toda aresta de falha converge para o nó `degradar`, que
  entrega o determinístico com o motivo registrado. O harness existente
  (58 testes) é a rede de proteção da refatoração e DEVE permanecer verde
  sem alteração de comportamento.
- `interrupt()` + checkpointer viabilizam o fluxo "confira antes de adicionar"
  da GUI (M3) sem gambiarras de estado global.
- Custo assumido: `langgraph` puxa `langchain-core`/`langsmith` como deps
  transitivas (~10 pacotes). Telemetria do LangSmith permanece **desligada**
  (opt-in por env `LANGSMITH_TRACING`, que não setamos) — nada sai da máquina.
- Risco M4 (freeze PyInstaller) antecipado pelo spike T-257.

## Modelo padrão (T-253)

`HF_MODEL` padrão passa de `qwen2.5:14b` para **`qwen2.5:3b`** — na GPU-alvo
(GTX 1650, 4 GB de VRAM) o 3B roda na GPU; o 14B nem carrega e o 7B
transborda para CPU. **Atenção à licença:** o Qwen2.5-3B usa a *Qwen Research
License* (não comercial; 0.5B/7B/14B são Apache 2.0).

**Bench na máquina-alvo (2026-07-04, n=3, timeout 300 s, num_ctx 8192):**

| modelo | schema | grounding | conteúdo | latência média |
|---|---|---|---|---|
| qwen2.5:3b | 100% | 100% | 100% | ~168 s |
| qwen3:4b | 0% (3× timeout) | — | — | >300 s |

O `qwen3:4b` (Apache 2.0) ficou **inviável neste hardware**: com o KV cache
de 8192 ele ocupa ~4,1 GB e transborda para CPU (45%/55%), estourando o
timeout nas 3 chamadas — agravado pelo modo *thinking* do Qwen3. Comparativo
histórico: o `qwen2.5:0.5b` fazia 100% de schema mas só 67% de grounding; o
3B fecha 100% em tudo. **Decisão: `qwen2.5:3b` como padrão.** Se o uso
comercial exigir Apache 2.0 neste hardware, os candidatos a testar são
`qwen3:1.7b` ou reduzir `num_ctx`; com mais VRAM, `qwen3:4b`/`qwen2.5:7b`.
A latência (~2,8 min/análise) reforça o T-303 (barra de progresso em thread).
