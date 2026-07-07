# TASKS — Helper Financeiro v2

- **Versão:** 2.3.0 (ciclo aberto) · **Deriva de:** `SPEC.md` / `PLAN.md`
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

## Milestone M7 — Fundação da GUI web (v2.3, ADR-0009)

> Primeira mudança pós-freeze v2.2.0, autorizada pela ADR-0009. Migração
> **paralela/incremental**: `gui_web/` nasce ao lado de `gui/` (tkinter segue
> como entrypoint até a paridade). O núcleo Python continua a FONTE DA VERDADE
> exposto por um sidecar — **sem cálculo em TypeScript**.

| ID | Task | REQ | Depende | Status |
|----|------|-----|---------|--------|
| T-701 | SPEC v2.3 (REQ-F-010+, REQ-NF-005, REQ-SEC-004) + sync do PRD §8 (DEC-2) e do denylist da CONSTITUTION (exceção web/Electron da ADR-0009) | SPEC/PRD/CONST | — | ✅ |
| T-702 | Scaffold `gui_web/` (Electron + Vite + React + TS) com *secure defaults* (`contextIsolation`/`sandbox`/CSP, `contextBridge`) | REQ-SEC-004 | T-701 | ✅ |
| T-703 | Sidecar FastAPI embrulhando `core` (`/health`, `/diagnostico`); loopback + porta efêmera + token por sessão | REQ-NF-005 | T-701 | ✅ |
| T-704 | Ponte tipada `window.hf` (preload) ↔ `main` ↔ sidecar; contrato de estados/erros | REQ-NF-005 | T-702/703 | ✅ |
| T-705 | Design Tokens do brief (cores claro/escuro, Plus Jakarta Sans, radius/sombras) como base do tema | Design | T-702 | ✅ |
| T-706 | CI: etapa Node `gate-front` (ESLint + `tsc` + build Vite, sem binário do Electron); Vitest entra com os testes de unidade (M8); portões Python inalterados | Processo | T-702 | ✅ |
| T-707 | Testes `pytest` do contrato do sidecar (token 401/inválido, validação 422, roundtrip determinístico, casos sem dívidas / reserva sem despesas / ordenação) | REQ-NF-005/SEC-004 | T-703 | ✅ |

## Milestone M8 — Telas 1–3 (v2.3)

| ID | Task | REQ | Depende | Status |
|----|------|-----|---------|--------|
| T-801 | Shell global (topbar + nav das 6 abas) e roteamento de telas; tema segue o SO (toggle no T-904) | REQ-F-010 | M7 | ✅ |
| T-802 | Tela **Visão geral**: hero + anel `conic-gradient` + 4 métricas + dívidas + estratégia (do sidecar, `/estrategias`) | REQ-F-011 | T-801 | ✅ |
| T-803 | Tela **Perfil/orçamento**: cards de categoria + barra de alocação animada + barra-resumo (roll-up do `core`) | REQ-F-012 | T-801 | ✅ |
| T-804 | Tela **Dívidas**: lista editável + estatísticas ponderadas + formulário CRUD (add/editar/remover) | REQ-F-013 | T-801 | ✅ |

## Milestone M9 — Telas 4–6 + paridade (v2.3)

| ID | Task | REQ | Depende | Status |
|----|------|-----|---------|--------|
| T-901 | Tela **Contrato PDF**: drop-zone + extração local com citação + confirmação (`interrupt`→resume); PDF→Markdown + LLM local OpenAI-compat (ADR-0010) | REQ-F-014, GRD-005 | M8 | ✅ |
| T-902 | Tela **Análise**: estratégias/portabilidade recalculadas + IA sênior (job async) + exportações xlsx/docx; teste de anonimização da fronteira cloud (H2/SEC-003) | REQ-F-015 | M8 | ✅ |
| T-903 | Tela **Carta ao credor**: tipos selecionáveis + campos contextuais + pré-visualização ao vivo + `.docx` | REQ-F-016 | M8 | ✅ |
| T-904 | Modo escuro persistido (`localStorage` `hf_dark`) e reidratação ao abrir | REQ-F-010 | T-801 | ⬜ |
| T-905 | Paridade funcional com o tkinter (checklist de equivalência) + E2E Playwright | Processo | T-901..904 | ⬜ |

## Milestone M10 — Empacotamento & freeze v2.3.0

