# Relatório de auditoria de saúde de código — ciclo v2.9 (M18)

- **Ciclo:** v2.9.0 (ADR-0017), fase M18 (auditoria). Base congelada: v2.8.0 (`7d2a664`).
- **Data:** 2026-07-12 (revisão crítica do consolidador aplicada na mesma data).
- **Natureza:** consolidação das cinco varreduras somente-leitura. **Nenhum
  arquivo do repositório foi alterado.** As correções são a fase M19, e só
  começam após o portão humano (§ *Portão* abaixo).
- **Autoria:** varreduras T-1801/T-1802 (Opus), T-1803/T-1804 (Sonnet),
  T-1805 (orquestrador Fable); consolidação, verificação independente no
  código-fonte e adjudicação de severidade por Fable (T-1806).

## Como ler este relatório

Cada achado tem um **ID consolidado** `C-NN` (estável) e o **ID de origem**
`A-<task>-<seq>` da varredura. Achados que apareceram em mais de uma varredura
foram **fundidos** numa linha só. A severidade segue os critérios objetivos da
ADR-0017 §D; onde a varredura e o consolidador divergiram, a divergência está
declarada (§ *Adjudicações de severidade*). A numeração pula o C-09
(posição vazia de uma versão anterior, mantida para não invalidar referências).

**O portão é seu:** para cada achado, você decide `CORRIGIR` (vira task T-19xx
com teste de regressão obrigatório) ou `REGISTRAR` (fica no relatório para
ciclos futuros, sem correção agora). Nada é corrigido sem sua marcação.

## Placar

| Severidade | Achados consolidados |
|---|---|
| **Crítico** | 1 |
| **Alto** | 5 |
| **Médio** | 14 |
| **Baixo** | 14 |
| **Total** | **34** |

Varreduras: T-1801 (segurança) 8 · T-1802 (concorrência/recursos) 9 · T-1803
(fronteira) 5 · T-1804 (higiene) 9 · T-1805 (silenciosos/dívida de teste) 6 =
**37 brutos**, fundidos em **34 consolidados** (3 fusões: A-1801-03→C-02,
A-1802-07→C-08, A-1804-08+09→C-35).

## Revisão crítica do consolidador (o que foi verificado no código)

Todos os achados de severidade crítico/alto e a maioria dos médios foram
**verificados linha a linha no código-fonte pelo consolidador**, independente da
evidência da varredura:

- **Confirmados sem ressalva:** C-01 (`schemas.py` sem `ge=0` + `parseBR`
  aceita negativo), C-02 (`encerrarSidecar()` = `kill()` fire-and-forget em
  `window-all-closed`/`before-quit`; lifespan é o único ponto que encerra o
  runtime), C-03 (`base_url()` numa instância obsoleta ressobe o servidor com o
  cfg antigo — `runtime_llm.py:279-283` vs `encerrar_runtime`), C-04 (a limpeza
  existe SÓ no poll final, `app.py:753`), C-06 (`main.ts:115` faz `resp.json()`
  antes do `!resp.ok`), C-07 (`ErroSidecar.detail: string` em `client.ts:59-64`),
  C-08 (`llmBaixarStatus` existe em `client.ts:227` e nenhuma tela chama),
  C-10 (concatenação sem validação de prefixo), C-12 (lock retido durante o
  poll de saúde), C-14 (`estado_arquivo` re-hasheia o arquivo inteiro por item
  por chamada), C-21 (DEK na f-string SQL em `persistencia.py:122`), C-24
  (`rl.close()` sem dreno posterior de stdout), C-25 (grep global: só as
  definições existem).
- **Pendência resolvida (C-25):** `llm_definir_modelo` (`app.py:1299`) entrega
  o REQ-F-028 chamando `definir_modelo_ativo` diretamente nos dois fluxos
  (catálogo e `.gguf` local); `apontar_gguf_local` é um alias puro de uma linha
  sem nenhum chamador. **Remoção segura — nada se perde.** O aviso da varredura
  ("confirmar antes de apagar") está encerrado.
- **Acoplamento identificado (importante para o plano do M19):** corrigir
  **C-01 sem corrigir C-07 piora a UX** — o `Field(ge=0)` passa a gerar
  exatamente os 422 de `RequestValidationError` cujo `detail` (lista) hoje vira
  `"[object Object]"` na tela. As duas correções devem andar juntas (ou C-07
  primeiro).
- **Remediação comum:** C-02 + C-11 (Job Object + shutdown gracioso com prazo)
  e C-04 + C-08 (mesmo mecanismo de TTL/expurgo de jobs) são pares naturais de
  task única.

## Adjudicações de severidade (varredura vs consolidador)

