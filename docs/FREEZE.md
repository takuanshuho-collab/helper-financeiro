# FREEZE — Ata de Congelamento v2.7.0

- **Data:** 2026-07-08
- **Versão da Constituição:** 2.0.0
- **Escopo congelado:** ciclo **v2.7** (ADR-0015): milestones **M14** e **M15** —
  **OCR local** de documento escaneado/imagem (RapidOCR + **PP-OCRv6 medium** em
  ONNX Runtime, 100% na máquina; os modelos são **EMBARCADOS** no pacote — zero
  rede em execução, REQ-NF-006). **M14:** a aba **Contrato** aceita PDF e imagem
  (JPG/PNG) — detecção determinística da fonte (`core/documento.py`: densidade de
  texto p/ PDF, extensão p/ imagem), motor `agent/ocr.py`, pré-marcação por
  **tipo** (`<valor>`/`<data>`/`<percentual>`, nunca semântica) e trave de
  citação **tolerante ao ruído de glifo** do OCR (`0`↔`O`, `1`↔`l`↔`I`, `5`↔`S`,
  `8`↔`B`) nas duas vias, sem afrouxar H1. Empacotamento: `SidecarHF.spec`
  embarca os `.onnx` + onnxruntime/cv2/shapely (`collect_all`);
  `scripts/preparar_ocr.py` materializa os modelos medium antes do freeze e o
  spec **trava** o build se algum `.onnx` obrigatório faltar. **M15:**
  comprovante/extrato **escaneado** desemboca na importação do v2.6 —
  `core.extrato.ler_extrato_ocr` reconstrói os lançamentos por layout e reusa a
  classificação por LLM local, a revisão humana e o `/importar/aplicar` (mesmos
  grupos, mesma regra de acréscimo; todo número vem do core — H1); a tela
  "Importar extrato (CSV ou imagem)" aceita foto/PDF. REQ-F-024/025/026 +
  REQ-NF-006. Sem migração de schema (`VERSAO_ESQUEMA` permanece 1). Recursos do
  ciclo existem só na GUI web; tkinter permanece fallback congelado do v2.3
  (`PARIDADE.md` §7).
- **Regra:** qualquer alteração nos artefatos abaixo exige nova ADR,
  incremento de versão e nova ata.
- **Atas anteriores:** v2.0.0..v2.2.0 (2026-07-04, M1..M6), v2.3.0..v2.5.0
  (2026-07-07, M7..M12) e v2.6.0 (2026-07-08, M13) — substituídas por esta.

> A lista congelada cobre todo o código de primeira parte (incluindo os
> artefatos novos do ciclo: `core/documento.py`, `agent/ocr.py`,
> `scripts/preparar_ocr.py` e as fixtures de OCR em `gui_web/e2e/fixtures/`) e o
> harness. `docs/INDEX.md` (mapa navegável) e este `FREEZE.md` não se
> auto-hasheiam.

## Checksums SHA-256 dos artefatos

### Documentos SDD e guia de IDE

