# TASKS — Helper Financeiro v2

- **Versão:** 2.12.0 (ciclo ABERTO — ADR-0020; v2.11.0 congelada na ata `FREEZE.md`) · **Deriva de:** `SPEC.md` / `PLAN.md`
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
| T-904 | Modo escuro persistido (`localStorage` `hf_dark`) e reidratação ao abrir | REQ-F-010 | T-801 | ✅ |
| T-905 | Paridade funcional com o tkinter (checklist de equivalência) + E2E Playwright | Processo | T-901..904 | ✅ |

## Milestone M10 — Empacotamento & freeze v2.3.0

| ID | Task | REQ | Depende | Status |
|----|------|-----|---------|--------|
| T-1001 | Build `electron-builder` + sidecar PyInstaller (`extraResource`); startup/health + shutdown do sidecar | — | M9 | ✅ |
| T-1002 | Telemetria LangSmith **local/self-hosted** (não sai da máquina) + auto-updater assinado/HTTPS, opt-in via env | REQ-SEC-004 | T-1001 | ✅ |
| T-1003 | Revisão de segurança do shell web (CSP, sem código remoto, loopback+token, sem PII) → doc | SEC | T-1001 | ✅ |
| T-1004 | Troca do entrypoint para a GUI web (tkinter aposentada ou mantida como fallback) | Processo | T-905 | ✅ |
| T-1005 | Ata de freeze v2.3.0 (SHA-256 dos artefatos + binário) e docs sincronizados | Processo | todos | ✅ |

## Milestone M11 — Rubricas do orçamento + persistência local (v2.4, ADR-0012)

> Primeira mudança pós-freeze v2.3.0, autorizada pela ADR-0012. Cada campo do
> Perfil pode ser detalhado em **rubricas** criadas pelo usuário (roll-up no
> core); o estado (perfil + dívidas + rubricas) passa a ser **persistido em
> SQLite local** gerido pelo sidecar — o app lembra do usuário entre sessões.

| ID | Task | REQ | Depende | Status |
|----|------|-----|---------|--------|
| T-1101 | ADR-0012 + bump 2.4.0 + camada de persistência SQLite no sidecar (repositório, schema v1 com `esquema`/`estado`/`rubrica`, `HF_DB_PATH`) + testes | REQ-F-018 | — | ✅ |
| T-1102 | Persistência de perfil + dívidas fim-a-fim: `GET/POST /estado`, hidratação no boot da GUI, auto-save com debounce | REQ-F-018 | T-1101 | ✅ |
| T-1103 | Rubricas no core (roll-up campo↔rubricas, campo com rubricas = soma) + endpoints CRUD no sidecar + testes | REQ-F-017 | T-1101 | ✅ |
| T-1104 | Tela "Planilha de orçamento" (grade editável: grupos expansíveis, adicionar/remover/renomear, subtotais ao vivo) + integração com a aba Perfil (campo detalhado somente-leitura + selo "detalhado ▸") | REQ-F-017 | T-1103 | ✅ |
| T-1105 | Rubricas no export `.xlsx`, `PARIDADE.md` atualizado e E2E Playwright dos fluxos novos (banco isolado por `HF_DB_PATH`) | REQ-F-017/018 | T-1104 | ✅ |
| T-1106 | Fechamento do ciclo: gates verdes, ata `FREEZE.md` v2.4.0 e docs sincronizados | Processo | todos | ✅ |

## Milestone M12 — Histórico mensal do orçamento (v2.5, ADR-0013)

> Primeira mudança pós-freeze v2.4.0, autorizada pela ADR-0013. O orçamento
> vivo ganha a dimensão TEMPO: "Arquivar mês" grava a competência (perfil +
> rubricas com `mes = 'AAAA-MM'`, coluna reservada no schema v1) e o core
> compara competências campo a campo. Bônus: sugestões de nome de rubrica.

| ID | Task | REQ | Depende | Status |
|----|------|-----|---------|--------|
| T-1201 | ADR-0013 + bump 2.5.0 + core `comparar_orcamentos` + snapshot no repositório (arquivar/listar/carregar competência) + testes | REQ-F-019 | — | ✅ |
| T-1202 | Endpoints `/historico` no sidecar (arquivar, listar, snapshot, comparar vs mês ou vs vivo) + testes de contrato | REQ-F-019 | T-1201 | ✅ |
| T-1203 | GUI: botão "Arquivar mês" + painel de histórico/comparação na Planilha; sugestões de rubrica via `datalist` + E2E | REQ-F-019/020 | T-1202 | ✅ |
| T-1204 | Fechamento do ciclo: gates, ata `FREEZE.md` v2.5.0 e docs sincronizados | Processo | todos | ✅ |

## Milestone M13 — Importação de CSV, evolução e histórico no .xlsx (v2.6, ADR-0014)

> Primeira mudança pós-freeze v2.5.0, autorizada pela ADR-0014. O caminho
> CSV → rubricas (parse determinístico no core + LLM local SÓ rotulando +
> revisão humana), o gráfico de evolução das competências arquivadas e a
> aba de histórico no export `.xlsx`.

| ID | Task | REQ | Depende | Status |
|----|------|-----|---------|--------|
| T-1301 | ADR-0014 + bump 2.6.0 + core: parser CSV determinístico (`core/extrato.py` — separador/encoding, colunas por cabeçalho ou conteúdo, valores BR/US, agrupamento por estabelecimento, competência sugerida) + `serie_evolucao` + testes | REQ-F-021/022 | — | ✅ |
| T-1302 | Classificação LLM local (`índice → campo`, valor NUNCA vem do modelo; sem LLM degrada p/ manual — P8) + endpoints de importação no sidecar + aplicação como rubricas na competência escolhida + testes | REQ-F-021 | T-1301 | ✅ |
| T-1303 | GUI importação: drop-zone CSV, painel de revisão (grupo + dropdown de campo + seletor de competência), aplicar → rubricas + E2E | REQ-F-021 | T-1302 | ✅ |
| T-1304 | Gráfico de evolução: `GET /historico/evolucao` + SVG próprio na Planilha (totais por seção + zoom por campo, tema claro/escuro) + E2E | REQ-F-022 | T-1301 | ✅ |
| T-1305 | Histórico no `.xlsx`: aba "Evolução mensal" (campos × competências, totais =SUM, gráfico nativo) + Gate B + SPEC/PARIDADE/HARNESS sincronizados | REQ-F-023 | T-1301 | ✅ |
| T-1306 | Fechamento do ciclo: gates, binários, ata `FREEZE.md` v2.6.0 e docs sincronizados | Processo | todos | ✅ |

## Milestone M14 — OCR de contrato escaneado/imagem (v2.7, ADR-0015)

> Primeira mudança pós-freeze v2.6.0, autorizada pela ADR-0015. Leva o OCR
> local (RapidOCR + PP-OCRv6 medium, na máquina) até a aba Contrato: detecção
> determinística da fonte, motor de OCR, pré-marcação por tipo e trave de
> citação tolerante ao ruído de glifo.