| Achado | Varredura | Consolidado | Razão (critério §D) |
|---|---|---|---|
| C-05 | alto (T-1805) | **médio** | Não há efeito de runtime hoje (sidecar está em 92%); é um gate que não cobre o que aparenta — o análogo direto de "teste que não testa o que diz" (médio). Correção continua prioritária pelo custo ínfimo (1 linha). |
| C-08 | alto (T-1803) / baixo (T-1802, mesmo vazamento) | **médio** | O §D exige "comportamento errado" para dessincronia ser alto; aqui o comportamento está certo e o efeito real é um vazamento pequeno (entradas de dict + `threading.Event`, poucos downloads por sessão). Médio é a leitura honesta entre as duas varreduras. |
| C-21 | alto (T-1801) | **médio** | Vazamento da DEK seria crítico SE ocorresse, mas não há gatilho comprovado — "bug latente de cenário raro" é a definição literal de médio no §D. Subir para alto é decisão válida do portão se você pesar o ativo (segredo-mestre) acima da probabilidade. |

## Perímetro auditado

**Coberto (ADR-0017 §B):** todo o Python de primeira parte (`core/`, `agent/`,
`guardrails/`, `outputs/`, `sidecar/`, `scripts/`, `main.py`) + a fronteira TS
dos dois lados (`gui_web/electron/main.ts`, `preload.ts`,
`gui_web/src/hf/client.ts`, `contract.ts`, `schemas.py` Pydantic).

**Declaradamente NÃO coberto:** as telas React `.tsx` (só tocadas quando um
achado da fronteira apontou para dentro — `CampoMoeda.tsx`, `Dividas.tsx`,
`Contrato.tsx`, `ConfiguracaoIa.tsx`, `Analise.tsx`); análise de CVE em código
nativo transitivo (DLLs Vulkan/OCR) além da verificação de integridade de build;
teste de mutação (mutmut) — sugerido para ciclo futuro. A GUI Tkinter legada
(`gui/`) está fora do perímetro, mas foi consultada para descartar falsos
positivos de código morto.

---

## CRÍTICO

### C-01 — Números negativos entram sem barreira nos dois lados da fronteira
- **Origem:** A-1803-03 · **Categoria:** fronteira/validação-de-entrada ·
  **Esforço:** P
- **Arquivos:** `sidecar/schemas.py:15-60` (nenhum campo `float` usa
  `Field(ge=0)`); `gui_web/src/lib/format.ts:14-21` (`parseBR("-500") → -500`);
  `gui_web/src/components/CampoMoeda.tsx:30-44` (`<input>` sem `min`).
- **Evidência (verificada pelo consolidador):** `DividaIn` (`saldo_devedor`,
  `taxa_mensal`, `parcela`), `RendaIn`, `FixasIn`, `VariaveisIn` e os campos
  soltos de `PerfilIn` são todos `float = 0.0` sem validador; `parseBR` devolve
  qualquer número, inclusive negativo.
- **Impacto:** um valor com sinal de menos (digitado ou colado por engano) em
  qualquer campo monetário grava número financeiro incorreto sem aviso. Pior:
  `Divida.juros_restantes = max(custo_total_restante - saldo_devedor, 0.0)`
  **mascara** o erro como `0.0` em vez de sinalizá-lo. Viola diretamente H1
  (número financeiro correto) — o determinístico não salva se a **entrada** já
  está errada e nada barra.
- **Proposta:** `Field(ge=0)` nos campos monetários/quantitativos de
  `schemas.py` (422 cedo, mensagem clara) + clamp `Math.max(0, …)` em
  `CampoMoeda.onValor` (mesmo padrão já usado em `Dividas.tsx:214` e
  `Contrato.tsx:44-47` para `parcelas_restantes`). **Obrigatoriamente em
  conjunto com C-07** (ver § *Revisão crítica*).

---

## ALTO

### C-02 — `llama-server` fica órfão em todo caminho de morte do sidecar
- **Origem:** A-1802-01 (dono) + A-1801-03 (ângulo de segurança) ·
  **Categoria:** recursos/processo-filho · **Esforço:** G
- **Arquivos:** `gui_web/electron/main.ts:210-213,271-276`;
  `sidecar/app.py:109-118` (lifespan); `sidecar/runtime_llm.py:305-307,335-347`.
- **Evidência (verificada):** no Windows `sidecar.kill()` = `TerminateProcess`
  (morte dura, sem sinal ao Python); o `llama-server` só é encerrado pelo
  lifespan do FastAPI, que **não roda** em kill duro/crash/quit/relaunch. É o
  órfão observado no T-1704 (dois seguraram EBUSY no rebuild). O caminho
  `TimeoutExpired → proc.kill()` do runtime está descoberto por teste (C-18).
- **Impacto:** processo `llama-server.exe` órfão segurando RAM/VRAM e o handle
  do `.gguf`; acúmulo a cada reinício; quebra de build (EBUSY).
- **Proposta:** Windows Job Object com `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`
  (mata a árvore junto com o pai, único mecanismo que cobre o kill duro);
  `atexit`/sinal como reforço para a saída graciosa. Task única com C-11.

