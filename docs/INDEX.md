# Artefatos SDD — Helper Financeiro v2

Mapa dos documentos que governam o projeto. **Comece pelo topo.**

| Ordem | Documento | Papel |
|---|---|---|
| 0 | [`../AGENTS.md`](../AGENTS.md) | Guia do agente de código na IDE (ler antes de codar) |
| 1 | [`CONSTITUTION.md`](CONSTITUTION.md) | Princípios in**violáveis** (P1–P8) e hard rules |
| 2 | [`PRD.md`](PRD.md) | Por que e o que (produto, metas, escopo, NEEDS_CLARIFICATION) |
| 3 | [`SPEC.md`](SPEC.md) | Requisitos em EARS + contratos de dados (REQ-IDs) |
| 4 | [`PLAN.md`](PLAN.md) | Arquitetura, stack, fluxo de dados, milestones |
| 5 | [`AGENT.md`](AGENT.md) | Persona e prompt do Agente Financeiro Sênior (CONSELHEIRO) |
| 6 | [`HARNESS.md`](HARNESS.md) | Suite de avaliação e portões de qualidade |
| 7 | [`TASKS.md`](TASKS.md) | Backlog rastreável (REQ ↔ task ↔ teste) |
| 8 | [`adr/`](adr/) | Decisões de arquitetura (ADR-0001..0013) |
| 9 | [`REVISAO-SEGURANCA.md`](REVISAO-SEGURANCA.md) | Revisão de segurança do M4 (T-403) |
| 10 | [`SEGURANCA-SHELL.md`](SEGURANCA-SHELL.md) | Revisão de segurança do shell web (T-1003) |
| 11 | [`PARIDADE.md`](PARIDADE.md) | Checklist de paridade tkinter ↔ web (T-905) |
| 12 | [`FREEZE.md`](FREEZE.md) | Ata de congelamento com SHA-256 |

## Fluxo Spec-Driven
```
CONSTITUTION → PRD → SPEC (EARS) → PLAN → TASKS → código
                                 ↘ HARNESS (testa cada REQ)
                                 ↘ ADR (registra decisões)
                                 ↘ FREEZE (congela a versão)
```

## Estado atual
- **M1 + M1.5 + M2 + M2.5 + M3 entregues e verdes**: guardrails, orquestração
  em **StateGraph** (LangGraph, ADR-0006) com degradação segura, providers
  reais com structured output (ADR-0005), **extração Code-First de documentos**
  com citação obrigatória + verificador determinístico + confirmação humana
  (`interrupt`), ingestão local LlamaIndex retriever-only (ADR-0007) e a
  **integração de saída** (M3): painel "assistido por IA" na GUI com thread e
  indicador de degradação, seção "Análise do Agente (IA)" no `.docx` e tela de
  confirmação da extração retomando o checkpoint. Harness com 80 testes
  (77 offline + 3 de integração real; cobertura ≥90% no CI, atual ~95%).
- **Modelo padrão:** `qwen2.5:3b` (GPU 4 GB); alternativa Apache 2.0: `qwen3:4b`.
- **M4 fechado:** `HelperFinanceiro.exe` (~94 MB, PyInstaller), revisão de
  segurança aprovada (`REVISAO-SEGURANCA.md`), higiene de checkpoint
  (estado só com dicts + allowlist msgpack) e v2.1.0 congelada em `FREEZE.md`.
- **Ciclo v2.2 fechado e congelado (`FREEZE.md` v2.2.0):** perfil como
  **orçamento doméstico detalhado** (ADR-0008: categorias tipadas no `core`,
  roll-up determinístico, cobertura da reserva em meses e resumo ao vivo) e
  **revisão de UI/UX** (M6): validação visual dos campos numéricos
  (REQ-F-009), aba Perfil rolável, contador de dívidas, barra de status
  contextual, edição por duplo clique/Enter/Delete e lista zebrada. Ata
  ampliada para congelar todo o código de primeira parte + o harness (104
  testes offline, cobertura 95,4%) e o `.exe` rebuild (93,8 MB).
- **Ciclo v2.3 FECHADO (`FREEZE.md` v2.3.0, ADR-0009):** GUI oficial migrada
  para **Electron + React/TypeScript** (`gui_web/`, 6 telas do redesign
  "Clareza"), núcleo Python como **sidecar** FastAPI em loopback+token (FONTE
  DA VERDADE — sem cálculo em TS, REQ-NF-005); tkinter mantida como fallback
  (`--tkinter`). **ADR-0010**: extração PDF assistida por LLM local
  OpenAI-compatible (LM Studio) — H2 por **endpoint (loopback)** + fusão
  determinística clássico+IA. **ADR-0011**: recuperação com feedback dos
  números órfãos + redação determinística (`sanear`) na análise sênior.
  Telemetria LangSmith só local e opt-in; auto-update HTTPS opt-in;
  empacotamento electron-builder + sidecar PyInstaller; paridade documentada
  (`PARIDADE.md`) com E2E Playwright; segurança do shell revisada
  (`SEGURANCA-SHELL.md`).
- **Ciclo v2.4 FECHADO (`FREEZE.md` v2.4.0, ADR-0012):** orçamento detalhado
  com **rubricas** — subcampos criados pelo usuário por campo do Perfil, com
  roll-up no `core` (campo detalhado = soma, somente-leitura com selo
  "detalhado ▸") editados na tela **Planilha de orçamento**; rubricas também
  na aba "Orçamento detalhado" do `.xlsx` (subtotais `=SUM`). **Persistência
  local** em SQLite gerida pelo sidecar (`%APPDATA%\HelperFinanceiro\
  dados.db`, `HF_DB_PATH` p/ testes): perfil + dívidas + rubricas com
  hidratação no boot e auto-save — o app lembra o usuário entre sessões
  (REQ-F-017/018). Só na GUI web (tkinter = fallback congelado do v2.3,
  `PARIDADE.md` §7).
- **Ciclo v2.5 FECHADO (`FREEZE.md` v2.5.0, ADR-0013):** o orçamento ganhou a
  dimensão TEMPO — **"Arquivar mês"** grava a competência (`AAAA-MM`:
  snapshot do perfil + rubricas; rearquivar substitui) e a Planilha compara
  competências (ou competência vs orçamento vivo) com deltas e variações %
  calculados no `core` ("seu mercado subiu 12,5%", cor semântica: renda
  subir = verde, despesa subir = vermelho). Bônus: **sugestões de nome de
  rubrica** por campo via `datalist` local (REQ-F-019/020). Sem migração de
  schema: a coluna `mes` já estava reservada desde o v2.4.
- **Mudanças nos artefatos congelados (v2.5.0) exigem nova ADR + incremento de
  versão + nova ata.**

## Rodar
```bash
uv sync --group dev
uv run pytest -q               # harness offline
uv run pytest -m ollama        # integração real (skip sem Ollama+modelo)
uv run python main.py          # GUI web (fallback: --tkinter)
cd gui_web && npm run e2e      # E2E Playwright (Electron + sidecar reais)
```
