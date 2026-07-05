# ADR-0009 — GUI web (Electron + sidecar Python) e redesign "Clareza"

- **Status:** Aceita (2026-07-05)
- **Contexto de processo:** primeira mudança pós-freeze v2.2.0. Esta ADR é a
  autorização formal exigida pela ata: abre o ciclo **v2.3.0** (M7..M10); nova
  ata de freeze será lavrada no fechamento do ciclo. O freeze v2.2.0 continua
  válido para todo o código já congelado — o código novo nasce fora dele.

## Contexto

O handoff de design (`Design/README.md` + `Design/screenshots/`) entrega uma
direção visual **hi-fi ("Clareza", tom fintech jovem)**: janela larga
1280×840, dashboard central + 6 telas, anel de progresso `conic-gradient`,
tipografia Plus Jakarta Sans, barras animadas (`cubic-bezier`), modo escuro
persistido em `localStorage`. Nada disso é alcançável no `tkinter` — a stack
atual da GUI. O brief recomenda **React + TypeScript** e manda recriar as telas
no ambiente de destino, tratando a **lógica financeira em Python como a fonte
de verdade dos cálculos**.

Isso é uma bifurcação de arquitetura, não um retema. A pergunta que o brief
**não** responde é como casar um front-end web com o núcleo Python
(FONTE DA VERDADE, ADR-0001) mantendo o funcionamento **offline por padrão**
(DEC-2, aqui refinada — ver Decisão §6 e Consequências) e num pacote único
distribuível. O mantenedor decidiu o rumo
(AskUserQuestion, 2026-07-05):

- **Shell/ponte:** **Electron + sidecar Python** (preferência por ecossistema
  e DX de React maduros).
- **Cadência:** **paralela/incremental** — a GUI web nasce ao lado da tkinter,
  que permanece funcional até haver paridade das 6 telas.

## Decisão

1. **Front-end:** **React + TypeScript + Vite**, implementando fielmente o
   brief "Clareza" (Design Tokens, 6 telas, dashboard central, modo escuro
   persistido em `localStorage`). É a **nova casca fina** — só apresenta e
   formata (REQ-NF-004 estendido ao TS).

2. **Shell:** **Electron** (empacotado com `electron-builder`), com
   *secure defaults* obrigatórios: `contextIsolation: true`,
   `nodeIntegration: false`, `sandbox: true`, **nenhum código remoto** (só
   assets locais empacotados) e **CSP estrita**. A superfície de API do Node
   é exposta ao renderer **apenas** via `preload` + `contextBridge`
   (`window.hf`), nunca `ipcRenderer` cru nem Node no renderer.

3. **Núcleo Python permanece a FONTE DA VERDADE.** Ele é exposto como
   **sidecar local** (FastAPI/uvicorn) que apenas embrulha `core`, `agent`,
   `guardrails` e `outputs` — **sem reimplementar cálculo algum**. O
   "recompute ao vivo" do brief é preservado, mas a aritmética roda **no
   Python** (chamada a cada mudança relevante, com *debounce*), não em JS.
   Isto reconcilia o brief com ADR-0001 e REQ-NF-004: **cálculo financeiro em
   TypeScript é proibido** (fonte única, sem risco de divergência
   determinística).

4. **Ponte de processos:**
   `renderer (React) → preload (contextBridge) → main (Node) → HTTP loopback
   → sidecar (Python)`. O `main` detém a porta e o token do sidecar; o
   renderer **nunca** vê o token nem fala com a rede diretamente.

5. **Fluxos longos** (análise sênior via LLM; extração de PDF com
   `interrupt`/confirmação humana) usam **modelo de job**: `submit → poll/stream
   de status`. O `interrupt` do LangGraph (ADR-0006) mapeia para um estado
   "aguardando confirmação" que devolve os campos + citações; a tela confirma
   e chama um endpoint de **resume** (`Command(resume)`).

6. **Segurança (fiel às restrições do projeto):**
   - Sidecar em `127.0.0.1` **apenas**, **porta efêmera** (nunca `0.0.0.0`);
     **token por sessão** em todo request (sem token ⇒ 401); sem CORS externo.
   - Extração roda **só no provider local** (o PDF cru contém PII); a nuvem só
     recebe payload **anonimizado** (H2/REQ-GRD-002); desanonimização **só na
     fronteira de exibição** (resposta do sidecar para as telas locais, via
     `agent/exibicao.py`).
   - Chaves **só via env** (REQ-SEC-001/002); PII **nunca** persistida; mapa de
     anonimização só em memória (REQ-SEC-003).
   - **Telemetria (opt-in, via env) — LangSmith LOCAL/self-hosted:** tracing do
     agente **habilitado**, porém apontando para um endpoint **na própria
     máquina** (`LANGSMITH_ENDPOINT` local ou trace em disco): **nenhum dado
     trafega para terceiros**, o que **preserva o denylist da CONSTITUTION** e
     P3/H7 **sem emenda constitucional**. Mesmo local, traça só payload já
     anonimizado (nunca PII crua nem a exibição desanonimizada, REQ-SEC-003);
     o trace parte do **sidecar** (LangGraph), não do renderer; ativa só com as
     env `LANGSMITH_*` presentes. Auto-updater do Electron **habilitado**, com
     **pacotes assinados sobre HTTPS**, tratado no processo `main` (o renderer
     segue sem código remoto e com CSP estrita). Continua **sem** *crash
     report* remoto; `.env`/`*.key` **nunca** versionados.

