# FREEZE — Ata de Congelamento v2.1.0

- **Data:** 2026-07-04
- **Versão da Constituição:** 2.0.0
- **Escopo congelado:** Milestones **M1 + M1.5 + M2 + M2.5 + M3 + M4** —
  agente sob guardrails (StateGraph/LangGraph), providers reais com structured
  output, extração Code-First com confirmação humana, integração GUI/.docx e
  empacotamento (`HelperFinanceiro.exe`).
- **Regra:** qualquer alteração nos artefatos abaixo exige nova ADR,
  incremento de versão e nova ata.
- **Ata anterior:** v2.0.0 (2026-07-01, escopo M1) — substituída por esta.

## Checksums SHA-256 dos artefatos

| Artefato | SHA-256 |
|---|---|
| `docs/CONSTITUTION.md` | `4c544fdcc94a353ae6e1c9917dcfeb49185d2e6b6fa2ecbf8c06f169702c16d1` |
| `docs/PRD.md` | `e3c03dc38103202078bb5abb82151a9a31981868691a61121c85c1e03b0cda04` |
| `docs/SPEC.md` | `9cf7059992de10dd6b5e241295b2c964da826f8967064adf6b5b2a5ed983c474` |
| `docs/PLAN.md` | `5f9c50d69669a2962e01d39e653d38a21125d41687dec3cdacd23e9d18a7f774` |
| `docs/TASKS.md` | `aae8b85e974415b328ddf54a11d8a6864b8f99d20d516b083bc4c286681567e4` |
| `docs/HARNESS.md` | `ffb51d56b10e95c8922853919186106bd13a8838d37929d0915c2c3286955c9d` |
| `docs/AGENT.md` | `2e84bf0991883ffdc8727c9cfa9c5b99edc65273c965e789238188629c40c9e6` |
| `docs/REVISAO-SEGURANCA.md` | `ec6923ac3abbe8e4235db73c8b1472558be1336d6d4d6b621b3cb91512ed4a2b` |
| `AGENTS.md` | `678a2473998cab86146a1b4b4fd8d6dda40bbc38d4a6d56a3c85d49c52e7e1f0` |
| `docs/adr/ADR-0001-deterministico-vs-llm.md` | `dc2f410f68e5665b66bf2726a8bdcad636298e9e85560f44a56ac6ef341f50d0` |
| `docs/adr/ADR-0002-provider-agnostico.md` | `1afa4cbed1e81b75c60604e636984a0ecc64e13751db1d12cacd053b70d02acc` |
| `docs/adr/ADR-0003-anonimizacao-guardrails.md` | `88abc358acfbf34d7c03d5a8fd1d498cb8c07aba345f91a234a111acf21a8d84` |
| `docs/adr/ADR-0004-camada-contracts.md` | `c8d5b730c8605ea4cdaf83dbe5e316c76d6681440c6f0c8fe48522da9076566d` |
| `docs/adr/ADR-0005-structured-output.md` | `5f33a3a95fd02b427ec60220c8aeca5f8789fa244866404ff616c9dc13e1af89` |
| `docs/adr/ADR-0006-langgraph-orquestrador.md` | `20df5b09b8055a80c553e91823ad76735d7d3e9e22ffee7d03ac34ddc055340f` |
| `docs/adr/ADR-0007-llamaindex-ingestao.md` | `9bcd0d2a83aa16f09a93221cfa2bbddd1cdf2054dd696b41220e48c78ad34c16` |
| `contracts/schemas.py` | `837414498553c939696248c2ab6734212799c892596efe4c9c7c208767d5996f` |
| `agent/prompts.py` | `e989c302db58f4da703c8b1b4371a376ab4c59b840ab21eb65664886518a9bbf` |
| `agent/agente.py` | `ee04dc65cb3647534be69a1efa5335f14b1a27100ce9f02e8d2c35810585f1ab` |
| `agent/grafo.py` | `72c97c617a92c4eeee7a7e96597d620ff9a3cce15efd1dcec7d37dc3fc5bb8c7` |
| `agent/extracao.py` | `5881404e69971f0212848123c12545df3b0d13129815118862935d322ec6535d` |
| `agent/ingestao.py` | `4c284457e4d77037524e4f1ef0b8992b22ee2fa314fff8911c5c5dd7a0aaec8c` |
| `agent/exibicao.py` | `c5a66ebfd1d2fd5e0347fa1c177e95e4efacc9962e4a2c8e41d67c79a04680d7` |
| `agent/provider.py` | `0a7584bd1835be4a4b5d862223cf4a0f7fda38db18911063cb01e9cb8aa0c627` |
| `agent/config.py` | `a86186d4b5b9282e549d795e21eca4cc1db318b19cd078888b85a807d97c74a3` |
| `agent/cache.py` | `badee5b1b2cd7d02129dcc1693bd1622b06398f2e041cb75a00b1d0f31e63748` |
| `guardrails/pii.py` | `240a29fc98db36da3cc925d11c506b2b1e52075e889ff9e51fbb76585f6d52db` |
| `guardrails/validador_numerico.py` | `26b39add7f0651f546bc250b32ef73f6b33edd2d99030cc984fce18139a3cdf9` |
| `guardrails/conteudo.py` | `66a7c0d5b957d86d48edec5a88146751c78a6d085cc1135a851d53ff7aa517fd` |

## Binário empacotado (T-401)

| Artefato | SHA-256 | Tamanho |
|---|---|---|
| `dist/HelperFinanceiro.exe` | `2757f5f468178081c515a41d3ee68399758c6443492d8a71af03082beaff9802` | 93,8 MB |

> O `.exe` não é versionado no git (`dist/` está no `.gitignore`); o hash acima
> identifica o binário gerado nesta ata. Rebuild em outra máquina/data produz
> hash diferente — regenere com o comando do README e registre em nova ata.

## Estado do harness no congelamento

```text
77 passed (suíte offline — Gate A)
80 passed no total com Ollama ativo (inclui 3 testes de integração real)
Cobertura: 95%+ (piso de 90% no CI)
```

Gerado automaticamente. Recalcule com `Get-FileHash -Algorithm SHA256`
(PowerShell) ou `sha256sum` (Linux/macOS) para verificar integridade.
