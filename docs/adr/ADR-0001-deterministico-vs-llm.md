# ADR-0001 — Separação estrita entre determinístico e LLM

- **Status:** Aceito · **Data:** 2026-07-01

## Contexto
O produto lida com dinheiro. Um número errado (parcela, economia, prazo) corrói
a confiança e pode induzir decisão ruim. LLMs são ótimos em linguagem, mas
podem "alucinar" cifras.

## Decisão
Todo número vem **exclusivamente** do `core/` determinístico. O LLM recebe os
números prontos e só os **interpreta**. Um validador pós-geração (H1) rejeita
qualquer cifra na saída do LLM que não exista nos fatos.

## Consequências
- (+) Correção numérica garantida e testável.
- (+) Permite trocar de modelo (inclusive locais pequenos) sem risco numérico.
- (−) O agente não pode "calcular" nada novo; se um número for necessário, ele
  precisa ser adicionado aos fatos determinísticos primeiro.

## Alternativas descartadas
- Deixar o LLM calcular com "tool use" de calculadora: mais complexo e ainda
  exigiria validação; não elimina o risco de o LLM narrar um número errado.
