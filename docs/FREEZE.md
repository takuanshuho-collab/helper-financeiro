# FREEZE — Ata de Congelamento v2.15.0

- **Data:** 2026-07-18
- **Versão da Constituição:** 2.0.0
- **Escopo congelado:** ciclo **v2.15** (ADR-0023): milestone **M26** —
  **checkpoint durável, persistência visível e progresso em tempo real**,
  desenhado via brainstorming + revisão multi-agente (disposição REVISE,
  15/17 objeções aplicadas ANTES do lançamento) a partir da síntese do
  documento externo "Melhorias de App com LLM". **T-2601**: checkpoint do
  grafo durável DENTRO do cofre cifrado — `SqliteSaver` numa 2ª conexão
  SQLCipher (Plano A descartado no spike: o saver tem lock interno próprio;
  o `setup()` força **WAL** no `dados.db` inteiro, conversão aprovada pelo
  mantenedor; `busy_timeout=5000` nas duas conexões ⇒ 0 `database is
  locked` sob concorrência com o auto-save), proxy chaveável singleton nos
  dois grafos com escrita/leitura **não-fatais** (a análise nunca aborta
  por checkpoint; plano C degrada para memória), `thread_id` = assinatura
  SHA-256 dos fatos (a chave do cache T-205), retomada SÓ de thread
  inacabado, poda (máx. 1 inacabado por grafo), toggle "retomar análises
  interrompidas" default ligado (opt-in da ADR-0006 honrado), teste
  anti-PII varrendo o checkpoint INTEIRO por super-step (incl. o estado
  pós-`gerar` pré-`sanear`). **T-2602**: última análise persistida no
  cofre (chave key-value `analise_ultima` — zero migração de schema;
  `SecaoIA` JÁ desanonimizada + assinatura + carimbo + modelo), `POST
  /analise/ultima` devolve a salva + a `assinatura_atual` dos dados vivos
  (a GUI só compara strings — REQ-NF-005); ordem **persistir-antes-de-
  apagar** o checkpoint; GUI com carimbo "dados inalterados"/"Gerar
  novamente" e selo âmbar "os dados mudaram" (seção antiga esmaecida).
  **T-2603**: os 3 degraus do T-2505 agora **streamam** — o spike no build
  embarcado real (b9966 + phi-3.5) provou que o 400 de gramática chega
  ANTES de qualquer token; provider com contador de tokens sob throttle
  (≥16 tokens/≥200 ms), "tokens e então erro" descarta o parcial; o job
  consome `grafo.stream()` síncrono (último `values` == `.invoke()`,
  provado por teste); `GET /analise/ia/{job_id}/eventos` (SSE: fases com
  rótulos pt-BR montados no backend, progresso, terminal com
  `aviso_runtime`, heartbeat; fecha no auto-lock — nada de PII ressuscita,
  G4 coberto). Correção do revisor: `tentativa` é SEMÂNTICA — o fallback
  de gramática do phi-3.5 é transparente ("o modelo está escrevendo");
  só o retry do guardrail e o conserto dirigido rotulam "refinando a
  resposta" (U3). **T-2604**: linha do tempo na GUI — a ponte SSE vive no
  MAIN do Electron (token nunca sai de lá, REQ-SEC-004; frames por IPC
  push), fases ✓ + item ativo pulsando + "escrevendo… N tokens", retomada
  explicada ("retomando a análise interrompida"), queda→polling graciosa
  SEM erro na tela (polling nunca roda em paralelo com o stream). O
  conteúdo do LLM NUNCA aparece antes dos guardrails/desanonimização.
  **T-2606 (adicionada no fechamento, aval do mantenedor — padrão
  T-2505)**: a bateria de perfis da aceitação achou um gap do ADR-0001 —
  o "Diagnóstico da Saúde Financeira" ignorava o fluxo de caixa (déficit
  de R$ 2.159,47/mês saía "Saudável"). Regra nova: **pior entre 2 eixos**
  (parcelas ≤30%/≤50% × fluxo: superávit Saudável; déficit ≤10% da renda
  Atenção; >10% ou renda zero Crítico), explicação cita o eixo que puxou;
  teste que FALHAVA antes (provado via stash); golden
  `relatorio_critico_deficit` regenerado deliberadamente (única mudança:
  explicação combinada).
- **Auditoria de dependências deste fechamento (regra ADR-0018 §5):**
  `npm audit` = **0**; `pip-audit` = **0**; Electron **43.1.1** (mesma
  janela dos fechamentos v2.12..v2.14). Deps novas do ciclo:
  `langgraph-checkpoint-sqlite==3.1.0` (+ transitivas `aiosqlite 0.22.1`,
  `sqlite-vec 0.1.9`; MIT/Apache) — SEM upgrade forçado do
  `langgraph 1.2.9` (goldens-sentinela intactos). Nenhum risco aceito
  novo. **CI remoto (regra ADR-0020 hotfix):** verde em todos os commits
  do ciclo.