### C-03 — Corrida na troca de modelo deixa dois `llama-server` no ar
- **Origem:** A-1802-02 · **Categoria:** concorrência/corrida-de-estado ·
  **Esforço:** M
- **Arquivos:** `sidecar/runtime_llm.py:272-283,355-385`;
  `sidecar/gestor_modelos.py:261-278`.
- **Evidência (verificada):** `runtime_embarcado()` devolve a instância sob
  `_LOCK_SINGLETON` e a solta; `base_url()` usa o lock de instância e, se o
  processo morreu, **ressobe com o cfg da própria instância** (o modelo antigo).
  Em paralelo, `POST /llm/modelo` → `encerrar_runtime()` zera `_RUNTIME`; a
  próxima chamada cria outra instância com o modelo novo.
- **Impacto:** dois servidores rodando, o antigo órfão (nunca mais referenciado,
  não encerra no shutdown) e a operação em voo rodando o modelo errado.
- **Proposta:** unificar a disciplina de lock (servir/guardar a instância sempre
  sob `_LOCK_SINGLETON`, ou invalidar a instância após `encerrar()` para que
  `base_url()` recuse subir).

### C-04 — `_JOBS_IA` retém seção **desanonimizada** (PII) sem TTL nem limpeza
- **Origem:** A-1802-03 · **Categoria:** recursos/vazamento-de-memória (toca
  REQ-SEC-003) · **Esforço:** M
- **Arquivos:** `sidecar/app.py:701-720,745-754`.
- **Evidência (verificada):** `_rodar_job_ia` grava `secao.model_dump()` já
  **desanonimizada** (nomes reais de credores); a entrada só é removida no poll
  final (`app.py:753`). Dicionário sem teto nem TTL; sem limpeza no
  bloqueio/auto-lock do cofre.
- **Impacto:** se a GUI fecha, troca de tela, o auto-lock dispara ou a rede cai
  antes do poll final, a PII financeira em claro fica **para sempre** em memória;
  jobs abandonados acumulam.
- **Proposta:** TTL/limite + coleta preguiçosa; **descartar `_JOBS_IA` no
  `bloquear()`/auto-lock** para não reter PII além da janela desbloqueada.
  Mecanismo compartilhável com C-08.

### C-06 — `chamarSidecar` faz `resp.json()` antes de checar `!resp.ok`
- **Origem:** A-1803-01 · **Categoria:** fronteira/caminho-de-erro-ipc ·
  **Esforço:** M
- **Arquivos:** `gui_web/electron/main.ts:106-116` ⇄ rotas sem try/except amplo
  em `sidecar/app.py` (`/diagnostico:342`, `/estrategias:655`,
  `/rubricas:497-540`, `/historico/*:428-491`).
- **Evidência (verificada):** `main.ts:115` roda `resp.json()` antes do
  `if (!resp.ok)`, sem try/catch. O sidecar não registra
  `@app.exception_handler(Exception)`; uma exceção não mapeada nessas rotas vira
  o **500 padrão do Starlette** (`PlainTextResponse`, não JSON).
- **Impacto:** o parse de texto puro como JSON falha, a rejeição da Promise passa
  pelo structured-clone do Electron e **perde tudo exceto `.message`** — a
  regressão exata ao padrão pré-T-1604, e o `status` (essencial para o gate
  423/429) se perde.
- **Proposta:** `try/catch` em torno do `resp.json()`, devolvendo `__hfErro`
  com `status: resp.status` e `detail` genérico quando o corpo não for JSON;
  considerar um `exception_handler(Exception)` no sidecar garantindo corpo JSON
  em todo 500.

### C-07 — `detail` de `RequestValidationError` é lista, tratado como string
- **Origem:** A-1803-02 · **Categoria:** fronteira/códigos-http · **Esforço:** P
- **Arquivos:** `gui_web/electron/main.ts:115` ⇄ `gui_web/src/hf/client.ts:40-64`
  ⇄ handler padrão do FastAPI (não sobrescrito).
- **Evidência (verificada):** validação automática do Pydantic devolve
  `{"detail": [{"loc":…,"msg":…}]}` (lista de objetos); `ErroSidecar` tipa
  `detail: string` e o valor vai cru para `new HfErro(...)`.
- **Impacto:** `Error()` coage via `String()` → `"[object Object]"`; o usuário
  não recebe pista do campo inválido. **A correção de C-01 multiplica a
  frequência deste cenário** — as duas andam juntas.
- **Proposta:** normalizar `detail` em `main.ts` (se array, reduzir `loc`+`msg`
  a string legível) ou registrar
  `@app.exception_handler(RequestValidationError)` no sidecar.

---

## MÉDIO

### C-05 — A catraca de cobertura **não mede o `sidecar/`** (nem `scripts`/`main`)
- **Origem:** A-1805-01 · **Categoria:** dívida-de-teste/catraca-cega ·
  **Esforço:** P · **Severidade adjudicada** (varredura: alto — ver tabela)
