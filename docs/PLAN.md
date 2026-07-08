# PLAN — Helper Financeiro v2

- **Versão:** 2.0.0 · **Implementa:** `SPEC.md` · **Regido por:** `CONSTITUTION.md`

---

## 1. Arquitetura em camadas

```
┌─────────────────────────────────────────────────────────────┐
│  gui/  (tkinter)  — apresenta números + análise da IA         │
│                     com separação visual explícita            │
└───────────────▲───────────────────────────▲──────────────────┘
                │                            │
        ResultadoAnalise             (arquivos .xlsx/.docx)
                │                            │
┌───────────────┴───────────────┐   ┌────────┴───────────────────┐
│  agent/  (orquestra a IA)      │   │  outputs/ (geradores)      │
│  agente.py · provider.py       │   │  planilha · relatorio ·    │
│  prompts.py · schemas · config │   │  proposta                  │
└───────▲───────────────▲────────┘   └────────────────────────────┘
        │               │
   FatosFinanceiros   guardrails/  (pii · validador_numerico · conteudo)
        │               │
┌───────┴───────────────┴────────────────────────────────────────┐
│  core/  (motor determinístico — Python puro, FONTE DA VERDADE)   │
│  models · calculos · diagnostico · estrategias · extrator_pdf    │
└──────────────────────────────────────────────────────────────────┘
```

**Regra de dependência (P1/REQ-NF-004):** setas só apontam para baixo. `core`
não importa `agent`, `outputs` nem `gui`. `agent` depende de `core`,
`guardrails` e `contracts`. Nada importa `gui`.

**Camada `contracts/` (ADR-0004):** os schemas Pydantic vivem em
`contracts/schemas.py`, pacote sem dependências internas. `agent` e
`guardrails` importam tipos apenas de lá — nunca um do outro.

## 2. Fluxo de uma análise (caminho feliz)

Desde o ADR-0006 o fluxo é um **StateGraph** (`agent/grafo.py`) — nós puros,
arestas explícitas, LLM só nas pontas (Code-First):

1. GUI monta `PerfilFinanceiro` (entradas do usuário + PDF conferido).
2. `core` calcula tudo → `diagnostico` + `estrategias`.
3. `agent.montar_fatos()` converte em `FatosFinanceiros` e **anonimiza**
   (guardrails/pii) → tokens `CREDOR_n`, `PESSOA_n`.
4. O grafo executa: cinto PII (H2, pré-cloud) → cache (T-205) → provider
   (local Ollama ou cloud) com **saída estruturada** e 1 retry (REQ-LLM-002).
5. `guardrails` validam: schema → **consistência numérica (H1)** → conteúdo (H6)
   → aviso legal (H3).
6. Se ok: `de-tokeniza` para exibição e devolve `ResultadoAnalise(modo="completo")`.
7. Se qualquer etapa falhar: toda aresta de erro converge para o nó `degradar`
   → `ResultadoAnalise(modo="degradado")` com o determinístico intacto (P8).

## 2.1 Fluxo de extração de documento (Fase 2.5, Code-First na entrada)

`agent/extracao.py` + `agent/ingestao.py` (ADR-0007). O modelo **extrai**
variáveis (`capital`, `taxa`, `prazo`...), o código **verifica** e **calcula**:

1. `ingestao.carregar_documento()` lê o PDF/extrato (texto = entrada NÃO
   confiável, H5); `preparar_contexto()` faz retrieval top-k se o texto não
   couber na janela (LlamaIndex `as_retriever`, nunca `as_query_engine`).
2. Nó `extrair`: LLM local (cloud é RECUSADA — o documento bruto tem PII, H2)
   devolve `ExtracaoContrato` com **citação verbatim obrigatória** por campo.
3. Nó `verificar` (código puro): quote-check (trecho existe? o valor está no
   trecho?) descarta campo sem fonte; checagem cruzada recalcula a parcela
   via Price e flagra inconsistências.
4. Nó `confirmar`: o grafo **pausa** (`interrupt` + checkpoint) e a GUI mostra
   os campos pré-preenchidos — o humano confere e o grafo retoma (M3).
