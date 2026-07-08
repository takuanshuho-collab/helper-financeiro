# ADR-0014 — Importação de CSV classificada por LLM local, gráfico de evolução e histórico no .xlsx

- **Status:** Aceita (2026-07-07)
- **Contexto de processo:** primeira mudança pós-freeze v2.5.0. Esta ADR é a
  autorização formal exigida pela ata: abre o ciclo **v2.6.0** (M13); nova
  ata será lavrada no fechamento. Escopo decidido pelo mantenedor: importação
  de extrato CSV com classificação assistida, gráfico de evolução por
  categoria e histórico mensal no export `.xlsx`; code signing e OCR seguem
  adiados (o primeiro depende de certificado do mantenedor).

## Contexto

O v2.4 criou as rubricas e o v2.5 criou o histórico mensal — mas ambos
dependem de digitação manual. O dado já existe pronto no banco do usuário:
todo extrato/fatura exporta CSV. Falta o caminho CSV → rubricas. E, com
competências acumulando no banco, falta a visão longitudinal: o gráfico de
evolução na tela e o histórico no export `.xlsx` (candidatos registrados na
ADR-0013 como "futuro").

Decisões do mantenedor (brainstorm do planejamento): lançamentos **agrupados
por estabelecimento** (não uma rubrica por linha), destino com **escolha da
competência** (sugerida pelas datas do CSV), **degradação para classificação
manual** sem LLM, gráfico com **totais por seção + zoom por campo**.

## Decisão

### A. Importação de CSV em três estágios, com a LLM só rotulando

1. **Parse determinístico no core** (`core/extrato.py`): detecção de
   separador/encoding, localização das colunas data/descrição/valor por
   cabeçalho (pt/en) ou por conteúdo, valores em formato brasileiro E
   internacional, datas `DD/MM/AAAA` e `AAAA-MM-DD`. Lançamentos são
   **agrupados por estabelecimento normalizado** (remove códigos, `*`,
   dígitos soltos) com soma, contagem e natureza (crédito/débito); a
   **competência é sugerida** pela moda das datas. Linhas ilegíveis viram
   avisos, nunca exceção.
2. **Classificação pela LLM local** (mesmo endpoint loopback da extração de
   PDF, ADR-0010 — H2 por endpoint: o extrato, que é PII pesada, nunca sai
   da máquina). O contrato é `índice do grupo → campo do orçamento`: a LLM
   **só rotula, nunca produz número** — valor, nome e contagem vêm do parser
   (H1 por construção). Rótulo fora de `CAMPOS_POR_CATEGORIA` é descartado
   (vira "não classificado"). Sem LLM disponível, o fluxo **degrada para
   classificação manual** (P8): os grupos chegam "não classificados" com o
   motivo indicado.
3. **Revisão humana antes de aplicar** (mesma filosofia do Contrato PDF):
   painel com dropdown de campo por grupo, seletor de competência com a
   sugestão detectada; só o clique em "Aplicar" cria as rubricas.

**Regra de destino:** no orçamento vivo, a importação usa o fluxo normal de
criação de rubricas (roll-up na escrita, ADR-0012). Numa competência
`AAAA-MM`, as rubricas nascem com `mes` preenchido e o snapshot do perfil é
recalculado (base = snapshot existente, ou perfil zerado se a competência é
nova); a importação **acrescenta, nunca apaga** rubricas existentes.
Créditos classificam em `renda`; débitos em `fixas`/`variaveis`.

### B. Gráfico de evolução com séries prontas do core

`core.rubricas.serie_evolucao(snapshots)` transforma as competências
arquivadas em séries: total por seção (renda/fixas/variáveis) por mês +
série por campo (para o zoom "como foi meu mercado no semestre?"). O sidecar
expõe `GET /historico/evolucao`; a GUI desenha em **SVG próprio** (tema
claro/escuro, sem dependência nova) — escala e eixos são apresentação, todo
número exibido vem do core (REQ-NF-005).

### C. Histórico mensal no `.xlsx`

Aba **"Evolução mensal"** no export: linhas = campos agrupados por seção,
colunas = competências arquivadas, totais por seção como fórmula `=SUM`
(filosofia da planilha viva) e **gráfico nativo** openpyxl (o export tem
gráfico desde a v1). A aba só existe quando há competências arquivadas;
entra no Gate B (zero erro de fórmula).

## Alternativas rejeitadas

- **LLM lendo o CSV bruto** (parse + classificação numa chamada): o modelo
  poderia inventar/alterar valores — viola H1. O parser determinístico
  garante que todo número tem origem verificável.
- **Classificação na nuvem**: extrato bancário é o dado mais sensível do
  app; H2 por endpoint (loopback) como na ADR-0010. Sem exceções.
- **Aplicar sem revisão**: classificador de 3B erra; a revisão humana é a
  mesma garantia do "confira antes de adicionar" do Contrato PDF.
- **Uma rubrica por lançamento**: dezenas de linhas por campo poluiriam a
  Planilha — agrupar por estabelecimento mantém o detalhe útil.
- **Biblioteca de gráficos no front** (recharts etc.): dependência nova e
  CSP para 3 linhas e um eixo; SVG próprio resolve e segue o tema.
- **Snapshot automático na importação**: o usuário pode importar vários CSVs
  do mesmo mês (conta + cartão); o arquivamento continua explícito.

## Consequências

- `core/extrato.py` nasce como fonte única do parse (o sidecar não interpreta
  CSV; a GUI só envia o texto).
- Formatos exóticos de banco podem exigir ajuste no parser — os testes
  cobrem os padrões comuns (vírgula/ponto-e-vírgula, valor BR/US, data
  BR/ISO, com/sem cabeçalho); fixtures reais anonimizadas são bem-vindas.
- A classificação reusa o provider local existente; nenhuma chave ou rede
  nova. O prompt vê apenas nomes de estabelecimento normalizados (sem
  valores, sem datas) — minimização de dado até no loopback.
- Sem migração de schema (`VERSAO_ESQUEMA` permanece 1).

## Requisitos derivados

`REQ-F-021` (importar CSV classificado com revisão), `REQ-F-022` (gráfico de
evolução) e `REQ-F-023` (histórico no `.xlsx`) no `SPEC.md` §1; harness em
`tests/test_extrato.py` (parser/agrupamento), `tests/test_rubricas.py`
(séries), `tests/test_sidecar.py` (contratos novos) e
`tests/test_outputs.py` (aba + Gate B); E2E em `gui_web/e2e/`.