- **Arquivos:** `pyproject.toml:91`
  (`source = ["core","agent","guardrails","outputs","contracts"]`).
- **Evidência (medida pelo consolidador):** o pacote mais crítico do app (cofre,
  auth, persistência, runtime) está fora do piso de 90%. Medição avulsa: sidecar
  está em **92,0%** hoje (1558 stmts), mas poderia cair a zero sem nenhum gate
  falhar. É o padrão "verde que não vê" que motivou o ciclo.
- **Impacto:** regressão de cobertura no sidecar é invisível — a única proteção
  quantitativa de teste ignora justamente a superfície mais sensível. Sem efeito
  de runtime hoje (por isso médio), mas correção de 1 linha.
- **Proposta:** adicionar `"sidecar"` (e avaliar `"scripts"`) ao `source`; o
  total combinado fica ~94,2%, acima do piso. `sidecar/__main__.py` (0%) entra em
  `omit` justificado ou ganha teste de fumaça.

### C-08 — `_JOBS_DOWNLOAD`/`_CANCELAMENTOS` nunca limpos (contrato dessincronizado)
- **Origem:** A-1803-04 (dono) + A-1802-07 (mesmo vazamento, ângulo recursos) ·
  **Categoria:** fronteira/jobs-assíncronos + recursos/vazamento · **Esforço:** P ·
  **Severidade adjudicada** (T-1803: alto; T-1802: baixo — ver tabela)
- **Arquivos:** `sidecar/app.py:1177-1273`; `gui_web/src/hf/client.ts:227-228`
  (`llmBaixarStatus` nunca chamado — verificado por grep global); 
  `gui_web/src/screens/ConfiguracaoIa.tsx:31-82`.
- **Evidência:** o único ponto que remove a entrada terminal é
  `GET /llm/baixar/{job_id}`, que **nenhuma tela chama**; a tela faz poll do
  catálogo agregado, que só filtra `status=="baixando"`.
- **Impacto:** cada download concluído deixa a entrada (e um `threading.Event`)
  presa em memória pela vida do processo. Vazamento real mas pequeno, raiz numa
  dessincronia contrato↔fluxo da tela.
- **Proposta:** (a) `ConfiguracaoIa.tsx` chama `llmBaixarStatus(job_id)` na
  transição para estado terminal; ou (b) `llm_catalogo` expira jobs terminais
  com TTL curto. Mecanismo compartilhável com C-04.

### C-10 — `chamarSidecar` concatena `metodo` do renderer sem validar prefixo `/`
- **Origem:** A-1801-02 · **Categoria:** segurança/superfície-de-rede ·
  **Esforço:** P
- **Arquivos:** `gui_web/electron/main.ts:104-114`.
- **Evidência (verificada):** `http://127.0.0.1:${porta}${metodo}` — um `metodo`
  como `@attacker.com/x` produz `http://127.0.0.1:porta@attacker.com/x`, onde o
  host efetivo é `attacker.com` (parsing WHATWG) e o `X-HF-Token` vaza.
- **Impacto:** um eventual XSS no renderer (hoje sem vetor conhecido — React
  escapa) escalaria para exfiltração do token + dados financeiros, fora da CSP
  (roda no processo main). Defesa em profundidade ausente.
- **Proposta:** validar que `metodo` começa com `/` e não contém `@`/`//`/`:`
  antes do 1º `/`, ou montar via `new URL(metodo, base)` e checar `origin`.

### C-11 — Shutdown do Electron é fire-and-forget, sem gracioso nem timeout
- **Origem:** A-1802-09 · **Categoria:** concorrência/shutdown · **Esforço:** M
- **Arquivos:** `gui_web/electron/main.ts:210-276`.
- **Evidência (verificada):** `encerrarSidecar()` faz `kill()` e retorna, sem
  pedir shutdown gracioso, sem aguardar `exit`, sem ordem garantida
  sidecar→janela (`window-all-closed` e `before-quit`).
- **Impacto:** no Windows não há SIGTERM real; o lifespan nunca roda (fechar
  SQLCipher, `encerrar_runtime`), requisições em voo são cortadas.
- **Proposta:** encerramento gracioso com prazo curto (endpoint/sinal + aguardar
  `exit`), `kill()` só como último recurso. **Task única com C-02.**

### C-12 — `base_url()` segura o lock de instância durante o boot do modelo (até 60 s)
- **Origem:** A-1802-04 · **Categoria:** concorrência/lock-durante-IO ·
  **Esforço:** M
- **Arquivos:** `sidecar/runtime_llm.py:272-283,316-327` (timeout health :83 = 60 s).
- **Evidência (verificada):** o `self._lock` é retido durante todo o
  `_esperar_saude_sem_lock`; `ativo()` (`GET /llm/status`, pollado pela tela) e
  `encerrar()` (`POST /llm/modelo`) também precisam do lock.