| Artefato | SHA-256 |
|---|---|
| `docs/CONSTITUTION.md` | `77b11451303e2d378a631ec420f95802e7c4799a21762fac7704f93f2fffefec` |
| `docs/PRD.md` | `7a0d731b4bf65918084da884ed70655afe0fc3d4595d268aa5c5f7c0840d7ff3` |
| `docs/SPEC.md` | `8b1b27b18088cee08706c54b109e603255b6b904decb48a8622941547abfdb42` |
| `docs/PLAN.md` | `8a92f8c48910e4acd3d64c11cb96820f39dc1dcf9e4488000540dcfd207b134c` |
| `docs/TASKS.md` | `ef6b0eb68e3f27a6f057ae257368f5a8454b182cd5b860ccf398093e8d0409e5` |
| `docs/HARNESS.md` | `7e8efe3a69ed66ec595913278dad9ac292a200c4f2133761b4bd3e67e9bd9a81` |
| `docs/AGENT.md` | `742de4d9d5bd1a16768f64bbf4dbcb74a39a5b01fa7d9d1e6995ea6952c0e842` |
| `docs/REVISAO-SEGURANCA.md` | `ec6923ac3abbe8e4235db73c8b1472558be1336d6d4d6b621b3cb91512ed4a2b` |
| `docs/SEGURANCA-SHELL.md` | `e59baca3c3023bb318dd231bce712fd6612524794fa9c5054f592ce772c19fd6` |
| `docs/PARIDADE.md` | `40f0bb272679f73f8737b765d678eb5b85d78927e5814453359ea58a8792b3f2` |
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
| `docs/adr/ADR-0007-llamaindex-ingestao.md` | `9bcd0d2a83aa16f09a93221cfa2bbddd1cdf2054dd696b41220e48c78ad34c16` |
| `docs/adr/ADR-0008-perfil-orcamento-detalhado.md` | `157bd569fb9cd4572d664afd1312aeeb69269b69d6e436df18a2f543a9249b44` |
| `docs/adr/ADR-0009-gui-web-electron-sidecar.md` | `d3d700d067ff90f3b1bdc64107672e2fd58b45f841592b889e657248cb2b0b5d` |
| `docs/adr/ADR-0010-extracao-markdown-e-llm-local-openai.md` | `f43edc306796e066f8a11d121fb13783d958390732a2d070b7361641cbb01dba` |
| `docs/adr/ADR-0011-recuperacao-com-feedback-e-redacao-deterministica.md` | `e0aba289f6766663f9c42119ed3618297c6aaa4679308febe37683410db3c258` |
| `docs/adr/ADR-0012-rubricas-e-persistencia-sqlite.md` | `314ed8ce7259f10ae0089510587a5684db3f76dd596088f665a7158757c907c4` |
| `docs/adr/ADR-0013-historico-mensal-do-orcamento.md` | `b660a37592e73eb25f1988d47723d15c054753ce8f93864c636cc0d6d493c82e` |
| `docs/adr/ADR-0014-importacao-csv-evolucao-e-historico-no-xlsx.md` | `b856f31b15546ebdd9aea53011f1c6c241f0b1566cd50dbbc7602b3da0c14f71` |
| `docs/adr/ADR-0015-ocr-de-documento-escaneado.md` | `49258054c14a329d19a53c89c4eca9410236fd1c0576f00c180b52462a4599af` |

### Contratos de dados

| Artefato | SHA-256 |
|---|---|
| `contracts/__init__.py` | `90b395b50166e4e31b8236aa8f452b9b5b93d0c57013920094bed6fed3ac98b0` |
| `contracts/schemas.py` | `a6368d864ce25de33afb7c254b6da38b596dabd0ab6f89aa3629478d8513e437` |

### Núcleo determinístico (core)

| Artefato | SHA-256 |
|---|---|
| `core/__init__.py` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `core/calculos.py` | `0c1d697451e4b7908c29178a4d5ab3ee43c282ead61a8cd19ccf02d6f4b57191` |
| `core/diagnostico.py` | `eca93d0b5cce853a6d9cd41af281427272376b2a96a21d5a9020a557c53fb7fb` |
| `core/documento.py` | `0ae72d0255f8f5eabbe88147f788d5bcfe9ce7a0d6f0de4ee0859daa5d0a85e9` |
| `core/estrategias.py` | `e46a4c078af1b37cabe79770481aee7f51f2384674afd5e17b27a13cbc8b04be` |
| `core/extrato.py` | `1b41612f65b86809d61ed63690cc7feb9e01d826947611bb2f52519ef9dc871f` |
| `core/extrator_pdf.py` | `bbfb0481a779d8dfd3a16bbcccd08c542c32112164ffef31216ad7f9dd706e13` |
| `core/models.py` | `12315f3f20bf24b5d7d42606c912d88bf9796c60d4553d4da4d526a9a6e787d3` |
| `core/rubricas.py` | `bbba4e9ef9311195ba90ac8579e143d3b0afe9923c7526b30a9cf670964cfe80` |
| `core/utils.py` | `f0f2e49d0f0ad59daed14ba63a39ee6aad49f9ce1bb1bffa341e05fa73c32cc1` |

### Agente sob guardrails (agent)