- **Build assinado (ADR-0021):** o PFX do cert de teste havia sido
  apagado do host — cert **regenerado** via `preparar_cert_teste.ps1`
  (thumbprint `DD6CFC3C5DDB35DD8E9C3409C658A8C3B92DB646`, validade 30
  dias; instruções de remoção impressas pelo script). Instalador E
  sidecar assinados (`CN=Helper Financeiro (Teste)`; o sidecar é assinado
  ANTES do empacotamento — extraResource). Lições: `npm run dist` puro
  NÃO assina (sem as envs `HF_CSC_*` a config é inerte); o prompt `!` do
  harness roda **bash**, não PowerShell — sintaxe `$env:` não seta env.
- **Aceitação de campo quádrupla (máquina do mantenedor, GTX 1650):**
  (a) app morto no meio da análise ⇒ retomada confirmada com "retomando a
  análise interrompida" na linha do tempo; (b) reabertura ⇒ última análise
  hidratada com carimbo; (c) linha do tempo acompanhada — **contador de
  tokens MANTIDO** por decisão do mantenedor (U2 encerrada; fases-puras
  segue documentado como recuo); (d) perfis variados completos em
  streaming — a bateria achou o T-2606, corrigido no ciclo e **revalidado
  pelo mantenedor com a régua nova** ("confirmo o fix", 2026-07-18).
- **Fora do escopo versionado (untracked de propósito):**
  `docs/RELATORIO-NOVA-VERSAO-STACK-WEB.md` (síntese do documento externo
  que originou o ciclo), `docs/PROJETO-SAAS-SERVER-EDITION.md` (blueprint
  SaaS futuro, critérios §6 para sair da gaveta),
  `docs/RELATORIO-PERSISTENCIA-ANALISE.md` (origem do T-2602, absorvido),
  `docs/PESQUISA-ONNX-RUNTIME-GENAI.md` e relatórios PaddleOCR-VL.

Qualquer mudança nos artefatos congelados abaixo exige **nova ADR +
incremento de versão + nova ata**.

## Checksums SHA-256 dos artefatos

### Documentos SDD e guia de IDE

| Artefato | SHA-256 |
|---|---|
| `docs/CONSTITUTION.md` | `77b11451303e2d378a631ec420f95802e7c4799a21762fac7704f93f2fffefec` |
| `docs/PRD.md` | `7a0d731b4bf65918084da884ed70655afe0fc3d4595d268aa5c5f7c0840d7ff3` |
| `docs/SPEC.md` | `800dd0b1801494f9a4120735ee0c5214ca913e4cc961ca347873b13f35e3a831` |
| `docs/PLAN.md` | `e61a988b03683dbd66076924d59384917d59420c5e743d7d9b0f253e0590156f` |
| `docs/TASKS.md` | `62980c0b5f6404b3187db8c9dd83a102ad3a3a96659b8abced99f39ce112ee34` |
| `docs/HARNESS.md` | `76b5ab35b4583f4c38771009452f21a2282aef826305ba5f1a75005f85cf2967` |
| `docs/AGENT.md` | `742de4d9d5bd1a16768f64bbf4dbcb74a39a5b01fa7d9d1e6995ea6952c0e842` |
| `docs/REVISAO-SEGURANCA.md` | `ec6923ac3abbe8e4235db73c8b1472558be1336d6d4d6b621b3cb91512ed4a2b` |
| `docs/SEGURANCA-SHELL.md` | `e59baca3c3023bb318dd231bce712fd6612524794fa9c5054f592ce772c19fd6` |
| `docs/PARIDADE.md` | `0b715d9664cdc8eb4b94703f9aed5667ac45e08be7837beb2af4b284ba1c4cc0` |
| `docs/RELATORIO-AUDITORIA.md` | `b81674da539bf81129c482bc19a564a0dc3847025288e3023f47b7518d7838ad` |
| `AGENTS.md` | `678a2473998cab86146a1b4b4fd8d6dda40bbc38d4a6d56a3c85d49c52e7e1f0` |

### Decisões de arquitetura (ADR)

