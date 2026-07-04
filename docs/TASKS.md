# TASKS — Helper Financeiro v2

- **Versão:** 2.2.0 · **Deriva de:** `SPEC.md` / `PLAN.md`
- **Regra:** toda task cita o(s) `REQ-ID` que satisfaz e só fecha com teste.

Legenda de status: ⬜ pendente · 🟨 em andamento · ✅ feito (neste scaffold)

---

## Milestone M1 — Contratos & guardrails determinísticos

| ID | Task | REQ | Depende | Status |
|----|------|-----|---------|--------|
| T-101 | Definir schemas Pydantic (`agent/schemas.py`) | SPEC §6 | — | ✅ |
| T-102 | `agent/prompts.py` com system prompt do CONSELHEIRO | REQ-LLM-001/005 | T-101 | ✅ |
| T-103 | Anonimização de PII (`guardrails/pii.py`) | REQ-GRD-002, SEC-003 | T-101 | ✅ |
| T-104 | Validador de consistência numérica (`guardrails/validador_numerico.py`) | REQ-GRD-001 | T-101 | ✅ |
| T-105 | Filtro de conteúdo + aviso legal (`guardrails/conteudo.py`) | REQ-GRD-003/004 | T-101 | ✅ |
| T-106 | `FakeProvider` determinístico | REQ-LLM-002 | T-101 | ✅ |
| T-107 | `montar_fatos()` core→FatosFinanceiros (`agent/agente.py`) | REQ-LLM-001 | T-101,T-103 | ✅ |
| T-108 | Orquestração + degradação segura (`agent/agente.py`) | REQ-LLM-002, P8 | T-104..T-107 | ✅ |
| T-109 | Harness offline (`tests/`) cobrindo M1 | HARNESS §1 | T-103..T-108 | ✅ |

## Milestone M1.5 — Conformidade (auditoria 2026-07-03)

> Fecha as divergências spec×código apontadas em `docs/AUDITORIA-2026-07-03.html`.

| ID | Task | REQ / Achado | Status |
|----|------|--------------|--------|
| T-151 | Camada `contracts/` quebra ciclo guardrails↔agent (ADR-0004) | REQ-NF-004 / F-05 | ✅ |
| T-152 | Retry único na chamada ao provider | REQ-LLM-002 / F-06 | ✅ |
| T-153 | Cinto de segurança `contem_pii()` pré-cloud | REQ-GRD-002 / F-07 | ✅ |
| T-154 | Testes de outputs (Gate B estrutural) | REQ-NF-003, H3/H4 / F-04 | ✅ |
| T-155 | Config lê env em tempo de execução | SEC-002 / F-11 | ✅ |
| T-156 | Testes de propriedade (Hypothesis) no core | REQ-F-001 / F-12 | ✅ |
| T-157 | Estabilidade numérica de Price (log1p/expm1) — bug achado por T-156 | REQ-F-001 | ✅ |
| T-158 | Limites do grounding e do simulador documentados | F-09/F-10 | ✅ |

## Milestone M2 — Providers reais

| ID | Task | REQ | Depende | Status |
|----|------|-----|---------|--------|
| T-201 | `OllamaProvider` (local-first, `/api/chat` + `format`=JSON Schema) | REQ-LLM-003/004 | T-106 | ✅ |
| T-202 | `OpenAICompatProvider` (nuvem, via env, `response_format` strict) | REQ-LLM-003, SEC-002 | T-106 | ✅ |
| T-203 | `agent/config.py` (provider, base_url, model, modo_degradado, cache) | REQ-LLM-003 | — | ✅ |
| T-204 | Structured output nativo + validação Pydantic (ADR-0005; sem `instructor`) | REQ-LLM-002 | T-201/202 | ✅ |
| T-205 | Cache local de análise (LRU em memória, só análise aprovada) | NF/RISCO, SEC-003 | T-201 | ✅ |
| T-206 | Teste de degradação com provider offline real (porta fechada) | P8 | T-201 | ✅ |
| T-207 | Bench de aderência de schema por modelo (`scripts/bench_schema.py`) | REQ-LLM-002 | T-201 | ✅ |
| T-208 | Suíte de integração `pytest -m ollama` (skip sem servidor/modelo) | REQ-LLM-004 | T-201 | ✅ |
| T-209 | Contrato reforçado: `confianca` com `ge=0/le=1` (achado do T-208) | SPEC §6.2 | T-208 | ✅ |