| ID | Task | REQ | Depende | Status |
|----|------|-----|---------|--------|
| T-1401 | ADR-0015 + bump 2.7.0 + `core/documento.py`: detector determinístico "precisa de OCR?" (densidade de texto p/ PDF, extensão p/ imagem) + pré-marcação por tipo (`<valor>/<data>/<percentual>`) + testes | REQ-F-024/025 | — | ✅ |
| T-1402 | `agent/ocr.py`: RapidOCR + PP-OCRv6 medium local-only, rasteriza PDF escaneado via PyMuPDF, saída texto+layout ordenado; degrada com motivo se o motor faltar (P8); deps no `pyproject`/`PLAN §Stack`; testes com fixtures de imagem | REQ-F-024, REQ-NF-006 | T-1401 | ✅ |
| T-1403 | Trave de citação normalizada (glifos de OCR nas duas vias) em `agent/extracao.py` + pré-marcação por tipo no prompt + integração OCR no `/contrato/extrair` + aba Contrato aceita imagem/scan com indicador de OCR + E2E | REQ-F-025 | T-1402 | ✅ |
| T-1404 | Empacotamento: modelos ONNX + onnxruntime no `SidecarHF.spec`, smoke do pacote OCRizando de verdade | Processo | T-1402 | ✅ |

## Milestone M15 — Comprovante escaneado → importação (v2.7, ADR-0015)

> Liga o OCR na importação do v2.6: comprovante/extrato em imagem ou PDF sem
> texto vira lançamentos e segue a mesma classificação/revisão/acréscimo.

| ID | Task | REQ | Depende | Status |
|----|------|-----|---------|--------|
| T-1405 | Comprovante escaneado → `Lancamento` (reconstrução de linhas por layout) reusando `agent/classificacao.py` e `/importar/*` do v2.6 + GUI + E2E | REQ-F-026 | T-1403 | ✅ |
| T-1406 | Fechamento do ciclo: gates, binários, ata `FREEZE.md` v2.7.0 e docs sincronizados | Processo | todos | ✅ |

## Milestone M16 — Cofre local: login + MFA + criptografia em repouso (v2.8, ADR-0016)

> Primeira mudança pós-freeze v2.7.0, autorizada pela ADR-0016. O app vira um
> **cofre**: senha mestra + TOTP abrem uma sessão; o banco inteiro passa a ser
> SQLCipher com envelope DEK/KEK (Argon2id); códigos de recuperação de uso
> único; sem backdoor. Modelo de ameaça: protege o dado em repouso (disco,
> backup, outra conta) — malware na sessão aberta está fora do escopo.

| ID | Task | REQ | Depende | Status |
|----|------|-----|---------|--------|
| T-1601 | ADR-0016 + bump 2.8.0 + `sidecar/auth.py`: Argon2id (KEK) + DEK envelopada (AES-GCM) + TOTP (pyotp) + 10 códigos de recuperação (hash + envelope da DEK) + anti-brute-force com atraso exponencial; metadados em `auth.json` fora do cofre; testes | REQ-SEC-005/006/007 | — | ✅ |
| T-1602 | Banco cifrado: `sidecar/persistencia.py` abre via SQLCipher (`PRAGMA key` = DEK) + migração atômica do `dados.db` em claro (exporta → verifica → remove) + testes | REQ-SEC-006 | T-1601 | ✅ |
| T-1603 | Sessão de cofre no sidecar: endpoints de negócio exigem desbloqueio (`423 Locked`), `POST /auth/*` (cadastro, login, logout, recuperação, trocar senha), auto-lock por inatividade + bloqueio manual; DEK só em memória; testes de contrato | REQ-SEC-005 | T-1601/1602 | ✅ |
| T-1604 | GUI: assistente de cadastro (senha + QR do TOTP + códigos p/ guardar + aviso "sem backdoor"), tela de desbloqueio, "esqueci a senha" via código, indicador/botão de bloqueio + E2E | REQ-SEC-005/007 | T-1603 | ✅ |

## Milestone M17 — LLM embarcada autogerida (v2.8, ADR-0016)

> Elimina a dependência de Ollama/LM Studio: o sidecar embarca e gerencia um
> `llama-server` (llama.cpp) em loopback; o modelo GGUF é instalado pelo
> próprio app (catálogo com SHA-256 travado — única exceção de rede, opt-in —
> ou arquivo local). ADR-0002 preservada: outros providers seguem opcionais.

| ID | Task | REQ | Depende | Status |
|----|------|-----|---------|--------|
| T-1701 | `sidecar/runtime_llm.py`: gerência do processo `llama-server` (start sob demanda, loopback + porta efêmera, health, shutdown), `OpenAICompatProvider` apontando p/ ele como padrão de fábrica; sem modelo ⇒ degrada com motivo (P8); testes | REQ-F-027, REQ-NF-007 | — | ✅ |
| T-1702 | Gestor de modelos: catálogo curado (URL + SHA-256 travados no código, licença comercial ok), download com progresso/retomada + verificação de hash obrigatória, opção de apontar `.gguf` local; tela de configuração da IA + E2E | REQ-F-028, REQ-NF-007 | T-1701 | ✅ |
| T-1703 | Empacotamento: `llama-server` (CPU + Vulkan) como *extraResource* + sqlcipher3 no `SidecarHF.spec`; smoke do pacote que abre cofre E gera análise com o runtime embarcado | Processo | T-1602/1701 | ✅ |
| T-1704 | Fechamento do ciclo: gates, binários, ata `FREEZE.md` v2.8.0 e docs sincronizados | Processo | todos | ✅ |

---

## Milestone M18 — Auditoria de saúde de código (ciclo v2.9, ADR-0017)

> Varreduras NÃO alteram código: produzem achados em formato único (ID
> `A-<task>-<seq>`, categoria, arquivo:linha, severidade, esforço P/M/G,
> evidência, impacto, proposta). Severidade pelos critérios da ADR-0017 §D.
> Perímetro: Python de primeira parte + fronteira TS (electron/main.ts,
> preload.ts, client.ts, contract.ts); telas React fora do perímetro base.

| ID | Task | REQ | Depende | Status |
|----|------|-----|---------|--------|
| T-1801 | Varredura de SEGURANÇA: pendências conhecidas (stderr SQLCipher, code signing), authz rota a rota, segredos/logs, TOCTOU nos arquivos do cofre, superfície loopback+token, `pip-audit`/`npm audit` | Processo (ADR-0017) | — | ✅ |
| T-1802 | Varredura de CONCORRÊNCIA E RECURSOS: jobs em memória e locks, corridas, processos filhos (órfão do llama-server), handles não fechados, caminhos de shutdown | Processo (ADR-0017) | — | ✅ |
| T-1803 | Varredura da FRONTEIRA backend↔frontend: sincronia Pydantic↔`contract.ts` campo a campo, caminhos de erro do IPC, códigos HTTP, serialização de opcionais, respostas truncadas, timeouts assimétricos | Processo (ADR-0017) | — | ✅ |
| T-1804 | Varredura de HIGIENE E BOAS PRÁTICAS: código morto, imports/deps não usados, duplicação, `except` largos, TODO/FIXME, complexidade, docstrings mentirosas | Processo (ADR-0017) | — | ✅ |
| T-1805 | Varredura de SILENCIOSOS E DÍVIDA DE TESTE: testes que degradam sem falhar, ramos dos 4,2% descobertos, asserts fracos, raiz do flake E2E, exceções engolidas em jobs async | Processo (ADR-0017) | — | ✅ |
| T-1806 | Consolidação: dedupe + priorização → `docs/RELATORIO-AUDITORIA.md` → PORTÃO (mantenedor aprova a lista de correções) | Processo (ADR-0017) | T-1801..1805 | ✅ |

> **Resultado (2026-07-12):** 37 achados brutos → 34 consolidados (`C-01..C-35`,
> sem C-09): 1 crítico, 5 altos, 14 médios, 14 baixos. Portão aprovado pelo
> mantenedor nos termos da recomendação do consolidador — correções abaixo;
> **registrados sem correção neste ciclo:** C-15 (code signing — depende de
> certificado), C-16 (bump Electron — ciclo próprio, §E.4), C-17 (nltk —
> aguardar upstream), C-23 (permissões POSIX — sem build POSIX), C-28/C-29
> (refatoração de complexidade — risco vs benefício num ciclo zero-regressão),
> C-35 (sem ação por definição).