| Artefato | SHA-256 |
|---|---|
| `agent/__init__.py` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `agent/agente.py` | `ee04dc65cb3647534be69a1efa5335f14b1a27100ce9f02e8d2c35810585f1ab` |
| `agent/cache.py` | `badee5b1b2cd7d02129dcc1693bd1622b06398f2e041cb75a00b1d0f31e63748` |
| `agent/classificacao.py` | `5ec2a55927a1d8ad871ecf1be2da197f0a0ec1eea135fa13bf675c928875d03b` |
| `agent/config.py` | `de94789fd2c79c4f67a5e27a483bf682d409c8ad7a98b0538000ab8fbdaa3140` |
| `agent/exibicao.py` | `d9db63887e3818ba580943370458ec271675c2c6bfc5928afa1255fb5974439d` |
| `agent/extracao.py` | `9a8b014827cd21cfab05044618aefcda635d6c4bc20c945570199cc874d0b1e4` |
| `agent/grafo.py` | `3416b0407f07b88b522b18ad79d00ef05ce070a5355f5d765f0fa74be6fc003f` |
| `agent/ingestao.py` | `4c284457e4d77037524e4f1ef0b8992b22ee2fa314fff8911c5c5dd7a0aaec8c` |
| `agent/ocr.py` | `96c5bf1ded98eb637094ac0faa1225144d2bf41728e287807729baa12311e287` |
| `agent/prompts.py` | `b3110d726d3abbca1ec97eb984ea7c401119a5861440e2c712d672a2fef49cd3` |
| `agent/provider.py` | `11dd56d09b43ab5489fbb73e0d5e2bd894d3f532140fa9cc9081f704f19e329c` |
| `agent/telemetria.py` | `508639cfed573988d84f3af75b88b54c37d22e0c5e2bbad5ecece7d464ff5753` |

### Guardrails

| Artefato | SHA-256 |
|---|---|
| `guardrails/__init__.py` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `guardrails/conteudo.py` | `66a7c0d5b957d86d48edec5a88146751c78a6d085cc1135a851d53ff7aa517fd` |
| `guardrails/pii.py` | `240a29fc98db36da3cc925d11c506b2b1e52075e889ff9e51fbb76585f6d52db` |
| `guardrails/validador_numerico.py` | `289afd816ee50768fb2b48100db62ec6582c49cddd74e9a2de23ae69a48dec81` |

### Geração de saídas (outputs)

| Artefato | SHA-256 |
|---|---|
| `outputs/__init__.py` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `outputs/planilha.py` | `7685fbcd47b73eaf1881b59beeded19d55a8e728a3956e95d0ef493f24d61214` |
| `outputs/proposta.py` | `171e1eeed4a05fc57bfdb9b904c3375f9b19edd9e2a0527a8c83702c6e0ea078` |
| `outputs/relatorio.py` | `b7d07116e2f850c565a3e21503a48b62e094d28d0c53cb28d6127e30ef03b10c` |

### Sidecar (fronteira HTTP local + persistência)

| Artefato | SHA-256 |
|---|---|
| `sidecar/__init__.py` | `0f55c31161b81aad9355fe5ad58fae8064defe1a7a7cfd238ed17e59073e5aad` |
| `sidecar/__main__.py` | `69a09e86fd31bf4f18019b0438e1a05d7db8141e945c8787b4325e00878a48d4` |
| `sidecar/app.py` | `d27f14b9546bb677e4c401038f746eb8e429c2ba491fdbc3807bcbcc998d3be4` |
| `sidecar/persistencia.py` | `f5361487e9c41b39c9fb4b306a5cf00c5a891fd67a06b7933fc7d61d8ca5eee1` |
| `sidecar/schemas.py` | `06949f2ab6ec2fcf7e16f09d686292e41c10907c52729ae55ce8f2dcc7ffcd2f` |
| `sidecar/security.py` | `1a6396f0e09140f6e0a599613071cb80ffe0508fc0c223241d1046993d68081b` |

### GUI clássica (gui — fallback)

| Artefato | SHA-256 |
|---|---|
| `gui/__init__.py` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `gui/app.py` | `f75c28d4742842dce03611acade3fc297a8521f14f221cab9f9db4ca324d9298` |

### GUI web (gui_web — Electron + React/TS + E2E)