7. **Empacotamento:** o sidecar é congelado com **PyInstaller** (onedir) e
   embutido como `extraResource` do Electron; instalador/portátil via
   `electron-builder`. Aceita-se conscientemente o **aumento de tamanho**
   (Chromium + runtime Python) em troca da DX/ecossistema escolhidos.

8. **Migração paralela/incremental:** a GUI web nasce em **`gui_web/`** ao lado
   de `gui/` (tkinter). O `tkinter` continua o entrypoint e permanece
   funcional até a **paridade das 6 telas**; só então o entrypoint troca.
   Reversível a qualquer ponto — alinhado à disciplina de freeze.

9. **Portões de qualidade:** o front TS/React entra com **toolchain própria**
   (ESLint + Prettier + `tsc` + Vitest; Playwright para E2E), **fora** dos
   portões Python de cobertura — análogo ao que já vale para `gui/` tkinter. A
   lógica testável continua no `core` (portões atuais **inalterados**). O
   **contrato do sidecar** ganha testes `pytest` do lado Python.

## Alternativas rejeitadas

- **PyWebView + React** (recomendação técnica original): menor superfície
  (**sem porta de rede**, ponte `js_api` in-process) e pacote menor, com Python
  seguindo host/entrypoint. Preterida pelo mantenedor em favor do
  ecossistema/DX do Electron. Registrada por honestidade de trade-off.
- **Tauri + sidecar Python:** binário nativo pequeno e rápido, porém **duas
  toolchains** (Rust) e a **mesma** porta loopback; menos familiar ao
  mantenedor.
- **Reescrever os cálculos em TypeScript (web puro):** viola ADR-0001 e
  REQ-NF-004 (fonte única da verdade); duplicaria o motor determinístico com
  risco de divergência. **Rejeitada.**
- **Retematizar o `tkinter`:** menor risco e sem stack nova, mas **não
  alcança** a fidelidade hi-fi do brief (anel `conic-gradient`, web fonts,
  transições CSS, modo escuro persistido). Descumpre o design pretendido.

## Consequências

- **Duas toolchains no repositório** (Python + Node). O CI ganha etapa de
  `install/lint/test/build` do front; os portões Python seguem como estão.
- **Pacote maior** (Chromium + sidecar Python). Custo aceito na decisão.
- **Nova superfície:** porta loopback com token é mais exposta que o
  in-process do tkinter/pywebview — mitigada por *loopback-only* + token por
  sessão + ausência de CORS externo + sem código remoto no renderer.
- O **contrato sidecar↔front** vira artefato de primeira classe (novo trecho de
  SPEC + `contracts/`), reforçando REQ-NF-004: a casca fina agora é o TS.
- **Denylist da CONSTITUTION:** a proibição de "frameworks web" mirava
  **cálculo em prompts/servidor de negócio**, não a camada de apresentação.
  Esta ADR abre exceção explícita e delimitada — web só na **apresentação**
  (Electron/React) e num **sidecar de transporte** que não contém lógica
  financeira. O núcleo determinístico e o denylist de cálculo permanecem
  intactos. A tabela de stack do PLAN §3 será atualizada no M7.
- **Latência do recompute ao vivo** via loopback: mitigada por *debounce*
  (~150–250 ms) e pelo custo sub-milissegundo do cálculo determinístico local.
- **DEC-2 refinada:** de "100% offline" para **"offline por padrão,
  conectividade opt-in"** — no modo local (Ollama) o app é integralmente
  offline. As **únicas** conectividades externas são a **nuvem** (provider LLM)
  e o **auto-updater**, ambas *opt-in* e sem PII crua (payload anonimizado;
  updates assinados). O tracing **LangSmith é local/self-hosted** (não sai da
  máquina) — logo o denylist e H7 permanecem íntegros sem emenda. `PRD.md` §8
  (DEC-2) sincronizado no M7.
- O freeze **v2.2.0 permanece válido**; o código novo (`gui_web/`, sidecar) só
  entra na ata **v2.3.0**, no fechamento do ciclo.

## Requisitos derivados

A formalizar no `SPEC.md` no início do **M7** (numeração reservada):

- `REQ-F-010..` — as 6 telas do brief (dashboard, perfil/orçamento, dívidas,
  contrato PDF, análise, carta) com paridade funcional ao tkinter atual.
- `REQ-NF-005` — contrato do sidecar (RPC local sobre `core`/`agent`, sem
  cálculo em TS; casca fina em React).
- `REQ-SEC-004` — binding `127.0.0.1` + porta efêmera + token por sessão;
  Electron com `contextIsolation`/`sandbox` e CSP estrita; tracing LangSmith
  **local/self-hosted** (não sai da máquina) e auto-updater assinado, ambos
  **opt-in via env**, sempre sem PII crua.

Milestones **M7..M10** no `PLAN.md` §7 e `TASKS.md`. Harness: testes `pytest`
do contrato do sidecar + Vitest/Playwright do front (fora dos portões Python).