## Milestone M19 — Correção dos achados aprovados (ciclo v2.9, ADR-0017)

> As tasks T-19xx nascem do portão do T-1806 (achado/grupo aprovado ⇒ task com
> teste de regressão obrigatório que falharia antes da correção). Restrições
> invioláveis: zero regressão, sem migração de schema/quebra do cofre, sem
> mudança de comportamento visível exceto correção de bug real, bump de
> dependência só com smoke do pacote repetido (ADR-0017 §E).

> Tasks definidas no portão de 2026-07-12 (achados `C-xx` do
> `docs/RELATORIO-AUDITORIA.md`). Cada uma exige teste de regressão que
> **falharia antes** da correção. Executor entre parênteses; ordem pensada para
> não haver duas tasks tocando os mesmos arquivos ao mesmo tempo.

| ID | Task | Achados | Depende | Status |
|----|------|-----|---------|--------|
| T-1901 | Validação de entrada na fronteira: `Field(ge=0)` nos campos monetários + clamp no `CampoMoeda`; normalizar `detail` de `RequestValidationError` (lista→string legível); alinhar saídas de `/rubricas` ao contrato (Sonnet) | C-01, C-07, C-32 | portão | ✅ `0eefba5` |
| T-1902 | Ciclo de vida de processos: Job Object no Windows (mata a árvore no kill duro), shutdown gracioso com prazo no Electron, dreno do stdout pós-handshake; testes cobrem o caminho de kill do runtime (C-18) (Opus) | C-02, C-11, C-24 | portão | ✅ `81372b5` |
| T-1903 | Disciplina de lock do runtime LLM: eliminar a corrida da troca de modelo (instância invalidada após `encerrar()`) e não reter o lock durante o boot/health (estado "iniciando") (Opus) | C-03, C-12 | T-1902 | ✅ `837f57b` |
| T-1904 | Expurgo de jobs em memória: TTL/limite p/ `_JOBS_IA` e `_JOBS_DOWNLOAD`, descarte no `bloquear()`/auto-lock (PII), cache do hash do catálogo por (caminho, mtime, tamanho) (Opus) | C-04, C-08, C-14 | T-1903 | ✅ `f7fac65` |
| T-1905 | Caminho de erro não-JSON do IPC: `try/catch` no `resp.json()` do `chamarSidecar` + `exception_handler(Exception)` no sidecar garantindo corpo JSON em todo 500 (Sonnet) | C-06 | T-1902 | ✅ `89dc338` |
| T-1906 | Pequenos silenciosos: catraca de cobertura passa a medir `sidecar/`; lock no singleton do OCR; log sem nome de arquivo (PII); `log.warning` no job de IA (Sonnet) | C-05, C-13, C-22, C-34 | T-1904 | ✅ `ee51fe3` |
| T-1907 | Flake E2E: substituir as 7 esperas fixas `waitForTimeout(1_500)` pela condição real esperada (Sonnet) | C-20 | — | ✅ `fd32081` |
| T-1908 | Blindagem da DEK: try/except nas execuções `PRAGMA key`/`ATTACH ... KEY` relançando sem a statement; política de stderr do T-1603 MANTIDA e documentada (decisão do portão) (Opus) | C-21 | T-1904 | ✅ `bfb24c5` |
| T-1909 | Limpeza e observabilidade: remover ramo RAG + 4 funções mortas + docstring; helper único de normalização pt-BR; `_gravar_json_atomico` único; `log.debug` nos 18 `except` de degradação P8 (Sonnet) | C-19, C-25, C-26, C-27, C-30, C-31 | T-1906 | ✅ `f980be7` |
| T-1910 | Testes de fallback: ramos com decisão de `agent/classificacao.py` e `core/extrator_pdf.py` + teste fixando o truncamento de documento longo (Sonnet) | C-33 (+C-19) | T-1909 | ✅ `982a75c` |
| T-1911 | Fechamento do ciclo: gates, rebuild dos binários, ata `FREEZE.md` v2.9.0 e docs sincronizados (orquestrador) | Processo | todas | ✅ `2b172df` |

## Milestone M20 — Bump do Electron 33 → 43 (ciclo v2.10, ADR-0018)

> Ciclo dedicado ao achado **C-16** (com carona do **C-10**), design validado
> em brainstorming com o mantenedor em 2026-07-13 — regras, escada de portões
> (43 → 42 → abortar sem merge) e Decision Log na **ADR-0018**. Correlatas só
> se exigidas ("o erro pede o bump"); diálogos preservam comportamento via
> `lastUsedPath`; zero regressão (ADR-0017 §E herdada); suíte Python intocada.

| ID | Task | Achados | Depende | Status |
|----|------|-----|---------|--------|
| T-2001 | Migração Electron 43: checklist de breaking changes 34→43 × superfície (tabela anexada à ADR-0018) → bump + correlatas comprovadas → `lastUsedPath` nos diálogos → escada de portões completa (tsc → eslint → E2E dev → dist → smoke do pacote) (Opus) | C-16 | ADR-0018 | ✅ `262b2ee` |
| T-2002 | Carona C-10 (validação do prefixo `/` em `chamarSidecar`, com E2E) + passo permanente de auditoria de deps no checklist de fechamento (Sonnet) | C-10 | T-2001 | ✅ `ea783c8` |
| T-2003 | Fechamento do ciclo: `npm audit` registrado, build oficial, smokes (pacote + órfão), ata `FREEZE.md` v2.10.0, docs sincronizados (orquestrador) | Processo | todas | ✅ `a55f817` |

## Milestone M21 — Endurecimento dormente e higiene de linter (ciclo v2.11, ADR-0019)

> Ciclo dedicado aos achados **C-23** e **C-35**, design validado em
> brainstorming com o mantenedor em 2026-07-13 (Decision Log na **ADR-0019**).
> Tasks independentes e paralelizáveis (arquivos disjuntos). Regra do C-35:
> veredito triplo por item (corrigir / suprimir com justificativa / manter);
> **nenhuma mudança de comportamento** — bug real encontrado PARA a task e
> vira achado novo para o portão. Zero regressão (ADR-0017 §E herdada).

| ID | Task | Achados | Depende | Status |
|----|------|-----|---------|--------|
| T-2101 | Endurecimento POSIX dormente: `0o600` nos arquivos e `0o700` nas pastas do cofre no ramo POSIX (`sidecar/arquivos.py` `gravar_json_atomico` + criação de pasta/banco em `sidecar/persistencia.py`); no-op no Windows; unit tests provam os flags via monkeypatch (Sonnet) | C-23 | ADR-0019 | ✅ `93a956f` |
| T-2102 | Mini-varredura C-35: reavaliação item a item dos grupos ARG001/ERA001/S608/PLW0603/FURB122 com veredito triplo; `ruff check` com as regras ativadas limpo ou 100% justificado em código (Sonnet) | C-35 | ADR-0019 | ✅ `f13c6ce` |

## Milestone M22 — Complexidade sob catraca (ciclo v2.11, ADR-0019)

> Achados **C-28/C-29** sob a régua do **golden-master** (T-2201 ANTES de
> qualquer refatoração, commit separado) e diretriz **extrair, não
> reescrever**: cada seção vira função privada, sem melhorar prosa, ordem ou
> formatação; golden idêntico é critério de aceite. Fecha com a catraca
> permanente **C901** no ruff (teto = pior caso pós-refatoração, "só aperta").

