# ADR-0013 — Histórico mensal do orçamento + sugestões de rubrica

- **Status:** Aceita (2026-07-07)
- **Contexto de processo:** primeira mudança pós-freeze v2.4.0. Esta ADR é a
  autorização formal exigida pela ata: abre o ciclo **v2.5.0** (M12); nova
  ata será lavrada no fechamento. Escopo decidido pelo mantenedor: os dois
  itens adiados do ADR-0012 (histórico mensal e sugestões de nomes); code
  signing e OCR ficam para ciclos futuros.

## Contexto

O ADR-0012 entregou o orçamento por rubricas e a persistência, mas um único
orçamento "vivo": editar o valor do mercado **apaga** o valor anterior. Para
a missão da tela ("reconhecer para onde está indo o dinheiro"), falta a
dimensão TEMPO — saber que o mercado subiu 12% desde o mês passado vale mais
do que o número isolado. A coluna `mes` da tabela `rubrica` foi reservada no
schema v1 exatamente para isso (NULL = orçamento vivo).

Segundo incômodo, menor: criar rubrica exige digitar nomes óbvios (luz,
água, internet) do zero.

## Decisão

### A. Snapshot mensal por arquivamento explícito

- O **orçamento vivo continua sendo o único editável** (rubricas com
  `mes IS NULL`; perfil na chave `perfil` da tabela `estado`).
- **"Arquivar mês"** (botão na Planilha) grava a competência `AAAA-MM`:
  o perfil completo vai para a chave `perfil:AAAA-MM` na tabela `estado` e
  as rubricas vivas são **copiadas** com `mes = 'AAAA-MM'`. Snapshots são
  imutáveis pela GUI; arquivar de novo a mesma competência **substitui** o
  snapshot (determinístico, sem versões).
- Nenhuma migração de schema: o schema v1 já comporta tudo (`VERSAO_ESQUEMA`
  permanece 1).

### B. Comparação determinística no core

`core.rubricas.comparar_orcamentos(antes, depois)` compara dois perfis
(dicts do contrato) campo a campo e por seção: valor anterior, valor atual,
delta e variação percentual (None quando o valor anterior é 0 — sem divisão
por zero). O sidecar expõe `GET /historico` (competências arquivadas),
`GET /historico/{mes}` (snapshot) e `POST /historico/comparar`
(`mes_a` vs `mes_b`, ou vs o orçamento vivo quando `mes_b` é null). A GUI
só renderiza — nenhuma aritmética em TS (REQ-NF-005).

### C. Sugestões de nome de rubrica (front)

Lista estática de nomes comuns por campo (`SUGESTOES_RUBRICA` em
`gui_web/src/lib/orcamento.ts`) ligada ao input do nome via `<datalist>`
nativo. É conveniência de digitação pura — sem número, sem rede, sem LLM —
por isso vive no front, ao lado dos rótulos que já espelham o core.

## Alternativas rejeitadas

- **Snapshot automático na virada do mês**: o app é desktop e pode ficar
  semanas fechado — a "virada" seria imprevisível; o arquivamento explícito
  deixa o usuário fechar o mês quando os lançamentos estão completos.
- **Histórico por versão de edição (event sourcing)**: complexidade
  desproporcional; a pergunta do usuário é mensal, não por tecla.
- **Snapshot só das rubricas**: campos não detalhados (digitados direto)
  ficariam fora da comparação — o snapshot leva o perfil inteiro.
- **Sugestões vindas da LLM**: rede/latência para autocompletar 10 nomes
  óbvios; a lista local resolve.

## Consequências

- O banco cresce ~1 snapshot/mês (dezenas de linhas) — irrelevante.
- `listar_rubricas()` (orçamento vivo) já filtra `mes IS NULL`, então NADA
  muda nos fluxos do v2.4; o roll-up continua intocado.
- Comparação entre competências com estruturas diferentes (campo detalhado
  num mês e direto no outro) é transparente: compara-se o VALOR do campo,
  que já é a soma em ambos os casos.
- Futuro (fora deste ciclo): gráfico de evolução por categoria; exportar o
  histórico para o `.xlsx`.

## Requisitos derivados

`REQ-F-019` (arquivar competência + comparar meses) e `REQ-F-020`
(sugestões de rubrica) no `SPEC.md` §1; harness em `tests/test_rubricas.py`
(comparação), `tests/test_persistencia.py` (snapshot) e
`tests/test_sidecar.py` (contrato `/historico`); E2E em `gui_web/e2e/`.
