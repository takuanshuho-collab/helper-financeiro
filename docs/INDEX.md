# Artefatos SDD — Helper Financeiro v2

Mapa dos documentos que governam o projeto. **Comece pelo topo.**

| Ordem | Documento | Papel |
|---|---|---|
| 0 | [`../AGENTS.md`](../AGENTS.md) | Guia do agente de código na IDE (ler antes de codar) |
| 1 | [`CONSTITUTION.md`](CONSTITUTION.md) | Princípios in**violáveis** (P1–P8) e hard rules |
| 2 | [`PRD.md`](PRD.md) | Por que e o que (produto, metas, escopo, NEEDS_CLARIFICATION) |
| 3 | [`SPEC.md`](SPEC.md) | Requisitos em EARS + contratos de dados (REQ-IDs) |
| 4 | [`PLAN.md`](PLAN.md) | Arquitetura, stack, fluxo de dados, milestones |
| 5 | [`AGENT.md`](AGENT.md) | Persona e prompt do Agente Financeiro Sênior (CONSELHEIRO) |
| 6 | [`HARNESS.md`](HARNESS.md) | Suite de avaliação e portões de qualidade |
| 7 | [`TASKS.md`](TASKS.md) | Backlog rastreável (REQ ↔ task ↔ teste) |
| 8 | [`adr/`](adr/) | Decisões de arquitetura (ADR-0001..0021) |
| 9 | [`REVISAO-SEGURANCA.md`](REVISAO-SEGURANCA.md) | Revisão de segurança do M4 (T-403) |
| 10 | [`SEGURANCA-SHELL.md`](SEGURANCA-SHELL.md) | Revisão de segurança do shell web (T-1003) |
| 11 | [`PARIDADE.md`](PARIDADE.md) | Checklist de paridade tkinter ↔ web (T-905) |
| 12 | [`RELATORIO-AUDITORIA.md`](RELATORIO-AUDITORIA.md) | Auditoria de saúde de código do ciclo v2.9 (M18) + desfecho do M19 |
| 13 | [`FREEZE.md`](FREEZE.md) | Ata de congelamento com SHA-256 |

## Fluxo Spec-Driven
```
CONSTITUTION → PRD → SPEC (EARS) → PLAN → TASKS → código
                                 ↘ HARNESS (testa cada REQ)
                                 ↘ ADR (registra decisões)
                                 ↘ FREEZE (congela a versão)
```

## Estado atual
- **M1 + M1.5 + M2 + M2.5 + M3 entregues e verdes**: guardrails, orquestração
  em **StateGraph** (LangGraph, ADR-0006) com degradação segura, providers
  reais com structured output (ADR-0005), **extração Code-First de documentos**
  com citação obrigatória + verificador determinístico + confirmação humana
  (`interrupt`), ingestão local LlamaIndex retriever-only (ADR-0007) e a
  **integração de saída** (M3): painel "assistido por IA" na GUI com thread e
  indicador de degradação, seção "Análise do Agente (IA)" no `.docx` e tela de
  confirmação da extração retomando o checkpoint. Harness com 80 testes
  (77 offline + 3 de integração real; cobertura ≥90% no CI, atual ~95%).
- **Modelo padrão:** `qwen2.5:3b` (GPU 4 GB); alternativa Apache 2.0: `qwen3:4b`.
- **M4 fechado:** `HelperFinanceiro.exe` (~94 MB, PyInstaller), revisão de
  segurança aprovada (`REVISAO-SEGURANCA.md`), higiene de checkpoint
  (estado só com dicts + allowlist msgpack) e v2.1.0 congelada em `FREEZE.md`.
- **Ciclo v2.2 fechado e congelado (`FREEZE.md` v2.2.0):** perfil como
  **orçamento doméstico detalhado** (ADR-0008: categorias tipadas no `core`,
  roll-up determinístico, cobertura da reserva em meses e resumo ao vivo) e
  **revisão de UI/UX** (M6): validação visual dos campos numéricos
  (REQ-F-009), aba Perfil rolável, contador de dívidas, barra de status
  contextual, edição por duplo clique/Enter/Delete e lista zebrada. Ata
  ampliada para congelar todo o código de primeira parte + o harness (104
  testes offline, cobertura 95,4%) e o `.exe` rebuild (93,8 MB).