| ID | Task | Achados | Depende | Status |
|----|------|-----|---------|--------|
| T-2201 | Golden-master dos outputs: `tests/test_golden_outputs.py` com extratores determinísticos (`.docx` → `(estilo, texto)`; `.xlsx` → por aba `(coordenada, valor_ou_fórmula)`), goldens JSON em `tests/golden/` das fixtures do harness; regeneração SÓ com `HF_REGENERAR_GOLDEN=1` fora do CI; máscara de campo volátil no extrator (Opus) | C-28/C-29 (régua) | M21 | ✅ `f71270a` |
| T-2202 | Refatoração `gerar_relatorio` (`outputs/relatorio.py`) por extração de seções; golden idêntico + C901 da função abaixo do teto (Opus) | C-28 | T-2201 | ✅ `3bef65c` |
| T-2203 | Refatoração `_aba_evolucao` (`outputs/planilha.py`) e `baixar_modelo` (`sidecar/gestor_modelos.py`), mesmo contrato do T-2202 (Sonnet) | C-29 | T-2201 | ✅ `4ffb5f8` |
| T-2204 | Fechamento do ciclo: medir pior C901 → fixar `max-complexity` e ativar `C901` no ruff (catraca permanente); gates, auditoria de deps (ADR-0018 §5), ata `FREEZE.md` v2.11.0; smoke NSIS dispensado (§E.4 não dispara — decisão registrada na ADR-0019 e na ata) (orquestrador) | Processo | todas | ✅ `9ff25fd` |

## Milestone M23 — Build/release v2.12 (ciclo v2.12, ADR-0020)

> Reconstrói os binários oficiais incorporando o código v2.11 e fecha o
> risco aceito da ata v2.11.0 (`setuptools` PYSEC-2026-3447). Design validado
> em brainstorming com o mantenedor em 2026-07-14 (Decision Log na
> **ADR-0020**). Sequência rígida: bumps → caronas de harness → build +
> smokes (§E.4 dispara: bump de deps ⇒ smoke do pacote repetido) →
> fechamento com **pip-audit obrigatoriamente 0**. Majors proibidos (§E).

| ID | Task | Alvo | Depende | Status |
|----|------|-----|---------|--------|
| T-2301 | Bumps dirigidos: `setuptools` 83.0.0 (fecha PYSEC-2026-3447), Electron 43.1.1 (patch), `langgraph` 1.2.9, `uvicorn` 0.51; gates completos + E2E dev completo (Sonnet) | risco aceito v2.11.0 | ADR-0020 | ✅ `b93e175` |
| T-2302 | Caronas de harness: smoke do auto-update (`e2e/empacotado-update.spec.ts`, feed local, escada HTTPS: CA de teste → fallback loopback-only) + blindagem T-1907 do cenário "recuperação por código de uso único" (Sonnet) | riscos residuais v2.10/v2.11 | T-2301 | ✅ `d75f10c` |
| T-2303 | Build oficial (PyInstaller + NSIS 2.12.0) + bateria contra o pacote real: smoke NSIS, smoke do órfão, smoke do auto-update (orquestrador) | §E.4 | T-2302 | ✅ (binários fora do git; hashes na ata) |
| T-2304 | Fechamento: auditoria de deps com pip-audit = 0 obrigatório, ata `FREEZE.md` v2.12.0 com hashes dos binários novos, docs sincronizados (orquestrador) | Processo | todas | ✅ (este commit) |

## Definição de Pronto (DoD)
Uma task só é ✅ quando: (1) o código adere ao SPEC/PLAN; (2) há teste no
harness cobrindo o REQ; (3) o teste passa offline; (4) nenhum guardrail é
violado; (5) sem PII/chave em claro.

## Fechamento de ciclo — auditoria de dependências (regra permanente, ADR-0018 §5)
Todo fechamento de ciclo (task T-x9xx/T-xx03) roda `npm audit` (gui_web) e
`pip-audit` (Python) e confere a janela de suporte oficial do Electron
instalado. O resultado — vulnerabilidades (ou "0"), decisão (corrigir /
registrar como risco aceito / abrir achado para ciclo próprio) e se o
Electron segue suportado — é **registrado na ata FREEZE**. Não força bump:
CVE transitiva sem fix upstream é risco registrado, não bloqueio. Objetivo:
defasagem como a do C-16 (Electron 33, 10 majors atrás) nunca mais passa
despercebida entre ciclos.

## Próxima ação recomendada
**Ciclo v2.9 FECHADO (ADR-0017, M18+M19) — saúde de código, 2026-07-13.**
M18: 5 varreduras + consolidação em `docs/RELATORIO-AUDITORIA.md` (34 achados:
1 crítico, 5 altos, 14 médios, 14 baixos) + portão aprovado em 2026-07-12.
M19: T-1901..T-1910 corrigiram 26 achados com teste de regressão obrigatório
(desfecho por achado na seção final do relatório); cobertura 95,8% → 96,6%.
T-1911: deps `llama-index-*` órfãs removidas (decisão do mantenedor; −43
pacotes, incl. `nltk` → C-17 resolvido de fato), bump 2.9.0, build oficial,
smoke do pacote e ata `docs/FREEZE.md` v2.9.0. **Registrados para ciclos
futuros:** C-10, C-15 (code signing), C-16 (bump Electron), C-23, C-28/C-29
(complexidade), C-35. Nota: a fase 0 do PaddleOCR-VL foi executada FORA de
ciclo (2026-07-12) com veredito "manter RapidOCR" — relatório em
`docs/EXPERIMENTO-PADDLEOCR-VL-FASE0.md` (untracked). **Ciclo v2.10 FECHADO
(ADR-0018, M20, 2026-07-13):** Electron 33.4.11 → **43.1.0** (atual; alvo
aprovado alcançado — o falso "bloqueio" do 43 era o flake histórico do
"planilha", encerrado pelo padrão T-1907), C-10 corrigido de carona,
`npm audit`/`pip-audit` = 0, nenhuma correlata exigida, diálogos preservados
via `lastUsedPath`. Regra permanente nova: auditoria de deps em todo
fechamento (seção acima). Ata `FREEZE.md` v2.10.0. **Pendentes para ciclos
futuros:** C-15 (code signing — certificado), C-23 (POSIX), C-28/C-29
(complexidade), C-35 (sem ação). **Ciclo v2.11 FECHADO (ADR-0019, M21+M22,
2026-07-14):** C-23 endurecido dormente (T-2101), C-35 fechado item a item —
84 ocorrências, nenhum bug real (T-2102), C-28/C-29 refatorados por extração
sob **golden-master** (T-2201..T-2203: 9 goldens JSON, `gerar_relatorio`
16→3, `_aba_evolucao` e `baixar_modelo` →2) e **catraca `C901` permanente**
no ruff (teto 13 = pior caso legado, `gui/app.py:_extrair_pdf`; só aperta).
Auditoria de deps: npm audit 0; pip-audit acusou `setuptools` 82.0.1
(PYSEC-2026-3447, transitiva do PyInstaller/build, vetor macOS-sdist — risco
aceito na ata). Sem build oficial neste ciclo (§E.4 não dispara). Ata
`FREEZE.md` v2.11.0. **Fora do ciclo:** C-15 (aguarda decisão de custo do
certificado). **Ciclo v2.12 ABERTO (ADR-0020, M23, 2026-07-14):**
build/release. **Ciclo v2.12 FECHADO (2026-07-14):** bumps dirigidos
entregues (setuptools 83 → **pip-audit 0**, fim do risco aceito da v2.11;
Electron 43.1.1; langgraph 1.2.9; uvicorn 0.51 — goldens intocados provaram
o langgraph); smoke do **auto-update** novo chegou à régua ideal
(`update-downloaded` com sha512 conferido) — degrau 2 da escada HTTPS com
evidência (o stack Chromium do electron-updater ignora `NODE_EXTRA_CA_CERTS`;
`http://` aceito SÓ para `127.0.0.1`, com teste negativo); flake do cofre
blindado (T-1907, asserção pela condição real). Build oficial 2.12.0
(instalador 347,0 MB + sidecar 22,6 MB, hashes na ata) validado por
**6 smokes do pacote + smoke do órfão**. Ata `FREEZE.md` v2.12.0. **Fora do
ciclo:** C-15 (code signing — decisão de custo). Próximo ciclo: a definir
(começa por ADR).

