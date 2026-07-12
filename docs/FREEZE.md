# FREEZE — Ata de Congelamento v2.8.0

- **Data:** 2026-07-11
- **Versão da Constituição:** 2.0.0
- **Escopo congelado:** ciclo **v2.8** (ADR-0016): milestones **M16** e **M17**.
  **M16 — o app vira um COFRE:** login local com senha mestra + **TOTP**
  (RFC 6238) e 10 códigos de recuperação de uso único — **sem backdoor** (perdeu
  senha E códigos ⇒ dados irrecuperáveis por design, decisão do mantenedor);
  envelope **DEK/KEK** com **Argon2id** (`sidecar/auth.py`, nonce novo por
  cifragem, anti-replay do TOTP, atraso exponencial anti-brute-force); banco
  **SQLCipher** (`sqlcipher3-wheels`, raw key `x'<hex>'`) com **migração
  atômica** do `dados.db` legado no cadastro; sessão do cofre no sidecar
  (`sidecar/sessao.py`: lock único, auto-lock preguiçoso por
  `HF_AUTO_LOCK_MIN`) com `423 Locked` em **todas** as 27 rotas de negócio e
  `429 + Retry-After` no brute-force; GUI com onboarding **forçado** em 4
  passos (senha → QR/segredo TOTP → códigos exibidos UMA vez → 1º login real),
  desbloqueio com 401 genérico e overlay de auto-lock que não desmonta telas
  (REQ-SEC-005/006/007). QR gerado no sidecar com `qrcode[png]`/pypng puro
  (sem Pillow). **M17 — a LLM deixa de exigir ferramenta de terceiros:**
  runtime **`llama-server` (llama.cpp) embarcado** — build **Vulkan** oficial
  `b9966` com fallback de CPU embutido, gerido pelo sidecar
  (`sidecar/runtime_llm.py`: start sob demanda, loopback + porta efêmera,
  health com timeout p/ carga do modelo, `terminate→wait→kill`; `-ngl 99`
  padrão, override `HF_LLAMA_FLAGS`); **gestor de modelos**
  (`sidecar/gestor_modelos.py`): catálogo curado com **URL + SHA-256 travados
  no código** (Phi-3.5 Mini / Qwen2.5-1.5B / Granite 3.1 2B, todos com licença
  comercial), download com retomada e **hash obrigatório** antes de promover —
  única exceção de rede, **opt-in** (REQ-NF-007) — ou `.gguf` local; tela
  "Configuração da IA" (7ª aba). Precedência preservada (ADR-0002):
  `HF_BASE_URL` definido ⇒ servidor do usuário (Ollama/LM Studio); ausente ⇒
  runtime embarcado; indisponível ⇒ degrada P8 com motivo
  (REQ-F-027/028). Empacotamento: `scripts/preparar_llama.py` materializa o
  binário verificado (SHA-256 conferido contra o digest da API do GitHub) em
  `resources/llama/` (gitignored) → *extraResource* ao lado do exe do sidecar;
  `SidecarHF.spec` embarca sqlcipher3/argon2/pyotp/qrcode/pypng. Schema
  relacional inalterado (`VERSAO_ESQUEMA` 1); o banco INTEIRO passou a ser
  cifrado. Recursos do ciclo existem só na GUI web; tkinter permanece fallback
  congelado do v2.3 (`PARIDADE.md` §7) e NÃO tem cofre — o fallback não abre
  banco cifrado.
- **Regra:** qualquer alteração nos artefatos abaixo exige nova ADR,
  incremento de versão e nova ata.
- **Atas anteriores:** v2.0.0..v2.2.0 (2026-07-04, M1..M6), v2.3.0..v2.5.0
  (2026-07-07, M7..M12), v2.6.0 (2026-07-08, M13) e v2.7.0 (2026-07-08,
  M14+M15) — substituídas por esta.