- **Impacto:** enquanto o modelo carrega, a UI de status/troca de modelo congela
  até 60 s. O resto do app responde (threadpool), mas a experiência trava.
- **Proposta:** não segurar o lock durante o poll; estado "iniciando"
  (evento/condição) para `ativo()` responder sem bloquear; só o START serializa.

### C-13 — Singleton do motor OCR sem lock → carga dupla concorrente
- **Origem:** A-1802-05 · **Categoria:** concorrência/singleton-sem-lock ·
  **Esforço:** P
- **Arquivos:** `sidecar/app.py:854-869`.
- **Evidência:** `_motor_ocr_singleton` lê/escreve globais sem lock; duas
  requisições OCR concorrentes na primeira vez (`/importar/ocr` +
  `/contrato/extrair`) constroem **dois** motores RapidOCR.
- **Impacto:** carga dupla dos modelos, pico de memória, motor descartado (leak
  de handle).
- **Proposta:** `threading.Lock` com double-checked locking, como já se faz no
  runtime LLM e na sessão.

### C-14 — `GET /llm/catalogo` re-hasheia os `.gguf` inteiros a cada chamada
- **Origem:** A-1802-06 · **Categoria:** recursos/IO-desnecessário · **Esforço:** M
- **Arquivos:** `sidecar/gestor_modelos.py:298-329`; `sidecar/app.py:1149-1169`.
- **Evidência (verificada):** `estado_arquivo` chama `_sha256_arquivo(final)`
  (arquivo inteiro) por item; `listar_catalogo_com_estado` itera o catálogo; a
  tela faz poll. Até 3 arquivos de 1–2,4 GB lidos por chamada.
- **Impacto:** abrir/atualizar a tela de Configuração da IA lê **vários GB do
  disco** por chamada, satura disco/CPU e pode colidir com um download em curso.
- **Proposta:** cachear o veredito por (caminho, mtime, tamanho); só re-hashear
  se mudou, ou verificar integridade só na promoção do download.

### C-15 — Ausência de code signing do app e dos binários embarcados
- **Origem:** A-1801-04 (pendência de ofício c) · **Categoria:**
  segurança/integridade-de-distribuição · **Esforço:** G
- **Arquivos:** `gui_web/electron/main.ts:187-208` (auto-update);
  `resources/llama/` (binários de terceiros).
- **Evidência (verificada):** o próprio código documenta que a distribuição de
  produção "deve ser assinada" e o `electron-updater` depende disso; não há
  assinatura no pipeline.
- **Impacto:** SmartScreen/Defender marca como desconhecido; auto-update não
  verifica autenticidade de forma robusta; sem garantia de integridade pós-install.
- **Proposta:** certificado Authenticode + assinar instalador e exes; até lá,
  manter auto-update opt-in desligado (já é o default). **Decisão de custo é sua.**

### C-16 — Electron 33.4.11: CVE *high* no `npm audit`, duas majors atrás do suporte
- **Origem:** A-1801-05 · **Categoria:** segurança/dependência-vulnerável ·
  **Esforço:** M
- **Arquivos:** `gui_web/package.json` (`electron: ^33.3.1`).
- **Evidência:** `npm audit` reporta `electron <=39.8.4` com múltiplos CVEs (ASAR
  bypass, spoof de IPC, header injection, UAF).
- **Impacto:** classificado pela exploitabilidade **no nosso perfil endurecido**
  (`contextIsolation`, `sandbox`, `nodeIntegration:false`, permission handler que
  nega tudo, sem conteúdo remoto, CSP restritiva): a maioria dos CVEs exige
  recursos que o app não usa; nenhum exploit direto identificado. Mas está fora
  da janela de suporte de segurança.
- **Proposta:** bump de Electron (major, breaking) em ciclo próprio, com smoke
  completo do pacote (regra ADR-0017 §E.4). **Não** aplicar `npm audit fix --force`.

### C-17 — `nltk 3.9.4` com path-traversal (transitivo, sem vetor no nosso uso)
- **Origem:** A-1801-06 · **Categoria:** segurança/dependência-vulnerável ·
  **Esforço:** M
- **Arquivos:** `uv.lock` (`nltk`, transitivo de `llama-index-core`).
- **Evidência:** `pip-audit` (venv real, via `uv run --with pip-audit`) reporta
  `PYSEC-2026-597`: path traversal em `nltk.data.load()/find()` com resource name
  controlado pelo atacante.
- **Impacto:** **sem exploit no nosso uso** — o app nunca passa entrada do usuário
  como resource name; o tokenizer é fixo ("punkt") e o retrieval só roda no
  provider local/ollama.
- **Proposta:** acompanhar o fix upstream (bump quando `llama-index-core`
  aceitar versão corrigida); sem urgência.