### Histórico do ciclo v2.8 (fechado)

**Ciclo v2.8 (ADR-0016, M16+M17)** — o app vira um **cofre** e a LLM
deixa de exigir ferramenta de terceiros. Decisões do mantenedor (2026-07-10):
runtime **llama.cpp embarcado** (`llama-server` gerido pelo sidecar), modelo
por **download gerenciado no 1º uso** (catálogo com SHA-256 travado; `.gguf`
local também aceito), cofre **SQLCipher + Argon2id** (envelope DEK/KEK) e MFA
**TOTP + códigos de recuperação** (offline, sem backdoor). **T-1601 ✅**:
`sidecar/auth.py` (classe `Cofre`: envelope DEK/KEK com nonce novo por
cifragem, TOTP com anti-replay monotônico, códigos consumíveis via HKDF,
atraso exponencial com relógio injetável; `auth.json` atômico via
`os.replace`, parâmetros do KDF persistidos p/ recalibração) + 30 testes
(339 passed). **T-1602 ✅**: banco cifrado — `sqlcipher3-wheels` (SQLCipher
2.6.0), `Repositorio(dek=...)` com **raw key** `x'<hex>'` (pula o PBKDF2
interno; o KDF forte é o Argon2id do T-1601) + leitura de sanidade pós-key
(chave errada só falha na 1ª leitura → `ChaveInvalida`, sem vazar a chave);
`migrar_para_cofre` atômica (exporta p/ `.novo` via `sqlcipher_export` →
verifica integridade+contagens → `os.replace`; falha preserva o original);
`dek=None` transitório até o T-1603; 9 testes novos (346 passed). Atenção p/
o T-1603: (1) o `Cofre` do auth.py não tem lock próprio — envolver num
`threading.Lock` (padrão `Repositorio`); (2) chave errada faz o SQLCipher
imprimir `hmac check failed` no stderr (não vaza a chave; decidir se filtra
no log do sidecar). **T-1603 ✅**: `sidecar/sessao.py` (`SessaoCofre` com um
lock único serializando tudo — inclusive o `Cofre` sem lock próprio;
auto-lock **preguiçoso** por `HF_AUTO_LOCK_MIN`, padrão 15 min, `0` desliga,
`status()` não conta como atividade) + `/auth/*` no `app.py` (status,
cadastrar — **migra o banco já no cadastro**, sessão segue bloqueada até o 1º
login confirmar o TOTP —, login 401/429+`Retry-After` via exception handler
global de `AguardeCofre`, bloquear, recuperar sem TOTP por design, trocar
senha) + gate `exigir_cofre` em TODAS as 27 rotas de negócio (auditadas rota
a rota; `/health` e `/auth/*` fora). **Janela de onboarding**: sem cofre
cadastrado o app opera como pré-v2.8 (REQ-SEC-005 atualizado no SPEC) — o
T-1604 força o cadastro na GUI. Decisão registrada: stderr do SQLCipher NÃO é
filtrado (`ChaveInvalida` pós-login = corrupção real). 19 testes novos
(365 passed). **T-1701 ✅**:
`sidecar/runtime_llm.py` (`RuntimeLLM` com lock único: start preguiçoso em
`base_url()`, loopback + porta efêmera, poll do `/health` com relógio
injetável — timeout 60 s p/ carga do modelo —, detecção de processo morto com
restart sob demanda, `terminate → wait → kill`; convenção p/ o T-1703:
binário em `resources/llama/llama-server(.exe)` relativo ao executável,
override `HF_LLAMA_SERVER`, modelo via `HF_LLM_MODELO`). Fábrica
(`agent/provider.py`): com `provider="local"`, `HF_BASE_URL` definido ⇒
servidor do usuário (ADR-0002 preservada); senão ⇒ runtime embarcado;
indisponível ⇒ `RuntimeLLMIndisponivel` → `ERRO_CONFIG:...` degrada P8 no
grafo. NOTA: extração/classificação têm fábricas próprias
(`obter_extrator`/`obter_classificador`) e ainda NÃO usam o runtime embarcado
— pendência explícita do T-1702, junto com ligar `encerrar_runtime()` no
lifespan do `app.py`. 15 testes novos (379 passed). **T-1604 ✅ — M16
FECHADO**: GUI do cofre (`Onboarding.tsx` com os 4 passos: senha → QR/segredo
TOTP → 10 códigos exibidos UMA vez com copiar/baixar .txt e aviso sem-backdoor
→ 1º login real; `Desbloqueio.tsx` com 401 genérico sem revelar o fator,
contador regressivo do 429 via `useContadorEspera` e "esqueci a senha" por
código de uso único; overlay de auto-lock que NÃO desmonta as telas — nada
digitado se perde; indicador/botão "Cofre aberto"). Ponte Electron: HTTP
não-ok vira objeto `__hfErro` (o IPC não preserva propriedades extras de um
Error) e o `client.ts` relança `HfErro` tipado com `status`/`aguardeS` +
listener global de 423. QR gerado no sidecar (`qrcode[png]` + `PyPNGImage`
fixado — SEM Pillow, decisão da revisão: `qrcode.make` sem factory escolhe o
Pillow quando presente e o backend puro não aceita `format=`; `types-qrcode`
no dev p/ o mypy). E2E: helper TOTP RFC 6238 em `node:crypto` puro com
anti-replay do passo de 30 s; 3 cenários novos (cadastro+login, 401 genérico,
recuperação com prova de uso único) + os 14 existentes adaptados
(`HF_AUTH_PATH` isolado, `HF_AUTO_LOCK_MIN=1440`) = **17 passed**. Sem porta
dos fundos de dev, por decisão do mantenedor. `empacotado.spec.ts` adaptado
mas só valida de verdade no T-1703 (pacote precisa embarcar
qrcode/sqlcipher3). **T-1702 ✅**: `sidecar/gestor_modelos.py` — catálogo
curado travado no código (Phi-3.5 Mini Q4 MIT ~2,3 GB; Qwen2.5-1.5B Q4
Apache-2.0 ~1,1 GB; Granite 3.1 2B Q4 Apache-2.0 ~1,5 GB; SHA-256 via
`lfs.oid` da API do HF, conferidos NA REVISÃO contra a API — 3/3 batem;
Ministral/Qwen2.5-3B fora por licença de pesquisa); download em `.parcial`
com retomada `Range`, hash obrigatório antes do `os.replace`, cancelamento
cooperativo; `llm.json` FORA do cofre (caminho de arquivo público) com
resolução `HF_LLM_MODELO` > `llm.json`; endpoints `/llm/*` (status, catálogo,
baixar como job async no padrão da análise, definir modelo) atrás de
token+cofre; `encerrar_runtime()` no lifespan (pendência do T-1701 fechada);
extração/classificação agora com a MESMA precedência `HF_BASE_URL` > runtime
embarcado (dialeto muda junto: o `llama-server` fala OpenAI-compat); tela
"Configuração da IA" (7ª aba) com progresso/cancelar/apontar `.gguf` via
diálogo nativo; E2E com catálogo fake (`HF_CATALOGO_TESTE`) sem rede real.
Correções da revisão: `/llm/baixar` idempotente por modelo (2 jobs no mesmo
`.parcial` corromperiam o download) + teste; fixture `HF_BASE_URL` no
`test_ollama_real.py` (a nova precedência tinha silenciado os 3 testes reais
— voltaram a passar contra o Ollama do usuário). Suíte 409 passed / 95,8%;
E2E 18 passed (1 flake do cenário "recuperação" em 1 de 3 rodadas, perfil do
flake histórico: pós-rodada pesada, passa na reexecução — sem correção às
cegas). **T-1703 ✅**: `scripts/preparar_llama.py` (análogo do
`preparar_ocr.py`) baixa/verifica/extrai o `llama-server` do release oficial
`ggml-org/llama.cpp` **b9966** — SHA-256 + tamanho dos zips travados no código
e conferidos NA REVISÃO contra o digest da API do GitHub (2/2 batem); download
em `.parcial` promovido só após o hash, extração seletiva achatada por
`Path(nome).name` (sem zip-slip), idempotente via marcador `.origem.json`.
**Variante Vulkan como único binário embarcado**: o zip Vulkan traz também
todos os backends de CPU (`ggml-cpu-*.dll`) — na GPU-alvo (GTX 1650 4 GB)
acelera, sem GPU/driver cai em CPU sozinho; `--variante cpu` existe mas nunca
é padrão. `resources/llama/` no `.gitignore` (~130 MB, rede só no build —
REQ-NF-006). Flags de GPU: default `-ngl 99` (offload total; os modelos do
catálogo 1,1–2,4 GB cabem nos 4 GB), override por `HF_LLAMA_FLAGS` (definida
vazia ⇒ zera = CPU puro). `SidecarHF.spec`: `collect_all` de
sqlcipher3/argon2/`_argon2_cffi_bindings` + hiddenimports pyotp/qrcode/png.
electron-builder: extraResource `../resources/llama` →
`sidecar-hf/resources/llama` (a convenção do `resolver_binario_llama`, ao lado
do exe do sidecar). Smoke do pacote REAL executado: cofre cadastra+loga no exe
congelado (dados.db SQLCipher criado), download fake ok, e **análise ponta a
ponta pelo runtime embarcado com o Qwen2.5-1.5B do catálogo: `modo: completo`,
zero guardrails** (0.5B de teste degradou P8 corretamente por SCHEMA); pytest
opt-in `HF_LLAMA_REAL` passou com binário+modelo reais. Novo
`empacotado-llm.spec.ts` (binário resolvido no pacote ⇒ MODELO_AUSENTE, nunca
BINARIO_AUSENTE + download/ativação contra o pacote); `empacotado.spec.ts`
enfim validado contra pacote com cofre (pendência do T-1604 fechada). Dois
testes ajustados por consequência do binário materializado no checkout
(`configuracao-ia.spec.ts` força BINARIO_AUSENTE via `HF_LLAMA_SERVER`
inexistente; `test_resolver_binario_ausente_sem_pacote` com monkeypatch de
`_base_pacote`) — determinísticos, sem enfraquecer. Suíte 425 passed / 95,8%;
E2E dev 18 passed; E2E pacote 4 passed. **T-1704 ✅ — CICLO FECHADO**: build
oficial completo (`preparar_llama.py` + `preparar_ocr.py` → PyInstaller →
electron-builder **NSIS**): `Helper Financeiro Setup 2.8.0.exe` (350,0 MB) +
`sidecar-hf.exe` (37,8 MB), hashes na ata. Incidente do build registrado: o
1º `npm run dist` falhou com `EBUSY` em `release\win-unpacked` — **dois
`llama-server.exe` órfãos** do smoke do T-1703 seguravam o diretório (kill
duro no sidecar vaza o filho; o `encerrar_runtime()` só roda no shutdown
limpo) — risco residual documentado na ata; encerrados os processos, o build
passou. Gates finais (rodados de novo após o build): ruff/mypy ok, suíte
**425 passed / 2 skipped opt-in / cobertura 95,8%**, E2E dev **18 passed**,
E2E contra o pacote NSIS novo **4 passed**. Docs sincronizados:
INDEX (ciclo fechado), README (cofre/LLM embarcada/privacidade),
HARNESS §7 (REQ-SEC-005/006/007, REQ-F-027/028, REQ-NF-007 → testes),
PARIDADE §7 (cofre + Configuração da IA). Ata `FREEZE.md` v2.8.0 com SHA-256
de todos os artefatos (TASKS.md finalizado ANTES de hashear; INDEX/FREEZE não
se auto-hasheiam). Lembretes p/ o próximo ciclo: bump da tag do llama.cpp
exige recomputar os 2 SHA-256 de `ASSETS`; modelos com menos de 1B degradam
no schema (o catálogo 1.5B–3.8B satisfaz); `docs/PaddleOCR-VL*.md` são
material de estudo NÃO versionado (avaliação fase 0 pendente).

