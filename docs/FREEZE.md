# FREEZE — Ata de Congelamento v2.9.0

- **Data:** 2026-07-13
- **Versão da Constituição:** 2.0.0
- **Escopo congelado:** ciclo **v2.9** (ADR-0017): milestones **M18** e **M19**
  — ciclo de **saúde de código**, sem nenhum recurso novo e com zero mudança
  de comportamento visível (restrições §E: zero regressão, sem migração de
  schema/quebra do cofre). **M18 — auditoria:** 5 varreduras somente-leitura
  (segurança, concorrência/recursos, fronteira TS↔Python, higiene,
  silenciosos/dívida de teste) consolidadas em `docs/RELATORIO-AUDITORIA.md`
  (34 achados: 1 crítico, 5 altos, 14 médios, 14 baixos) com portão humano em
  2026-07-12. **M19 — correção:** 26 achados corrigidos (T-1901..T-1910),
  cada um com teste de regressão que falharia antes da mudança. Destaques:
  **Job Object do Windows** (`sidecar/job_windows.py`) garante que o
  `llama-server` morre junto do sidecar em QUALQUER caminho de morte,
  inclusive kill duro — fecha o risco residual nº 2 da ata v2.8 (provado no
  smoke desta ata contra o exe congelado); disciplina de locks do runtime LLM
  (corrida da troca de modelo eliminada, boot fora do lock,
  `RuntimeLLMInvalidado` + retry no chokepoint); TTL e descarte de PII dos
  jobs em memória no bloqueio do cofre; blindagem da DEK na cadeia de
  exceções do SQLCipher (exceção limpa criada no `except` e levantada fora —
  `raise ... from None` não bastaria); shutdown gracioso do Electron
  (`POST /encerrar` + prazo de 3 s); handlers de validação/500 sempre JSON;
  validação `ge=0` nos campos monetários de entrada; E2E sem esperas fixas
  (poll da condição real); remoção do ramo RAG morto (`agent/ingestao.py` =
  truncagem pura; ADR-0007 **revogada**) e das deps `llama-index-*` órfãs
  (−43 pacotes na árvore, incl. `nltk` — PYSEC-2026-597 deixou de se
  aplicar); cobertura passou a medir o `sidecar/` e subiu de 95,8% para
  **96,6%**. Sem correção neste ciclo (registrados no relatório): C-10,
  C-15 (code signing), C-16 (bump Electron), C-23, C-28/C-29 (complexidade),
  C-35.
- **Regra:** qualquer alteração nos artefatos abaixo exige nova ADR,
  incremento de versão e nova ata.
- **Atas anteriores:** v2.0.0..v2.2.0 (2026-07-04, M1..M6), v2.3.0..v2.5.0
  (2026-07-07, M7..M12), v2.6.0 (2026-07-08, M13), v2.7.0 (2026-07-08,
  M14+M15) e v2.8.0 (2026-07-11, M16+M17) — substituídas por esta.

> A lista congelada cobre todo o código de primeira parte (incluindo os
> artefatos novos do ciclo: `sidecar/job_windows.py`, `sidecar/arquivos.py`,
> `tests/test_job_windows.py`, `docs/RELATORIO-AUDITORIA.md` e a ADR-0017) e
> o harness. `docs/INDEX.md` (mapa navegável) e este `FREEZE.md` não se
> auto-hasheiam. Os arquivos `docs/PaddleOCR-VL.en.md`,
> `docs/paddleocr_vl_sft.md` (material de estudo de terceiros) e
> `docs/EXPERIMENTO-PADDLEOCR-VL-FASE0.md` (experimento fora de ciclo,
> veredito "manter RapidOCR") são **não versionados** e fora do escopo
> congelado.

## Checksums SHA-256 dos artefatos

### Documentos SDD e guia de IDE