### C-18 — Caminhos sensíveis do sidecar descobertos por teste
- **Origem:** A-1805-02 · **Categoria:** dívida-de-teste · **Esforço:** M
- **Arquivos:** `sidecar/runtime_llm.py:344-347` (kill do runtime — onde nasce o
  órfão de C-02); `sidecar/sessao.py:174-184` (decisão de não filtrar stderr,
  ligada a C-21); `sidecar/app.py:716-717` (`except` do job de IA).
- **Evidência:** `--cov=sidecar` term-missing aponta exatamente esses trechos.
- **Impacto:** os três caminhos mais delicados só funcionam "por fé"; correções
  do M19 nessas áreas não têm rede de segurança hoje.
- **Proposta:** os testes de regressão obrigatórios das tasks correspondentes
  (C-02 etc.) devem cobrir estas linhas; não precisa de task própria.

### C-19 — Ramo RAG de documento longo é código quase-morto e sem teste
- **Origem:** A-1805-03 (+ relaciona A-1804-01 `carregar_documento`) ·
  **Categoria:** dívida-de-teste/caminho-inalcançável · **Esforço:** M
- **Arquivos:** `agent/ingestao.py:46-70` (54,2% cobertura);
  `sidecar/app.py:1002-1007`.
- **Evidência (verificada):** o caminho "documento longo" (`SentenceSplitter` +
  `VectorStoreIndex` + `OllamaEmbedding`) não tem teste offline e só é alcançável
  com provider ∈ `_PROVIDERS_COM_EMBEDDINGS`; com o runtime embarcado do v2.8 o
  sidecar sempre trunca em `texto[:LIMITE_EXTRACAO_LLM]`.
- **Impacto:** para o usuário padrão v2.8, documento longo é silenciosamente
  truncado (correto por decisão, mas invisível e sem teste); o ramo RAG é
  quase-morto no produto empacotado.
- **Proposta:** teste offline fixando o truncamento; **decisão consciente no
  portão** — manter o ramo RAG (documentado) ou removê-lo.

### C-20 — Flake E2E: 7 esperas fixas `waitForTimeout(1_500)`
- **Origem:** A-1805-04 · **Categoria:** silencioso/flake-e2e · **Esforço:** M
- **Arquivos:** `gui_web/e2e/app.spec.ts:228,238,290,305,381,420`;
  `gui_web/e2e/cofre-helpers.ts:63`.
- **Evidência (verificada por grep):** espera fixa intercalada com asserts de UI
  — causa clássica de flake sob carga; pós-build pesado (o cenário exato da ata
  v2.8.0) o render demora mais que 1,5 s e o assert corre contra estado antigo.
- **Impacto:** o flake E2E recorrente registrado na ata; erode a confiança no
  gate (re-rodar até passar vira hábito).
- **Proposta:** trocar cada `waitForTimeout` pela condição real
  (`expect(...).toHaveText/toBeVisible` ou `waitForResponse` do endpoint).

### C-21 — DEK na string SQL + stderr do SQLCipher não filtrado (vazamento latente)
- **Origem:** A-1801-01 · **Categoria:** segurança/vazamento-de-segredo ·
  **Esforço:** P · **Severidade adjudicada** (varredura: alto — ver tabela)
- **Arquivos:** `sidecar/persistencia.py:122,168`; `sidecar/sessao.py:176-184`;
  `gui_web/electron/main.ts:68`.
- **Evidência (verificada):** a DEK é interpolada na string SQL
  (`PRAGMA key = "x'…64hex…'"`) e a decisão do T-1603 de **não** filtrar o stderr
  do SQLCipher está ativa; o `main.ts:68` ecoa todo o stderr do sidecar sem scrub.
- **Impacto:** *se* algum traceback/log futuro ecoar a statement, o hex da DEK
  vai ao stderr → terminal. DEK vazada = cofre aberto (REQ-SEC-001/006). Não há
  gatilho comprovado hoje (o `PRAGMA key` bem-formado raramente erra; chave
  errada é capturada no `SELECT` de sanidade e traduzida em `ChaveInvalida` sem
  a chave) — risco **latente por decisão explícita**.
- **Proposta:** manter a raw key fora de qualquer superfície de erro (try/except
  que relança sem a statement) e/ou scrub de stderr redigindo `x'[0-9a-f]{64}'`.
  **Revalidar a política do T-1603 §b no portão** — subir para alto é marcação
  sua, se pesar o ativo acima da probabilidade.

---

## BAIXO

### C-22 — Nome de arquivo do usuário (PII-adjacente) em log de OCR
- **Origem:** A-1801-07 · **Esforço:** P · `sidecar/app.py:906,1055`.
- Nome do comprovante/contrato (frequentemente com PII) ecoado ao stderr.
  REQ-SEC-001 é estrito. **Proposta:** logar só `type(e).__name__`+extensão, ou
  redigir o nome.

