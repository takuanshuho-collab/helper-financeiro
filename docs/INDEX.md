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
| 8 | [`adr/`](adr/) | Decisões de arquitetura (ADR-0001..0007) |
| 9 | [`FREEZE.md`](FREEZE.md) | Ata de congelamento com SHA-256 |

## Fluxo Spec-Driven
```
CONSTITUTION → PRD → SPEC (EARS) → PLAN → TASKS → código
                                 ↘ HARNESS (testa cada REQ)
                                 ↘ ADR (registra decisões)
                                 ↘ FREEZE (congela a versão)
```

## Estado atual
- **M1 + M1.5 + M2 + M2.5 entregues e verdes**: guardrails, orquestração em
  **StateGraph** (LangGraph, ADR-0006) com degradação segura, providers reais
  com structured output (ADR-0005), **extração Code-First de documentos** com
  citação obrigatória + verificador determinístico + pausa para confirmação
  humana (`interrupt`), ingestão local LlamaIndex retriever-only (ADR-0007),
  cache de análise e harness com 72 testes (cobertura ≥90% no CI).
- **Modelo padrão:** `qwen2.5:3b` (GPU 4 GB); alternativa Apache 2.0: `qwen3:4b`.
- **Próximo:** M3 (T-301..T-304) — GUI/.docx, incluindo a tela de confirmação
  da extração retomando o checkpoint do grafo.

## Rodar
```bash
uv sync --group dev
uv run pytest -q               # harness offline
uv run pytest -m ollama        # integração real (skip sem Ollama+modelo)
uv run python demo_agente.py   # pipeline da IA com FakeProvider
```