### Histórico do ciclo v2.7 (fechado)

**Ciclo v2.7 FECHADO E CONGELADO (`FREEZE.md` v2.7.0, ADR-0015, M14+M15).** OCR
local de documento escaneado, do Contrato à importação. **T-1401** deu a fundação
(`core/documento.py`); **T-1402** o motor `agent/ocr.py` (RapidOCR + PP-OCRv6
medium); **T-1403** a trave de citação tolerante a glifo + Contrato aceitando
imagem; **T-1404** o empacotamento (modelos ONNX embarcados no sidecar congelado
+ smoke OCRizando de verdade); **T-1405** ligou o OCR na importação do v2.6
(`core.extrato.ler_extrato_ocr` → mesmos grupos/revisão/aplicação do CSV;
`POST /importar/ocr`; tela "Importar extrato (CSV ou imagem)"). **T-1406 fechou o
ciclo:** gates verdes (**309 passed**, 1 skip = opt-in `HF_OCR_REAL`; cobertura
**95,8%**; gate-front verde; **E2E 16 passed** = 14 dev + 2 smoke do pacote real,
incluindo OCR de verdade do binário congelado), binários reconstruídos (sidecar
PyInstaller + instalador NSIS **2.7.0**, ~329,6 MB — os modelos OCR embarcados
somam ~+132 MB, REQ-NF-006) e nova ata **`FREEZE.md` v2.7.0** com SHA-256 de
todos os artefatos (131) e dos binários.

**Regra de congelamento:** qualquer mudança nos artefatos congelados exige **nova
ADR + incremento de versão + nova ata**. Watch-items: (1) rebuild do pacote
depende de `scripts/preparar_ocr.py` ter rodado antes do PyInstaller (materializa
os `.onnx` medium na venv); (2) flake do E2E "planilha" pós-build (2/8, timing,
nunca valor errado); (3) code signing segue adiado (depende de certificado do
mantenedor). Candidatos p/ o próximo ciclo (nova ADR obrigatória): code signing,
exportar histórico/comparação no `.docx`, metas de orçamento por campo.

### Histórico do ciclo v2.6 (fechado)