## Milestone M2.5 — Orquestração em grafo + extração Code-First (Fase 2.5)

> ADR-0006 (LangGraph orquestra; providers do ADR-0005 mantidos como nós) e
> ADR-0007 (LlamaIndex retriever-only na ingestão). O modelo extrai variáveis
> e narra; o CÓDIGO verifica, calcula e decide rota — Code-First nas 2 pontas.

| ID | Task | REQ | Depende | Status |
|----|------|-----|---------|--------|
| T-251 | ADR-0006 — LangGraph como orquestrador (supersede parcial do ADR-0005) | P8, REQ-LLM-002 | — | ✅ |
| T-252 | `agent/grafo.py`: StateGraph (pii→cache→llm⇄retry→guardrails→aprovar/degradar), InMemorySaver | REQ-LLM-002, SEC-003 | T-251 | ✅ |
| T-253 | `HF_MODEL` padrão → `qwen2.5:3b` (GPU 4 GB) + bench vs `qwen3:4b` (licença) | REQ-LLM-004 | T-252 | ✅ |
| T-254 | ADR-0007 — LlamaIndex ingestão local (retriever-only, embeddings Ollama) | REQ-NF-002, H2 | — | ✅ |
| T-255 | `agent/ingestao.py` + `agent/extracao.py`: extração estruturada com citação obrigatória e pausa p/ confirmação (`interrupt`) | REQ-GRD-005, H5 | T-254 | ✅ |
| T-256 | Verificador determinístico (quote-check + checagem cruzada Price) + harness | REQ-GRD-001 (na entrada) | T-255 | ✅ |
| T-257 | Spike freeze PyInstaller com langgraph+llama-index (~84 MB, sem collects extras) | risco M4 | T-252/255 | ✅ |
| T-258 | Docs sincronizados (PLAN/TASKS/HARNESS/INDEX/README) + CI verde | Processo | todos | ✅ |

## Milestone M3 — Integração de saída

> A lógica testável vive fora do tkinter: `contracts.SecaoIA` + `agent/exibicao.py`
> (fronteira da desanonimização, REQ-SEC-003) alimentam a GUI e o `.docx`;
> `gui/app.py` permanece casca fina (fora dos portões, ver pyproject).

| ID | Task | REQ | Depende | Status |
|----|------|-----|---------|--------|
| T-301 | Seção "Análise do Agente (IA)" no `.docx`, separada dos números (`SecaoIA` + `agent/exibicao.py`) | REQ-GRD-003 | T-108 | ✅ |
| T-302 | Painel na GUI com narrativa + rótulo "assistido por IA" | REQ-LLM-001, P2 | T-108 | ✅ |
| T-303 | Botão "Gerar análise sênior" com barra de progresso (thread+fila+`after`) | NF-usabilidade | T-302 | ✅ |
| T-304 | Indicador visual de modo degradado na GUI (status colorido + motivos) | P8 | T-302 | ✅ |
| T-305 | Tela de confirmação da extração (Toplevel com campos+citações) retomando o checkpoint (`interrupt`→`Command(resume)`) | REQ-GRD-005, H5 | T-255 | ✅ |

## Milestone M4 — Empacotamento & freeze

| ID | Task | REQ | Depende | Status |
|----|------|-----|---------|--------|
| T-401 | Build PyInstaller definitivo (`HelperFinanceiro.exe` ~94 MB, onefile/windowed; langgraph/llama-index sem collects extras) | — | M3 | ✅ |
| T-402 | Ata de freeze com SHA-256 dos artefatos (v2, escopo M1..M4) | Processo | todos | ✅ |
| T-403 | Revisão de segurança (sem PII/keys em log) → `docs/REVISAO-SEGURANCA.md` | SEC-001/002 | M2 | ✅ |
| T-404 | Higiene de checkpoint: estado dos grafos só com dicts (`model_dump`) + allowlist msgpack explícita no serializador | SEC-003 | T-252/T-255 | ✅ |

