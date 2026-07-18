# ADR-0023 — Ciclo v2.15: checkpoint durável do grafo, persistência visível da análise e progresso em tempo real (SSE)

- **Status:** Aceita (design validado em brainstorming com o mantenedor,
  2026-07-17) · **Data:** 2026-07-17
- **Relacionada a:** `docs/RELATORIO-NOVA-VERSAO-STACK-WEB.md` (síntese do
  documento externo "Melhorias de App com LLM"; este ciclo absorve, **no
  desktop**, os itens de valor real dele) e
  `docs/RELATORIO-PERSISTENCIA-ANALISE.md` (desenho da persistência visível,
  que entra como T-2602). Blueprint de longo prazo que herdará estas peças
  prontas: `docs/PROJETO-SAAS-SERVER-EDITION.md`. Evolui a decisão
  "só-memória" da **ADR-0006** (`grafo.py:293` já registra a condição para
  durar). Regras herdadas: ADR-0017 §E (zero regressão; rebuild + smokes
  quando o produto muda), ADR-0018 §5 (auditoria de deps no fechamento),
  hotfix v2.12.1 (CI remoto verde antes de congelar), ADR-0020/0021 (build
  assinado). Preserva o provider resiliente do **T-2505/ADR-0022** e o
  expurgo de PII/job do **T-1904/ADR-0017**.
- **Ciclo:** v2.15.0 · **Milestone:** M26 (T-2601..T-2605)

## Contexto

Três limites conhecidos da análise sênior no desktop:

1. **Estado do grafo é volátil.** `agent/grafo.py` e `agent/extracao.py`
   compilam com `InMemorySaver` (serializador com allowlist explícita —
   `grafo.py:66`). O comentário em `grafo.py:293` registra a condição para
   evoluir: persistir em disco exige pós-anonimização + opt-in (ADR-0006).
   Queda do sidecar/app no meio da análise descarta o progresso.
2. **A análise se perde entre sessões.** O cache T-205 (que devolve a mesma
   análise para os mesmos dados em ms) é só-memória por decisão de segurança
   (REQ-SEC-003); ao reabrir o app, a tela recomeça vazia e o usuário paga
   2–4 min de novo pelos MESMOS dados. Lacuna mapeada em
   `docs/RELATORIO-PERSISTENCIA-ANALISE.md`.
3. **A espera é um poço escuro.** `POST /analise/ia` cria um job e a GUI faz
   polling em `GET /analise/ia/{job_id}` com status grosso. Com LLM local em
   hardware modesto (GTX 1650, alvo do ADR-0016 §E), são minutos de silêncio
   — pior quando o boot cai em `cpu_fallback` (ADR-0022) e o tempo dobra. O
   documento externo aponta a mitigação (feedback perceptivo / SSE).

**Nota de honestidade sobre o checkpoint (decidida no brainstorming):** o
checkpointer grava o estado **ao fim de cada nó**. O nó caro (`gerar`, a
chamada ao LLM) é atômico — seu checkpoint só existe DEPOIS que o LLM
termina. Logo, crash **durante** a geração ⇒ a retomada refaz o `gerar` do
zero; só crash **entre** nós (após o LLM, antes do `END`) economiza tempo.
O checkpoint durável entra, portanto, como **resiliência a falha parcial**,
sem prometer cobrir o caso "caiu no meio do LLM". O valor cotidiano
(reabrir e ver a análise de ontem) vem do T-2602, não dele.

**Streaming sem furar guardrails:** a variante "tokens em tempo real" do
documento externo **não serve** — o texto do LLM só é aprovado depois dos
guardrails (aprovar/sanear/degradar) e só é desanonimizado no fim; streamar
tokens crus exporia conteúdo não aprovado e tokens `CREDOR_n`. A solução
adotada mostra **fases + contador de tokens** ("escrevendo… N tokens"): o
conteúdo NUNCA aparece, só a fase e a contagem — sinal de vida fino que
ataca o "tempo até o primeiro token" sem violar o contrato.

## Decisão

