# ADR-0002 — LLM agnóstico de provedor, local-first

- **Status:** Aceito · **Data:** 2026-07-01

## Contexto
Dados financeiros são sensíveis (LGPD). Depender de nuvem levanta risco de
privacidade, custo e latência, e quebra o requisito de operação offline.

## Decisão
Definir uma interface única `LLMProvider.analisar(fatos) -> AnaliseAgente` com
implementações intercambiáveis: `OllamaProvider` (local, **padrão
recomendado**), `OpenAICompatProvider` (nuvem, via env) e `FakeProvider`
(testes). Cliente compatível com o padrão OpenAI para reaproveitar ferramentas.

## Consequências
- (+) Roda 100% offline com Ollama (Qwen etc.) — aderente a LGPD (P3).
- (+) Harness determinístico com `FakeProvider`, sem rede.
- (+) Facilita reuso da estação LLM local já planejada.
- (−) Modelos locais menores podem aderir pior ao schema → mitigado por
  `instructor` + modo degradado (P8).

## Relacionado
`docs/PLAN §4`, REQ-LLM-003/004, ADR-0004 (anonimização).