| Artefato | SHA-256 |
|---|---|
| `gui_web/package.json` | `ac513159c6c9e33d371dd7ebf81dcf0d618e3408eaf01962b7aa99ae04c1d8f7` |
| `gui_web/index.html` | `65d438e190c6a2eb076894d03bc2690dc7bc842d8ee58691c81690fb64555d8d` |
| `gui_web/vite.config.ts` | `babedaf0e48959bea2faf692583ca7d63bd97739572284ca11c982c02c3816e3` |
| `gui_web/playwright.config.ts` | `1fc12157bfc5c21d51f9f2ab7f237108a550501b387bcd7c3033081bb741ea29` |
| `gui_web/electron/main.ts` | `1d2d60903f9fc0d63deb5187a5cf787716a6bd97721644838b9c3359066fb188` |
| `gui_web/electron/preload.ts` | `5cb5a51e824ac66aab14954e07cea4f6467974450dec415dafd05eb7ea5ce4d4` |
| `gui_web/src/App.tsx` | `58fcc7c3591e1139ad2688247c4a209994defb3c6f3deec183d13a65c7a60d77` |
| `gui_web/src/main.tsx` | `908e625518862c14c075ebc584fd1e40a6390b908206f685f3d7d865361c887c` |
| `gui_web/src/vite-env.d.ts` | `7c5a44be51ba4f0e4c8e32b0d5cfee9657fca6092b1f6e00d99736b26f22b94f` |
| `gui_web/src/components/CampoMoeda.tsx` | `a90bbe9a2dc1031299e31fa5f1c8fb5776484ab1fff4523be8cf43093b691d42` |
| `gui_web/src/components/CampoPercent.tsx` | `08a26bc4de92e4c6b6c7eba76c1a2f3e8bc3e62aef591c57ac0a7ef2c0bb83c3` |
| `gui_web/src/components/Icones.tsx` | `3c3e67df79b4a9f7323fe7589d2cf2fda34adf5323884e0b17c83b0a121d949d` |
| `gui_web/src/hf/client.ts` | `3e21662b84230046ced48e390dc0498788758a2fb4800af9fa65fd96a3670764` |
| `gui_web/src/hf/contract.ts` | `221c95d534638b111f61ea35e968fe5b93e20cdc10b8ddf45944dbb84ae8b582` |
| `gui_web/src/hf/useAnalise.ts` | `96cceff3430ea2f151383a6820902c9b3cf7bf66a50a2c0c977fb9fec608782e` |
| `gui_web/src/lib/arquivo.ts` | `b62cdb2e2d5b0bd70b1b9bd76b89d71fa02bd0d7490ea1a55d578d85dec7076c` |
| `gui_web/src/lib/format.ts` | `ea47dd440e7437ab296b0dc772d347c5dd7a689de4bf8ea1a8a49363116e9b2e` |
| `gui_web/src/lib/orcamento.ts` | `d5d082919ec4c408e7670250fe45ec638246d24883e23ef2df1b27b44b5988ba` |
| `gui_web/src/screens/Analise.tsx` | `2975630873fe0b2a17152b9d6052c17fd2e2e854bb008bd910ba28e7858a4d34` |
| `gui_web/src/screens/Carta.tsx` | `dfe11757da61e7fdf8a3c8c2274d8d0acf2c64f467a4cf7882eeb710725d42c9` |
| `gui_web/src/screens/Contrato.tsx` | `cf23c4e472a948158aa08ccbf91b7ccd6c309cac78ddda3e2328234838158583` |
| `gui_web/src/screens/Dividas.tsx` | `e5531e9041823be6d1a8a211266700e169f43825ba6b84c51ac1bcc15c838216` |
| `gui_web/src/screens/ImportarCsv.tsx` | `31734694a30201343ec71f0b66abdc480505871fce173708609d77b6e29601d3` |
| `gui_web/src/screens/Perfil.tsx` | `84a95595c2f30f84a0a6240ed77a17e9f53b6d3ae8e3dc1f3885670760e99834` |
| `gui_web/src/screens/Planilha.tsx` | `965d08b87e801b2901b1a7adf3587a86bce465fc8629ff1b6fa5f7b29591b4e3` |
| `gui_web/src/screens/VisaoGeral.tsx` | `cabe2c56e24693bddf2c9b53c20d6644ffa7c8c083d29b509257a30fa7dc3140` |
| `gui_web/src/styles.css` | `a9451e60e48e1b099c8ad9651eb05f459776130a7c4dd3a13da922548afe9502` |
| `gui_web/e2e/app.spec.ts` | `7374f669f5269d857369c9b8d22f3fd0de11504ac7e0f231e70a4f05151acb2b` |
| `gui_web/e2e/empacotado.spec.ts` | `796fc419a4448589a8b0a8ce3cd09ddde6643ea238f869bec9fc3dc42207cbba` |
| `gui_web/e2e/fixtures/comprovante-escaneado.png` | `e40b7dfe7b9b5523b1cf05a65b9743dd200b9bad6a207b4fbdd74df9eab41a8e` |
| `gui_web/e2e/fixtures/contrato-escaneado.png` | `abca12f61ce1fef2323c5f818d9c076ed23c0b4506e3de1cb9b5965002d36747` |