| Artefato | SHA-256 |
|---|---|
| `docs/CONSTITUTION.md` | `77b11451303e2d378a631ec420f95802e7c4799a21762fac7704f93f2fffefec` |
| `docs/PRD.md` | `7a0d731b4bf65918084da884ed70655afe0fc3d4595d268aa5c5f7c0840d7ff3` |
| `docs/SPEC.md` | `800dd0b1801494f9a4120735ee0c5214ca913e4cc961ca347873b13f35e3a831` |
| `docs/PLAN.md` | `e61a988b03683dbd66076924d59384917d59420c5e743d7d9b0f253e0590156f` |
| `docs/TASKS.md` | `21400168d3ae923d9c45c3a7bdd1cdccc0f9246f8e0acaeda86c40b4f3d79569` |
| `docs/HARNESS.md` | `a07111ff4bcffe23b303fc9e641729d8707d1b31023848a7d92bcfbf9e2b292a` |
| `docs/AGENT.md` | `742de4d9d5bd1a16768f64bbf4dbcb74a39a5b01fa7d9d1e6995ea6952c0e842` |
| `docs/REVISAO-SEGURANCA.md` | `ec6923ac3abbe8e4235db73c8b1472558be1336d6d4d6b621b3cb91512ed4a2b` |
| `docs/SEGURANCA-SHELL.md` | `e59baca3c3023bb318dd231bce712fd6612524794fa9c5054f592ce772c19fd6` |
| `docs/PARIDADE.md` | `390cc2ef3b473f4e31819f998b81070991e10aa61f13b4ec44834bfdd92ef6de` |
| `docs/RELATORIO-AUDITORIA.md` | `ad88bc02c01fc86384c61f21c05c75fffbbed3c0eda9c6abdbe2d151e8653446` |
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
| `agent/agente.py` | `ee04dc65cb3647534be69a1efa5335f14b1a27100ce9f02e8d2c35810585f1ab` |
| `agent/cache.py` | `badee5b1b2cd7d02129dcc1693bd1622b06398f2e041cb75a00b1d0f31e63748` |
| `agent/classificacao.py` | `1e811e51ea848474d75092ed08e4a2cf79cebb93afe5088bde1192f3c07d05db` |
| `agent/config.py` | `de94789fd2c79c4f67a5e27a483bf682d409c8ad7a98b0538000ab8fbdaa3140` |
| `agent/exibicao.py` | `d9db63887e3818ba580943370458ec271675c2c6bfc5928afa1255fb5974439d` |
| `agent/extracao.py` | `340c1f5d43214656a0cc9d2cf1ad5ead9672d35c2d69b3c686f8c2f7fd94c5f6` |
| `agent/grafo.py` | `3629fc51dd3993fcd67de69c58ba7868b018c464215c4d31392e1213ef40e68b` |
| `agent/ingestao.py` | `5a80bf93dd28b792d39622b8dfb3ba02582b424cb804086a02b19f46430fe3fd` |
| `agent/ocr.py` | `96c5bf1ded98eb637094ac0faa1225144d2bf41728e287807729baa12311e287` |
| `agent/prompts.py` | `b3110d726d3abbca1ec97eb984ea7c401119a5861440e2c712d672a2fef49cd3` |
| `agent/provider.py` | `c0e0b000b8de5d8fc67cee11ef6eb99d39ff780f494b3ad8f1a014fb8e3d2a55` |
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
| `outputs/planilha.py` | `7685fbcd47b73eaf1881b59beeded19d55a8e728a3956e95d0ef493f24d61214` |
| `outputs/proposta.py` | `171e1eeed4a05fc57bfdb9b904c3375f9b19edd9e2a0527a8c83702c6e0ea078` |
| `outputs/relatorio.py` | `b7d07116e2f850c565a3e21503a48b62e094d28d0c53cb28d6127e30ef03b10c` |

### Sidecar (fronteira HTTP local + persistência + cofre + LLM)

| Artefato | SHA-256 |
|---|---|
| `sidecar/__init__.py` | `0f55c31161b81aad9355fe5ad58fae8064defe1a7a7cfd238ed17e59073e5aad` |
| `sidecar/__main__.py` | `7e57e7ff71a25020a25ec5c715fd58f6dafcff633121f6db49d83f14cff7b7c0` |
| `sidecar/app.py` | `40b9407d28b533d3e8457a9dd2a43c52f358e5157eaf509babf504fbd005bd31` |
| `sidecar/arquivos.py` | `8e314b83e677a024d1b6367717826e71d8a78bde9c486ca480855c883ba54aa0` |
| `sidecar/auth.py` | `d3df8f125a75620b400efdd77de65f65520b186661cb5d1d354e4a167157c9dd` |
| `sidecar/gestor_modelos.py` | `1755050802295082cb6b4f3727acabb9a7299c0468256ef34fdd63d3ae6f7557` |
| `sidecar/job_windows.py` | `5dc3f805f35cfcbc1b81357f4f0e1ca2830021c168f74fa31d55d56ef8436f95` |
| `sidecar/persistencia.py` | `ae2bab9e30d699225f446a80e1eaa0b0f8a61dc2fda4dbacaba7853b06524478` |
| `sidecar/runtime_llm.py` | `bd1da093272a913dd0f43e087b6bb665a1efe7b879f43ad49550541029d309de` |
| `sidecar/schemas.py` | `27bad92e479fa80877ddd9364dd1d9496cc6c568916a661b7a10d6231e79464b` |
| `sidecar/security.py` | `1a6396f0e09140f6e0a599613071cb80ffe0508fc0c223241d1046993d68081b` |
| `sidecar/sessao.py` | `997856ce343c94ff1eaa80de7bcf9ec92b28f37e722c5397d9cc6554ddb794e7` |

