# ADR-0017 — Ciclo de saúde de código: auditoria profunda + correção com portão humano

- **Status:** Aceita (2026-07-12)
- **Contexto de processo:** primeira mudança pós-freeze v2.8.0. Esta ADR é a
  autorização formal exigida pela ata: abre o ciclo **v2.9.0** (milestones
  **M18** e **M19**); nova ata será lavrada no fechamento. Escopo decidido pelo
  mantenedor em brainstorm estruturado (2026-07-12): nenhum recurso novo —
  o ciclo inteiro é **qualidade**: encontrar e corrigir o que os gates verdes
  não veem.

## Contexto

O app chega ao v2.8 com todos os indicadores verdes: 425 testes offline,
cobertura 95,8% (catraca ≥ 90%), 18+4 E2E, hooks de ruff/mypy/pytest em todo
commit. Mas oito ciclos de desenvolvimento intenso (v2.0 → v2.8) acumularam
dívidas que indicador nenhum mede — e a própria história do projeto prova que
elas existem: o IPC do Electron **engolia propriedades de `Error`** até o
T-1604; a precedência nova de provider **silenciou 3 testes reais** sem nenhum
teste falhar (T-1702); o `/llm/baixar` tinha **corrida** que corromperia
download (T-1702); o kill duro do sidecar **vaza um `llama-server` órfão**
(observado no T-1704, registrado na ata como risco residual). Cada um desses
foi achado por revisão atenta — não pelos gates. A pergunta que este ciclo
responde: **o que mais está lá, no mesmo padrão?**

Pendências conhecidas que entram de ofício: órfão do llama-server, flake E2E
recorrente pós-build pesado, stderr do SQLCipher não filtrado (decisão a
revalidar), ausência de code signing (segue dependendo de certificado).

## Decisão

### A. Estrutura em duas fases com portão humano

- **M18 — Auditoria:** cinco varreduras especializadas por família de
  categoria + consolidação. Varreduras NÃO alteram código — produzem achados
  em formato único (ID, categoria, arquivo:linha, severidade, esforço,
  evidência, impacto, proposta). Consolidação gera `docs/RELATORIO-AUDITORIA.md`
  deduplicado e priorizado.
- **Portão:** o mantenedor aprova, achado a achado (ou por grupo), o que vira
  correção. Achado reprovado permanece registrado no relatório para ciclos
  futuros.
- **M19 — Correção:** cada achado/grupo aprovado vira task com **teste de
  regressão obrigatório** (que falharia antes da correção). Fechamento com
  gates completos, rebuild dos binários e ata `FREEZE.md` v2.9.0.

### B. Perímetro

Todo o Python de primeira parte (`core/`, `agent/`, `guardrails/`, `outputs/`,
`sidecar/`, `scripts/`, `main.py`) **+ a fronteira dos dois lados**
(`gui_web/electron/main.ts`, `preload.ts`, `gui_web/src/hf/client.ts`,
`contract.ts`). Telas React (`.tsx`) fora do perímetro base — entram apenas
onde um achado da fronteira apontar para dentro delas.

### C. Taxonomia das varreduras (M18)

| Task | Família | Executor |
|---|---|---|
| T-1801 | Segurança: pendências conhecidas, authz rota a rota, segredos/logs, TOCTOU nos arquivos do cofre, superfície loopback+token, `pip-audit`/`npm audit` | Opus + `/security-review` |
| T-1802 | Concorrência e recursos: jobs em memória e locks, corridas, processos filhos, handles não fechados, caminhos de shutdown | Opus |
| T-1803 | Fronteira backend↔frontend: sincronia Pydantic↔`contract.ts`, caminhos de erro do IPC, códigos HTTP, serialização de opcionais, respostas truncadas, timeouts assimétricos | Sonnet |
| T-1804 | Higiene e boas práticas: código morto, imports/deps não usados, duplicação, `except` largos, TODO/FIXME, complexidade, docstrings mentirosas | Sonnet + `/code-review`, `simplify`, `find-bugs` |
| T-1805 | Silenciosos e dívida de teste: testes que degradam sem falhar, o que os 4,2% descobertos escondem, asserts fracos, raiz do flake E2E, exceções engolidas em jobs async | Orquestrador (Fable) |
| T-1806 | Consolidação + relatório + portão | Orquestrador |

### D. Severidade (critérios objetivos)

- **Crítico:** corrupção/perda de dado, quebra do cofre/cifra, vazamento de
  segredo, número financeiro errado (viola H1).
- **Alto:** bug silencioso com efeito real (corrida, recurso vazado, erro
  engolido que mascara falha, contrato dessincronizado com comportamento errado).
- **Médio:** bug latente de cenário raro; dependência vulnerável sem exploit
  no nosso uso; teste que não testa o que diz.
- **Baixo:** higiene (código morto, duplicação, complexidade, docstring).

### E. Restrições invioláveis do ciclo

1. **Zero regressão:** suíte, E2E e cobertura permanecem verdes em toda task;
   correção que quebra teste legítimo é retrabalhada, nunca o teste afrouxado.
2. **Sem migração de schema e sem quebra do cofre:** `dados.db` cifrado,
   `auth.json` e `llm.json` de usuários existentes continuam válidos.
3. **Nenhuma mudança de comportamento visível**, exceto correção de bug real.
4. **Bump de dependência** só com aprovação no portão E smoke do pacote real
   repetido (lição do v2.8).
5. Orquestração do v2.8 mantida: Fable revisa tudo (diff inteiro + gates
   independentes), executores executam, commit só com autorização do
   mantenedor task a task.

## Consequências

- O ciclo não entrega recurso — entrega **confiança**: um app auditado, com
  dívidas conhecidas quitadas ou conscientemente registradas.
- O `RELATORIO-AUDITORIA.md` vira artefato permanente: memória de qualidade
  do projeto e insumo dos próximos ciclos.
- O relatório declara explicitamente o que NÃO cobriu (telas React) — sem
  falso senso de completude.
- Risco assumido: auditoria tem custo fixo mesmo se achar pouco — aceito,
  porque o histórico do projeto sugere que não achará pouco.

## Decision log do brainstorm (2026-07-12)

| Decisão | Alternativas | Porquê |
|---|---|---|
| Auditar E corrigir no ciclo | só auditar; só corrigir conhecidos | app termina melhor, não só diagnosticado |
| Perímetro Python + fronteira TS | só Python; incluir telas | fronteira é onde mora a "falha de comunicação"; telas têm 22 E2E |
| Skills + executores por categoria | só skills; + ultrareview | genérico + específico; ultrareview fica opcional ao critério do mantenedor |
| Portão de aprovação humana | regra automática crítico/alto; corrigir tudo | controle task a task, padrão dos ciclos |
| Estrutura em 2 fases por categoria | módulo a módulo | preserva o portão, paraleliza, relatório durável |
