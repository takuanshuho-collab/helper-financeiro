# FREEZE — Ata de Congelamento v2.2.0

- **Data:** 2026-07-04
- **Versão da Constituição:** 2.0.0
- **Escopo congelado:** Milestones **M1 + M1.5 + M2 + M2.5 + M3 + M4 + M5 +
  M6** — agente sob guardrails (StateGraph/LangGraph), providers reais com
  structured output, extração Code-First com confirmação humana, integração
  GUI/.docx, empacotamento (`HelperFinanceiro.exe`), **perfil como orçamento
  doméstico detalhado** (ADR-0008) e **revisão de UI/UX** (validação visual,
  aba rolável, ergonomia da lista, tema consistente).
- **Regra:** qualquer alteração nos artefatos abaixo exige nova ADR,
  incremento de versão e nova ata.
- **Atas anteriores:** v2.0.0 (2026-07-01, escopo M1) e v2.1.0 (2026-07-04,
  escopo M1..M4) — ambas substituídas por esta.

> **Ampliação de escopo nesta ata.** A partir do ciclo v2.2 o produto voltou
> a evoluir na camada determinística e na GUI (M5/M6). Por isso a lista de
> artefatos congelados foi estendida para incluir **todo o código de primeira
> parte** (`core`, `outputs`, `gui`, além de `agent`, `guardrails`,
> `contracts`) e **o harness completo** (`tests/`) — não apenas a camada de
> IA congelada na v2.1.0. `docs/INDEX.md` (mapa navegável) e este próprio
> `FREEZE.md` não se auto-hasheiam.

## Checksums SHA-256 dos artefatos

### Documentos SDD e guia de IDE

| Artefato | SHA-256 |
|---|---|
| `docs/CONSTITUTION.md` | `4c544fdcc94a353ae6e1c9917dcfeb49185d2e6b6fa2ecbf8c06f169702c16d1` |
| `docs/PRD.md` | `53f4a6bff80fa88f8c1fc7d9813bc830b6dbd4480be7740566121d680e386629` |
| `docs/SPEC.md` | `01fe06b92f453b52b317fdf092e382cce8138f3164d9013ad018518cee15d073` |
| `docs/PLAN.md` | `58b6762428ccc081e3950d3c1d0d562f979cbf8f5601066544cb674cb740df02` |
| `docs/TASKS.md` | `ec4f2e93fff64d954bfbe2601c45c1c070a48f85b4c732c82a6cbb82126e3355` |
| `docs/HARNESS.md` | `bf24ae5ef1173907ddd39da7acae4cd062bdfad4ea5a029f0537129888257b8c` |
| `docs/AGENT.md` | `742de4d9d5bd1a16768f64bbf4dbcb74a39a5b01fa7d9d1e6995ea6952c0e842` |
| `docs/REVISAO-SEGURANCA.md` | `ec6923ac3abbe8e4235db73c8b1472558be1336d6d4d6b621b3cb91512ed4a2b` |
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
| `core/models.py` | `12315f3f20bf24b5d7d42606c912d88bf9796c60d4553d4da4d526a9a6e787d3` |
| `core/utils.py` | `f0f2e49d0f0ad59daed14ba63a39ee6aad49f9ce1bb1bffa341e05fa73c32cc1` |
| `core/diagnostico.py` | `545b9f2adf8a2259949f9f19f402272b258fb36f32bbb29b0f0f8e84f4546823` |
| `core/estrategias.py` | `9be0e450ea786030d2825d82563df262c60b27c7660b4ce166518345f258d2bb` |
| `core/extrator_pdf.py` | `4168d9a640507ee8e1f479fd1b9af84a38a8812ef7f928d11c814e8895e8175a` |

### Agente sob guardrails (agent)

| Artefato | SHA-256 |
|---|---|
| `agent/__init__.py` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `agent/prompts.py` | `4e2539c71e99a98eeb3373870ed70493397ddaa19977f7bda669500d0b8473ab` |
| `agent/agente.py` | `ee04dc65cb3647534be69a1efa5335f14b1a27100ce9f02e8d2c35810585f1ab` |
| `agent/grafo.py` | `72c97c617a92c4eeee7a7e96597d620ff9a3cce15efd1dcec7d37dc3fc5bb8c7` |
| `agent/extracao.py` | `5881404e69971f0212848123c12545df3b0d13129815118862935d322ec6535d` |
| `agent/ingestao.py` | `4c284457e4d77037524e4f1ef0b8992b22ee2fa314fff8911c5c5dd7a0aaec8c` |
| `agent/exibicao.py` | `c5a66ebfd1d2fd5e0347fa1c177e95e4efacc9962e4a2c8e41d67c79a04680d7` |
| `agent/provider.py` | `0a7584bd1835be4a4b5d862223cf4a0f7fda38db18911063cb01e9cb8aa0c627` |
| `agent/config.py` | `a86186d4b5b9282e549d795e21eca4cc1db318b19cd078888b85a807d97c74a3` |
| `agent/cache.py` | `badee5b1b2cd7d02129dcc1693bd1622b06398f2e041cb75a00b1d0f31e63748` |

### Guardrails