### GUI clássica (gui — fallback)

| Artefato | SHA-256 |
|---|---|
| `gui/__init__.py` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `gui/app.py` | `f75c28d4742842dce03611acade3fc297a8521f14f221cab9f9db4ca324d9298` |

### GUI web (gui_web — Electron + React/TS + E2E)

| Artefato | SHA-256 |
|---|---|
| `gui_web/e2e/app.spec.ts` | `56603bb03ffc8ef6e87664c386bb95ceef97f3438e39a332d91f97cf40608a29` |
| `gui_web/e2e/cofre-helpers.ts` | `765a7a6605d7b0105da9a53b390afa0d11bb5c8ebe6be82060c9d27ea6a5607e` |
| `gui_web/e2e/cofre.spec.ts` | `600b7b7e1f520726ca151946816435b8e512d39c01d3262b3bf014d27c47d2a6` |
| `gui_web/e2e/configuracao-ia.spec.ts` | `bef5560ca0e2ec9e0ffdcf5b4218edfd161a93a1d5b9142fccef9bf30f4240c0` |
| `gui_web/e2e/empacotado-llm.spec.ts` | `634e91e333a4c37269c17ec98baa61dcd4878097650565044eb694c8b54cd93d` |
| `gui_web/e2e/empacotado.spec.ts` | `829dbd5b9092859c8c97ea4613ab723e78b50afeb1bc47900603543da8a703be` |
| `gui_web/e2e/fixtures/comprovante-escaneado.png` | `e40b7dfe7b9b5523b1cf05a65b9743dd200b9bad6a207b4fbdd74df9eab41a8e` |
| `gui_web/e2e/fixtures/contrato-escaneado.png` | `abca12f61ce1fef2323c5f818d9c076ed23c0b4506e3de1cb9b5965002d36747` |
| `gui_web/electron/main.ts` | `e7bd041d1794afe19006b50d1c4eab204401ee785040aef4fbd63111fec421f8` |
| `gui_web/electron/preload.ts` | `c78a0c0b185631100335db687cd99fc8e542d924325322c3bc7b0f5de6a605fa` |
| `gui_web/eslint.config.mjs` | `5f6f18f557d1fb301b6f3437d02a47ff372d9ced55d23582ff63c3003213c155` |
| `gui_web/index.html` | `65d438e190c6a2eb076894d03bc2690dc7bc842d8ee58691c81690fb64555d8d` |
| `gui_web/package.json` | `eb247d90e6dd5a028a982331909fab4b8bb369217c5ebb8807fdc1242b98d2c0` |
| `gui_web/playwright.config.ts` | `1fc12157bfc5c21d51f9f2ab7f237108a550501b387bcd7c3033081bb741ea29` |
| `gui_web/src/App.tsx` | `1b9a7de77f16bd75a6eb76d1cd5e36d5b9e0d3bb6ff30cda033888e03920ecff` |
| `gui_web/src/components/CampoMoeda.tsx` | `564687d9facbc452b9d15d8c5d919121a98d1d323a3a1b9111a459526286cc4a` |
| `gui_web/src/components/CampoPercent.tsx` | `08a26bc4de92e4c6b6c7eba76c1a2f3e8bc3e62aef591c57ac0a7ef2c0bb83c3` |
| `gui_web/src/components/Icones.tsx` | `3312534d790dd48a45b084441b7edd7813a2d61dee18567577b829051206c677` |
| `gui_web/src/hf/client.ts` | `b6ae6c8b2ef7f76d0676ccb12f91e5eb7581812bf0c78959de222421e84b821e` |
| `gui_web/src/hf/contract.ts` | `37ac21af615d80538c74946bc4ecce60f41ae8061d6d38a70c1680c4efe3e612` |
| `gui_web/src/hf/useAnalise.ts` | `96cceff3430ea2f151383a6820902c9b3cf7bf66a50a2c0c977fb9fec608782e` |
| `gui_web/src/hf/useContadorEspera.ts` | `d5b212be39fbbbd3d681d92c6c8d368a10d464759f8ef4acc40ee68ad5693485` |
| `gui_web/src/lib/arquivo.ts` | `b62cdb2e2d5b0bd70b1b9bd76b89d71fa02bd0d7490ea1a55d578d85dec7076c` |
| `gui_web/src/lib/format.ts` | `ea47dd440e7437ab296b0dc772d347c5dd7a689de4bf8ea1a8a49363116e9b2e` |
| `gui_web/src/lib/orcamento.ts` | `d5d082919ec4c408e7670250fe45ec638246d24883e23ef2df1b27b44b5988ba` |
| `gui_web/src/main.tsx` | `908e625518862c14c075ebc584fd1e40a6390b908206f685f3d7d865361c887c` |
| `gui_web/src/screens/Analise.tsx` | `2975630873fe0b2a17152b9d6052c17fd2e2e854bb008bd910ba28e7858a4d34` |
| `gui_web/src/screens/Carta.tsx` | `dfe11757da61e7fdf8a3c8c2274d8d0acf2c64f467a4cf7882eeb710725d42c9` |
| `gui_web/src/screens/ConfiguracaoIa.tsx` | `94556e271c52c8d744b83191201f8394f0634806fa53103a41249c7b8b2efb95` |
| `gui_web/src/screens/Contrato.tsx` | `cf23c4e472a948158aa08ccbf91b7ccd6c309cac78ddda3e2328234838158583` |
| `gui_web/src/screens/Desbloqueio.tsx` | `31afaf550a9d593c45594639964bd81b20fc077935bbc5b40bc1aa1c4aa888c9` |
| `gui_web/src/screens/Dividas.tsx` | `e5531e9041823be6d1a8a211266700e169f43825ba6b84c51ac1bcc15c838216` |
| `gui_web/src/screens/ImportarCsv.tsx` | `31734694a30201343ec71f0b66abdc480505871fce173708609d77b6e29601d3` |
| `gui_web/src/screens/Onboarding.tsx` | `77b0749b56782f327ca14621a484e73058944a0c0842a3e968acd067a163f140` |
| `gui_web/src/screens/Perfil.tsx` | `84a95595c2f30f84a0a6240ed77a17e9f53b6d3ae8e3dc1f3885670760e99834` |
| `gui_web/src/screens/Planilha.tsx` | `965d08b87e801b2901b1a7adf3587a86bce465fc8629ff1b6fa5f7b29591b4e3` |
| `gui_web/src/screens/VisaoGeral.tsx` | `cabe2c56e24693bddf2c9b53c20d6644ffa7c8c083d29b509257a30fa7dc3140` |
| `gui_web/src/styles.css` | `2a9be11ea184f7dfc95120e3bd1d65c6d9109bfff4800a6688cb73d8d70733db` |
| `gui_web/src/vite-env.d.ts` | `ff1194308ddcb162fb87e9fbcb0bbcff6657fcdec7ef8aa52d3339c36a62f28c` |
| `gui_web/vite.config.ts` | `babedaf0e48959bea2faf692583ca7d63bd97739572284ca11c982c02c3816e3` |

