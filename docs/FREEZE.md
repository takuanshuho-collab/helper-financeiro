# FREEZE — Ata de Congelamento v2.4.0

- **Data:** 2026-07-07
- **Versão da Constituição:** 2.0.0
- **Escopo congelado:** ciclo **v2.4** (ADR-0012): milestone **M11** —
  **orçamento detalhado com rubricas** (subcampos criados pelo usuário por
  campo do Perfil; roll-up determinístico no `core`: campo detalhado = soma,
  somente-leitura na GUI com selo "detalhado ▸"; tela **Planilha de
  orçamento** com grade editável; rubricas na aba "Orçamento detalhado" do
  `.xlsx`, subtotais `=SUM`) e **persistência local** do estado do usuário
  (SQLite `sqlite3` stdlib gerido pelo sidecar em
  `%APPDATA%\HelperFinanceiro\dados.db`, override `HF_DB_PATH`; hidratação
  no boot + auto-save; schema v1 versionado, coluna `mes` reservada ao
  histórico mensal futuro) — REQ-F-017/REQ-F-018. Recursos do ciclo existem
  só na GUI web; tkinter permanece fallback congelado do v2.3
  (`PARIDADE.md` §7).
- **Regra:** qualquer alteração nos artefatos abaixo exige nova ADR,
  incremento de versão e nova ata.
- **Atas anteriores:** v2.0.0..v2.2.0 (2026-07-04, M1..M6) e v2.3.0
  (2026-07-07, M7..M10) — substituídas por esta.

> A lista congelada cobre todo o código de primeira parte (incluindo os
> artefatos novos do ciclo: `core/rubricas.py`, `sidecar/persistencia.py`,
> `gui_web/src/screens/Planilha.tsx`, `gui_web/src/lib/orcamento.ts`) e o
> harness. `docs/INDEX.md` (mapa navegável) e este `FREEZE.md` não se
> auto-hasheiam.

## Checksums SHA-256 dos artefatos

### Documentos SDD e guia de IDE

| Artefato | SHA-256 |
|---|---|
| `docs/CONSTITUTION.md` | `77b11451303e2d378a631ec420f95802e7c4799a21762fac7704f93f2fffefec` |
| `docs/PRD.md` | `7a0d731b4bf65918084da884ed70655afe0fc3d4595d268aa5c5f7c0840d7ff3` |
| `docs/SPEC.md` | `38e38e382f4424f6199d703e936c3fa34d0b88cdcbd0f29dc7ddd76b381e25b3` |
| `docs/PLAN.md` | `c5929e1bee472e40a5ad3f9debbf043812e29acdfdba5281e144ffbe5728a4ac` |
| `docs/TASKS.md` | `036652a2f1b044983d7306370f80ce367cc5d4e2a92bab6cc73622583cafe078` |
| `docs/HARNESS.md` | `2e65c8e41436ed29e63dd68bddafcffe5cc6e8f92a5b9d6853e003212e7e4c38` |
| `docs/AGENT.md` | `742de4d9d5bd1a16768f64bbf4dbcb74a39a5b01fa7d9d1e6995ea6952c0e842` |
| `docs/REVISAO-SEGURANCA.md` | `ec6923ac3abbe8e4235db73c8b1472558be1336d6d4d6b621b3cb91512ed4a2b` |
| `docs/SEGURANCA-SHELL.md` | `e59baca3c3023bb318dd231bce712fd6612524794fa9c5054f592ce772c19fd6` |
| `docs/PARIDADE.md` | `743a56d11e33044d4c15558ba3f8a576c59e6209264a5db0f9dff99282497c2c` |
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

### Contratos de dados

| Artefato | SHA-256 |
|---|---|
| `contracts/__init__.py` | `ced36d4ee64fdaa773e73fdee4f286042b40607a731f0075a63e49c54e29511a` |
| `contracts/schemas.py` | `837414498553c939696248c2ab6734212799c892596efe4c9c7c208767d5996f` |

### Núcleo determinístico (core)

| Artefato | SHA-256 |
|---|---|
| `core/__init__.py` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `core/calculos.py` | `0c1d697451e4b7908c29178a4d5ab3ee43c282ead61a8cd19ccf02d6f4b57191` |
| `core/diagnostico.py` | `eca93d0b5cce853a6d9cd41af281427272376b2a96a21d5a9020a557c53fb7fb` |
| `core/estrategias.py` | `e46a4c078af1b37cabe79770481aee7f51f2384674afd5e17b27a13cbc8b04be` |
| `core/extrator_pdf.py` | `bbfb0481a779d8dfd3a16bbcccd08c542c32112164ffef31216ad7f9dd706e13` |
| `core/models.py` | `12315f3f20bf24b5d7d42606c912d88bf9796c60d4553d4da4d526a9a6e787d3` |
| `core/rubricas.py` | `7f8b3d2a4ffca5b500a99178e427323c4b7d0e94a27f7b4a8fe1d2ff9dd846fa` |
| `core/utils.py` | `f0f2e49d0f0ad59daed14ba63a39ee6aad49f9ce1bb1bffa341e05fa73c32cc1` |