5. Falha em qualquer ponto ⇒ nó `falhar` com motivo; o chamador cai no
   extrator regex determinístico (`core/extrator_pdf.py`) — P8 na entrada.

## 3. Stack (congelada — ver Denylist na CONSTITUTION)

| Camada | Tecnologia | Justificativa |
|---|---|---|
| Linguagem | Python 3.12+ | v1, empacotável em `.exe` |
| GUI | tkinter (stdlib) | offline, sem JS, vira `.exe` |
| Planilha | openpyxl | fórmulas + gráfico |
| Documentos | python-docx | `.docx` sem Node |
| PDF (LLM) | pymupdf4llm → Markdown | ADR-0010: tabelas p/ a extração; AGPL (uso não-comercial) |
| PDF (fallback/regex) | pdfplumber | extração de texto (MIT) |
| OCR local | rapidocr (PP-OCRv6 medium, ONNX) + onnxruntime | ADR-0015: scan/imagem, 100% local (H2/H7); rasterização via PyMuPDF |
| Schemas | pydantic v2 | contratos tipados |
| LLM (structured) | JSON Schema nativo (Ollama `format` / `response_format`) + Pydantic, via stdlib | ADR-0005: sem SDK/framework |
| Orquestração | LangGraph (StateGraph + interrupt + InMemorySaver) | ADR-0006: fluxo rígido, pausa p/ humano |
| Ingestão/RAG | LlamaIndex core (retriever-only) + embeddings via Ollama | ADR-0007: local, sem torch |
| LLM local | Ollama (`/api/chat`) OU OpenAI-compatible local (LM Studio/llama.cpp, `/v1`) — loopback | ADR-0010: local por endpoint |
| Testes | pytest | harness |

**Não entram (denylist):** frameworks web, ORMs, libs de telemetria, cálculo
financeiro dentro de prompts.

## 4. Provider agnóstico (REQ-LLM-003/004)

- Interface única `LLMProvider.analisar(fatos) -> AnaliseAgente`.
- Implementações: `OllamaProvider` (base_url local), `OpenAICompatProvider`,
  `FakeProvider` (determinístico, para o harness — sem rede).
- Seleção por `agent/config.py` (env). Padrão recomendado: **local-first**.

## 5. Anonimização (REQ-GRD-002/SEC-003)
- `mascarar(perfil) -> (fatos_tokenizados, mapa)`; `mapa` só em memória.
- Tokens estáveis por execução: `CREDOR_1..n` na ordem das dívidas.
- `desmascarar(texto, mapa)` restaura para exibição local.

## 6. Guardrail de consistência numérica (REQ-GRD-001/H1)
- Extrai todos os números (R$, %, inteiros) dos campos de texto da `AnaliseAgente`.
- Compara com o conjunto permitido (todos os números de `FatosFinanceiros`).
- Tolerância: ±1% relativo (moeda/%) e exato (contagens).
- Número órfão ⇒ violação ⇒ modo degradado + log do REQ violado.

## 7. Sequenciamento (milestones)
- **M1 — Contratos & guardrails determinísticos** (schemas, pii, validador,
  conteúdo) + harness verde offline. *Sem LLM real ainda (FakeProvider).*
- **M2 — Providers reais** (Ollama, OpenAI-compat) + config + degradação.
- **M2.5 — Orquestração em grafo + extração Code-First** (LangGraph,
  LlamaIndex retriever-only, verificador com citação obrigatória).
- **M3 — Integração de saída** (narrativa no `.docx`, painel na GUI e tela de
  confirmação da extração retomando o checkpoint do grafo). A desanonimização
  acontece SÓ na fronteira da exibição: `agent/exibicao.py` produz `SecaoIA`
  (contracts) com os nomes reais; `gui/` e `outputs/` apenas renderizam.
- **M4 — Empacotamento** (.exe) e ata de freeze.
- **M5 — Perfil como orçamento detalhado** (v2.2, ADR-0008): categorias
  tipadas no `core` com roll-up determinístico (`com_orcamento`), indicador
  de cobertura da reserva (`meses_reserva`) e aba Perfil com itemização
  obrigatória + resumo ao vivo; decisões DEC-1..DEC-4 registradas no PRD §8
  (inclui generalizar menções a programas públicos de renegociação).