> A lista congelada cobre todo o código de primeira parte (incluindo os
> artefatos novos do ciclo: `sidecar/auth.py`, `sidecar/sessao.py`,
> `sidecar/runtime_llm.py`, `sidecar/gestor_modelos.py`,
> `scripts/preparar_llama.py`, as telas do cofre e da IA e os E2E novos) e o
> harness. `docs/INDEX.md` (mapa navegável) e este `FREEZE.md` não se
> auto-hasheiam. Os arquivos `docs/PaddleOCR-VL.en.md` e
> `docs/paddleocr_vl_sft.md` são material de estudo de terceiros,
> **não versionados** e fora do escopo congelado.

## Checksums SHA-256 dos artefatos

### Documentos SDD e guia de IDE

| Artefato | SHA-256 |
|---|---|
| `docs/CONSTITUTION.md` | `77b11451303e2d378a631ec420f95802e7c4799a21762fac7704f93f2fffefec` |
| `docs/PRD.md` | `7a0d731b4bf65918084da884ed70655afe0fc3d4595d268aa5c5f7c0840d7ff3` |
| `docs/SPEC.md` | `800dd0b1801494f9a4120735ee0c5214ca913e4cc961ca347873b13f35e3a831` |
| `docs/PLAN.md` | `2757a8602fd19da86bed0d8634e378c0ed0b1e44c410ac416df656a64a6d0024` |
| `docs/TASKS.md` | `12ac92b9d1b6e454404b7f8104a509554f9076df79ad0e2f0db7019e58486282` |
| `docs/HARNESS.md` | `c061c4f2cfdc011e9dcfbaeb2341fd5686edc5a5d6b4663160e6bb3339eafecf` |
| `docs/AGENT.md` | `742de4d9d5bd1a16768f64bbf4dbcb74a39a5b01fa7d9d1e6995ea6952c0e842` |
| `docs/REVISAO-SEGURANCA.md` | `ec6923ac3abbe8e4235db73c8b1472558be1336d6d4d6b621b3cb91512ed4a2b` |
| `docs/SEGURANCA-SHELL.md` | `e59baca3c3023bb318dd231bce712fd6612524794fa9c5054f592ce772c19fd6` |
| `docs/PARIDADE.md` | `390cc2ef3b473f4e31819f998b81070991e10aa61f13b4ec44834bfdd92ef6de` |
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
| `docs/adr/ADR-0016-cofre-local-mfa-e-llm-embarcada.md` | `3039f7fc88ede7bbdcf4b3c1d68e132d38ebdd6ab5d75d8d7f2f9027858c7d30` |

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
| `agent/classificacao.py` | `807b6299d2bdf85e5acef447012ca691b39761926ab502a0258c6cc1f26dc743` |
| `agent/config.py` | `de94789fd2c79c4f67a5e27a483bf682d409c8ad7a98b0538000ab8fbdaa3140` |
| `agent/exibicao.py` | `d9db63887e3818ba580943370458ec271675c2c6bfc5928afa1255fb5974439d` |
| `agent/extracao.py` | `ce5c117409612e69b6cf2c4d0e3cb9f3569d64ad6ac7b2358539616ba536f552` |
| `agent/grafo.py` | `3416b0407f07b88b522b18ad79d00ef05ce070a5355f5d765f0fa74be6fc003f` |
| `agent/ingestao.py` | `4c284457e4d77037524e4f1ef0b8992b22ee2fa314fff8911c5c5dd7a0aaec8c` |
| `agent/ocr.py` | `96c5bf1ded98eb637094ac0faa1225144d2bf41728e287807729baa12311e287` |
| `agent/prompts.py` | `b3110d726d3abbca1ec97eb984ea7c401119a5861440e2c712d672a2fef49cd3` |
| `agent/provider.py` | `7924bc2c03af86f05e85dbe6806e33c9de6e95af2adcaa65a34d6fe3f425cac6` |
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

### Sidecar (fronteira HTTP local + persistência + cofre + LLM)