### C-23 — Arquivos do cofre sem permissão restritiva no fallback POSIX
- **Origem:** A-1801-08 · **Esforço:** M · `sidecar/auth.py:322-331`;
  `sidecar/persistencia.py:257-260`.
- No fallback `~/.helper_financeiro` os arquivos nascem `0644`; outra conta local
  pode copiar `auth.json`/`dados.db` (força-bruta offline do Argon2id). Windows
  (`%APPDATA%`) não afetado (ACL herdada). **Proposta:** `os.open(..., 0o600)` +
  pasta `0700` no POSIX.

### C-24 — `stdout` do sidecar não drenado após o handshake (deadlock latente)
- **Origem:** A-1802-08 · **Esforço:** P · `gui_web/electron/main.ts:69-82`.
- Se o sidecar escrever >64 KB em stdout após o handshake, o pipe enche e o
  Python bloqueia. Hoje latente (só emite handshake em stdout). **Proposta:**
  `sidecar.stdout.resume()` após ler o handshake.

### C-25 — 4 funções mortas de verdade
- **Origem:** A-1804-01 · **Esforço:** P ·
  `guardrails/validador_numerico.py:93` (`extrair_numeros`),
  `sidecar/gestor_modelos.py:290` (`apontar_gguf_local`),
  `sidecar/sessao.py:264` (`resetar_sessao`), `agent/ingestao.py:30`
  (`carregar_documento`).
- Zero chamadores em produção ou teste (verificado por grep global pelo
  consolidador). **Pendência da varredura resolvida:** `llm_definir_modelo`
  entrega o REQ-F-028 chamando `definir_modelo_ativo` direto nos dois fluxos;
  `apontar_gguf_local` é alias puro — **remoção segura das 4**.

### C-26 — Normalização de valor monetário pt-BR reimplementada 3×
- **Origem:** A-1804-02 · **Esforço:** P · `core/utils.py:11-39,65-86`;
  `guardrails/validador_numerico.py:46-48`.
- Três cópias da mesma regra pt-BR; `validador_numerico` nem importa `core.utils`.
  Divergência futura violaria H1. **Proposta:** helper único; avaliar se
  guardrails pode depender de `core.utils`.

### C-27 — Escrita atômica de JSON duplicada byte a byte
- **Origem:** A-1804-03 · **Esforço:** P · `sidecar/auth.py:322-331`;
  `sidecar/gestor_modelos.py:229-236`.
- `tmp + os.replace` copiado; um `fsync` futuro teria de ser aplicado nos dois.
  **Proposta:** extrair `_gravar_json_atomico`.

### C-28 — `gerar_relatorio` é o maior hotspot de complexidade
- **Origem:** A-1804-04 · **Esforço:** M · `outputs/relatorio.py:93`.
- C901=16, PLR0912=14, PLR0915=94 statements. Números que aparecem no `.docx`
  entregue (H1-adjacente) difíceis de isolar. **Proposta:** quebrar por seção.

### C-29 — Hotspots secundários de complexidade
- **Origem:** A-1804-05 · **Esforço:** M · `outputs/planilha.py:258`
  (`_aba_evolucao`, C901=11); `sidecar/gestor_modelos.py:333` (`baixar_modelo`,
  C901=11 + TRY301). **Proposta:** extrair funções internas.

### C-30 — Docstring mentirosa em `resetar_sessao`
- **Origem:** A-1804-06 · **Esforço:** P · `sidecar/sessao.py:264-270`.
- Afirma existirem "poucos testes" que a usam; nenhum teste a referencia.
  Resolver junto com C-25 (remoção).

### C-31 — 18 `except Exception` sem log (observabilidade, não bug)
- **Origem:** A-1804-07 · **Esforço:** M (se logar) · lista em
  `core/`, `agent/`, `sidecar/app.py`, `scripts/`.
- Decisão arquitetural P8 (degradação segura) **documentada** — por isso baixo.
  Efeito colateral: falha recorrente real fica invisível sem log. **Proposta
  opcional:** `log.debug(...)` antes do fallback onde já há logger. **Sua
  decisão no portão.**

### C-32 — Sinal fraco de contrato em `/rubricas` (schema drift inofensivo)
- **Origem:** A-1803-05 · **Esforço:** P · `sidecar/app.py:502-540` ⇄
  `contract.ts:140-143` (`RubricaMutOut`).
- As três rotas devolvem chaves (`rubrica`, `ok`) que o contrato não modela;
  ninguém consome hoje. **Proposta:** alinhar as rotas a `{rubricas, perfil}` ou
  tipar três saídas.

### C-33 — Lacunas de cobertura em fallbacks de classificação/PDF
- **Origem:** A-1805-06 · **Esforço:** M · `agent/classificacao.py` (85,7%);
  `core/extrator_pdf.py` (80,0%).
- Ramos de fallback (o que degrada sem falhar) sem teste. **Proposta:** testes
  direcionados aos ramos com decisão (sem perseguir 100%).