### Agente sob guardrails (agent)

| Artefato | SHA-256 |
|---|---|
| `agent/__init__.py` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `agent/agente.py` | `ee04dc65cb3647534be69a1efa5335f14b1a27100ce9f02e8d2c35810585f1ab` |
| `agent/cache.py` | `badee5b1b2cd7d02129dcc1693bd1622b06398f2e041cb75a00b1d0f31e63748` |
| `agent/config.py` | `de94789fd2c79c4f67a5e27a483bf682d409c8ad7a98b0538000ab8fbdaa3140` |
| `agent/exibicao.py` | `d9db63887e3818ba580943370458ec271675c2c6bfc5928afa1255fb5974439d` |
| `agent/extracao.py` | `ff2291d3fec011c532e20cc48c11233ad3dc900a25b40d11fef51e49dd3ac456` |
| `agent/grafo.py` | `3416b0407f07b88b522b18ad79d00ef05ce070a5355f5d765f0fa74be6fc003f` |
| `agent/ingestao.py` | `4c284457e4d77037524e4f1ef0b8992b22ee2fa314fff8911c5c5dd7a0aaec8c` |
| `agent/prompts.py` | `83837a145202caafa70b77896d24546e34c9ffa6316b777077eb87fcd8447fef` |
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
| `outputs/planilha.py` | `c03f9ce9db0a8d360215996203833010f4920c63757c69dea06506c93bc4e110` |
| `outputs/proposta.py` | `171e1eeed4a05fc57bfdb9b904c3375f9b19edd9e2a0527a8c83702c6e0ea078` |
| `outputs/relatorio.py` | `b7d07116e2f850c565a3e21503a48b62e094d28d0c53cb28d6127e30ef03b10c` |

### Sidecar (fronteira HTTP local + persistência)

| Artefato | SHA-256 |
|---|---|
| `sidecar/__init__.py` | `0f55c31161b81aad9355fe5ad58fae8064defe1a7a7cfd238ed17e59073e5aad` |
| `sidecar/__main__.py` | `69a09e86fd31bf4f18019b0438e1a05d7db8141e945c8787b4325e00878a48d4` |
| `sidecar/app.py` | `cbb0039f5e6f078c52a1cbbdc6d67eae375648d62038302a7408840dacc5b399` |
| `sidecar/persistencia.py` | `79615b7693d1ad7b82cf3c485bf625c3619293749361c484f6edb38eea58e13c` |
| `sidecar/schemas.py` | `14be0da86e0cefc7f2ecf37099db2f49a9ed29b2cee9a032e4e8a95bd788664e` |
| `sidecar/security.py` | `1a6396f0e09140f6e0a599613071cb80ffe0508fc0c223241d1046993d68081b` |

### GUI clássica (gui — fallback)

| Artefato | SHA-256 |
|---|---|
| `gui/__init__.py` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `gui/app.py` | `f75c28d4742842dce03611acade3fc297a8521f14f221cab9f9db4ca324d9298` |

### GUI web (gui_web — Electron + React/TS + E2E)