**Ciclo v2.6 ABERTO (ADR-0014, M13)** — importação de CSV classificada por
LLM local, gráfico de evolução e histórico no `.xlsx`. Decisões do
mantenedor: lançamentos **agrupados por estabelecimento**, destino com
**escolha da competência** (sugerida pelas datas), **degradação para
classificação manual** sem LLM (P8), gráfico com **totais por seção + zoom
por campo**. **T-1301 ✅**: ADR-0014 + bump 2.6.0 (pyproject, sidecar,
gui_web); `core/extrato.py` nasce como fonte única do parse
(`ler_extrato_csv`: separador `,`/`;`/tab, colunas por cabeçalho pt/en ou
inferidas pelo conteúdo, valores BR e internacionais, datas BR/ISO;
`normalizar_estabelecimento` agrupa "UBER *TRIP 8291"+"...4415" → "Uber
Trip"; sinais mistos = extrato de conta, sinal único = fatura; competência
sugerida pela moda das datas; linha ilegível vira AVISO, nunca exceção) e
`core.rubricas.serie_evolucao` (séries por seção + por campo, alinhadas a
`meses`, campo todo zerado fora, seção sempre presente). 14 testes novos
(233 passed). **T-1302 ✅**: `agent/classificacao.py` — a LLM local SÓ rotula
(`ClassificacaoExtrato`: itens `índice → categoria/campo_pai`; prompt vê
apenas nomes normalizados + natureza, sem valores/datas) com travas
determinísticas reimostas em código (índice existe e não repete, campo
existe em `CAMPOS_POR_CATEGORIA`, natureza coerente: crédito→renda,
débito→fixas/variáveis — item que viola é descartado e o grupo volta "não
classificado"); fábrica local-only (H2, mesmo racional da extração:
Ollama nativo vs OpenAI-compatible) e degradação p/ classificação manual
com motivo (P8, 2 tentativas). Sidecar: `POST /importar/csv` (base64 →
`core/extrato` → classificação → grupos PARA REVISÃO, nada persistido;
`modo` ia/manual/vazio) e `POST /importar/aplicar` (itens revisados →
rubricas no vivo com roll-up do ADR-0012, ou na competência com snapshot
recalculado sobre a base existente/zerada — a importação ACRESCENTA, nunca
apaga); `criar_rubrica(mes=...)` e `salvar_perfil_do_mes` no repositório.
16 testes novos (249 passed). **T-1303 ✅**: seção **Importar extrato
(CSV)** na Planilha (`screens/ImportarCsv.tsx`): escolha do arquivo →
painel de revisão (grupo com total do core + chip de nº de lançamentos +
dropdown de campo filtrado pela natureza: crédito só em renda, débito só
em despesas — mesma trava do backend) → destino (competência com a
sugestão detectada via `input month`, ou orçamento vivo) → Importar. No
vivo, a resposta reusa o pipeline das mutações de rubrica (`aoMutar` com
rubricas+perfil do roll-up); na competência, o Histórico recarrega a lista
de meses (prop `versao`). Banner de degradação com o motivo quando a LLM
não roda (P8) — `classificar_grupos` agora respeita `HF_MODO_DEGRADADO`
sem tentar rede; helper `arquivoParaBase64` extraído p/ `lib/arquivo.ts`
(compartilhado com o Contrato PDF). E2E: 11º cenário "importação" (CSV com
2 grupos → classificação manual → 1 rubrica no vivo → roll-up 180,50 →
limpeza), 11 passed. **T-1304 ✅**: `GET /historico/evolucao` no sidecar
(séries prontas de `core.rubricas.serie_evolucao`; rota literal declarada
ANTES de `/historico/{mes}` para "evolucao" não virar competência) e
gráfico **SVG próprio** na seção Histórico da Planilha (componentes
`Evolucao`+`Grafico`: 3 polylines de totais por seção nas cores das seções,
seletor de zoom por campo com `optgroup`, rótulo do valor final + tooltip
por ponto — todo número exibido vem do core, coordenadas são apresentação;
aparece com 2+ competências arquivadas; tema claro/escuro via variáveis
CSS). E2E: 12º cenário "evolução" (arquiva o mês anterior → 3 séries →
zoom no Mercado → valor final do core), 12 passed. Observação: o flake
intermitente pré-existente do cenário "planilha" reapareceu em 2 de 5
rodadas (pós-build; passa na reexecução) — investigar no fechamento.
**T-1305 ✅**: aba **"Evolução mensal"** no `.xlsx` (`_aba_evolucao` —
campos × competências com valores editáveis, total da seção = fórmula
`=SUM` por coluna, bloco-resumo referenciando os totais que alimenta o
**gráfico de linhas nativo**; a aba só existe com histórico e seção zerada
no período fica de fora); `/exportar/planilha` monta a `serie_evolucao`
dos snapshots do banco. SPEC ganhou REQ-F-021/022/023, PARIDADE §7 ganhou
as 3 linhas do ciclo e o HARNESS (2.6.0) mapeou os REQs novos. Gate B
verde na aba nova (255 passed). Próximo: **T-1306** (fechamento: gates,
binários, investigar o flake do E2E "planilha", ata `FREEZE.md` v2.6.0).

### Histórico do ciclo v2.5 (fechado)

**Ciclo v2.5 FECHADO E CONGELADO (`FREEZE.md` v2.5.0, ADR-0013)** — o
orçamento ganhou a dimensão TEMPO. **T-1201 ✅**: ADR-0013 + bump 2.5.0;
`core/rubricas.py` ganhou `validar_mes` (competência `AAAA-MM`) e
`comparar_orcamentos` (deltas + variação % por campo/seção, arredondamento no
core); `sidecar/persistencia.py` ganhou snapshot por competência
(`arquivar_mes` — perfil em `estado['perfil:AAAA-MM']` + cópia das rubricas
vivas com `mes` preenchido, rearquivar substitui; `listar_meses`,
`carregar_mes`, `rubricas_do_mes`), sem migração de schema (a coluna `mes`
estava reservada desde o v2.4). **T-1202 ✅**: endpoints `/historico` no
sidecar (arquivar, listar, snapshot por mês com 404 sem competência, comparar
mês vs mês ou mês vs orçamento vivo) + testes de contrato ("mercado subiu
12,5%"). **T-1203 ✅**: seção **Histórico mensal** na Planilha (arquivar a
competência atual, dois seletores de comparação, deltas com cor semântica:
renda subir = verde, despesa subir = vermelho — tudo formatação, números do
core) e **sugestões de nome de rubrica** por campo via `datalist` nativo
(lista estática local, sem rede); E2E ganhou os cenários "histórico" e
"sugestões" (10 passed no app dev). **T-1204 ✅ — CICLO v2.5 FECHADO**: gates
verdes (219 passed, cobertura 96,5%; gate-front ok; E2E 11 passed incluindo o
smoke do pacote real — que agora roda com **banco isolado** por `HF_DB_PATH`:
desde a persistência v2.4 ele lia o banco REAL do usuário em `%APPDATA%`),
binários reconstruídos (sidecar PyInstaller + instalador NSIS 2.5.0), docs
sincronizados (SPEC REQ-F-019/020, HARNESS 2.5.0, PARIDADE §7, INDEX, README)
e nova ata **`FREEZE.md` v2.5.0** com SHA-256 de todos os artefatos e dos
binários. Qualquer mudança nos artefatos congelados exige nova ADR +
incremento de versão + nova ata. Candidatos ao próximo ciclo: code signing
(exige certificado do mantenedor), OCR para PDF escaneado, importação CSV
classificada pela LLM, gráfico de evolução por categoria, histórico no
`.xlsx`.

### Histórico do ciclo v2.4 (fechado)