### M26 — Durabilidade, persistência visível e progresso (tasks por entregável)

- **T-2601 (checkpoint durável no cofre — Opus, toca segurança):**
  - **Spike no dia 1** (antes de comprometer o desenho): `SqliteSaver`
    (pacote `langgraph-checkpoint-sqlite`) aceita `conn` no construtor —
    validar que engole uma conexão do `sqlcipher3` (fork do `sqlite3`):
    cursor/tipos e `check_same_thread` (o job roda em thread pool). **O spike
    DEVE exercitar concorrência real** (revisão multi-agente S3/G2): checkpoint
    do job escrevendo enquanto o auto-save do repo (600 ms, T-1102) escreve no
    MESMO `dados.db` — com **WAL + `busy_timeout`** e a escrita de checkpoint
    **não-fatal** (falha de lock degrada para "sem checkpoint neste step",
    nunca aborta a análise). Plano B: 2ª conexão SQLCipher ao mesmo `dados.db`
    com a mesma DEK. **Plano C (degradação segura):** se nenhuma conexão casar
    ou a concorrência não estabilizar, cair para `InMemorySaver` naquela sessão
    (checkpoint desligado + log), **jamais** falhar a análise — o T-2601 nunca
    torna o produto pior que hoje.
  - `criar_checkpointer()` ganha dois modos: com cofre aberto **e** toggle
    ligado ⇒ `SqliteSaver` sobre a conexão do cofre, com **o mesmo**
    `JsonPlusSerializer` e a **mesma allowlist** de tipos do saver atual;
    toggle desligado ⇒ `InMemorySaver` como hoje. Tabelas
    `checkpoints`/`writes` dentro do `dados.db` **cifrado** — nenhum byte de
    estado em claro (REQ-SEC-001); `SqliteSaver.setup()` idempotente na
    abertura do cofre.
  - **`thread_id` determinístico = assinatura SHA-256 dos fatos** (a chave
    do cache T-205): retomar só faz sentido para os mesmos dados; dados
    mudaram ⇒ thread novo.
  - **Toggle** "retomar análises interrompidas" em `llm.json` (preferência,
    não segredo — mesmo lugar de `ctx_size`/`gpu_offload` do T-2502),
    **default ligado** (honra a condição opt-in da ADR-0006). Controle na
    tela Configuração da IA **com uma linha de ajuda explicando QUANDO importa**
    (revisão U4: "se o app fechar no meio de uma análise, ela continua de onde
    parou ao reabrir") — sem a ajuda o interruptor é um cenário abstrato.
  - **Higiene e precedência (revisão multi-agente S2/S5):** no sucesso
    (análise aprovada **e persistida pelo T-2602**), o thread é apagado
    **obrigatoriamente** — se a deleção falhar, o thread completo é tratado
    como órfão podável e **nunca** é retomado. **Retomada só se aplica a
    thread INACABADO** (que não chegou ao `END`) — enforce checando o estado
    antes de retomar, para um thread completo jamais servir resultado velho.
    Máx. **1 thread inacabado por tipo de grafo**; iniciar thread novo (de
    assinatura diferente) varre e apaga inacabados órfãos — **consequência
    documentada:** iniciar uma análise de dados diferentes ANTES de repetir a
    interrompida descarta esta última. **Precedência dos três mecanismos:**
    (1) T-2602 = fonte de exibição ao reabrir; (2) cache T-205 = curto-circuito
    intra-sessão; (3) checkpoint = retomar SÓ inacabado. Não competem.
  - **Segurança (revisão multi-agente G1):** teste que serializa o checkpoint
    **inteiro em CADA super-step** de uma corrida-fixture — incluindo o estado
    **pós-`gerar` pré-`sanear`** (saída crua do LLM antes da desanonimização) —
    e varre por PII do perfil (nomes, valores exatos, datas em combinação
    identificante) ⇒ nada aparece. Não basta varrer só "nomes reais": o estado
    intermediário do LLM é o ponto de maior risco.
  - **Versão:** o estado carrega a versão do schema; incompatível após
    update ⇒ descarta e recomeça (nunca pior que hoje).
  - Cobre **os dois grafos** (análise e extração usam `criar_checkpointer`);
    a extração ganha durabilidade de graça (sem SSE — ver premissas).
- **T-2602 (persistência visível da última análise — Sonnet, desenho pronto
  no relatório):**
  - **Mecanismo separado** do checkpointer. Tabela nova em
    `sidecar/persistencia.py` (dentro do `dados.db` cifrado): assinatura
    SHA-256 dos fatos + `SecaoIA` **já desanonimizada** (JSON) + modelo +
    carimbo. **Só a última** (upsert numa linha por perfil vivo — YAGNI,
    sem histórico por competência).
  - **Escrita** pelo job ao completar (aprovada). **Ordem segura:**
    persistir a `SecaoIA` PRIMEIRO, só então o T-2601 apaga o thread do
    checkpoint (crash entre os dois deixa thread completo órfão, inócuo,
    podado depois; nunca perde a análise pronta).
  - `GET /analise/ultima` (token + cofre): devolve `analise_salva` (com a
    assinatura, carimbo, modelo) **e** `assinatura_atual` (o backend calcula
    dos fatos vivos). A GUI **só compara as duas strings** (REQ-NF-005).
  - **UX (aba Análise):** iguais ⇒ análise salva com carimbo, botão vira
    "Gerar novamente"; diferentes ⇒ análise antiga esmaecida + selo âmbar
    "os dados mudaram desde esta análise", clique gera e substitui; sem
    salva ⇒ estado de hoje. Auto-lock esconde a análise e ela volta do banco
    no desbloqueio. Exportações `.docx` herdam a `SecaoIA` da tela de graça.
- **T-2603 (SSE: provider streaming + contador + job consome o stream +
  endpoint — Opus, toca provider T-2505 + job T-1904):**
  - **Spike no dia 1:** provar que os 3 degraus do T-2505 sobrevivem ao
    `stream=true` (o 400 de gramática chega na init do sampler, ANTES de
    qualquer token? o parse lida com `data: [DONE]`?). **Asserção explícita
    da ordem 400-antes-do-token para o build EMBARCADO** (revisão S4 — a saga
    T-2505 provou que builds divergem); o provider **trata defensivamente
    "tokens e só então erro"**: descarta o parcial e segue pelo caminho do
    400 de gramática. Se um degrau não casar, ele **degrada para POST único**
    naquela tentativa específica — mantém a resiliência, perde só o contador.
  - **Provider (`agent/provider.py`):** POST com `stream=true`, consome os
    chunks do `llama-server`, acumula o texto e conta tokens; chama
    `on_progress(n_tokens, tentativa)` **com throttle** (≥200 ms OU ≥16
    tokens entre emissões — revisão G3, para não inundar o event loop/SSE) —
    callback **opcional** (ausente na extração/testes ⇒ funciona como hoje,
    retrocompatível). Os 3 degraus do T-2505 permanecem, cada tentativa
    agora streaming; o contador reseta por tentativa.
  - **Plumbing (Abordagem 1 — `stream_mode` do LangGraph):** o nó `gerar`
    recebe o `StreamWriter` e passa ao provider um callback que escreve
    `{tipo:"tokens", n, tentativa}` no stream **custom**. O job (`_JOBS_IA`)
    troca `ainvoke` por `async for modo, chunk in grafo.astream(...,
    stream_mode=["updates","custom"])`: `updates` ⇒ transição de nó =
    evento de **fase**; `custom` ⇒ **contador**. Cada evento vai para uma
    `asyncio.Queue`/deque bounded do job (como o ring buffer do ADR-0022).
    O **expurgo de PII do T-1904** permanece intacto (só muda a forma do
    laço; bloqueio no meio ⇒ para e expurga).
  - **`GET /analise/ia/{job_id}/eventos`** (`StreamingResponse`,
    `text/event-stream`): eventos `fase` (rótulo human-friendly montado no
    backend — REQ-NF-005: "calculando indicadores", "o modelo está
    escrevendo", "validando a resposta"…), `progresso` (n tokens), `terminal`
    (mesmo payload do status atual, incl. `aviso_runtime`), `erro`. **Rótulos
    nunca expõem mecânica de retry como falha (revisão U3/S7):** o conserto
    dirigido do T-2505 aparece como **"refinando a resposta"**, jamais
    "tentativa 2 de 2" — o usuário não deve ler o retry interno como "a IA
    errou". **heartbeat 15 s**; **token no header** (a GUI consome via `fetch`
    + leitura de stream, não `EventSource` — nada de token em query string).
    **O stream fecha no auto-lock (revisão G6):** cofre bloqueado no meio ⇒ o
    job para e expurga (T-1904) e o endpoint emite `terminal`/`erro` e
    encerra, nunca fica aberto pendurado. **Polling continua** como fallback
    (contrato de hoje intacto).
- **T-2604 (GUI linha do tempo — Sonnet):** na aba Análise, o spinner mudo
  dá lugar a uma linha do tempo de fases alimentada pelo SSE (helper de
  fetch streaming; parse de `fase`/`progresso`/`terminal`/`erro`). Fase
  atual pulsando, concluídas com ✓; durante "escrevendo" mostra
  "escrevendo… N tokens" (sem expor "tentativa"; o refino aparece como fase
  "refinando a resposta"). **Retomada explicada, não rótulo cru (revisão U1):**
  quando o job retoma, a linha do tempo diz em linguagem clara que uma análise
  anterior foi interrompida e está continuando, com as fases já feitas
  marcadas — o usuário que clicou "Gerar" não é surpreendido por um "retomando"
  sem contexto. **Queda do stream ⇒ fallback polling gracioso (revisão U5):**
  preserva a última fase visível e **não** exibe erro (o contador apenas para
  de atualizar); a degradação não pode parecer quebra. Integra com o T-2602 na
  mesma aba: abrir ⇒ `GET /analise/ultima` (hidratação); Gerar ⇒ `POST
  /analise/ia` + abre o SSE. E2E Playwright com stream mockado (fases,
  contador, retomada, queda→polling **sem erro na tela**, terminal com
  `aviso_runtime`).
- **T-2605 (fechamento — Fable):** gates locais + **CI remoto verde** +
  auditoria de deps §5 (entra `langgraph-checkpoint-sqlite` — **confirmar que
  casa com o `langgraph 1.2.9` do lockfile SEM forçar upgrade; se forçar,
  reconferir os 9 goldens como sentinela**, revisão G5; janela Electron +
  npm/pip-audit) + **rebuild oficial 2.15.0** (o produto muda —
  §E) + smokes §E.4 **incluindo o smoke do órfão** llama-server (Job Object
  no exe congelado) + bump 2.15.0 nos 3 lugares + **aceitação de campo**
  (abaixo). Ata `FREEZE.md` v2.15.0.

### Critérios de fechamento

Gates verdes; CI remoto verde; testes novos (allowlist do saver durável,
**varredura anti-PII do checkpoint INTEIRO em cada super-step incl.
pós-`gerar` pré-`sanear`**, retomada após kill entre nós, **retomada só de
thread inacabado**, poda, **escrita de checkpoint não-fatal sob lock
concorrente**, toggle liga/desliga, versão incompatível; upsert/`GET
/analise/ultima`/ordem persistir-antes-de-apagar; provider streaming = POST
único como sentinela, contador com throttle, 3 degraus do T-2505 em
streaming, **`astream` × expurgo T-1904 com bloqueio no meio — TESTE
OBRIGATÓRIO (revisão G4)**, endpoint SSE com heartbeat/terminal/erro,
**fecho no auto-lock**, fallback POST único); E2E da linha do tempo verde;
build 2.15.0 assinado + smokes (incl. órfão); **aceitação de campo
quádrupla**; ata v2.15.0. Golden-master e catraca C901 intactos.

**Aceitação de campo (máquina do mantenedor):** (a) matar o app **entre
nós** ⇒ retoma do último nó bom; (b) fechar e reabrir com os mesmos dados
⇒ última análise **hidratada** com carimbo; (c) acompanhar uma análise
inteira pela **linha do tempo com contador** — e **o mantenedor julga se o
contador de tokens de fato reduz a ansiedade** ou se um pulso "escrevendo…"
simples serviria igual (revisão U2); se o contador não agregar, o desenho
**cai para fases-puras** (a alternativa da Decisão #4 fica preservada como
plano de recuo, não descartada); (d) **reprovar os fallbacks do T-2505 em
streaming** — 4/4 perfis variados completos pelo grafo (como o T-2505 fez).

## Riscos aceitos

| Risco | Mitigação |
|---|---|
| `SqliteSaver` × conexão `sqlcipher3` não casar | **spike no dia 1 do T-2601** decide antes de comprometer; plano B = 2ª conexão SQLCipher ao mesmo `dados.db` |
| `stream=true` quebrar um dos 3 degraus do T-2505 | **spike no dia 1 do T-2603**; degrau que não casar degrada para POST único (resiliência mantida, só sem contador) |
| Checkpoint com PII fora do perímetro | teste varre checkpoints serializados por nomes reais do perfil-fixture; estado é pós-anonimização por construção; e vive dentro do cofre cifrado |
| Retomar estado de versão antiga do grafo após update | checkpoint carrega versão do schema; incompatível ⇒ descarta e recomeça (nunca pior que hoje) |
| Job com `astream` regredir o expurgo de PII do T-1904 | só muda a forma do laço; o expurgo no completar/bloquear é preservado e coberto por teste (job que termina após bloqueio não ressuscita PII) |
| Stream SSE segurar conexão em análise longa | heartbeat + timeout de inatividade; fallback polling é o plano B nativo |
| Fila de eventos encher se a GUI não consumir | deque bounded (padrão do ring buffer ADR-0022); evento perdido é irrelevante — o `terminal` sempre carrega o estado completo |
| Contador de tokens mostrar progresso mas a análise ainda falhar nos guardrails | o contador é sinal de vida, não promessa de sucesso; o `terminal` reflete aprovada/degradada com `aviso_runtime`; conteúdo nunca é exibido antes do fim |

## Decision Log (brainstorming 2026-07-17)

| # | Decisão | Alternativas consideradas | Por quê |
|---|---|---|---|
| 1 | **Escopo = 3 frentes** (checkpoint + persistência visível + SSE) | só os 2 pedidos (checkpoint+SSE); reordenar por valor (persistência+SSE, adiar checkpoint) | o mantenedor quis o valor cotidiano (persistência) junto, ciente do trade-off de ciclo maior |
| 2 | Checkpoint = **resiliência a falha parcial** (mecanismo separado da persistência) | fundação da persistência (T-2602 lê do checkpoint); repensar/derrubar | honesto sobre a janela estreita (nó `gerar` atômico); desacopla os dois entregáveis |
| 3 | Toggle **com default ligado** | sem toggle (sempre ligado); toggle default desligado | honra a condição opt-in da ADR-0006 ao pé da letra; usuário pode desligar para "não acumular estado" |
| 4 | SSE = **fases + contador de tokens** (conteúdo nunca exibido) | fases puras (sem detalhe no nó longo); tokens crus na tela; decidir no design | ataca o "tempo até o 1º token" sem furar guardrails/anonimização; o mantenedor aceitou o risco de mexer no provider T-2505 |
| 5 | T-2603 (SSE núcleo) **vira Opus**; T-2604 (GUI) fica Sonnet | separar T-2603a/b; manter Sonnet + revisão | o contador tornou o SSE código crítico (provider resiliente + execução do job/T-1904); modelo alinhado à criticidade |
| 6 | Plumbing = **`astream(stream_mode=["updates","custom"])` + `StreamWriter`** | `astream_events`; fila fora-de-banda | caminho idiomático do LangGraph; separa fase (updates) de progresso (custom); o custo (`astream` no job) já foi aceito |

**Premissas travadas (confirmadas no Understanding Lock):** (1) persistência
= só a última análise, sem histórico por competência; (2) SSE/progresso = só
a análise sênior — a extração de contrato fica sem SSE, mas ganha o
checkpoint durável de graça; (3) `thread_id` = assinatura SHA-256 dos fatos;
(4) versão incompatível ⇒ descarta e recomeça; (5) auth do SSE = `fetch` +
token no header (não `EventSource`), polling como fallback; (6) higiene =
máx. 1 thread inacabado por tipo de grafo, checkpoint apagado no sucesso.

## Alternativas rejeitadas

- **Streaming de tokens crus na tela (proposta literal do documento
  externo):** incompatível com os guardrails (aprovação e desanonimização
  só no fim); mostraria conteúdo rejeitável e tokens `CREDOR_n`. Fases +
  contador entregam o valor psicológico sem furar o contrato.
- **WebSocket em vez de SSE:** o fluxo é unidirecional (servidor→GUI); SSE é
  mais simples, passa por proxy HTTP e o fallback polling reusa o contrato.
- **Checkpoint em arquivo próprio fora do cofre:** segunda chave, segundo
  ciclo de vida, segunda superfície de auditoria — o cofre existe para isso.
- **`PostgresSaver`/serviço externo:** pertence à Server Edition (blueprint
  §2.4); no desktop seria dependência de servidor num produto local-first.
- **Persistir o cache T-205 inteiro no disco:** o cache guarda conteúdo
  anonimizado cuja desanonimização depende do mapa só-memória (REQ-SEC-003);
  o T-2602 grava a `SecaoIA` JÁ desanonimizada dentro do cofre — mesmo
  benefício, sem tocar o requisito.
- **Debounce com limiar monetário (terceiro item do documento externo):**
  registrado como padrão para quando a GUI tiver edição contínua de valores;
  hoje não há gatilho automático de análise — YAGNI.

## Revisão multi-agente (2026-07-17)

Design submetido à skill `multi-agent-brainstorming` (Skeptic → Constraint
Guardian → User Advocate → Arbiter). **Disposição do Arbiter: REVISE** — o
design não tinha falha fatal nem exigiu reverter nenhuma decisão travada, mas
tinha lacunas materiais (escopo do teste anti-PII, concorrência de escrita no
SQLite, precedência dos mecanismos, provisoriedade do contador) que foram
**corrigidas acima antes do lançamento**. As decisões travadas do Decision Log
seguem de pé (nenhuma objeção trouxe causa nova para reabri-las).

| # | Objeção | Papel | Disposição | Resolução (já aplicada) |
|---|---|---|---|---|
| S1 | Valor da retomada é <0,1% do relógio (YAGNI?) | Skeptic | **Rejeitada reopen / aceita como residual** | Decisão #2 foi informada; sem causa nova. Registrado: T-2601 é o item de menor razão valor/custo do ciclo e **1º candidato a corte** se um spike vacilar |
| S2 | Poda descarta a análise interrompida se o usuário iniciar outra | Skeptic | **Aceita** | Semântica agora explícita na higiene do T-2601 |
| S3 | Plano B (2 conexões) tão arriscado quanto o A; sem plano C | Skeptic | **Aceita (funde G2)** | Spike exercita concorrência; **plano C = cair para `InMemorySaver`**, nunca falhar a análise |
| S4 | Ordem 400-antes-do-token é específica do build | Skeptic | **Aceita** | Spike assere a ordem no build embarcado; provider trata "tokens e então erro" defensivamente |
| S5 | Três mecanismos sem precedência | Skeptic | **Aceita** | Precedência definida; retomada só de thread inacabado; deleção obrigatória no sucesso |
| S6 | Toggle é YAGNI | Skeptic | **Rejeitada** | Decisão #3 explícita, honra ADR-0006; mitigado por U4 (ajuda) |
| S7 | Rótulo de fase vaza metadado | Skeptic | **Aceita (funde U3)** | Rótulo "refinando a resposta", nunca expõe retry |
| G1 | Teste anti-PII cobre só nomes, não o estado intermediário do LLM | Guardian | **Aceita (forte)** | Teste varre o checkpoint inteiro por super-step, incl. pós-`gerar` pré-`sanear` |
| G2 | Concorrência de escrita SQLite pode abortar a análise | Guardian | **Aceita (funde S3)** | WAL + `busy_timeout` + escrita não-fatal + plano C |
| G3 | Contador sem throttle inunda o event loop | Guardian | **Aceita** | Throttle ≥200 ms OU ≥16 tokens |
| G4 | `astream` × expurgo T-1904 era linha de risco, não teste | Guardian | **Aceita** | Promovido a **teste obrigatório** de fechamento |
| G5 | Compat da dep nova com langgraph 1.2.9 | Guardian | **Aceita** | Auditoria confirma sem upgrade forçado; goldens sentinela se forçar |
| G6 | SSE aberto por minutos não fecha no auto-lock | Guardian | **Aceita** | Stream fecha com terminal/erro no bloqueio do cofre |
| U1 | Entrada da retomada é invisível → surpresa | Advocate | **Aceita** | Linha do tempo explica a retomada em linguagem clara, não rótulo cru |
| U2 | Contador mostra vida, não progresso; pode não reduzir ansiedade | Advocate | **Aceita (importante)** | Aceitação de campo (c) julga contador vs pulso; **fases-puras preservado como recuo** |
| U3 | "tentativa 2 de 2" lê como "a IA errou" | Advocate | **Aceita** | Rótulo "refinando a resposta"; nunca expõe retry como falha |
| U4 | Toggle sem ajuda é abstrato | Advocate | **Aceita** | Linha de ajuda de *quando* importa |
| U5 | Fallback para polling pode parecer quebra | Advocate | **Aceita** | Preserva última fase, sem erro na tela; E2E cobre |

**Objeções rejeitadas (2):** S1 e S6 — ambas pressionaram decisões travadas
(#2 e #3) sem trazer causa nova; mantidas como residuais documentados, não
reaberturas. **Todas as demais (15) foram aceitas e aplicadas ao design
acima.** O par de spikes do dia 1 (T-2601 SQLCipher/concorrência, T-2603
streaming×T-2505) concentra o risco remanescente e cada um agora tem
degradação segura definida (plano C / POST único), de modo que nenhum pode
travar o ciclo — no pior caso o entregável correspondente encolhe, o produto
nunca piora. **Design apto ao lançamento após estas revisões.**

## Registro da execução (2026-07-18, fechamento)

- **Os dois spikes do dia 1 APROVARAM os desenhos sem acionar os recuos:**
  - T-2601: `SqliteSaver` × `sqlcipher3` viável via **Plano B** (2ª conexão
    dedicada; o Plano A caiu por análise de API — o saver tem lock interno
    próprio, dois locks sobre a mesma conexão = commit de um encerra a
    transação do outro). O `setup()` do saver **força `journal_mode=WAL` no
    `dados.db` inteiro** (hardcoded no pacote) — conversão aprovada
    explicitamente pelo mantenedor; `busy_timeout=5000` nas duas conexões ⇒
    0 `database is locked` sob concorrência com o auto-save. Plano C
    (`InMemorySaver`) implementado mas nunca necessário em teste/smoke.
  - T-2603: no build embarcado real (b9966 + phi-3.5), o 400 de recusa de
    gramática chega no `urlopen` **antes de qualquer chunk** ⇒ os 3 degraus
    do T-2505 streamam; nenhum precisou do recuo para POST único. 1º token
    em ~0,5–1,2 s no `json_object`.
- **Correção do revisor no T-2603 (relevante):** `tentativa` do contador
  virou **semântica** (`refinando` declarado pelo chamador), não número de
  chamada HTTP — sem isso, TODA análise com phi-3.5 (que sempre leva o 400
  na 1ª chamada; a memoização não atravessa análises) nasceria rotulada
  "refinando a resposta", violando o espírito da U3. O fallback de gramática
  é transparente; só o retry do guardrail e o conserto dirigido refinam.
- **Achados de execução registrados:** (1) `HF_MODO_DEGRADADO=1` degrada
  ANTES do grafo (em `agente.analisar`) ⇒ não emite fases — o E2E do caminho
  feliz da linha do tempo usa conexão recusada (P8 real, fases genuínas);
  (2) o T-2602 persistiu na tabela key-value `estado` (chave
  `analise_ultima`) em vez de tabela nova — zero migração de schema
  (ADR-0017 §E), e o endpoint virou `POST /analise/ultima` (a ponte escolhe
  o verbo pelo payload; o backend calcula `assinatura_atual` dos dados
  vivos); (3) evento `retomada` (U1) foi adicionado no T-2604 (o T-2603 não
  o emitia); (4) **flake E2E novo registrado**: cenário "correção T-2602" de
  `analise-linha-do-tempo.spec.ts`, 2 falhas em 6 rodadas SOB primeira
  carga pós-mudança, 4 rodadas limpas depois (incl. suíte 20/20) — perfil
  histórico das atas v2.4..v2.11; sem correção às cegas, trace na
  reincidência.
- **Execução:** T-2601/T-2603 executor-opus, T-2602/T-2604 executor-sonnet
  (3 quedas por session-limit ao longo do ciclo, todas retomadas por
  mensagem sem perda de progresso). Deps novas:
  `langgraph-checkpoint-sqlite==3.1.0` (+ transitivas `aiosqlite`,
  `sqlite-vec`) — sem upgrade forçado do `langgraph 1.2.9`, goldens
  intactos.
- **Fechamento (T-2605):** CI remoto verde em todos os pushes do ciclo;
  auditoria §5: npm audit 0, pip-audit 0, Electron 43.1.1 na janela
  vigente; build oficial 2.15.0 **assinado** (cert de teste regenerado —
  o PFX anterior havia sido apagado; sidecar assinado antes do
  empacotamento, ADR-0021) + smoke do pacote (2/2) + smoke do órfão
  recriado e verde (Job Object efetivo no exe congelado, agora pelo caminho
  de análise streaming).
- **Aceitação de campo (2026-07-18, máquina do mantenedor):** (a) retomada
  após kill confirmada, com a frase "retomando a análise interrompida" na
  linha do tempo; (b) hidratação com carimbo confirmada; (c) **contador de
  tokens MANTIDO** por decisão do mantenedor ("até ter certeza" — U2
  encerrada; fases-puras permanece documentado como recuo); (d) a bateria
  de perfis variados **achou o T-2606**: o "Diagnóstico da Saúde
  Financeira" ignorava o fluxo de caixa — déficit mensal de R$ 2.159,47
  saía "Saudável" (a regra do ADR-0001 só olhava parcelas÷renda; gap de
  produto pré-existente, não regressão do ciclo).
- **T-2606 (adicionada ao M26 com aval do mantenedor, padrão T-2505):**
  `classificar_saude` vira **pior entre 2 eixos** — parcelas (clássico) ×
  fluxo de caixa (superávit ⇒ Saudável; déficit ≤10% da renda ⇒ Atenção;
  >10% ou renda zero ⇒ Crítico); a explicação cita o eixo que puxou para
  baixo (empate num nível ruim ⇒ frases combinadas). Teste de regressão que
  FALHAVA antes (provado via stash contra o core antigo); golden
  `relatorio_critico_deficit` regenerado deliberadamente (única mudança: a
  explicação agora combina os dois motivos); rebuild assinado + smokes
  repetidos no artefato final. **Revalidação do item (d) confirmada pelo
  mantenedor (2026-07-18, "confirmo o fix")** — dashboard refletindo o
  déficit com a régua nova e perfis variados completos. Ciclo fechado com a
  ata `FREEZE.md` v2.15.0.