| Artefato | SHA-256 |
|---|---|
| `gui_web/package.json` | `6d88d43d79afccbefb7b61973317f99359ea03e681b2d59aa833c3869d492336` |
| `gui_web/index.html` | `65d438e190c6a2eb076894d03bc2690dc7bc842d8ee58691c81690fb64555d8d` |
| `gui_web/vite.config.ts` | `babedaf0e48959bea2faf692583ca7d63bd97739572284ca11c982c02c3816e3` |
| `gui_web/playwright.config.ts` | `1fc12157bfc5c21d51f9f2ab7f237108a550501b387bcd7c3033081bb741ea29` |
| `gui_web/electron/main.ts` | `1d2d60903f9fc0d63deb5187a5cf787716a6bd97721644838b9c3359066fb188` |
| `gui_web/electron/preload.ts` | `5cb5a51e824ac66aab14954e07cea4f6467974450dec415dafd05eb7ea5ce4d4` |
| `gui_web/src/App.tsx` | `25052ccaf3c499f5a91dab82ec65ab74922aa8d0fd7e46cb7508b5e542db11a5` |
| `gui_web/src/components/CampoMoeda.tsx` | `a90bbe9a2dc1031299e31fa5f1c8fb5776484ab1fff4523be8cf43093b691d42` |
| `gui_web/src/components/CampoPercent.tsx` | `08a26bc4de92e4c6b6c7eba76c1a2f3e8bc3e62aef591c57ac0a7ef2c0bb83c3` |
| `gui_web/src/components/Icones.tsx` | `3c3e67df79b4a9f7323fe7589d2cf2fda34adf5323884e0b17c83b0a121d949d` |
| `gui_web/src/hf/client.ts` | `76f6a5ef7fe322842449691bc9308bc41a996d378f66eb2584408671702c60bb` |
| `gui_web/src/hf/contract.ts` | `0dc2085aa5803df1477ae2c7b3a13893a14308648a32916ac48c3e39f71dd168` |
| `gui_web/src/hf/useAnalise.ts` | `96cceff3430ea2f151383a6820902c9b3cf7bf66a50a2c0c977fb9fec608782e` |
| `gui_web/src/lib/format.ts` | `ea47dd440e7437ab296b0dc772d347c5dd7a689de4bf8ea1a8a49363116e9b2e` |
| `gui_web/src/lib/orcamento.ts` | `e383f6224a1d9f2fca12087d5a6694a5eeee42fbdf014b566e3ca5a60791902d` |
| `gui_web/src/main.tsx` | `908e625518862c14c075ebc584fd1e40a6390b908206f685f3d7d865361c887c` |
| `gui_web/src/screens/Analise.tsx` | `2975630873fe0b2a17152b9d6052c17fd2e2e854bb008bd910ba28e7858a4d34` |
| `gui_web/src/screens/Carta.tsx` | `dfe11757da61e7fdf8a3c8c2274d8d0acf2c64f467a4cf7882eeb710725d42c9` |
| `gui_web/src/screens/Contrato.tsx` | `c8c45722217fccbd1f2d854479b9ba6b39852d349bf58be91e22bc578e5150e8` |
| `gui_web/src/screens/Dividas.tsx` | `e5531e9041823be6d1a8a211266700e169f43825ba6b84c51ac1bcc15c838216` |
| `gui_web/src/screens/Perfil.tsx` | `84a95595c2f30f84a0a6240ed77a17e9f53b6d3ae8e3dc1f3885670760e99834` |
| `gui_web/src/screens/Planilha.tsx` | `e42f54c05028b5c7ae4980dfd7a125d7af82f981ef13fe59fc5ca6881b60df68` |
| `gui_web/src/screens/VisaoGeral.tsx` | `cabe2c56e24693bddf2c9b53c20d6644ffa7c8c083d29b509257a30fa7dc3140` |
| `gui_web/src/vite-env.d.ts` | `7c5a44be51ba4f0e4c8e32b0d5cfee9657fca6092b1f6e00d99736b26f22b94f` |
| `gui_web/src/styles.css` | `154db8c6296761611fd46d370ef8886708e59c54718dd5be41446d9bfbbfeb69` |
| `gui_web/e2e/app.spec.ts` | `429b663a27e88897b27a0fb928199248c56df5508bdb099d513073c53e6bc258` |
| `gui_web/e2e/empacotado.spec.ts` | `4f7fa119b141da58d21b1af5e1cee97ba60c2e78635a047102b8c0712bd43029` |

### Entrypoint, build e empacotamento

| Artefato | SHA-256 |
|---|---|
| `main.py` | `a979656c100f6d12b02e0d625f6197a6b792769aab885f328631faedc019a448` |
| `pyproject.toml` | `abfc31a267f263ec8350a7543e7913a0bc5ce9bf2996c19282f9665e3d0bcb79` |
| `SidecarHF.spec` | `481ffa76c037852d4323a21ee3f181de59ba899ee2bb6f6e965b2b1a34146b01` |
| `scripts/sidecar_entry.py` | `c63c53e315cd42423f06832d120ab66c4ff66965bf038bfcf3012d638acae3d9` |

### Harness de testes (tests)