- **Ciclo v2.3 FECHADO (`FREEZE.md` v2.3.0, ADR-0009):** GUI oficial migrada
  para **Electron + React/TypeScript** (`gui_web/`, 6 telas do redesign
  "Clareza"), núcleo Python como **sidecar** FastAPI em loopback+token (FONTE
  DA VERDADE — sem cálculo em TS, REQ-NF-005); tkinter mantida como fallback
  (`--tkinter`). **ADR-0010**: extração PDF assistida por LLM local
  OpenAI-compatible (LM Studio) — H2 por **endpoint (loopback)** + fusão
  determinística clássico+IA. **ADR-0011**: recuperação com feedback dos
  números órfãos + redação determinística (`sanear`) na análise sênior.
  Telemetria LangSmith só local e opt-in; auto-update HTTPS opt-in;
  empacotamento electron-builder + sidecar PyInstaller; paridade documentada
  (`PARIDADE.md`) com E2E Playwright; segurança do shell revisada
  (`SEGURANCA-SHELL.md`).
- **Ciclo v2.4 FECHADO (`FREEZE.md` v2.4.0, ADR-0012):** orçamento detalhado
  com **rubricas** — subcampos criados pelo usuário por campo do Perfil, com
  roll-up no `core` (campo detalhado = soma, somente-leitura com selo
  "detalhado ▸") editados na tela **Planilha de orçamento**; rubricas também
  na aba "Orçamento detalhado" do `.xlsx` (subtotais `=SUM`). **Persistência
  local** em SQLite gerida pelo sidecar (`%APPDATA%\HelperFinanceiro\
  dados.db`, `HF_DB_PATH` p/ testes): perfil + dívidas + rubricas com
  hidratação no boot e auto-save — o app lembra o usuário entre sessões
  (REQ-F-017/018). Só na GUI web (tkinter = fallback congelado do v2.3,
  `PARIDADE.md` §7).
- **Ciclo v2.5 FECHADO (`FREEZE.md` v2.5.0, ADR-0013):** o orçamento ganhou a
  dimensão TEMPO — **"Arquivar mês"** grava a competência (`AAAA-MM`:
  snapshot do perfil + rubricas; rearquivar substitui) e a Planilha compara
  competências (ou competência vs orçamento vivo) com deltas e variações %
  calculados no `core` ("seu mercado subiu 12,5%", cor semântica: renda
  subir = verde, despesa subir = vermelho). Bônus: **sugestões de nome de
  rubrica** por campo via `datalist` local (REQ-F-019/020). Sem migração de
  schema: a coluna `mes` já estava reservada desde o v2.4.
- **Ciclo v2.6 FECHADO (`FREEZE.md` v2.6.0, ADR-0014):** o caminho **CSV →
  rubricas** — parse determinístico no `core` (`core/extrato.py`: separador,
  colunas, valores BR/US, agrupamento por estabelecimento, competência
  sugerida), **LLM local que SÓ rotula** (`índice → campo`, travas
  determinísticas, endpoint loopback obrigatório — H1/H2) e **revisão humana**
  antes de aplicar (degrada p/ classificação manual sem LLM, P8); destino =
  orçamento vivo ou competência (acrescenta, nunca apaga). **Gráfico de
  evolução** das competências (SVG próprio; séries prontas do `core` via
  `/historico/evolucao`; totais por seção + zoom por campo) e aba **"Evolução
  mensal"** no `.xlsx` (totais `=SUM` + gráfico nativo, Gate B) —
  REQ-F-021/022/023. Sem migração de schema.
- **Ciclo v2.7 FECHADO (`FREEZE.md` v2.7.0, ADR-0015):** **OCR local** de
  documento escaneado/imagem (RapidOCR + PP-OCRv6 medium em ONNX, 100% na
  máquina; modelos **embarcados** no pacote — zero rede, REQ-NF-006). A aba
  **Contrato** aceita PDF e imagem: detecção determinística da fonte
  (`core/documento.py`), motor `agent/ocr.py`, pré-marcação por **tipo** e trave
  de citação tolerante ao **ruído de glifo** do OCR sem afrouxar H1. E o
  **comprovante/extrato escaneado** desemboca na importação do v2.6
  (`core.extrato.ler_extrato_ocr` → mesmos grupos/revisão/aplicação do CSV) —
  REQ-F-024/025/026. O instalador cresce p/ ~330 MB (modelos OCR). Sem migração
  de schema.