| ID | Task | REQ | Depende | Status |
|----|------|-----|---------|--------|
| T-1001 | Build `electron-builder` + sidecar PyInstaller (`extraResource`); startup/health + shutdown do sidecar | — | M9 | ⬜ |
| T-1002 | Telemetria LangSmith **local/self-hosted** (não sai da máquina) + auto-updater assinado/HTTPS, opt-in via env | REQ-SEC-004 | T-1001 | ⬜ |
| T-1003 | Revisão de segurança do shell web (CSP, sem código remoto, loopback+token, sem PII) → doc | SEC | T-1001 | ⬜ |
| T-1004 | Troca do entrypoint para a GUI web (tkinter aposentada ou mantida como fallback) | Processo | T-905 | ⬜ |
| T-1005 | Ata de freeze v2.3.0 (SHA-256 dos artefatos + binário) e docs sincronizados | Processo | todos | ⬜ |

---

## Definição de Pronto (DoD)
Uma task só é ✅ quando: (1) o código adere ao SPEC/PLAN; (2) há teste no
harness cobrindo o REQ; (3) o teste passa offline; (4) nenhum guardrail é
violado; (5) sem PII/chave em claro.

## Próxima ação recomendada
**Ciclo v2.3 ABERTO (ADR-0009).** **T-701 concluída**: SPEC v2.3 com
REQ-F-010..016 (6 telas) + REQ-NF-005 (contrato do sidecar) + REQ-SEC-004
(loopback+token, Electron seguro, telemetria local opt-in); PRD §8 DEC-2
refinada para "offline por padrão, conectividade opt-in"; denylist da
CONSTITUTION sincronizado (exceção web/Electron). **T-702 e T-703 concluídas**:
sidecar FastAPI (`/health`, `/diagnostico`, loopback + token, validado por
`tests/test_sidecar.py` + smoke real) e o front `gui_web/` (Electron+Vite+React
+TS, *secure defaults*, ponte `window.hf`) — **launch real confirmado pelo
mantenedor** (a janela conecta ao sidecar e exibe o diagnóstico do `core`).
**M7 e M8 fechados.** T-801..T-804 ✅ — **Visão geral** (dashboard reativo),
**Perfil/orçamento** editável (campos pt-BR, subtotais/alocação/resumo do core
ao vivo) e **Dívidas** (CRUD add/editar/remover + estatísticas ponderadas —
taxa média pelo saldo e custo até quitar calculados no `core` via
`taxa_media_ponderada`/`custo_total_ate_quitar`, barra de participação por
dívida) confirmadas visualmente. **M9 em andamento: T-901 ✅** — **Contrato
PDF**: drop-zone, extração **local** com citação da fonte e `interrupt`→resume.
No caminho, a **ADR-0010**: extração PDF→**Markdown** (`pymupdf4llm`, fallback
`pdfplumber`) para dar mais sinal à LLM, e suporte a **LLM local
OpenAI-compatible** (LM Studio/llama.cpp) — a invariante H2 passou a ser **por
endpoint (loopback)**, não pelo nome do provider. Extração assistida validada
end-to-end com o LM Studio (`scripts/diag_llm.py`). **T-902 ✅** — tela
**Análise**: pacote determinístico no sidecar (`/analise`: estratégias com
extra, oportunidades de portabilidade com taxa-alvo e recomendações — tudo do
`core`), **análise sênior como job assíncrono** (`/analise/ia` + poll; fatos
anonimizados CREDOR_n, desanonimização só na fronteira de exibição) e
exportações `.xlsx`/`.docx` (`/exportar/*`; o Electron abre o diálogo nativo e
o sidecar escreve o arquivo). Teste de anonimização da fronteira cloud
(H2/SEC-003) com provider espião em `tests/test_sidecar.py`. No teste manual, a
IA sênior degradava sempre com `NUMEROS_FABRICADOS` no modelo local 3B — a
**ADR-0011** corrige: recuperação única com **feedback dos números órfãos** +
nó `sanear` (redação determinística das frases órfãs, H1 preservado); validado
4/4 com o ministral-3b real. **T-903 ✅** — tela **Carta ao credor**:
`outputs/proposta.py` refatorada com `montar_carta()` (fonte única do texto,
data em pt-BR sem depender de locale); sidecar `/carta/previa`
(pré-visualização ao vivo = exatamente o texto do `.docx`) e `/exportar/carta`;
tela com cards de tipo (quitação/portabilidade/redução), campos contextuais
por tipo e assinatura (nome/CPF ficam locais). **Próximo: T-904** (modo escuro
persistido), depois T-905 (paridade + E2E). Nova ata `FREEZE.md` v2.3.0 no
fechamento (M10).