### C-34 — `_rodar_job_ia` engole exceção sem log (assimétrico ao download)
- **Origem:** A-1805-05 · **Esforço:** P · `sidecar/app.py:716-718`.
- Diferente de `_rodar_job_download` (que loga), o job de IA grava
  `status:"erro"` sem `log.warning`. **Proposta:** espelhar o padrão do download.

### C-35 — Estilo menor / falsos positivos de linter (sem ação recomendada)
- **Origem:** A-1804-08 + A-1804-09 (fundidos) · **Esforço:** P ·
  `ARG001` do LangGraph (assinatura exigida pelo framework), `ERA001`
  falso-positivo (cabeçalhos de seção), `S608` (SQL com constante do módulo, não
  entrada do usuário), `PLW0603`/`FURB122` (padrões intencionais). Registrados por
  transparência; **nenhum atinge o patamar "vale mexer"** pelo critério §D.

---

## Sobreposições e fusões (rastreabilidade)

| Consolidado | IDs de origem | Resolução |
|---|---|---|
| C-02 | A-1802-01 + A-1801-03 | fundidos: mesmo órfão, ângulos recursos + segurança; dono T-1802 |
| C-08 | A-1803-04 + A-1802-07 | fundidos: mesmo vazamento, ângulos contrato + recursos; severidade adjudicada |
| C-35 | A-1804-08 + A-1804-09 | fundidos: grupo "sem ação recomendada" |
| C-11 | A-1802-09 | correlato de C-02 (remediação comum, task única) |
| C-18 | A-1805-02 | caminhos sem teste que dão rede às correções de C-02/C-21 |
| C-19 | A-1805-03 (+A-1804-01 parcial) | ramo quase-morto + função morta relacionados |

**Sem achado (verificações registradas para não reabrir):** authz rota a rota
(nenhuma rota de negócio sem token+cofre); bind loopback estrito; CORS ausente;
comparações em tempo constante; anti-brute-force/anti-replay TOTP; migração do
cofre atômica; download GGUF (corrida do T-1702 já fechada); SQLite conexão
única serializada; escrita atômica de JSON e `.parcial`; timeouts HTTP
presentes; sem `shell=True`/`os.system`; nenhum TODO/FIXME real; nenhuma API
deprecada (Pydantic v1, `utcnow`, `on_event`).

---

## Portão — RESULTADO (2026-07-12)

**O mantenedor aprovou integralmente a recomendação do consolidador** ("vamos
fazer do jeito que vc propôs"). Tasks resultantes: **T-1901..T-1910** (ver
`docs/TASKS.md`, M19); **registrados sem correção neste ciclo:** C-15, C-16,
C-17, C-23, C-28, C-29, C-35. Decisões específicas ratificadas: C-21 ganha o
try/except em `persistencia.py` com a política de stderr do T-1603 **mantida**
(T-1908); o ramo RAG de C-19 será **removido** (T-1909); os 18 `except` de
C-31 ganham `log.debug` (T-1909).

A recomendação aprovada, na íntegra:

1. **`CORRIGIR` já no M19:** C-01+C-07 (task única — acopladas), C-02+C-11
   (task única — Job Object + shutdown gracioso), C-03, C-04+C-08 (mecanismo
   comum de expurgo), C-05 (1 linha), C-06, C-13 (trivial), C-20 (mata o flake
   que suja o gate), C-34 (1 linha). Isso quita o crítico, todos os altos e os
   médios de melhor custo-benefício.
2. **Decisão explícita sua:** C-21 — mantém a política do T-1603 (registrar) ou
   corrige o scrub/try-except (esforço P)? Minha recomendação: **corrigir o
   try/except em `persistencia.py` (barato, elimina a superfície) e manter a
   política de stderr documentada** — melhor dos dois mundos.
3. **`REGISTRAR` para ciclo dedicado:** C-15 (code signing — depende de
   certificado), C-16 (bump Electron — major breaking, ciclo próprio §E.4),
   C-17 (nltk — aguardar upstream).
4. **Decisão de produto:** C-19 (minha recomendação: **remover o ramo RAG** — é
   quase-morto no produto e a remoção simplifica; quem usa Ollama externo não
   perde extração, só o retrieval de documento >LIMITE) e C-31 (minha
   recomendação: adicionar `log.debug` — barato, sem mudança de comportamento).
5. **Lote de higiene (baixos):** C-25+C-30, C-26, C-27, C-34 são P e podem ir
   num lote único; C-12, C-14, C-22, C-24, C-28, C-29, C-32, C-33 ao seu
   critério; C-23 só importa se um dia houver build POSIX; C-35 sem ação.

Me diga, por achado ou por grupo, o que vira task de correção (T-19xx) e o que
fica registrado. A partir daí monto o plano do M19 com teste de regressão
obrigatório para cada correção aprovada.