### Entrypoint, build e empacotamento

| Artefato | SHA-256 |
|---|---|
| `main.py` | `a979656c100f6d12b02e0d625f6197a6b792769aab885f328631faedc019a448` |
| `pyproject.toml` | `ad5a0fc0018faabf2c1095f9e5bebb2d9a5f906d2cc795596abd5d012d7f629b` |
| `SidecarHF.spec` | `cc3471a70cb6ebf50da89c6eb8820fde375645fedcbe40785ff8b187561c3cfa` |
| `scripts/sidecar_entry.py` | `c63c53e315cd42423f06832d120ab66c4ff66965bf038bfcf3012d638acae3d9` |
| `scripts/preparar_ocr.py` | `fb305d8a58947eed84070e898cce647e2abebd7d7aec409a2ad0899cbb96b0a5` |
| `scripts/preparar_llama.py` | `79f4e1ddc70006a94dc89d9cd75dd40347e3e2ef9004468f0ab01c9e08547abb` |

### Harness de testes (tests)

| Artefato | SHA-256 |
|---|---|
| `tests/__init__.py` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `tests/conftest.py` | `aa1980d6c11b623adeba6e5a6b65d525d0e576ec4e3e6227563c6675adf8f656` |
| `tests/test_auth.py` | `4032712de76e12dae65fbc68aef342cea5f149c295f33af097da5802b36ea7ce` |
| `tests/test_cache.py` | `27216c7195ea3ff989da4fcbc761acb06ea71c73e8b15bb4f0256017f4ad224a` |
| `tests/test_classificacao.py` | `c520363fef4c48476a866df0c1be34c9fa82915d15b509894b985772bd9abc28` |
| `tests/test_config.py` | `b2b932b36ab59afb057769bc2ba97efb6f2b5804e0ef740604899a57ed79a5b6` |
| `tests/test_conteudo.py` | `73984521960a262548bf5386b41124ce557c032a9340ffa2d13bf96d7f7fd39d` |
| `tests/test_core.py` | `8c63e0aa5e7f2145ad4e42f36db9bb5f56b5dde237346a92fdb0b57c2785bc23` |
| `tests/test_degradacao.py` | `921fc14ef77b75527efdd3e048c874a60069de68549ed6d9e331da2010a8eda2` |
| `tests/test_documento.py` | `c42135d3237092f8a574cd400c133b61fdcb915fa0ffb5db68e87372c55839bd` |
| `tests/test_exibicao.py` | `a6a649d7e47622ba4ab9480d7d83b6534118a78d326f57ee61b9fcb749811ee0` |
| `tests/test_extracao.py` | `aef01a76ebd8a2ce31f607172386a928b651c13e8169c3558ae98507e366d5ea` |
| `tests/test_extrato.py` | `508c78dffe5add2f1de180dfcf504de81c3d75b5051b79e57380838b3dbb2cce` |
| `tests/test_extrator_pdf.py` | `c9d3dde5cfd9c1e8b97d7602b17fef10761e3d7c4b4b8c1827abb01ee4b06c36` |
| `tests/test_gestor_modelos.py` | `d9dd68a0f2e7aaa49384c6818af8e1992ea652f92491c23f1fe725fddefcb7da` |
| `tests/test_grounding.py` | `210c334ff521fb47871a6c8e9e0a55176c5c20921e2ff830903593271e61a231` |
| `tests/test_injecao.py` | `fba9b077cce3796fae23df4eb2619e34adbf841e01044d132620f651a494a856` |
| `tests/test_job_windows.py` | `7caf7a4a9383f1f08b62f206124c10acbed1e6df86583de813c31ea9dcd032bf` |
| `tests/test_ocr.py` | `5e81263c566c95624838b5fbbbbca77fa860b3d4fafde64f73dbd1640142186a` |
| `tests/test_ollama_real.py` | `5899fe7af504afca16c943a4510c20683f2d2fbb58e382148a34b385fc3206ee` |
| `tests/test_orcamento.py` | `608b5e0afa36db0d573f23663971157dce42d7130fac3ebe42591f260f7c6fbe` |
| `tests/test_outputs.py` | `a60018215ca39cbd410720cfb547176459e67ef31b44c98f944b27c11a18da2e` |
| `tests/test_persistencia.py` | `5ee110cb17ba0630cd4976762c1814fa92800bf3d6bf90c5872b145ddb92cf0f` |
| `tests/test_pii.py` | `9e0b052158b1f1af14f89c80bfcedc4be4c33d0e49bd40cebb29790d235c9dbc` |
| `tests/test_preparar_llama.py` | `f55fbe488449bcfbac1261a5d886c3e3153571406c9f6f478e2fac6393c691a9` |
| `tests/test_propriedades.py` | `a3dceb73aa42df79840b9b44925e8c2d3a736faf9df697146e82029035dcb358` |
| `tests/test_providers.py` | `af4d8df65c614b9295dd4e65523fe421d42c01240b14e40d950fc74aeb598b5f` |
| `tests/test_recuperacao.py` | `94129e9a3fcf8bca1d180bcc61ea23010107ffeedc15659db961565f666d15c9` |
| `tests/test_rubricas.py` | `74dc0e22bd922ec6d890bf203d6063b7c78176e247bb562a500a31d9d3f4545f` |
| `tests/test_runtime_llm.py` | `4bb6ac86c120aef376495571fcde98943b1b4d0bf0610f2fa547b5820300c180` |
| `tests/test_sessao.py` | `b3e658562bc6b5a2d2dbb928c9fe714ce203b4439e61034c8bd81824771ba0e5` |
| `tests/test_sidecar.py` | `3ee347a00b2960672b7e035fc9bb4efff4357834be8f068295ce1f7bacadb958` |
| `tests/test_sidecar_llm.py` | `a745551db84dc598337469a97ba83e5f7cadb4e5f3164d846085405f0d058d0b` |
| `tests/test_telemetria.py` | `f5750e70fe314e187d25f464ea0c5871c2a807e518821cb1a41a4ec1580bdbe8` |
| `tests/test_validacao_texto.py` | `4c9482f0ea98fc9af46a3ea89d4f2262eda6a207e54da9d5ed322ecebdfce3e7` |