## Milestone M5 — Perfil como orçamento detalhado (v2.2, ADR-0008)

> Reabre o desenvolvimento pós-freeze v2.1.0 com autorização formal da
> ADR-0008; nova ata de freeze será lavrada no fechamento do ciclo v2.2.

| ID | Task | REQ | Depende | Status |
|----|------|-----|---------|--------|
| T-501 | PRD: resolver NC-1..NC-4 como DEC-1..DEC-4 (agnóstico/local padrão; 100% offline; sem orçamento formal de tokens; programas generalizados) | PRD §8 | — | ✅ |
| T-502 | Generalizar menção a programas públicos (prompts, AGENT.md, README) — Desenrola encerrado | DEC-4, RES-4 | T-501 | ✅ |
| T-503 | `core/models.py`: `ComposicaoRenda`/`DespesasFixas`/`DespesasVariaveis` + `PerfilFinanceiro.com_orcamento` (roll-up) + `meses_reserva` | REQ-F-006/007 | — | ✅ |
| T-504 | GUI: aba Perfil com itemização obrigatória, totais ao vivo, cobertura da reserva e resumo (fluxo/comprometimento) | REQ-F-008 | T-503 | ✅ |
| T-505 | Harness: `tests/test_orcamento.py` (roll-up, meses de reserva, retrocompatibilidade, propriedade Hypothesis) | REQ-F-006/007 | T-503 | ✅ |
| T-506 | Docs sincronizados (PRD/SPEC/PLAN/TASKS/HARNESS/INDEX + ADR-0008) e CI verde | Processo | todos | ✅ |

## Milestone M6 — Revisão de UI/UX (v2.2)

> A GUI continua fora dos portões de cobertura; a lógica nova testável
> (`texto_numerico_valido`) vive no `core` e tem harness próprio.

| ID | Task | REQ | Depende | Status |
|----|------|-----|---------|--------|
| T-601 | `core.utils.texto_numerico_valido` + testes (padrão BR, vazio = válido) | REQ-F-009 | — | ✅ |
| T-602 | Validação visual ao vivo dos campos numéricos (estilo `Invalido.TEntry` via trace) | REQ-F-009 | T-601 | ✅ |
| T-603 | Aba Perfil rolável (Canvas + Scrollbar + roda do mouse) p/ não cortar campos | NF-usabilidade | M5 | ✅ |
| T-604 | Contador de dívidas no rótulo da aba + barra de status contextual por aba | NF-usabilidade | — | ✅ |
| T-605 | Ergonomia da aba Dívidas: duplo clique edita, Enter adiciona, Delete remove | NF-usabilidade | — | ✅ |
| T-606 | Tema consistente: molduras no fundo padrão e lista de dívidas zebrada | NF-usabilidade | — | ✅ |
| T-607 | Docs sincronizados (SPEC/PLAN/TASKS/HARNESS/INDEX) + smoke GUI + CI verde | Processo | todos | ✅ |

---

## Definição de Pronto (DoD)
Uma task só é ✅ quando: (1) o código adere ao SPEC/PLAN; (2) há teste no
harness cobrindo o REQ; (3) o teste passa offline; (4) nenhum guardrail é
violado; (5) sem PII/chave em claro.

## Próxima ação recomendada
**Ciclo v2.2 (ADR-0008): M5 e M6 entregues.** Perfil como orçamento
detalhado com roll-up no `core` e resumo ao vivo (M5); revisão de UI/UX com
validação visual, aba rolável, ergonomia da lista e tema consistente (M6).
Próximo passo para fechar o ciclo v2.2: **nova ata de freeze** — rebuild do
`.exe`, recalcular os SHA-256 (agora incluindo `ADR-0008`,
`tests/test_orcamento.py`, `tests/test_validacao_texto.py` e os fontes
alterados) e incrementar a versão da ata.