| Artefato | SHA-256 |
|---|---|
| `docs/adr/ADR-0001-deterministico-vs-llm.md` | `dc2f410f68e5665b66bf2726a8bdcad636298e9e85560f44a56ac6ef341f50d0` |
| `docs/adr/ADR-0002-provider-agnostico.md` | `1afa4cbed1e81b75c60604e636984a0ecc64e13751db1d12cacd053b70d02acc` |
| `docs/adr/ADR-0003-anonimizacao-guardrails.md` | `88abc358acfbf34d7c03d5a8fd1d498cb8c07aba345f91a234a111acf21a8d84` |
| `docs/adr/ADR-0004-camada-contracts.md` | `c8d5b730c8605ea4cdaf83dbe5e316c76d6681440c6f0c8fe48522da9076566d` |
| `docs/adr/ADR-0005-structured-output.md` | `5f33a3a95fd02b427ec60220c8aeca5f8789fa244866404ff616c9dc13e1af89` |
| `docs/adr/ADR-0006-langgraph-orquestrador.md` | `20df5b09b8055a80c553e91823ad76735d7d3e9e22ffee7d03ac34ddc055340f` |
| `docs/adr/ADR-0007-llamaindex-ingestao.md` | `4a96caec6ab8aad9417a17ba09730dc6154b69d5bef6c069a0a321293edec89f` |
| `docs/adr/ADR-0008-perfil-orcamento-detalhado.md` | `157bd569fb9cd4572d664afd1312aeeb69269b69d6e436df18a2f543a9249b44` |
| `docs/adr/ADR-0009-gui-web-electron-sidecar.md` | `d3d700d067ff90f3b1bdc64107672e2fd58b45f841592b889e657248cb2b0b5d` |
| `docs/adr/ADR-0010-extracao-markdown-e-llm-local-openai.md` | `f43edc306796e066f8a11d121fb13783d958390732a2d070b7361641cbb01dba` |
| `docs/adr/ADR-0011-recuperacao-com-feedback-e-redacao-deterministica.md` | `e0aba289f6766663f9c42119ed3618297c6aaa4679308febe37683410db3c258` |
| `docs/adr/ADR-0012-rubricas-e-persistencia-sqlite.md` | `314ed8ce7259f10ae0089510587a5684db3f76dd596088f665a7158757c907c4` |
| `docs/adr/ADR-0013-historico-mensal-do-orcamento.md` | `b660a37592e73eb25f1988d47723d15c054753ce8f93864c636cc0d6d493c82e` |
| `docs/adr/ADR-0014-importacao-csv-evolucao-e-historico-no-xlsx.md` | `b856f31b15546ebdd9aea53011f1c6c241f0b1566cd50dbbc7602b3da0c14f71` |
| `docs/adr/ADR-0015-ocr-de-documento-escaneado.md` | `49258054c14a329d19a53c89c4eca9410236fd1c0576f00c180b52462a4599af` |
| `docs/adr/ADR-0016-cofre-local-mfa-e-llm-embarcada.md` | `3039f7fc88ede7bbdcf4b3c1d68e132d38ebdd6ab5d75d8d7f2f9027858c7d30` |
| `docs/adr/ADR-0017-ciclo-de-saude-de-codigo.md` | `13b35818103cab2ca0f6c2238838dca28b0078c7119ed93ce28dafdbc9cc2955` |
| `docs/adr/ADR-0018-bump-electron-43.md` | `f12c84d43ba96307e94f338509a563e843ab605dd259a75cffaf718aa51966c3` |
| `docs/adr/ADR-0019-ciclo-higiene-e-complexidade.md` | `6d389a871ccee5c435616fc00027f5bb2e86e53d5c401f31b85f3c9c7eb03204` |
| `docs/adr/ADR-0020-ciclo-build-release.md` | `67fa63282e74500c3f598847ba73d30a3e1e6d0eddccb8542ddcb6bcc4046455` |
| `docs/adr/ADR-0021-ciclo-code-signing.md` | `ca9c643f1aa5b60df5ea69955a7187debd8d1c802c9db1abde4952a191e297d9` |
| `docs/adr/ADR-0022-ciclo-runtime-llm-configuravel.md` | `ebd5cf7e4f5ae887caac62342d01d5f70f2034e5569028206c82231b7ad6a6de` |
| `docs/adr/ADR-0023-checkpointers-duraveis-e-streaming-sse.md` | `1ed5c1accbb869bb797f3f41c09e27984e86bd42ec7a14a0626b8e0a53bedb80` |

### Contratos de dados

| Artefato | SHA-256 |
|---|---|
| `contracts/__init__.py` | `45bb5509b0070df695e5fba97b45e7beeaf80ad0f26d968fb2778898924d892c` |
| `contracts/schemas.py` | `751fd5d246334dea399ddb31d95f4952ff526df28bb1c3936b58a83718183bd2` |

### Núcleo determinístico (core)

| Artefato | SHA-256 |
|---|---|
| `core/__init__.py` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `core/calculos.py` | `0c1d697451e4b7908c29178a4d5ab3ee43c282ead61a8cd19ccf02d6f4b57191` |
| `core/diagnostico.py` | `e9f1cba99922ff6e687947db33f970694f381caf0258521bb8aa85b35d1f52f4` |
| `core/documento.py` | `cc25fd326d1bc1dbf9c686fcc430eeb81bfca3ffb7edf5880feb85c94ed9b27d` |
| `core/estrategias.py` | `e46a4c078af1b37cabe79770481aee7f51f2384674afd5e17b27a13cbc8b04be` |
| `core/extrato.py` | `1b41612f65b86809d61ed63690cc7feb9e01d826947611bb2f52519ef9dc871f` |
| `core/extrator_pdf.py` | `18223c2bdce0f113e8642634ada88fe2996c5bdb9713805af284326a51a5c6d5` |
| `core/models.py` | `12315f3f20bf24b5d7d42606c912d88bf9796c60d4553d4da4d526a9a6e787d3` |
| `core/rubricas.py` | `bbba4e9ef9311195ba90ac8579e143d3b0afe9923c7526b30a9cf670964cfe80` |
| `core/utils.py` | `ff4046f95a19f4282fc9c92056e66e23633369fea54567b754049736f65896d6` |