| Artefato | SHA-256 |
|---|---|
| `sidecar/__init__.py` | `0f55c31161b81aad9355fe5ad58fae8064defe1a7a7cfd238ed17e59073e5aad` |
| `sidecar/__main__.py` | `69a09e86fd31bf4f18019b0438e1a05d7db8141e945c8787b4325e00878a48d4` |
| `sidecar/app.py` | `5d7220139655fcedf743df93ed5691d64f6f63c9ab3b34b357b356a4e30dd6d2` |
| `sidecar/auth.py` | `87b7161f642806e056024fd1fa70fe3bc5a43868c864637d1034752fea070244` |
| `sidecar/gestor_modelos.py` | `1dada8ee89ecd58ab3d381bd6ec73ad17641ca2bb24bd497b408a7dea591dbad` |
| `sidecar/persistencia.py` | `c6f9f178f2033759482ebbe5d4fe48eaecdec4319b3fc47f52d8e915ffb78e02` |
| `sidecar/runtime_llm.py` | `769731c91ff65bdaa0ab94881b4de628ad72296984227b8ac3af142692d406f4` |
| `sidecar/schemas.py` | `8c14b37d7056597a73b32580b485355fd540e32e05f72cdda820371f50acbb16` |
| `sidecar/security.py` | `1a6396f0e09140f6e0a599613071cb80ffe0508fc0c223241d1046993d68081b` |
| `sidecar/sessao.py` | `da4adb7e8c60606bc608d5693ec8ffe156d5a9ab8a884d2aca0446e3ce5d4ae1` |

### GUI clássica (gui — fallback)

| Artefato | SHA-256 |
|---|---|
| `gui/__init__.py` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `gui/app.py` | `f75c28d4742842dce03611acade3fc297a8521f14f221cab9f9db4ca324d9298` |

### GUI web (gui_web — Electron + React/TS + E2E)

