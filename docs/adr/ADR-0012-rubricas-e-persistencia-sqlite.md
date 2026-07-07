# ADR-0012 — Orçamento detalhado com rubricas + persistência local em SQLite

- **Status:** Aceita (2026-07-07)
- **Contexto de processo:** primeira mudança pós-freeze v2.3.0. Esta ADR é a
  autorização formal exigida pela ata: abre o ciclo **v2.4.0** (M11); nova ata
  de freeze será lavrada no fechamento do ciclo.

## Contexto

Duas dores de uso real, levantadas pelo mantenedor:

1. **Os campos do Perfil ainda são agregados demais.** O ADR-0008 desceu de
   "despesas fixas" para categorias ("Contas da casa", "Mercado"...), mas o
   usuário pensa em **rubricas individuais** — conta de luz, internet, escola
   do filho. Colocar todas na aba Perfil poluiria a tela e tiraria a agilidade
   de "reconhecer para onde está indo o dinheiro".
2. **O programa não lembra de nada.** Perfil, dívidas e orçamento vivem só no
   estado do React e se perdem ao fechar o app (a única persistência hoje é a
   preferência de tema no `localStorage`). Para um app de acompanhamento
   financeiro, redigitar tudo a cada sessão é inaceitável a partir do momento
   em que a entrada fica detalhada.

## Decisão

### A. Rubricas (subcampos) por campo do orçamento

Nova entidade **rubrica**: um lançamento nomeado pelo usuário dentro de um
campo do orçamento (ex.: "Conta de luz — R$ 180" dentro de `contas_casa`).
Valem para as seções **renda, fixas e variáveis** (todos os campos do
ADR-0008); reserva/FGTS ficam de fora — são saldos, não fluxos.

Regra do roll-up, **no core** (REQ-NF-005 intacto — zero cálculo em TS):

- Campo **sem** rubricas ⇒ continua editável direto na aba Perfil, como hoje.
- Campo **com** rubricas ⇒ o valor do campo passa a ser **a soma das
  rubricas** e o campo fica somente-leitura no Perfil, com indicador
  "detalhado ▸" que leva à planilha. Isso elimina por construção o conflito
  "total editado ≠ soma dos subitens".

Os agregados (`DespesasFixas.total` etc.) continuam sendo a única fonte de
`diagnostico`/`estrategias`/agente — as rubricas apenas alimentam os campos.

A edição acontece numa **tela dedicada** ("planilha de orçamento"), aberta por
um botão na aba Perfil: grade editável com grupos expansíveis por campo,
linha = nome + valor, subtotais ao vivo e total batendo com o Perfil.

### B. Persistência local em SQLite, no sidecar

O app passa a **persistir todo o estado do usuário** (perfil, dívidas e
rubricas) em um banco **SQLite** — arquivo local
`%APPDATA%\HelperFinanceiro\dados.db` (sobrescritível por `HF_DB_PATH`;
fallback `~/.helper_financeiro/` fora do Windows):

- **`sqlite3` da stdlib** — zero dependência nova, nada escuta em rede; o
  banco é aberto e gerido **exclusivamente pelo sidecar Python** (a GUI
  continua casca fina consumindo endpoints).
- Conexão única com `threading.Lock` (o sidecar atende em múltiplas threads),
  mesmo padrão do `_JOBS_IA`.
- Tabela `esquema` com a versão do schema para migrações futuras; a tabela
  `rubrica` já nasce com coluna `mes` (NULL = orçamento vivo) para o
  histórico mensal entrar num ciclo futuro **sem** migração dolorosa.
- Auto-save: a GUI hidrata o estado do banco no boot e salva com debounce —
  sem botão "salvar".

**Privacidade (H2/SEC):** o banco fica no perfil do usuário, fora do
repositório e fora de logs — mesma situação dos exports `.docx`/`.xlsx`, que
já contêm credor/nome em claro por serem documentos do usuário (REQ-SEC-001
segue respeitado). O **mapa de anonimização** (token → valor real) continua
existindo **apenas em memória** (REQ-SEC-003): o que vai ao LLM permanece
tokenizado, e nada do banco é enviado a endpoint não-loopback.

## Alternativas rejeitadas

- **MySQL/servidor de banco**: exigiria instalar e manter um serviço com
  credenciais na máquina do usuário — destrói o instalador NSIS de um clique,
  cria superfície de rede nova e não traz nada para um app single-user local.
- **Arquivo JSON**: suficiente para "salvar o perfil", mas rubricas dinâmicas
  com CRUD por id + histórico mensal futuro pedem consultas e migração de
  schema; SQLite dá isso de graça na stdlib.
- **Rubricas dentro da aba Perfil** (sem tela dedicada): poluição visual —
  exatamente o problema que motivou a demanda.
- **Total editável mesmo com rubricas**: geraria estado inconsistente
  (total ≠ soma) e uma pergunta sem boa resposta ("qual vale?").

## Consequências

- O app finalmente "lembra" do usuário entre sessões — mudança de expectativa:
  testes E2E precisam isolar o banco (`HF_DB_PATH` temporário) para
  continuarem determinísticos.
- Retrocompatível: quem nunca criar rubrica usa o Perfil exatamente como hoje.
- `FatosFinanceiros` NÃO ganha as rubricas: o agente continua recebendo
  agregados (mesma postura do ADR-0008); levar o detalhamento ao CONSELHEIRO
  exigiria nova avaliação de guardrails.
- Fora deste ciclo (anotado para o futuro): histórico mensal com comparações,
  sugestões de nomes de rubrica, importação de extrato CSV classificada pela
  LLM local.

## Requisitos derivados

`REQ-F-017` (rubricas + roll-up campo↔rubricas), `REQ-F-018` (persistência
local: hidratação no boot + auto-save) no `SPEC.md`; harness em
`tests/test_persistencia.py` e extensão de `tests/test_orcamento.py` /
`tests/test_sidecar.py`; E2E em `gui_web/e2e/`.