### Agente sob guardrails (agent)

| Artefato | SHA-256 |
|---|---|
| `agent/__init__.py` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `agent/agente.py` | `d8074262d0edb3242fb63a43010671b2a04148150f94b7839b6338cf72105939` |
| `agent/cache.py` | `badee5b1b2cd7d02129dcc1693bd1622b06398f2e041cb75a00b1d0f31e63748` |
| `agent/classificacao.py` | `1e811e51ea848474d75092ed08e4a2cf79cebb93afe5088bde1192f3c07d05db` |
| `agent/config.py` | `de94789fd2c79c4f67a5e27a483bf682d409c8ad7a98b0538000ab8fbdaa3140` |
| `agent/exibicao.py` | `d9db63887e3818ba580943370458ec271675c2c6bfc5928afa1255fb5974439d` |
| `agent/extracao.py` | `87ecef070ba4b179cba41bb6d0ee599097e5613a510cefec6e07b23c81484164` |
| `agent/grafo.py` | `e2b3ea29f53ccbe3de2b3bb25567a4aca7f27d6c621b454ba4ef19d799d55ddd` |
| `agent/ingestao.py` | `5a80bf93dd28b792d39622b8dfb3ba02582b424cb804086a02b19f46430fe3fd` |
| `agent/ocr.py` | `96c5bf1ded98eb637094ac0faa1225144d2bf41728e287807729baa12311e287` |
| `agent/prompts.py` | `b3110d726d3abbca1ec97eb984ea7c401119a5861440e2c712d672a2fef49cd3` |
| `agent/provider.py` | `6df326ad96f5bc3a5435c0de6ddfed22ae1a7d70abe66a2dfe5a647f0c1b8e9d` |
| `agent/telemetria.py` | `508639cfed573988d84f3af75b88b54c37d22e0c5e2bbad5ecece7d464ff5753` |

### Guardrails

| Artefato | SHA-256 |
|---|---|
| `guardrails/__init__.py` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `guardrails/conteudo.py` | `66a7c0d5b957d86d48edec5a88146751c78a6d085cc1135a851d53ff7aa517fd` |
| `guardrails/pii.py` | `240a29fc98db36da3cc925d11c506b2b1e52075e889ff9e51fbb76585f6d52db` |
| `guardrails/validador_numerico.py` | `a3a3dca36af95b479fd1d790174e50b4c0626e0b22a83e80b132585f2029f30f` |

### Geração de saídas (outputs)

| Artefato | SHA-256 |
|---|---|
| `outputs/__init__.py` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `outputs/planilha.py` | `10a1d8dec1d831576868dc88add3a6db50a7e5f1f49a3ecb2d1473e6411ebef7` |
| `outputs/proposta.py` | `6ec379824f5cea82e89ae51700849aa019ebca22ee1fda35db7abba44ecddb74` |
| `outputs/relatorio.py` | `e6980afd2237c41800630327d49627ab9df2acbec7e338f98f752b3c7727a33a` |

### Sidecar (fronteira HTTP local + persistência + cofre + LLM)

| Artefato | SHA-256 |
|---|---|
| `sidecar/__init__.py` | `0f55c31161b81aad9355fe5ad58fae8064defe1a7a7cfd238ed17e59073e5aad` |
| `sidecar/__main__.py` | `7e57e7ff71a25020a25ec5c715fd58f6dafcff633121f6db49d83f14cff7b7c0` |
| `sidecar/app.py` | `34b9f3ca04041a670046a29c7f4868aa7a3d182b01b301e56ccc21e77c59a7bb` |
| `sidecar/arquivos.py` | `e15cc431874ae3cb0a076a9b0d1809e281f0b796ebff771bf6409173ef73fe82` |
| `sidecar/auth.py` | `26431b0a512199853cda420de97e67573b11fdfb9a55ca608fe52e404462a3e0` |
| `sidecar/gestor_modelos.py` | `ab559c5e9cb998777be4407dfe172e93a0010e8f6ce82e21fd7e6ddd8a46142e` |
| `sidecar/job_windows.py` | `5dc3f805f35cfcbc1b81357f4f0e1ca2830021c168f74fa31d55d56ef8436f95` |
| `sidecar/persistencia.py` | `f96a0903851d4fd8fc00a7b5919438f2174f00add81bca3f4389d6d54ca5f6da` |
| `sidecar/runtime_llm.py` | `685b7824709472f1dc0f9a9625b197243b1b9d20d03efc67fb30bfe89f81fbe3` |
| `sidecar/schemas.py` | `641936ba020934052dc858a069fa76890c57e51097f9725225649d9ab9aa85f8` |
| `sidecar/security.py` | `1a6396f0e09140f6e0a599613071cb80ffe0508fc0c223241d1046993d68081b` |
| `sidecar/sessao.py` | `88e5b5ac70e8e1785cc1dfcb2c803a7ef76e3e4868d6481ec9acf0bf6e33c1de` |
| `sidecar/checkpoint_cofre.py` | `a0a743f69c21778aedfb82dcc6e4263da7021ae5f77d48061427b9162e597ae7` |