| Artefato | SHA-256 |
|---|---|
| `gui_web/e2e/app.spec.ts` | `7d0445abf96a3027a42000b0b5ef23f65fea5ccad2135cb79ad7e685a02ef865` |
| `gui_web/e2e/cofre-helpers.ts` | `4ad0dd2ea683076b530cde95bf5724748b12f66d7c5a430f6ba2862d6ccbd3d0` |
| `gui_web/e2e/cofre.spec.ts` | `600b7b7e1f520726ca151946816435b8e512d39c01d3262b3bf014d27c47d2a6` |
| `gui_web/e2e/configuracao-ia.spec.ts` | `bef5560ca0e2ec9e0ffdcf5b4218edfd161a93a1d5b9142fccef9bf30f4240c0` |
| `gui_web/e2e/empacotado-llm.spec.ts` | `634e91e333a4c37269c17ec98baa61dcd4878097650565044eb694c8b54cd93d` |
| `gui_web/e2e/empacotado.spec.ts` | `829dbd5b9092859c8c97ea4613ab723e78b50afeb1bc47900603543da8a703be` |
| `gui_web/e2e/fixtures/comprovante-escaneado.png` | `e40b7dfe7b9b5523b1cf05a65b9743dd200b9bad6a207b4fbdd74df9eab41a8e` |
| `gui_web/e2e/fixtures/contrato-escaneado.png` | `abca12f61ce1fef2323c5f818d9c076ed23c0b4506e3de1cb9b5965002d36747` |
| `gui_web/electron/main.ts` | `9233878035638d8b623aebbbb48bb293df57333380b95a336c989f307552db94` |
| `gui_web/electron/preload.ts` | `c78a0c0b185631100335db687cd99fc8e542d924325322c3bc7b0f5de6a605fa` |
| `gui_web/index.html` | `65d438e190c6a2eb076894d03bc2690dc7bc842d8ee58691c81690fb64555d8d` |
| `gui_web/package.json` | `3afd011937c5ccc34cbeaa21839957bd9e7d88443012ff031ca72d02a3405465` |
| `gui_web/playwright.config.ts` | `1fc12157bfc5c21d51f9f2ab7f237108a550501b387bcd7c3033081bb741ea29` |
| `gui_web/src/App.tsx` | `1b9a7de77f16bd75a6eb76d1cd5e36d5b9e0d3bb6ff30cda033888e03920ecff` |
| `gui_web/src/components/CampoMoeda.tsx` | `a90bbe9a2dc1031299e31fa5f1c8fb5776484ab1fff4523be8cf43093b691d42` |
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
| `pyproject.toml` | `5dad71312aa037bc4e65ad1b52822915f9284aa94118e597c9be9d7ac726d619` |
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
| `tests/test_classificacao.py` | `bc21a4a3049344388d16462b9975d5fc5c548eefdc3411294eb0633c963b6653` |
| `tests/test_config.py` | `b2b932b36ab59afb057769bc2ba97efb6f2b5804e0ef740604899a57ed79a5b6` |
| `tests/test_conteudo.py` | `73984521960a262548bf5386b41124ce557c032a9340ffa2d13bf96d7f7fd39d` |
| `tests/test_core.py` | `8c63e0aa5e7f2145ad4e42f36db9bb5f56b5dde237346a92fdb0b57c2785bc23` |
| `tests/test_degradacao.py` | `921fc14ef77b75527efdd3e048c874a60069de68549ed6d9e331da2010a8eda2` |
| `tests/test_documento.py` | `c42135d3237092f8a574cd400c133b61fdcb915fa0ffb5db68e87372c55839bd` |
| `tests/test_exibicao.py` | `a6a649d7e47622ba4ab9480d7d83b6534118a78d326f57ee61b9fcb749811ee0` |
| `tests/test_extracao.py` | `e3393954d5ea82f68731fb7b295377ad947f6f74bca4fc1aa0dae534f60bd495` |
| `tests/test_extrato.py` | `508c78dffe5add2f1de180dfcf504de81c3d75b5051b79e57380838b3dbb2cce` |
| `tests/test_extrator_pdf.py` | `98fb17d065fd263b19e8843646e0df6eb4fa9a640f63937150f8e1d525c359da` |
| `tests/test_gestor_modelos.py` | `a9105ae8faf33997ab2a1caa78c128d131110b3c33df85d5436d725c1cdc967b` |
| `tests/test_grounding.py` | `210c334ff521fb47871a6c8e9e0a55176c5c20921e2ff830903593271e61a231` |
| `tests/test_injecao.py` | `fba9b077cce3796fae23df4eb2619e34adbf841e01044d132620f651a494a856` |
| `tests/test_ocr.py` | `5e81263c566c95624838b5fbbbbca77fa860b3d4fafde64f73dbd1640142186a` |
| `tests/test_ollama_real.py` | `5899fe7af504afca16c943a4510c20683f2d2fbb58e382148a34b385fc3206ee` |
| `tests/test_orcamento.py` | `608b5e0afa36db0d573f23663971157dce42d7130fac3ebe42591f260f7c6fbe` |
| `tests/test_outputs.py` | `a60018215ca39cbd410720cfb547176459e67ef31b44c98f944b27c11a18da2e` |
| `tests/test_persistencia.py` | `42ca9a631475eba59e0160c4e606eb27d1ece3ed1282b996e86302b5e96b18c6` |
| `tests/test_pii.py` | `9e0b052158b1f1af14f89c80bfcedc4be4c33d0e49bd40cebb29790d235c9dbc` |
| `tests/test_preparar_llama.py` | `f55fbe488449bcfbac1261a5d886c3e3153571406c9f6f478e2fac6393c691a9` |
| `tests/test_propriedades.py` | `a3dceb73aa42df79840b9b44925e8c2d3a736faf9df697146e82029035dcb358` |
| `tests/test_providers.py` | `af4d8df65c614b9295dd4e65523fe421d42c01240b14e40d950fc74aeb598b5f` |
| `tests/test_recuperacao.py` | `94129e9a3fcf8bca1d180bcc61ea23010107ffeedc15659db961565f666d15c9` |
| `tests/test_rubricas.py` | `74dc0e22bd922ec6d890bf203d6063b7c78176e247bb562a500a31d9d3f4545f` |
| `tests/test_runtime_llm.py` | `84e4a6c85f7c72fb834d4ee5a6b0e9e85093c2753ab596eb64ea48b6ffd7dd95` |
| `tests/test_sessao.py` | `89b37e1c3bac18ab1d25470ab8b720fe2a9ca6a782a4ab1efb42efdbf99abd07` |
| `tests/test_sidecar.py` | `fcd49e29136c9cfb8d959a87852d80948b788d33422115400dadf16299100998` |
| `tests/test_sidecar_llm.py` | `dd29cf98b32784bb246504aafd1e28b2e88c23a4aa68bf0ef641564f7325fe39` |
| `tests/test_telemetria.py` | `f5750e70fe314e187d25f464ea0c5871c2a807e518821cb1a41a4ec1580bdbe8` |
| `tests/test_validacao_texto.py` | `4c9482f0ea98fc9af46a3ea89d4f2262eda6a207e54da9d5ed322ecebdfce3e7` |