- **Ciclo v2.8 FECHADO (`FREEZE.md` v2.8.0, ADR-0016, M16+M17):** o app virou
  um **cofre** — login local com senha mestra + **TOTP** e códigos de
  recuperação (sem backdoor), banco **SQLCipher** com envelope DEK/KEK
  (**Argon2id**), sessão bloqueada/desbloqueada no sidecar (`423 Locked`),
  anti-brute-force e auto-lock, onboarding forçado na GUI
  (REQ-SEC-005/006/007) — e a **LLM local deixou de exigir Ollama/LM Studio**:
  `llama-server` (llama.cpp, build Vulkan com fallback de CPU) **embarcado**
  no pacote e gerido pelo sidecar em loopback, modelo GGUF instalado pelo
  próprio app na tela "Configuração da IA" (catálogo com SHA-256 travado,
  download opt-in — única exceção de rede, REQ-NF-007 — ou `.gguf` local) —
  REQ-F-027/028. `HF_BASE_URL` definido preserva o servidor do usuário
  (ADR-0002). Sem migração de schema relacional (o banco inteiro passou a ser
  cifrado; migração atômica no cadastro do cofre).
- **Ciclo v2.9 FECHADO (`FREEZE.md` v2.9.0, ADR-0017, M18+M19):** ciclo de
  **saúde de código** — nenhum recurso novo. M18: 5 varreduras somente-leitura
  + consolidação (`RELATORIO-AUDITORIA.md`, 34 achados) + portão humano. M19:
  26 achados corrigidos com teste de regressão obrigatório (Job Object mata a
  árvore do `llama-server` em kill duro; disciplina de locks do runtime LLM;
  TTL + descarte de PII dos jobs em memória; blindagem da DEK na cadeia de
  exceções; handlers de validação/500 sempre JSON; remoção do ramo RAG morto e
  das deps `llama-index-*` órfãs — −43 pacotes; E2E sem esperas fixas).
  Cobertura 95,8% → 96,6% com o `sidecar/` medido. Zero regressão, sem
  migração de schema (ADR-0017 §E).
- **Ciclo v2.10 FECHADO (`FREEZE.md` v2.10.0, ADR-0018, M20):** **Electron
  33 → 43.1.0** (C-16: dez majors de defasagem e CVEs high eliminados;
  `npm audit` e `pip-audit` zerados) sem nenhuma correlata exigida e com os
  diálogos preservando a última pasta (`lastUsedPath`, em memória). Carona:
  C-10 (IPC rejeita `metodo` sem `/` antes do sidecar). Bônus: o flake
  histórico do E2E "planilha" (v2.4..v2.8) foi diagnosticado como corrida do
  próprio teste e encerrado pelo padrão T-1907. Regra permanente nova:
  auditoria de deps registrada na ata em todo fechamento de ciclo.
- **Ciclo v2.11 FECHADO (`FREEZE.md` v2.11.0, ADR-0019, M21+M22):** higiene e
  complexidade. C-23 endurecido dormente (cofre `0o600`/`0o700` no ramo POSIX,
  no-op no Windows); C-35 fechado item a item (84 ocorrências, veredito
  triplo, nenhum bug real); C-28/C-29 refatorados por **extração sob
  golden-master** (9 goldens JSON fixam os `.docx`/`.xlsx`; `gerar_relatorio`
  C901 16→3, `_aba_evolucao` e `baixar_modelo` →2) e **catraca `C901`
  permanente** no ruff (teto 13 = pior caso legado; só aperta). Sem build
  oficial no ciclo (nenhuma dep subiu — §E.4 não dispara).