### GUI clássica (gui — fallback)

| Artefato | SHA-256 |
|---|---|
| `gui/__init__.py` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `gui/app.py` | `7ddc1358ec13667b64ea2a0e9479119f1d0fa07b9cc95141f20ea53cc72dfd87` |

### GUI web (gui_web — Electron + React/TS + E2E)

| Artefato | SHA-256 |
|---|---|
| `gui_web/e2e/app.spec.ts` | `f578df02871759e23302145a316eeca956d29d865e18861932d2ece2fd4d0187` |
| `gui_web/e2e/cofre-helpers.ts` | `765a7a6605d7b0105da9a53b390afa0d11bb5c8ebe6be82060c9d27ea6a5607e` |
| `gui_web/e2e/cofre.spec.ts` | `2a499871e441b4a7069e5747d4fc634d0f6a2a81f214708b5bc46631ae367896` |
| `gui_web/e2e/configuracao-ia-runtime.spec.ts` | `793e82d49cec26cb7d65b3bd60efaa58f1aff26dcbc0ac537d156971f518472b` |
| `gui_web/e2e/configuracao-ia.spec.ts` | `bef5560ca0e2ec9e0ffdcf5b4218edfd161a93a1d5b9142fccef9bf30f4240c0` |
| `gui_web/e2e/empacotado-llm.spec.ts` | `634e91e333a4c37269c17ec98baa61dcd4878097650565044eb694c8b54cd93d` |
| `gui_web/e2e/empacotado-update.spec.ts` | `e60678e3a21499519b180b31b6a006827a886316e4470fc7a2f9900ce0b92e7a` |
| `gui_web/e2e/empacotado.spec.ts` | `829dbd5b9092859c8c97ea4613ab723e78b50afeb1bc47900603543da8a703be` |
| `gui_web/e2e/fixtures/comprovante-escaneado.png` | `e40b7dfe7b9b5523b1cf05a65b9743dd200b9bad6a207b4fbdd74df9eab41a8e` |
| `gui_web/e2e/fixtures/contrato-escaneado.png` | `abca12f61ce1fef2323c5f818d9c076ed23c0b4506e3de1cb9b5965002d36747` |
| `gui_web/e2e/fixtures/fake-llama-server.py` | `54ae2469b5e0cadede36ddbc6400ae4a3fe06328b6f6fea667c424f4355de441` |
| `gui_web/electron/main.ts` | `f9e57f7c4cf0752ac5ee834149852fccf96bb0fee0a0c65dcae0243646b3467c` |
| `gui_web/electron/preload.ts` | `d37fc0b9414b218897c8473701f196609808b166f0d4ba7686c790316cf0ddc8` |
| `gui_web/eslint.config.mjs` | `5f6f18f557d1fb301b6f3437d02a47ff372d9ced55d23582ff63c3003213c155` |
| `gui_web/index.html` | `65d438e190c6a2eb076894d03bc2690dc7bc842d8ee58691c81690fb64555d8d` |
| `gui_web/package.json` | `1feca5503649cc4ed95af49b8d610df8487fb2b699b47c01480edbf21e759556` |
| `gui_web/playwright.config.ts` | `1fc12157bfc5c21d51f9f2ab7f237108a550501b387bcd7c3033081bb741ea29` |
| `gui_web/src/App.tsx` | `1b9a7de77f16bd75a6eb76d1cd5e36d5b9e0d3bb6ff30cda033888e03920ecff` |
| `gui_web/src/components/CampoMoeda.tsx` | `564687d9facbc452b9d15d8c5d919121a98d1d323a3a1b9111a459526286cc4a` |
| `gui_web/src/components/CampoPercent.tsx` | `08a26bc4de92e4c6b6c7eba76c1a2f3e8bc3e62aef591c57ac0a7ef2c0bb83c3` |
| `gui_web/src/components/Icones.tsx` | `3312534d790dd48a45b084441b7edd7813a2d61dee18567577b829051206c677` |
| `gui_web/src/hf/client.ts` | `59f5e3eb1dbad92efa672a258a7accb06df2e3f9a6cbc1d8d75a5d8dda668538` |
| `gui_web/src/hf/contract.ts` | `0892ff4fe452db547c5534e8e086fdd4986de08b5032fd822c603d35afad06fc` |
| `gui_web/src/hf/useAnalise.ts` | `96cceff3430ea2f151383a6820902c9b3cf7bf66a50a2c0c977fb9fec608782e` |
| `gui_web/src/hf/useContadorEspera.ts` | `d5b212be39fbbbd3d681d92c6c8d368a10d464759f8ef4acc40ee68ad5693485` |
| `gui_web/src/lib/arquivo.ts` | `b62cdb2e2d5b0bd70b1b9bd76b89d71fa02bd0d7490ea1a55d578d85dec7076c` |
| `gui_web/src/lib/format.ts` | `5b5a0ee0fb9c8c7daf597991def853b4a133531471b40dbab85622a95184c729` |
| `gui_web/src/lib/orcamento.ts` | `d5d082919ec4c408e7670250fe45ec638246d24883e23ef2df1b27b44b5988ba` |
| `gui_web/src/main.tsx` | `908e625518862c14c075ebc584fd1e40a6390b908206f685f3d7d865361c887c` |
| `gui_web/src/screens/Analise.tsx` | `49c30d61b4203594af8e13f6ff8ac73c83ef9fe2fc99fc7c3288d802bde885d6` |
| `gui_web/src/screens/Carta.tsx` | `dfe11757da61e7fdf8a3c8c2274d8d0acf2c64f467a4cf7882eeb710725d42c9` |
| `gui_web/src/screens/ConfiguracaoIa.tsx` | `0a253497e6a5c896da00116ffd9b14a1010b928ccb88cf127e3c2bb075128143` |
| `gui_web/src/screens/Contrato.tsx` | `cf23c4e472a948158aa08ccbf91b7ccd6c309cac78ddda3e2328234838158583` |
| `gui_web/src/screens/Desbloqueio.tsx` | `31afaf550a9d593c45594639964bd81b20fc077935bbc5b40bc1aa1c4aa888c9` |
| `gui_web/src/screens/Dividas.tsx` | `e5531e9041823be6d1a8a211266700e169f43825ba6b84c51ac1bcc15c838216` |
| `gui_web/src/screens/ImportarCsv.tsx` | `31734694a30201343ec71f0b66abdc480505871fce173708609d77b6e29601d3` |
| `gui_web/src/screens/Onboarding.tsx` | `77b0749b56782f327ca14621a484e73058944a0c0842a3e968acd067a163f140` |
| `gui_web/src/screens/Perfil.tsx` | `84a95595c2f30f84a0a6240ed77a17e9f53b6d3ae8e3dc1f3885670760e99834` |
| `gui_web/src/screens/Planilha.tsx` | `965d08b87e801b2901b1a7adf3587a86bce465fc8629ff1b6fa5f7b29591b4e3` |
| `gui_web/src/screens/VisaoGeral.tsx` | `cabe2c56e24693bddf2c9b53c20d6644ffa7c8c083d29b509257a30fa7dc3140` |
| `gui_web/src/styles.css` | `f4d891a18a54d7c8117a41785099e5e7ab3a97b2a22255577d01819b3223e8eb` |
| `gui_web/src/vite-env.d.ts` | `a49ff9d71ddfefc9d21b83877de10043399c72e1c883e909f14a81c6431423be` |
| `gui_web/vite.config.ts` | `babedaf0e48959bea2faf692583ca7d63bd97739572284ca11c982c02c3816e3` |
| `gui_web/e2e/analise-persistencia.spec.ts` | `bdcd0ddc2c93607a66df9fd5c21043fab6c0ad4be4a86ac73478d106e7c4bd97` |
| `gui_web/e2e/analise-linha-do-tempo.spec.ts` | `03662f7e9b169f6cbff9664f6fc54a1d173472548ab566518c2aac20c6786d4c` |