### Entrypoint, build e empacotamento

| Artefato | SHA-256 |
|---|---|
| `main.py` | `a979656c100f6d12b02e0d625f6197a6b792769aab885f328631faedc019a448` |
| `pyproject.toml` | `e8cde9b9f1fc4fb7fe201c9efb20e9c3c259fa9f49b06043471bcf0f8ae9704e` |
| `SidecarHF.spec` | `f201b4e2dbf1a9fb99a518957fba6db8edeba6e84b6e2bfec3eb7410a40974b6` |
| `scripts/sidecar_entry.py` | `c63c53e315cd42423f06832d120ab66c4ff66965bf038bfcf3012d638acae3d9` |
| `scripts/preparar_ocr.py` | `fb305d8a58947eed84070e898cce647e2abebd7d7aec409a2ad0899cbb96b0a5` |

### Harness de testes (tests)

| Artefato | SHA-256 |
|---|---|
| `tests/__init__.py` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `tests/conftest.py` | `aa1980d6c11b623adeba6e5a6b65d525d0e576ec4e3e6227563c6675adf8f656` |
| `tests/test_cache.py` | `27216c7195ea3ff989da4fcbc761acb06ea71c73e8b15bb4f0256017f4ad224a` |
| `tests/test_classificacao.py` | `f64ad3f69b586907a1e34444968f707635f1219f279c0ffb75abc3dd58ea7018` |
| `tests/test_config.py` | `b2b932b36ab59afb057769bc2ba97efb6f2b5804e0ef740604899a57ed79a5b6` |
| `tests/test_conteudo.py` | `73984521960a262548bf5386b41124ce557c032a9340ffa2d13bf96d7f7fd39d` |
| `tests/test_core.py` | `8c63e0aa5e7f2145ad4e42f36db9bb5f56b5dde237346a92fdb0b57c2785bc23` |
| `tests/test_degradacao.py` | `31778f22a9b167434edfdfaadd442f758190ef4be85ae7c5a23cf3b727c2239a` |
| `tests/test_documento.py` | `c42135d3237092f8a574cd400c133b61fdcb915fa0ffb5db68e87372c55839bd` |
| `tests/test_exibicao.py` | `a6a649d7e47622ba4ab9480d7d83b6534118a78d326f57ee61b9fcb749811ee0` |
| `tests/test_extracao.py` | `2590f4506f6c82a0443c5b02760e28b4274cac6a506e814a8b7a39e67d6ab970` |
| `tests/test_extrato.py` | `508c78dffe5add2f1de180dfcf504de81c3d75b5051b79e57380838b3dbb2cce` |
| `tests/test_extrator_pdf.py` | `98fb17d065fd263b19e8843646e0df6eb4fa9a640f63937150f8e1d525c359da` |
| `tests/test_grounding.py` | `210c334ff521fb47871a6c8e9e0a55176c5c20921e2ff830903593271e61a231` |
| `tests/test_injecao.py` | `fba9b077cce3796fae23df4eb2619e34adbf841e01044d132620f651a494a856` |
| `tests/test_ocr.py` | `5e81263c566c95624838b5fbbbbca77fa860b3d4fafde64f73dbd1640142186a` |
| `tests/test_ollama_real.py` | `f916616d2aa130ff87a1cd91ac92ca8c56cf56c6b501d2ffea1bd1f3d9952fc0` |
| `tests/test_orcamento.py` | `608b5e0afa36db0d573f23663971157dce42d7130fac3ebe42591f260f7c6fbe` |
| `tests/test_outputs.py` | `a60018215ca39cbd410720cfb547176459e67ef31b44c98f944b27c11a18da2e` |
| `tests/test_persistencia.py` | `99744e1ac8b910b535392dacfd54713ebf36f181ef4c88f23b04dfad5befeae0` |
| `tests/test_pii.py` | `9e0b052158b1f1af14f89c80bfcedc4be4c33d0e49bd40cebb29790d235c9dbc` |
| `tests/test_propriedades.py` | `a3dceb73aa42df79840b9b44925e8c2d3a736faf9df697146e82029035dcb358` |
| `tests/test_providers.py` | `35d28d15b8c3b1dc9bffe388c019ebbd4144a7a680feddd00061b00945e1e941` |
| `tests/test_recuperacao.py` | `94129e9a3fcf8bca1d180bcc61ea23010107ffeedc15659db961565f666d15c9` |
| `tests/test_rubricas.py` | `74dc0e22bd922ec6d890bf203d6063b7c78176e247bb562a500a31d9d3f4545f` |
| `tests/test_sidecar.py` | `32fb30f71d73c0825e3c0924b6c14d2e5f811659e8cccd90dffe8efbf55c09b7` |
| `tests/test_telemetria.py` | `f5750e70fe314e187d25f464ea0c5871c2a807e518821cb1a41a4ec1580bdbe8` |
| `tests/test_validacao_texto.py` | `4c9482f0ea98fc9af46a3ea89d4f2262eda6a207e54da9d5ed322ecebdfce3e7` |