## Binários empacotados (build oficial do T-1704, nesta data)

| Artefato | SHA-256 | Tamanho |
|---|---|---|
| `gui_web/release/Helper Financeiro Setup 2.8.0.exe` | `399765da099d49a14f8fb8f8ce7418a01e1c72e75520259365101ad09e66e294` | 350,0 MB |
| `dist/sidecar-hf/sidecar-hf.exe` (dentro do instalador) | `33817a41aa0648ebddde6a31afd9ccdc2eb9572e0f1d891694afa25dbd09acc6` | 37,8 MB |

> Os binários não são versionados no git (`dist/`, `gui_web/release/` e
> `resources/llama/` no `.gitignore`); os hashes identificam o build desta ata
> (PyInstaller 6.x + electron-builder NSIS, sem code signing — ver riscos
> residuais em `SEGURANCA-SHELL.md`). O instalador foi de 329,6 MB (v2.7) para
> **350,0 MB**: o `llama-server` (llama.cpp `b9966`, build **Vulkan** com
> backends de CPU embutidos, ~130 MB descompactados) viaja como
> *extraResource* em `resources/sidecar-hf/resources/llama/`, e o sidecar
> ganhou sqlcipher3/argon2/pyotp/qrcode/pypng. **Nenhum modelo GGUF é
> embarcado**: o download é opt-in no 1º uso (REQ-NF-007), com SHA-256
> obrigatório do catálogo. Rebuild em outra máquina/data produz hash diferente
> — rode **`scripts/preparar_llama.py` E `scripts/preparar_ocr.py` antes**, e
> regenere com `uv run --group build pyinstaller SidecarHF.spec --noconfirm` e
> `npm run dist`, registrando em nova ata. Validado pelos smokes
> `e2e/empacotado.spec.ts` + `e2e/empacotado-llm.spec.ts` (4 passed contra o
> pacote desta ata: onboarding real do cofre no exe congelado, diagnóstico,
> OCR de verdade e binário llama resolvido + download/ativação com catálogo
> fake) e, no T-1703, pela análise ponta a ponta no pacote com o
> Qwen2.5-1.5B do catálogo (`modo: completo`, zero guardrails violados).

## Estado do harness no congelamento

```text
425 passed, 2 skipped (opt-in reais: HF_OCR_REAL=1 e HF_LLAMA_REAL=1) — suíte offline (Gate A)
Cobertura: 95,8% (piso de 90% no CI)
E2E Playwright: 18 passed no app dev + 4 passed contra o pacote NSIS real
(cofre + diagnóstico + OCR + runtime llama embarcado), estado isolado por
HF_DB_PATH/HF_AUTH_PATH/HF_MODELOS_DIR
Gate Front (CI): ESLint + tsc + build Vite verdes
Observações: (1) flake intermitente conhecido nos cenários E2E pesados
("planilha" no v2.7; "recuperação" do cofre neste ciclo, 1 falha em 3 rodadas)
logo após builds pesados — passa na reexecução, nunca produziu valor errado;
sem correção às cegas. (2) Risco residual: kill DURO do sidecar (fora do
shutdown limpo do lifespan) pode deixar um llama-server.exe órfão — observado
no T-1704 após o smoke do T-1703 (segurava o diretório de release e fez o
1º electron-builder falhar com EBUSY); mitigação atual: encerrar o processo;
candidato a job object/atexit em ciclo futuro. (3) Modelos com menos de ~1B
de parâmetros tendem a degradar por REQ-LLM-002:SCHEMA (P8 correto) — o
catálogo curado (1.5B–3.8B) satisfaz o schema.
```

Gerado automaticamente. Recalcule com `Get-FileHash -Algorithm SHA256`
(PowerShell) ou `sha256sum` (Linux/macOS) para verificar integridade.