### Entrypoint, build e empacotamento

| Artefato | SHA-256 |
|---|---|
| `main.py` | `a979656c100f6d12b02e0d625f6197a6b792769aab885f328631faedc019a448` |
| `pyproject.toml` | `5cf8f357a5f44269690b17761591a0da45202249e463f1f7c40e65277713c82f` |
| `SidecarHF.spec` | `cc3471a70cb6ebf50da89c6eb8820fde375645fedcbe40785ff8b187561c3cfa` |
| `scripts/sidecar_entry.py` | `c63c53e315cd42423f06832d120ab66c4ff66965bf038bfcf3012d638acae3d9` |
| `scripts/preparar_ocr.py` | `fb305d8a58947eed84070e898cce647e2abebd7d7aec409a2ad0899cbb96b0a5` |
| `scripts/preparar_llama.py` | `3ad30037f9abe6006a1c92e806c8cb4d304da82983a737792e615c2d56e56bd1` |
| `scripts/preparar_cert_teste.ps1` | `79716b49d44adab7bdfe152179c0518d545340391ec971e9feb0fc80f9f5b7a7` |
| `scripts/build_assinado.ps1` | `56e37073ca9b7b170c3728adff08e8b2949432df4d517c73b5f1dfd327d8a021` |
| `LICENSE` | `a9b26795036f6be56cef2d6837c7be6d0d2d0c27b6bc1bf565cd0c5e4c3a083b` |
| `.github/workflows/ci.yml` | `f603c1b67ac25cb7abb09b2ca2b448725f1cf669d1446499348622478d3af94c` |
| `.github/workflows/release.yml` | `ed06d34a20d1418c04740dc122adde75448ba6a73933035ee4b3e408bee2e577` |

### Harness de testes (tests)