## Binários empacotados (rebuild do T-1406, nesta data)

| Artefato | SHA-256 | Tamanho |
|---|---|---|
| `gui_web/release/Helper Financeiro Setup 2.7.0.exe` | `42507be3aaae62878b7980ad96c12d99beee38921be86b403f2c5ac3aec9f6fc` | 329,6 MB |
| `dist/sidecar-hf/sidecar-hf.exe` (dentro do instalador) | `33d7ef07d2c77eaddafd2835db969eeb9aa217b2ea991addf1750abfb6bb177b` | 37,4 MB |

> Os binários não são versionados no git (`dist/` e `gui_web/release/` no
> `.gitignore`); os hashes identificam o build desta ata (PyInstaller 6.x +
> electron-builder, sem code signing — ver riscos residuais em
> `SEGURANCA-SHELL.md`). O instalador saltou de ~172 MB (v2.6) para **329,6 MB**:
> os modelos ONNX PP-OCRv6 medium (det+rec, ~132 MB) e o onnxruntime/cv2/shapely
> agora viajam embarcados (REQ-NF-006 — zero download em execução). Rebuild em
> outra máquina/data produz hash diferente — **rode `scripts/preparar_ocr.py`
> antes** para materializar os modelos na venv, e regenere com
> `uv run --group build pyinstaller SidecarHF.spec --noconfirm` e `npm run dist`,
> registrando em nova ata. Validado pelo smoke `e2e/empacotado.spec.ts`
> (2 passed: o app real abre e exibe o diagnóstico, e **OCRiza de verdade** um
> documento escaneado a partir do binário congelado, offline; banco isolado por
> `HF_DB_PATH`).

## Estado do harness no congelamento

```text
309 passed, 1 skipped (teste opt-in do OCR real, HF_OCR_REAL=1) — suíte offline (Gate A)
Cobertura: 95,8% (piso de 90% no CI)
E2E Playwright: 16 passed (14 cenários no app dev + 2 smoke do pacote real:
diagnóstico + OCR de verdade), banco isolado por HF_DB_PATH
Gate Front (CI): ESLint + tsc + build Vite verdes
Observação: flake intermitente conhecido no cenário E2E "planilha" logo após
builds pesados (2 falhas em 8 rodadas; passa na reexecução; nunca produziu
valor errado) — acompanhar; sem correção às cegas.
```

Gerado automaticamente. Recalcule com `Get-FileHash -Algorithm SHA256`
(PowerShell) ou `sha256sum` (Linux/macOS) para verificar integridade.