| Artefato | SHA-256 |
|---|---|
| `tests/__init__.py` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `tests/conftest.py` | `aa1980d6c11b623adeba6e5a6b65d525d0e576ec4e3e6227563c6675adf8f656` |
| `tests/test_cache.py` | `27216c7195ea3ff989da4fcbc761acb06ea71c73e8b15bb4f0256017f4ad224a` |
| `tests/test_config.py` | `b2b932b36ab59afb057769bc2ba97efb6f2b5804e0ef740604899a57ed79a5b6` |
| `tests/test_conteudo.py` | `73984521960a262548bf5386b41124ce557c032a9340ffa2d13bf96d7f7fd39d` |
| `tests/test_core.py` | `8c63e0aa5e7f2145ad4e42f36db9bb5f56b5dde237346a92fdb0b57c2785bc23` |
| `tests/test_degradacao.py` | `31778f22a9b167434edfdfaadd442f758190ef4be85ae7c5a23cf3b727c2239a` |
| `tests/test_exibicao.py` | `a6a649d7e47622ba4ab9480d7d83b6534118a78d326f57ee61b9fcb749811ee0` |
| `tests/test_extracao.py` | `ef7fdab586289d52e0b1c5e69307766ce29f0bcee2914d907b14310855b532b6` |
| `tests/test_extrator_pdf.py` | `98fb17d065fd263b19e8843646e0df6eb4fa9a640f63937150f8e1d525c359da` |
| `tests/test_grounding.py` | `210c334ff521fb47871a6c8e9e0a55176c5c20921e2ff830903593271e61a231` |
| `tests/test_injecao.py` | `fba9b077cce3796fae23df4eb2619e34adbf841e01044d132620f651a494a856` |
| `tests/test_ollama_real.py` | `f916616d2aa130ff87a1cd91ac92ca8c56cf56c6b501d2ffea1bd1f3d9952fc0` |
| `tests/test_orcamento.py` | `608b5e0afa36db0d573f23663971157dce42d7130fac3ebe42591f260f7c6fbe` |
| `tests/test_outputs.py` | `009dc31f321d55083151d02f889715a4710bce747a06b2498256dd1e56afc6ff` |
| `tests/test_persistencia.py` | `70bedbbe91b1decdf696ca2aa3f2b7aff75c31b081d48189ebc30684b190c650` |
| `tests/test_pii.py` | `9e0b052158b1f1af14f89c80bfcedc4be4c33d0e49bd40cebb29790d235c9dbc` |
| `tests/test_propriedades.py` | `a3dceb73aa42df79840b9b44925e8c2d3a736faf9df697146e82029035dcb358` |
| `tests/test_providers.py` | `35d28d15b8c3b1dc9bffe388c019ebbd4144a7a680feddd00061b00945e1e941` |
| `tests/test_recuperacao.py` | `94129e9a3fcf8bca1d180bcc61ea23010107ffeedc15659db961565f666d15c9` |
| `tests/test_rubricas.py` | `f3986fef30b5f3b1e02be8ec752510a36f696941c733352abf889c9570c3dd06` |
| `tests/test_sidecar.py` | `487a48c55c16e72d6fd3aad7145ddbef90b5a1b830eeba48481689d3b0fdcca0` |
| `tests/test_telemetria.py` | `f5750e70fe314e187d25f464ea0c5871c2a807e518821cb1a41a4ec1580bdbe8` |
| `tests/test_validacao_texto.py` | `4c9482f0ea98fc9af46a3ea89d4f2262eda6a207e54da9d5ed322ecebdfce3e7` |

## Binários empacotados (rebuild do T-1106, nesta data)

| Artefato | SHA-256 | Tamanho |
|---|---|---|
| `gui_web/release/Helper Financeiro Setup 2.4.0.exe` | `45bb1de78dd01faa24782e1755ff7ef4303dd20b16fcc042c8906cd216cb006c` | 172,0 MB |
| `dist/sidecar-hf/sidecar-hf.exe` (dentro do instalador) | `e1b6b392961ecb65db6ddb8d248985beb0ae07aae3cc95ddb9bb7dd645e66349` | 35,0 MB |

> Os binários não são versionados no git (`dist/` e `gui_web/release/` no
> `.gitignore`); os hashes identificam o build desta ata (PyInstaller 6.x +
> electron-builder, sem code signing — ver riscos residuais em
> `SEGURANCA-SHELL.md`). Rebuild em outra máquina/data produz hash diferente —
> regenere com `uv run --group build pyinstaller SidecarHF.spec --noconfirm` e
> `npm run dist`, e registre em nova ata. Validado pelo smoke
> `e2e/empacotado.spec.ts` (app real abre e exibe o diagnóstico).

## Estado do harness no congelamento

```text
207 passed, 3 deselected (suíte offline — Gate A)
Cobertura: 96,4% (piso de 90% no CI)
E2E Playwright: 9 passed (8 cenários no app dev + 1 smoke do pacote real),
banco isolado por HF_DB_PATH
Gate Front (CI): ESLint + tsc + build Vite verdes
```

Gerado automaticamente. Recalcule com `Get-FileHash -Algorithm SHA256`
(PowerShell) ou `sha256sum` (Linux/macOS) para verificar integridade.