| Artefato | SHA-256 |
|---|---|
| `tests/__init__.py` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `tests/conftest.py` | `aa1980d6c11b623adeba6e5a6b65d525d0e576ec4e3e6227563c6675adf8f656` |
| `tests/golden/planilha_atencao.json` | `5c15be89bd5ec904dca005bbb49a0befeded138f8b0c7de59b9eea7a5976a213` |
| `tests/golden/planilha_atencao_evolucao.json` | `924eeef52646acf97e8f7650670a950a77743d955e2941abbc44bc53275a13b0` |
| `tests/golden/planilha_atencao_rubricas.json` | `7df508896c7c14463b526c31fe638910ad86aa22377bb67a92aad363854adb9e` |
| `tests/golden/planilha_saudavel_sem_dividas.json` | `e8f9f3fe44288b995a6539cb085004884e7ea244610615be8084a863ce277ed0` |
| `tests/golden/relatorio_atencao.json` | `7761ff6c5073e6b55fa9464033f1ceb359ed90fbf2e7d2247e42fe1142370f03` |
| `tests/golden/relatorio_atencao_com_ia.json` | `dbe546d23a0525f631381c50c90a31994bad509eb3c8ae88af11db0964fb53bd` |
| `tests/golden/relatorio_critico_deficit.json` | `0be4dafeefd272eef8ddaf2613fa507647be5577b4a6811649764b95a8916098` |
| `tests/golden/relatorio_saudavel_sem_dividas.json` | `cfc0fac9751c8f0e3701ca6082bbf5cd2280a94e60ee94c67dd085265cfa2868` |
| `tests/golden/relatorio_saudavel_sem_portabilidade.json` | `26e1c26cb653ba50ebd798f289a71e619c6aa9c2f9b63c9ed95e918b8a0920a3` |
| `tests/test_auth.py` | `4032712de76e12dae65fbc68aef342cea5f149c295f33af097da5802b36ea7ce` |
| `tests/test_cache.py` | `27216c7195ea3ff989da4fcbc761acb06ea71c73e8b15bb4f0256017f4ad224a` |
| `tests/test_classificacao.py` | `c520363fef4c48476a866df0c1be34c9fa82915d15b509894b985772bd9abc28` |
| `tests/test_config.py` | `b2b932b36ab59afb057769bc2ba97efb6f2b5804e0ef740604899a57ed79a5b6` |
| `tests/test_conteudo.py` | `73984521960a262548bf5386b41124ce557c032a9340ffa2d13bf96d7f7fd39d` |
| `tests/test_core.py` | `1a9c0dc73e201112efee8ddc6368ff56128d4a70314e739f5877cc0093dd3ecc` |
| `tests/test_degradacao.py` | `921fc14ef77b75527efdd3e048c874a60069de68549ed6d9e331da2010a8eda2` |
| `tests/test_documento.py` | `c42135d3237092f8a574cd400c133b61fdcb915fa0ffb5db68e87372c55839bd` |
| `tests/test_endurecimento_permissoes.py` | `6072dd6f720f6f36459ac160b110492fad19bf104a3d39c1aa2109a34bf02c0f` |
| `tests/test_exibicao.py` | `a6a649d7e47622ba4ab9480d7d83b6534118a78d326f57ee61b9fcb749811ee0` |
| `tests/test_extracao.py` | `79935566352b880c7fb764e743cc3b8f4e4ce4f5a6bd8cb7be579360514b6c0d` |
| `tests/test_extrato.py` | `508c78dffe5add2f1de180dfcf504de81c3d75b5051b79e57380838b3dbb2cce` |
| `tests/test_extrator_pdf.py` | `c9d3dde5cfd9c1e8b97d7602b17fef10761e3d7c4b4b8c1827abb01ee4b06c36` |
| `tests/test_gestor_modelos.py` | `d9dd68a0f2e7aaa49384c6818af8e1992ea652f92491c23f1fe725fddefcb7da` |
| `tests/test_golden_outputs.py` | `329df104a4411d5663b66f318fc802b8794d303739d8f2dcdd98f83bf7ec5d25` |
| `tests/test_grounding.py` | `210c334ff521fb47871a6c8e9e0a55176c5c20921e2ff830903593271e61a231` |
| `tests/test_injecao.py` | `fba9b077cce3796fae23df4eb2619e34adbf841e01044d132620f651a494a856` |
| `tests/test_job_windows.py` | `7caf7a4a9383f1f08b62f206124c10acbed1e6df86583de813c31ea9dcd032bf` |
| `tests/test_ocr.py` | `db382b6dd08e9c3d42a453d648ad557b8766a2c4a306550cc9a0fb4ef239509f` |
| `tests/test_ollama_real.py` | `5899fe7af504afca16c943a4510c20683f2d2fbb58e382148a34b385fc3206ee` |
| `tests/test_orcamento.py` | `608b5e0afa36db0d573f23663971157dce42d7130fac3ebe42591f260f7c6fbe` |
| `tests/test_outputs.py` | `a60018215ca39cbd410720cfb547176459e67ef31b44c98f944b27c11a18da2e` |
| `tests/test_persistencia.py` | `9d0bd572643a8673ea756d39bd36f1e751b973222a1cc221566254150c0057ad` |
| `tests/test_pii.py` | `9e0b052158b1f1af14f89c80bfcedc4be4c33d0e49bd40cebb29790d235c9dbc` |
| `tests/test_preparar_llama.py` | `f55fbe488449bcfbac1261a5d886c3e3153571406c9f6f478e2fac6393c691a9` |
| `tests/test_propriedades.py` | `a3dceb73aa42df79840b9b44925e8c2d3a736faf9df697146e82029035dcb358` |
| `tests/test_providers.py` | `073853e7704c62c19e0066b60c22f26ca990afbac07470144a15fe57e1692d37` |
| `tests/test_recuperacao.py` | `94129e9a3fcf8bca1d180bcc61ea23010107ffeedc15659db961565f666d15c9` |
| `tests/test_rubricas.py` | `74dc0e22bd922ec6d890bf203d6063b7c78176e247bb562a500a31d9d3f4545f` |
| `tests/test_runtime_llm.py` | `3c4a8fe9f42ecd223776411b747cef27001d14167e449941f2dc84bc8998092c` |
| `tests/test_sessao.py` | `b3e658562bc6b5a2d2dbb928c9fe714ce203b4439e61034c8bd81824771ba0e5` |
| `tests/test_sidecar.py` | `a4e6feeeccfb09c62e626c3d0492af2d6bd22e0c1acf41ccc9ebc84ec8d8e601` |
| `tests/test_sidecar_llm.py` | `0de056f6864382d50f990f0f6df52e378a301d64fdc68d45fd501d7ba9804519` |
| `tests/test_telemetria.py` | `f5750e70fe314e187d25f464ea0c5871c2a807e518821cb1a41a4ec1580bdbe8` |
| `tests/test_validacao_texto.py` | `4c9482f0ea98fc9af46a3ea89d4f2262eda6a207e54da9d5ed322ecebdfce3e7` |
| `tests/test_checkpoint_cofre.py` | `155b612eb362e4554ef536a38f32ee68a85af35daeb8f9b1aea134c600dde130` |
| `tests/test_analise_ultima.py` | `91aeab4b28a37694c7579200271669a63edb2400c935e3aca01742ad3e964eca` |
| `tests/test_grafo_stream.py` | `996ce6cdc4f56aa5ed719f77e27805cc3a14c09fcad812989c529c6047a2a996` |

