# ADR-0003 — Anonimização de PII e guardrails de saída

- **Status:** Aceito · **Data:** 2026-07-01

## Contexto
Mesmo com provider local, tratar PII com disciplina é boa prática (defesa em
profundidade). E a saída do LLM precisa ser filtrada antes de chegar ao usuário
(conteúdo indevido, ausência de aviso legal).

## Decisão
1. **Entrada:** antes de qualquer chamada, `guardrails/pii.py` substitui nome,
   CPF e credores por tokens (`PESSOA_1`, `CREDOR_1`). O mapa fica só em memória.
2. **Saída:** pipeline de guardrails na ordem schema → numérico (H1) →
   conteúdo (H6) → aviso legal (H3). Falha em qualquer etapa ⇒ degradação (P8).

## Consequências
- (+) LGPD por padrão; nada de PII crua sai da máquina (H2).
- (+) Saída sempre com aviso e sem recomendação de investimento.
- (−) Custo de manter regex/listas de padrões atualizadas → coberto por testes.

## Relacionado
REQ-GRD-001..006, REQ-SEC-003, `docs/HARNESS`.