## Binários empacotados (build oficial do T-1911, nesta data)

| Artefato | SHA-256 | Tamanho |
|---|---|---|
| `gui_web/release/Helper Financeiro Setup 2.9.0.exe` | `1e00a181240895c3b193db9ae6b9a2b89f80213226a69e85920c1bb49622e84e` | 328,5 MB |
| `dist/sidecar-hf/sidecar-hf.exe` (dentro do instalador) | `d5613bd412b4af37b577069dc42fb1982ae71be401635712b1df3132abc25829` | 22,6 MB |

> Os binários não são versionados no git (`dist/`, `gui_web/release/` e
> `resources/llama/` no `.gitignore`); os hashes identificam o build desta ata
> (PyInstaller 6.x + electron-builder NSIS, sem code signing — registrado como
> C-15 para ciclo futuro). O instalador **encolheu** de 350,0 MB (v2.8) para
> **328,5 MB** e o sidecar congelado de 37,8 MB para **22,6 MB**: a remoção
> das deps `llama-index-*` órfãs (T-1911) tirou pandas/sqlalchemy/nltk e
> outros 40 pacotes do freeze. **Nenhum modelo GGUF é embarcado**: o download
> é opt-in no 1º uso (REQ-NF-007), com SHA-256 obrigatório do catálogo.
> Rebuild em outra máquina/data produz hash diferente — rode
> **`scripts/preparar_llama.py` E `scripts/preparar_ocr.py` antes**, e
> regenere com `uv run --group build pyinstaller SidecarHF.spec --noconfirm` e
> `npm run dist`, registrando em nova ata. Validado pelos smokes
> `e2e/empacotado.spec.ts` + `e2e/empacotado-llm.spec.ts` (4 passed contra o
> pacote desta ata: onboarding real do cofre no exe congelado, diagnóstico,
> OCR de verdade e binário llama resolvido + download/ativação com catálogo
> fake) e pelo **smoke do órfão** exclusivo desta ata: sidecar congelado
> subiu um `llama-server` real (GGUF local), levou `TerminateProcess` (kill
> DURO, sem lifespan) e o filho **morreu junto** — Job Object confirmado no
> pacote real. O rebuild sobre release anterior não reproduziu o EBUSY do
> T-1704.