- **M6 — Revisão de UI/UX** (v2.2): validação visual de campos numéricos
  (`core.utils.texto_numerico_valido`, REQ-F-009), aba Perfil rolável,
  contador de dívidas na aba, barra de status contextual, edição de dívida
  por duplo clique/Enter/Delete e tema consistente (molduras + lista
  zebrada). A GUI segue casca fina: a lógica testável fica no `core`.

### Ciclo v2.3 — Redesign "Clareza" (GUI web, ADR-0009)

> Migra a apresentação de `tkinter` para **Electron + React/TypeScript**
> (sidecar Python como FONTE DA VERDADE — sem cálculo em TS). Cadência
> **paralela/incremental**: `gui_web/` nasce ao lado de `gui/`, que segue
> como entrypoint até a paridade das 6 telas. DEC-2 refinada para "offline
> por padrão, conectividade opt-in".

- **M7 — Fundação da GUI web**: SPEC v2.3 (REQ-F-010+, REQ-NF-005,
  REQ-SEC-004) e sync do PRD §8 (DEC-2); scaffold Electron + Vite + React + TS
  com *secure defaults* (`contextIsolation`/`sandbox`/CSP, `contextBridge`);
  sidecar FastAPI embrulhando `core`/`agent`/`guardrails`/`outputs`
  (loopback + token por sessão); Design Tokens do brief; CI com etapa de
  `lint/test/build` do front.
- **M8 — Telas 1–3**: Visão geral (dashboard + anel `conic-gradient`),
  Perfil/orçamento (barra de alocação + resumo) e Dívidas (CRUD + estatísticas
  ponderadas), consumindo o sidecar.
- **M9 — Telas 4–6**: Contrato PDF (extração com citação + confirmação via
  `interrupt`/resume), Análise (estratégias/portabilidade/IA sênior +
  exportações) e Carta ao credor; modo escuro persistido (`localStorage`);
  paridade funcional com o tkinter.
- **M10 — Empacotamento & freeze v2.3.0**: build `electron-builder` +
  sidecar PyInstaller (`extraResource`), tracing LangSmith local + updater
  assinado (opt-in), revisão de segurança, troca do entrypoint e ata
  `FREEZE.md` v2.3.0.

## 8. Riscos técnicos
- Modelos locais pequenos podem não aderir bem ao schema → o `format` do
  Ollama restringe a gramática no servidor (ADR-0005); o que escapar, o
  contrato Pydantic rejeita e o `MODO_DEGRADADO` segura (P8). Medir com
  `scripts/bench_schema.py` antes de fixar o `HF_MODEL` padrão.
- Extração pode alucinar valores → citação verbatim obrigatória + quote-check
  + checagem cruzada Price + confirmação humana (M2.5); pior caso: fallback
  ao extrator regex.
- Peso de langgraph/llama-index no freeze → spike T-257 mediu: ~84 MB
  `--onefile`, sem collects extras. Aceito.
- pdfplumber no PyInstaller → `--collect-all` (ver README).
- rapidocr/onnxruntime no PyInstaller (ADR-0015, T-1404) → os modelos ONNX são
  *data files* e o onnxruntime/cv2/shapely trazem binários nativos; o
  `SidecarHF.spec` os embarca com `collect_all` (`rapidocr`, `onnxruntime`,
  `cv2`, `shapely`). O wheel do rapidocr só traz os modelos tiny/small, então
  os **medium** (det+rec, ~132 MB) são materializados na venv por
  `scripts/preparar_ocr.py` ANTES do freeze (rede só no build); o spec TRAVA o
  build se algum `.onnx` obrigatório faltar (`agent.ocr.MODELOS_OCR_NECESSARIOS`).
  Sem download em execução (REQ-NF-006) — validado no smoke do pacote que OCRiza
  de verdade (`e2e/empacotado.spec.ts`). Config validada em runtime: PP-OCRv6
  medium, `lang_type='pt'` (modelo multilíngue único; `lang_type` é string).
