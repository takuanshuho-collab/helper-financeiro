# TASKS — Helper Financeiro v2

- **Versão:** 2.0.0 · **Deriva de:** `SPEC.md` / `PLAN.md`
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
| T-201 | `OllamaProvider` (local-first) | REQ-LLM-003/004 | T-106 | ⬜ |
| T-202 | `OpenAICompatProvider` (nuvem, via env) | REQ-LLM-003, SEC-002 | T-106 | ⬜ |
| T-203 | `agent/config.py` (provider, base_url, model, modo_degradado) | REQ-LLM-003 | — | ✅ (base) |
| T-204 | Integração `instructor` p/ structured output | REQ-LLM-002 | T-201/202 | ⬜ |
| T-205 | Cache local de análise (evitar custo/latência) | NF/RISCO | T-201 | ⬜ |
| T-206 | Teste de degradação com provider offline real | P8 | T-201 | ⬜ |

## Milestone M3 — Integração de saída

| ID | Task | REQ | Depende | Status |
|----|------|-----|---------|--------|
| T-301 | Seção "Análise do Agente (IA)" no `.docx`, separada dos números | REQ-GRD-003 | T-108 | ⬜ |
| T-302 | Painel na GUI com narrativa + rótulo "assistido por IA" | REQ-LLM-001, P2 | T-108 | ⬜ |
| T-303 | Botão "Gerar análise sênior" com barra de progresso (thread) | NF-usabilidade | T-302 | ⬜ |
| T-304 | Indicador visual de modo degradado na GUI | P8 | T-302 | ⬜ |

## Milestone M4 — Empacotamento & freeze

| ID | Task | REQ | Depende | Status |
|----|------|-----|---------|--------|
| T-401 | Atualizar build PyInstaller (incluir pydantic/instructor) | — | M3 | ⬜ |
| T-402 | Ata de freeze com SHA-256 dos artefatos | Processo | todos | ✅ (M1) |
| T-403 | Revisão de segurança (sem PII/keys em log) | SEC-001/002 | M2 | ⬜ |

---

## Definição de Pronto (DoD)
Uma task só é ✅ quando: (1) o código adere ao SPEC/PLAN; (2) há teste no
harness cobrindo o REQ; (3) o teste passa offline; (4) nenhum guardrail é
violado; (5) sem PII/chave em claro.

## Próxima ação recomendada
M1 está entregue e verde neste scaffold. O próximo passo natural é **T-201**
(OllamaProvider), plugando o modelo local ao pipeline já validado.
