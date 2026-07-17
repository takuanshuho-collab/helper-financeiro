# ADR-0022 — Ciclo v2.14: runtime LLM resiliente e configurável (fix do -ngl 99 + ajustes na GUI)

- **Status:** Aceita (design validado em brainstorming com o mantenedor) ·
  **Data:** 2026-07-15
- **Relacionada a:** primeiro bug de produto pego em campo (2026-07-15, na
  máquina do mantenedor, app 2.13.0): `_FLAGS_PADRAO = ("-ngl", "99")` em
  `sidecar/runtime_llm.py` crasha o `llama-server` com
  `ggml_vulkan: ErrorOutOfDeviceMemory` em GPUs sem VRAM livre suficiente
  (GTX 1650 4 GB, hardware-alvo do ADR-0016 §E) — o auto-ajuste do llama.cpp
  b9966 **desiste** quando `-ngl` é forçado ("n_gpu_layers already set by
  user, abort") em vez de reduzir, e o boot morre em ~5 s ⇒
  `HEALTH_TIMEOUT` ⇒ análise sênior degradada com
  `ERRO_CONFIG:RuntimeLLMIndisponivel`. Sem a flag, o mesmo binário e modelo
  sobem saudáveis em 9 s (auto-fit). Regras herdadas: ADR-0017 §E (zero
  regressão; rebuild + smokes quando o produto muda), ADR-0018 §5 (auditoria
  de deps no fechamento), ADR-0020 hotfix (CI remoto verde antes de
  congelar).
- **Ciclo:** v2.14.0 · **Milestone:** M25 (T-2501..T-2504)

## Contexto

O runtime LLM embarcado (T-1701..T-1703) herdou defaults fixos em código:
contexto 8192 e `-ngl 99` (todas as camadas na GPU). O comentário da época
("se o driver não conseguir offloadar, o servidor roda em CPU — o default é
seguro nos dois mundos") **provou-se errado** para o llama.cpp b9966: com
`-ngl` explícito o servidor aborta no OOM. Na máquina de campo, o
phi-3.5-mini q4 (2,4 GB) + cache KV de contexto 8192 (~1 GB) não cabem nos
4 GB da GTX 1650 — exatamente a GPU-alvo declarada quando escolhemos a
variante Vulkan. Além do fix, o mantenedor decidiu expor os dois parâmetros
na tela de Configurações da IA (hoje só o modelo é configurável; contexto e
offload exigiam a env `HF_LLAMA_FLAGS`) e aproveitar a captura de stderr —
necessária para explicar falhas de GPU — como painel de diagnóstico do
último boot.

## Decisão

### M25 — Runtime resiliente e configurável (tasks por entregável)

- **T-2501 (runtime: fix + captura + retry, Opus — coração crítico):**
  - `_FLAGS_PADRAO` → **tupla vazia** (auto-fit do llama.cpp decide o
    offload a cada boot, medindo a VRAM livre daquele momento);
    `_CTX_PADRAO` → **4096**. Comentário reescrito com a lição de campo.
  - **Resolução da config efetiva** (`ctx_size`, `gpu_offload`):
    `env HF_LLAMA_FLAGS` (vence tudo, contrato de override intacto) >
    campos novos do `llm.json` (`ctx_size`: int; `gpu_offload`: `"auto"` |
    `"cpu"` | int de camadas) > defaults. Leitura tolerante (campo inválido
    ⇒ default), como o restante do `llm.json`.
  - **Captura de stderr:** `Popen` troca `stderr=DEVNULL` por `PIPE` +
    thread leitora com **ring buffer em memória** (~200 linhas; nunca em
    disco — REQ-SEC-001). Classificador puro (fixtures dos logs reais de
    campo) mapeia padrões → motivos tipados: `GPU_SEM_MEMORIA`
    (`ErrorOutOfDeviceMemory`), `GPU_FIT_ABORTADO` (`failed to fit
    params`), `GENERICO`. Do boot bom, extrai: camadas offloadadas/total,
    VRAM alocada, contexto efetivo, dispositivo.
  - **Retry em CPU puro:** se o boot falha (processo morre ou health
    estoura) e a config não era CPU puro, **uma única retentativa** com
    `-ngl 0` antes de degradar. Resultado num `boot_info` consultável sob o
    lock de estado: modo final (`nunca_subiu` | `gpu` | `cpu_configurado` |
    `cpu_fallback`), motivo tipado do fallback e métricas.
- **T-2502 (contratos + endpoints + regra da dica, Sonnet):**
  - `GET /llm/config`: `config` (valores efetivos + origem de cada um:
    `padrao` | `tela` | `env`), `boot_info`, `dica` (texto pronto ou
    `null`). **Regra única da dica** no backend, testável: último boot
    `cpu_fallback` por memória OU offload < 50% das camadas ⇒ sugerir o
    degrau de contexto abaixo (8192 → 4096 → 2048; em 2048 não há dica).
  - `PUT /llm/config`: valida (`ctx_size` ∈ {2048, 4096, 8192};
    `gpu_offload` `"auto"` | `"cpu"` | int 1..999), persiste no `llm.json`
    (escrita atômica existente) e **encerra o runtime corrente** — próximo
    `base_url()` sobe com a config nova (mesmo padrão do
    `definir_modelo_ativo`). Inválido ⇒ 422, sem tocar o disco.
  - **`aviso_runtime`** (string opcional, aditivo) na resposta da análise
    sênior, preenchido quando o boot que a serviu foi `cpu_fallback`.
  - Modelos Pydantic em `contracts/schemas.py`.
- **T-2503 (GUI + E2E, Sonnet):** na tela de Configurações da IA:
  - Seção **"Ajustes avançados"**: seletor de contexto (3 degraus com frase
    de custo) + uso da GPU (Auto / Só CPU / Fixar camadas com input
    numérico). Salvar ⇒ PUT + toast "vale a partir da próxima análise".
    Com `HF_LLAMA_FLAGS` ativa ⇒ controles desabilitados com aviso de
    origem `env` (a GUI nunca finge que o salvar teria efeito).
  - Painel **"Último boot da IA"**: badge de modo (🟢 GPU / 🔵 CPU /
    🟠 CPU por falha na GPU + motivo em linguagem clara), dispositivo,
    camadas offloadadas ("22 de 33"), VRAM alocada, contexto efetivo;
    `nunca_subiu` ⇒ texto neutro.
  - **Dica de contexto**: callout com botão "Aplicar sugestão"
    (pré-seleciona o degrau; o usuário ainda confirma no Salvar — nada muda
    sozinho).
  - Na tela de análise: banner âmbar informativo quando `aviso_runtime`
    vier preenchido (não bloqueia nem esconde o resultado).
  - E2E Playwright: três estados do painel (GET mockado), salvar ⇒ PUT +
    toast, "Aplicar sugestão" pré-seleciona, banner do aviso.
- **T-2504 (fechamento, orquestrador):** gates locais + **CI remoto
  verde** + auditoria de deps (§5) + **rebuild oficial 2.14.0** (o produto
  mudou — §E) + smokes do pacote (§E.4) + **aceitação de campo**: na
  máquina do mantenedor, `HF_LLAMA_FLAGS` removida ⇒ análise sênior sai
  com o default novo (auto-fit) e o painel mostra o boot real. Ata
  `FREEZE.md` v2.14.0.

### Critérios de fechamento

Gates verdes; CI remoto verde; suíte com os testes novos (classificador,
retry, resolução, endpoints, regra da dica); E2E da tela verde; build
2.14.0 + smokes; aceitação de campo confirmada pelo mantenedor; ata
v2.14.0. Golden-master e catraca C901 intactos.

## Riscos aceitos

| Risco | Mitigação |
|---|---|
| Thread leitora de stderr travar/atrasar o boot | ring buffer não-bloqueante (deque bounded); a thread é daemon e morre com o processo; health poll independe dela |
| Classificador não reconhecer um padrão novo de erro | motivo `GENERICO` sempre existe; GUI mostra mensagem neutra; fixtures crescem quando surgir caso novo |
| Retry em CPU dobrar o tempo até a 1ª análise em máquina ruim | é uma única retentativa; pior caso ~2× timeout de health, e a alternativa era ficar SEM análise |
| Duplicação de `-c` no argv (config + env override) | comportamento "último vence" do llama.cpp b9966 verificado empiricamente em campo (n_ctx efetivo confere) |
| Usuário fixar camadas inviáveis na tela | é exatamente o caso coberto pelo retry CPU + painel com motivo |

## Alternativas rejeitadas (Decision Log do brainstorming)

- **Hotfix cirúrgico (só o fix de 1 linha):** o mantenedor quer os
  parâmetros acessíveis na GUI — env é invisível para usuário final.
- **Manter 8192 de contexto:** foi o que estourou a VRAM do hardware-alvo
  junto com o offload total; 4096 era a config validada na era LM Studio.
- **Só degradar com motivo (P8 atual, sem retry):** deixaria o usuário sem
  análise até corrigir a config; escolha do mantenedor foi retry + motivo.
- **Validar a config no salvar (boot de teste):** lento (~10 s por
  tentativa) e não cobre VRAM que muda em runtime.
- **Seletor de perfil único / campo de flags livres:** ou pouco flexível ou
  corda para flag inválida; contexto + offload cobre os casos reais.
- **Motor de recomendação de hardware completo:** duplicaria (pior) o
  auto-fit, que já mede a VRAM real a cada boot; frágil a concorrência de
  VRAM e caro por vendor. O painel do último boot mostra o resultado do
  auto-fit de graça (carona na captura de stderr) e a dica cobre o único
  parâmetro que ele não ajusta (contexto).
- **Adicionar ministral-3b ao catálogo / campo "modelo local":** YAGNI;
  ministral exigiria validação de schema (REQ-LLM-002) antes de entrar.
- **Persistir config em arquivo novo ou no cofre:** mesmo arquivo e padrão
  do `modelo_ativo` (`llm.json`); números e caminhos não são segredo.
- **Log do llama-server em arquivo:** REQ-SEC-001 — ring buffer só em
  memória.

## Registro da execução (2026-07-17, fechamento)

- T-2501..T-2504 entregues conforme o design. A **aceitação de campo**
  (critério do T-2504) encontrou um SEGUNDO bug, mascarado pelo primeiro: o
  `llama-server` (b9966 **e** b10043 — bump não corrige; com e sem
  `--jinja`) recusa com HTTP 400 a gramática derivada de `json_schema`
  estrito para o tokenizer do **phi-3.5** (`Failed to initialize samplers:
  Unexpected empty grammar stack after accepting piece: | (29989)`; bug
  conhecido do llama.cpp, issues #12597/#21017/#23677). O smoke do T-1703
  nunca o viu porque usou o Qwen2.5-1.5B (outro tokenizer).
- **T-2505 (adicionada ao M25 com aval do mantenedor):** fallback no
  `OpenAICompatProvider` em três degraus, todos medidos no host real —
  (1) 400 de gramática ⇒ reenvio único com `json_object` + schema injetado
  no prompt (memoizado por instância); (2) **temperatura 0** só nesse
  caminho (com 0.2, 1/3 das análises validava o schema; com 0.0, 4/4);
  (3) **conserto dirigido**: JSON que não valida volta ao modelo UMA vez
  com os erros nomeados do Pydantic (com temp 0 o retry cego do grafo
  repetiria o erro byte a byte). Validação final: **4/4 perfis variados**
  em modo completo pelo grafo inteiro no host, e aceitação de campo dupla
  (dados alterados entre as análises) pelo mantenedor. A imposição do
  contrato segue 100% Pydantic + retry-correção + P8 (REQ-LLM-002).
- Plano B estrutural registrado: `docs/PESQUISA-ONNX-RUNTIME-GENAI.md`
  (não versionado) + candidato no TASKS.md — ONNX Runtime GenAI
  (constrained decoding via llguidance) caso a classe de bug reapareça.