- **Ciclo v2.12 FECHADO (`FREEZE.md` v2.12.0, ADR-0020, M23):** build/release
  — os binários oficiais voltaram a conter o código corrente (instalador NSIS
  2.12.0 + sidecar congelado, validados por 6 smokes do pacote + smoke do
  órfão). Bumps dirigidos: `setuptools` 83 (**pip-audit zerado** — fim do
  risco aceito da v2.11), Electron 43.1.1, langgraph 1.2.9, uvicorn 0.51.
  Novidades de harness: **smoke do auto-update** (electron-updater 6.8 real
  chegou a `update-downloaded`; exceção `http://` só-loopback no `main.ts`
  com teste negativo) e blindagem T-1907 do cenário de recuperação do cofre.
- **Ciclo v2.13 FECHADO (`FREEZE.md` v2.13.0, ADR-0021, M24):** **code
  signing (C-15, o último achado da auditoria v2.9)** em duas fases. Fase 1
  provada fim a fim com certificado de teste: pipeline de assinatura local
  (`scripts/preparar_cert_teste.ps1` + `build_assinado.ps1`, inerte sem as
  envs `HF_CSC_*`) e o degrau final do smoke de auto-update — **instalação
  real do update verificada** (assinatura → NSIS silencioso → desinstalação
  limpa), mais a negativa (pacote não assinado recusado). Fase 2 preparada:
  licença **MIT**, política de assinatura no README, e `release.yml` (build
  verificável por tag → draft de Release) com a submissão **SignPath
  Foundation** atrás de flag até a aprovação da inscrição — quando sair, o
  publisher das releases será "SignPath Foundation" (modelo do programa).
- **Ciclo v2.14 FECHADO (`FREEZE.md` v2.14.0, ADR-0022, M25):** runtime LLM
  **resiliente e configurável** — correção do primeiro bug de produto pego
  em campo (o default `-ngl 99` crashava o `llama-server` Vulkan por falta
  de VRAM na GPU-alvo; o auto-fit aborta com `-ngl` explícito). Novo
  default: **auto-fit + contexto 4096**; `ctx_size`/`gpu_offload`
  configuráveis na tela de Configuração da IA (`GET/PUT /llm/config`, com a
  origem de cada valor: padrão/tela/env); falha de boot ⇒ **retentativa
  única em CPU puro** com motivo classificado do stderr (ring buffer só em
  memória, REQ-SEC-001); painel **"Último boot da IA"** (modo, dispositivo,
  camadas, VRAM, contexto) + **dica de contexto** (regra única no backend)
  + banner `aviso_runtime` na análise que rodou em CPU por falha de GPU.
  A aceitação de campo achou (e o **T-2505** corrigiu) um segundo bug
  mascarado: o llama.cpp recusa a gramática do `json_schema` estrito com o
  tokenizer do phi-3.5 — fallback `json_object` + temperatura 0 + conserto
  dirigido no provider, validado com 4/4 perfis completos no hardware real.
- **Ciclo v2.15 FECHADO (`FREEZE.md` v2.15.0, ADR-0023, M26):** checkpoint
  **durável** do grafo dentro do cofre cifrado (`SqliteSaver` numa 2ª conexão
  SQLCipher; cofre convertido para **WAL**; retomada só de thread inacabado,
  `thread_id` = assinatura dos fatos; toggle "retomar análises interrompidas"
  default ligado), **persistência visível da última análise** (`POST
  /analise/ultima`, carimbo "dados inalterados"/selo âmbar "os dados
  mudaram") e **progresso em tempo real** da análise sênior (SSE de fases +
  contador de tokens — conteúdo do LLM nunca aparece antes dos guardrails;
  linha do tempo na GUI com retomada explicada e queda→polling graciosa).
  Os 3 degraus do T-2505 agora **streamam** (provado no build real). A
  aceitação de campo achou (e o **T-2606** corrigiu) um gap do ADR-0001: a
  saúde financeira ignorava o fluxo de caixa — agora é o **pior entre 2
  eixos** (parcelas × déficit relativo à renda); déficit mensal nunca mais
  sai "Saudável".
- **Mudanças nos artefatos congelados (v2.15.0) exigem nova ADR + incremento
  de versão + nova ata** — o próximo ciclo começa por uma ADR.

## Rodar
```bash
uv sync --group dev
uv run pytest -q               # harness offline
uv run pytest -m ollama        # integração real (skip sem Ollama+modelo)
uv run python main.py          # GUI web (fallback: --tkinter)
cd gui_web && npm run e2e      # E2E Playwright (Electron + sidecar reais)
```