## Estado do harness no congelamento

```text
472 passed, 2 skipped (opt-in reais: HF_OCR_REAL=1 e HF_LLAMA_REAL=1) — suíte offline (Gate A)
Cobertura: 96,6% (piso de 90% no CI; desde o v2.9 a medição inclui sidecar/)
E2E Playwright: 18 passed no app dev + 4 passed contra o pacote NSIS real
(cofre + diagnóstico + OCR + runtime llama embarcado), estado isolado por
HF_DB_PATH/HF_AUTH_PATH/HF_MODELOS_DIR; esperas fixas eliminadas (T-1907)
Gate Front (CI): ESLint + tsc + build Vite verdes
Smoke extra do fechamento: Job Object mata o llama-server órfão no exe
congelado (kill duro comprovado com GGUF real)
Observações: (1) o flake intermitente dos cenários E2E pesados não se
manifestou nas rodadas do fechamento (a T-1907 removeu as esperas fixas que
o alimentavam); histórico mantido em atas anteriores. (2) O risco residual
do llama-server órfão (ata v2.8) está FECHADO pelo Job Object (T-1902).
(3) Modelos com menos de ~1B de parâmetros tendem a degradar por
REQ-LLM-002:SCHEMA (P8 correto) — o catálogo curado (1.5B–3.8B) satisfaz o
schema.
```

Gerado automaticamente. Recalcule com `Get-FileHash -Algorithm SHA256`
(PowerShell) ou `sha256sum` (Linux/macOS) para verificar integridade.