| Artefato | SHA-256 |
|---|---|
| `guardrails/__init__.py` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `guardrails/pii.py` | `240a29fc98db36da3cc925d11c506b2b1e52075e889ff9e51fbb76585f6d52db` |
| `guardrails/validador_numerico.py` | `26b39add7f0651f546bc250b32ef73f6b33edd2d99030cc984fce18139a3cdf9` |
| `guardrails/conteudo.py` | `66a7c0d5b957d86d48edec5a88146751c78a6d085cc1135a851d53ff7aa517fd` |

### Geração de saídas (outputs)

| Artefato | SHA-256 |
|---|---|
| `outputs/__init__.py` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `outputs/relatorio.py` | `b7d07116e2f850c565a3e21503a48b62e094d28d0c53cb28d6127e30ef03b10c` |
| `outputs/planilha.py` | `c30444330f9fa34a3d0e7772315640165a95dd32977f970ff0e05fa83bc5a03b` |
| `outputs/proposta.py` | `b218b4ee48fc17a29c2ea5fb2d47aba23579115c789185837ed244398d89a5f7` |

### Interface gráfica (gui)

| Artefato | SHA-256 |
|---|---|
| `gui/__init__.py` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `gui/app.py` | `f75c28d4742842dce03611acade3fc297a8521f14f221cab9f9db4ca324d9298` |

### Harness de testes (tests)

| Artefato | SHA-256 |
|---|---|
| `tests/__init__.py` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `tests/conftest.py` | `aa1980d6c11b623adeba6e5a6b65d525d0e576ec4e3e6227563c6675adf8f656` |
| `tests/test_cache.py` | `da1d14239a269956b4843317c3d094e7bd0442a3ad3a7d04838e0f697bd1aff6` |
| `tests/test_config.py` | `9b9a04d4e91ef1fb4cedff41a8c943c7302ebbd0da68fe8ca621436adfd5ba11` |
| `tests/test_conteudo.py` | `73984521960a262548bf5386b41124ce557c032a9340ffa2d13bf96d7f7fd39d` |
| `tests/test_core.py` | `212ddad840cbfd456cfa7127809f0c65bae81b03c3f64810b61e8ec1f8af0d2c` |
| `tests/test_degradacao.py` | `31778f22a9b167434edfdfaadd442f758190ef4be85ae7c5a23cf3b727c2239a` |
| `tests/test_exibicao.py` | `69601235e0a681934165003051882d4a4b41f9ceaf6b3ca6db11325b605d25c9` |
| `tests/test_extracao.py` | `81abb7833f001d2390644d15655d16bef81179bdeb428544c5056aa4cce20c92` |
| `tests/test_grounding.py` | `c4e635306d9b875029f158eddfdaa44c13791a1ef8067621322d64a3b7d29a2f` |
| `tests/test_injecao.py` | `fba9b077cce3796fae23df4eb2619e34adbf841e01044d132620f651a494a856` |
| `tests/test_ollama_real.py` | `f916616d2aa130ff87a1cd91ac92ca8c56cf56c6b501d2ffea1bd1f3d9952fc0` |
| `tests/test_orcamento.py` | `608b5e0afa36db0d573f23663971157dce42d7130fac3ebe42591f260f7c6fbe` |
| `tests/test_outputs.py` | `0811e5c15b47533b30c28d0bc6b44a606e5f96168f4aaa796a7658afe3fd1905` |
| `tests/test_pii.py` | `a98bd4a75523ee0395a84520124b8066e9958bb05b6f9b4a4ea35200fe720ddd` |
| `tests/test_propriedades.py` | `a3dceb73aa42df79840b9b44925e8c2d3a736faf9df697146e82029035dcb358` |
| `tests/test_providers.py` | `c6a7d18db1134eee5b9fb8711199a9c21fe73ca2a93f778347e148bdbf6961aa` |
| `tests/test_recuperacao.py` | `8e5ff3284ce83e41861c506b11c858a0f7cee7454a164c52347eeea53fb4180a` |
| `tests/test_validacao_texto.py` | `4c9482f0ea98fc9af46a3ea89d4f2262eda6a207e54da9d5ed322ecebdfce3e7` |

## Binário empacotado (rebuild do T-401)

| Artefato | SHA-256 | Tamanho |
|---|---|---|
| `dist/HelperFinanceiro.exe` | `f3e76d53ac66904271f9961092254b90eadbbbf1519e487221c3c12e4b385dd9` | 93,8 MB |

> O `.exe` não é versionado no git (`dist/` está no `.gitignore`); o hash acima
> identifica o binário gerado nesta ata (PyInstaller 6.21, Python 3.14,
> `--onefile --windowed`). Rebuild em outra máquina/data produz hash diferente
> — regenere com o comando do README e registre em nova ata. Validado abrindo
> a GUI (processo vivo por 12 s sem crash).

## Estado do harness no congelamento

```text
104 passed (suíte offline — Gate A)
107 passed no total com Ollama ativo (inclui 3 testes de integração real)
Cobertura: 95,4% (piso de 90% no CI)
```

Gerado automaticamente. Recalcule com `Get-FileHash -Algorithm SHA256`
(PowerShell) ou `sha256sum` (Linux/macOS) para verificar integridade.
