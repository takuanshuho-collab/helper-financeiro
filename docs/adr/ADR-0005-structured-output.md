# ADR-0005 — Structured output nativo, sem framework intermediário

- **Status:** Aceita · **Data:** 2026-07-03
- **Relacionada a:** REQ-LLM-002/003, T-201/T-202/T-204, ADR-0002

## Contexto

Os providers reais (M2) precisam garantir que o LLM devolva JSON aderente ao
schema `AnaliseAgente`. O TASKS.md original previa `instructor` (T-204) e a
auditoria pediu que a escolha entre `instructor` e `PydanticAI` fosse fechada
por ADR. Avaliamos quatro caminhos:

| Opção | Aderência | Custo |
|---|---|---|
| `PydanticAI` | forte | framework de agente inteiro para 1 chamada; árvore de deps grande; retry/validação próprios que **duplicam** o orquestrador |
| `instructor` | forte | retry embutido duplica o REQ-LLM-002 (1 recuperação, do orquestrador); esconde a requisição real |
| SDK `openai` + `response_format` | forte | ~10 deps transitivas (httpx etc.) só para 1 POST; não fala o `format` nativo do Ollama |
| **JSON Schema nativo + stdlib + Pydantic** | **a mais forte no local** | escrever ~30 linhas de HTTP com `urllib` |

Dois fatos técnicos pesaram:

1. O endpoint **nativo** do Ollama (`/api/chat`) aceita o JSON Schema completo
   no parâmetro `format` e **restringe a gramática de amostragem no servidor** —
   aderência por construção, mais forte do que qualquer retry no cliente. A
   própria doc oficial recomenda `Modelo.model_json_schema()` + validação
   Pydantic da resposta.
2. O retry de schema **já existe e é testado** no orquestrador
   (`agent/agente.py`, REQ-LLM-002, `tests/test_recuperacao.py`). Qualquer
   biblioteca com retry próprio criaria duas camadas de recuperação — número
   de chamadas imprevisível, quebrando o contrato "1 recuperação" da SPEC.

## Decisão

**Nenhum framework.** Os providers fazem o POST com `urllib` (stdlib):

- `OllamaProvider` → `/api/chat` com `format = AnaliseAgente.model_json_schema()`
  (gramática restrita no servidor, local-first, REQ-LLM-004);
- `OpenAICompatProvider` → `/v1/chat/completions` com
  `response_format: {type: json_schema, strict: true}` (schema endurecido:
  `additionalProperties: false` + todos os campos obrigatórios, exigência do
  modo strict OpenAI);
- ambos validam a resposta com `AnaliseAgente.model_validate_json` e deixam
  `ValidationError`/erros de rede **subirem** — quem decide recuperar ou
  degradar é o orquestrador (P8), como sempre foi.

## Consequências

- **Zero dependências novas de runtime** — relevante para o freeze
  PyInstaller (M4) e para a promessa offline (REQ-NF-002).
- A requisição é transparente e testável offline com um servidor HTTP local
  (`tests/test_providers.py`), sem mocks de SDK.
- Custo assumido: mantemos nós mesmos ~60 linhas de HTTP/schema. Se um dia o
  agente precisar de tool-calling ou streaming, reavaliar (provável upgrade:
  `PydanticAI`), registrando novo ADR.
- T-204 muda de "integração instructor" para "structured output nativo +
  validação Pydantic" — o objetivo (saída aderente ao schema) permanece.