**Ciclo v2.4 ABERTO (ADR-0012)** — rubricas do orçamento (subcampos criados
pelo usuário, roll-up no core) + persistência local SQLite no sidecar
(`%APPDATA%\HelperFinanceiro\dados.db`, `HF_DB_PATH` p/ testes). Decisões do
mantenedor: SQLite (não MySQL), orçamento único vivo (schema já preparado p/
histórico mensal), persistir TUDO (perfil + dívidas + rubricas), rubricas em
renda/fixas/variáveis. **T-1101 ✅**: `sidecar/persistencia.py` (Repositorio
SQLite, schema v1, lock) + 13 testes. **T-1102 ✅**: `GET/POST /estado` no
sidecar (payload validado pelo `PerfilIn` antes de persistir — a hidratação
nunca surpreende a GUI), hidratação no boot (`hf.estadoCarregar`) e auto-save
com debounce de 600 ms no `App.tsx` (só liga após a hidratação, para o seed
não sobrescrever o banco); E2E com banco isolado (`HF_DB_PATH` em tmp) + teste
novo: perfil editado sobrevive à reabertura do app (8º cenário). **T-1103 ✅**:
`core/rubricas.py` (Rubrica, `CAMPOS_POR_CATEGORIA` derivado dos dataclasses
do ADR-0008, `somas_por_campo` + `aplicar_somas`) e CRUD no sidecar
(`GET/POST /rubricas`, `POST /rubricas/{id}`, `POST /rubricas/{id}/remover` —
a ponte do Electron só faz GET/POST). O roll-up é aplicado NA ESCRITA: toda
mutação de rubrica recalcula e persiste o perfil (campo detalhado = soma) e
devolve `rubricas` + `perfil` juntos; `POST /estado` reimpõe a soma (front
fora de sincronia não grava total divergente); remover a última rubrica
conserva a última soma no campo. **T-1104 ✅**: tela **Planilha de orçamento**
(`screens/Planilha.tsx` — sub-tela da aba Perfil, grupos expansíveis por
campo, linha = nome+valor com rascunho por foco e gravação quando o foco sai
da linha, subtotais do sidecar/core), `lib/orcamento.ts` (fonte única dos
rótulos pt-BR, espelha `CAMPOS_POR_CATEGORIA`), aba Perfil refatorada para
derivar as seções do mesmo módulo — campo detalhado vira somente-leitura com
selo "detalhado ▸" que abre a planilha; botão "Detalhar orçamento" no topo.
E2E: 9º cenário (rubricas → roll-up do core → selo no Perfil → remoção
conserva a soma), 8 passed. **T-1105 ✅**: aba **"Orçamento detalhado"** no
`.xlsx` (`_aba_orcamento` — rubricas como entradas editáveis + subtotal por
campo como fórmula =SUM, filosofia da planilha viva; a aba só existe quando
há rubricas), rótulos pt-BR canônicos no core (`ROTULO_CATEGORIA`/
`ROTULO_CAMPO`, espelhados pelo front), `/exportar/planilha` lê as rubricas
do banco; SPEC ganhou REQ-F-017/018, `PARIDADE.md` ganhou a §7 (novidades
v2.4 só na web; tkinter = fallback congelado do v2.3) e o HARNESS mapeou os
REQs novos. E2E dos fluxos novos já entregue no T-1102/T-1104 (banco isolado
e cenários "persistência" e "planilha"). **T-1106 ✅ — CICLO v2.4 FECHADO E
CONGELADO**: gates verdes (207 passed, cobertura 96,4%; gate-front ok; E2E
9 passed incluindo o smoke do pacote real), binários reconstruídos
(sidecar PyInstaller + instalador NSIS 2.4.0), docs sincronizados (INDEX,
README, HARNESS 2.4.0) e nova ata **`FREEZE.md` v2.4.0** com SHA-256 de
todos os artefatos e dos binários. Qualquer mudança nos artefatos
congelados exige nova ADR + incremento de versão + nova ata. Próximo
ciclo: abrir com nova ADR.

### Histórico do ciclo v2.3 (fechado)

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
por tipo e assinatura (nome/CPF ficam locais). **T-904 ✅** — toggle de tema na
topbar: `hf_dark` no `localStorage` ('1'/'0'; sem escolha salva segue o SO via
`prefers-color-scheme`), reidratação ao abrir, `data-theme` no `<html>`;
completados os tokens faltantes do escuro forçado (`--trilha`, tints) e o
fundo inicial da janela Electron segue o `nativeTheme` (sem flash branco).
**T-905 ✅ — M9 FECHADO**: checklist de equivalência em **docs/PARIDADE.md**
(nada do tkinter se perdeu; nome/CPF migraram para a Carta) e **E2E
Playwright** (`gui_web/e2e/app.spec.ts`, `npm run e2e`) rodando o Electron +
sidecar REAIS, offline (`HF_MODO_DEGRADADO=1`): 6 cenários — visão geral,
perfil→recálculo, CRUD de dívidas, análise (portabilidade + job da IA
degradando com P8), carta (prévia viva) e tema persistido com reabertura do
app. Portão local; o gate-front do CI segue sem Electron (T-706). **M10 em
andamento: T-1001 ✅** — sidecar congelado com PyInstaller (`SidecarHF.spec`,
onedir ~149 MB, console p/ o handshake; `uv run --group build pyinstaller
SidecarHF.spec --noconfirm`) e app empacotado com electron-builder (`npm run
dist` → instalador NSIS ~172 MB; `dist:dir` p/ o smoke). `main.ts` escolhe o
exe congelado (`process.resourcesPath`) quando `app.isPackaged`, com
`windowsHide` e espera do `/health` antes de abrir a janela; shutdown já
matava o processo. Smoke automatizado: `e2e/empacotado.spec.ts`
(HF_E2E_PACOTE=1) valida o pacote real de ponta a ponta. **T-1002 ✅** —
telemetria: `agent/telemetria.py` (`configurar_telemetria`, chamada na
partida do sidecar) só liga o tracing com `HF_TELEMETRIA=1` **e**
`LANGSMITH_ENDPOINT` em loopback; nos demais casos FORÇA
`LANGSMITH_TRACING/LANGCHAIN_TRACING_V2=false` (um `=true` perdido no
ambiente não vaza traces à nuvem — REQ-SEC-004/H2; `tests/test_telemetria.py`).
Auto-updater (`electron-updater`): só no app empacotado com
`HF_AUTO_UPDATE=1` + `HF_UPDATE_URL` **HTTPS** (provider generic); no Windows
o pacote baixado precisa de assinatura compatível com o app instalado —
produção exige code signing. **T-1003 ✅** — revisão de segurança do shell em
**docs/SEGURANCA-SHELL.md** (controles verificados código em mãos) com 4
achados CORRIGIDOS: meta CSP no `index.html` (o header não vale em `file://`
⇒ o pacote rodava sem CSP), token em tempo constante
(`secrets.compare_digest`), DevTools desabilitado no pacote e permissões web
negadas por padrão; riscos residuais documentados (code signing pendente).
**T-1004 ✅** — `python main.py` agora sobe a **GUI web** (`npm start` em
`gui_web/`); a tkinter fica como **fallback** (`--tkinter`, ou automático
quando npm/node_modules faltam ou no exe congelado antigo). README
atualizado (árvore com sidecar/gui_web, instruções e instalador). **T-1005 ✅
— CICLO v2.3 FECHADO E CONGELADO**: docs sincronizados (INDEX com
SEGURANCA-SHELL/PARIDADE e estado v2.3; HARNESS 2.3.0 com gate-front, E2E
local, nota do ADR-0011 e mapa REQ→teste ampliado; README no T-1004; versão
do pyproject → 2.3.0) e nova ata **`FREEZE.md` v2.3.0** com SHA-256 de todos
os artefatos de primeira parte (agora incluindo `sidecar/` e `gui_web/`) e
dos binários (instalador NSIS + sidecar congelado). Qualquer mudança nos
artefatos congelados exige nova ADR + incremento de versão + nova ata.
Próximo ciclo: abrir com nova ADR.
