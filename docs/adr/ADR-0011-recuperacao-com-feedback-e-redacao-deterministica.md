# ADR-0011 — Recuperação com feedback e redação determinística na análise sênior

- **Status:** Aceita (2026-07-07)
- **Contexto de processo:** ajuste dentro do ciclo **v2.3.0** (ADR-0009),
  surgido no teste manual do T-902 (tela Análise). Refina o comportamento do
  grafo do CONSELHEIRO (ADR-0006) e do guardrail numérico (ADR-0003 / H1)
  **sem afrouxar o H1** — nenhum número fabricado chega ao usuário.

## Contexto

No teste manual do T-902 com o modelo local (ministral-3b via LM Studio), a
análise sênior degradava praticamente sempre com
`REQ-GRD-001:NUMEROS_FABRICADOS`. Diagnóstico com o modelo real:

1. Modelos locais pequenos fabricam números sobretudo em **exemplos
   acessórios** — "ex.: 24 meses", "0,5%–1,0% ao ano", "R$ 200/mês" — e em
   **porcentagens derivadas** ("90% do fluxo"). O conteúdo central costuma
   estar fundamentado nos FATOS.
2. O grafo usava a recuperação única (REQ-LLM-002) **só** para falha de
   chamada/schema; violação de guardrail degradava direto, desperdiçando o
   orçamento de retry.
3. Mesmo com prompt endurecido, uma nova amostra às cegas era cara-ou-coroa
   (temperatura 0,2) — o modelo repetia o vício dos exemplos numéricos.

Resultado: o recurso central da tela Análise ficava inutilizável no hardware
local de referência, apesar de a análise conter conteúdo aproveitável.

## Decisão

### A. Prompt endurecido contra números derivados/exemplificados

A regra 1 do `SYSTEM_PROMPT` passa a proibir explicitamente números em
exemplos, faixas e porcentagens derivadas, orientando a expressar a ideia SEM
número ("um prazo maior", "uma taxa menor").

### B. A recuperação única cobre guardrail reprovado — com feedback

`validar_guardrails` → `chamar_llm` enquanto houver orçamento (o teto global
continua `MAX_TENTATIVAS` = 2 chamadas por análise, REQ-LLM-002). No retry, o
provider recebe uma mensagem de correção que **nomeia os números órfãos**
(`analisar_com_correcao`, suportado por Ollama e OpenAI-compat; detectado por
`hasattr`, então fakes/providers antigos continuam funcionando). Nomear o erro
é muito mais eficaz do que reamostrar às cegas.

### C. Redação determinística como último recurso (`sanear`)

Esgotado o retry e persistindo **apenas** `NUMEROS_FABRICADOS`, o novo nó
`sanear` remove as **frases** que contêm números órfãos
(`guardrails.validador_numerico.remover_frases_orfas`) e **revalida**:

- sobra análise limpa com sumário e diagnóstico não vazios ⇒ **aprova**;
- caso contrário (ex.: sumário 100% fabricado) ⇒ **degrada**, como antes.

O H1 é preservado por construção: a revalidação garante que nenhum número
órfão sobrevive à redação. Conteúdo indevido (REQ-GRD-004) **nunca** passa
pelo saneamento — degrada sempre.

## Consequências

- Com o ministral-3b real: taxa de aprovação foi de ~0/3 para **4/4** nas
  rodadas de validação, com todos os números citados presentes nos FATOS.
- O modo degradado continua existindo (P8): provider fora do ar, schema
  inválido persistente, conteúdo indevido e análises integralmente fabricadas.
- Custo: no pior caso continua em 2 chamadas ao LLM; a redação é O(texto),
  local e determinística.
- Testes: `tests/test_recuperacao.py` (feedback com órfãos, saneamento salva,
  fabricação total degrada) e `tests/test_grounding.py` (redação preserva
  frases fundamentadas e zera órfãos).