## Binários oficiais deste ciclo (build 2.15.0, assinado — ADR-0021)

| Binário | SHA-256 | Tamanho |
|---|---|---|
| `gui_web/release/Helper Financeiro Setup 2.15.0.exe` | `ee145b9610c2140bf2b8a078814db2bd52ac7a6be2f2c252a191ac5b158b8ce1` | 347,1 MB |
| `dist/sidecar-hf/sidecar-hf.exe (dentro do instalador)` | `e9ee9e32fbce1304a4b67a1a379d48639bbfc01102cbbcc7f76863cce7d67076` | 22,6 MB |

## Estado do harness no congelamento

```
Suíte Python: verde (exit 0; 2 skips opt-in HF_OCR_REAL/HF_LLAMA_REAL) —
inclui os 13 do checkpoint durável (anti-PII por super-step, retomada,
poda, WAL), os 8 da persistência visível, o streaming do provider
(sentinela POST único, throttle, tentativa semântica), o endpoint SSE
(terminal/erro/heartbeat, fecho no auto-lock, G4 — bloqueio no meio não
ressuscita PII) e a saúde em 2 eixos (T-2606, provado via stash).
Golden-master: 9/9 (relatorio_critico_deficit regenerado deliberadamente
no T-2606 — única mudança: explicação combinada). Catraca C901 intacta.
ruff + mypy (win32): limpos.
Gate Front: typecheck (renderer + electron) + ESLint verdes.
E2E dev: 20/20 na rodada final (app 15 + linha do tempo 3 + persistência 1
+ configuração 1); smoke do pacote real 2/2 (HF_E2E_PACOTE=1); smoke do
órfão verde no exe congelado ASSINADO (Job Object mata o llama-server
filho após kill duro — agora pelo caminho de análise streaming).
CI remoto: verde em todos os commits do ciclo (regra ADR-0020).
Auditoria de deps (ADR-0018 §5): npm audit 0 · pip-audit 0 ·
Electron 43.1.1 — nenhum risco aceito novo.
Aceitação de campo: quádrupla, confirmada pelo mantenedor (2026-07-18),
incl. revalidação do T-2606 com a régua nova.
Observações: (1) flake E2E novo registrado — cenário "correção T-2602" de
analise-linha-do-tempo.spec.ts, 2 falhas em 7+ rodadas SEMPRE sob a
primeira carga pós-mudança, depois limpo (perfil histórico das atas
v2.4..v2.11; sem correção às cegas — capturar trace na reincidência);
(2) HF_MODO_DEGRADADO degrada ANTES do grafo (sem fases no SSE) — os E2E
do caminho feliz usam conexão recusada (P8 real); (3) o cert de teste
regenerado NÃO herda a confiança do anterior no host (afeta só smoke de
auto-update; remoção do cert: instruções na saída do
preparar_cert_teste.ps1, thumbprint DD6CFC3C…).
```
