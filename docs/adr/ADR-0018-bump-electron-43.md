# ADR-0018 — Bump do Electron 33 → 43 (ciclo v2.10, achado C-16)

- **Status:** Aceita (design validado em brainstorming com o mantenedor) ·
  **Data:** 2026-07-13
- **Relacionada a:** achado **C-16** do `RELATORIO-AUDITORIA.md` (ciclo v2.9,
  ADR-0017), carona **C-10**; REQ-SEC-004 (superfície IPC mínima)
- **Ciclo:** v2.10 · **Milestone:** M20 (T-2001..T-2003)

## Contexto

O app usa Electron **33.4.11** — dez majors atrás da atual (43.1.0 em
2026-07) e fora da janela de suporte de segurança (suportadas: 41/42/43).
O `npm audit` reporta CVEs *high* (`electron <=39.8.4`: ASAR bypass, spoof de
IPC, header injection, UAF). O perfil endurecido do app (`contextIsolation`,
`sandbox`, `nodeIntegration:false`, permission handler que nega tudo, CSP
restritiva, sem conteúdo remoto) mitiga a exploitabilidade, mas fora do
suporte não há correção upstream possível. O portão do ciclo v2.9 classificou
o bump como "major breaking, ciclo próprio" (ADR-0017 §E.4: bump de dep exige
aprovação no portão E smoke do pacote repetido).

A superfície Electron de primeira parte é pequena: `gui_web/electron/main.ts`
(326 linhas) e `preload.ts` (17 linhas), usando `app`, `BrowserWindow`,
`dialog`, `ipcMain`, `nativeTheme`, `session.setPermissionRequestHandler`,
`webRequest.onHeadersReceived`, `contextBridge`, `ipcRenderer.invoke`,
`webPreferences`, `before-quit` e `electron-updater`.

## Decisão

**Bump direto Electron 33 → 43.x** (Abordagem A: salto único com escada de
portões), dirigido por checklist — a lista oficial de breaking changes das
majors 34→43 é cruzada com a superfície acima ANTES de qualquer build, e a
tabela resultante (nos toca / não nos toca / adaptação) é anexada a esta ADR
na T-2001.

### Escada de portões (ordem crescente de custo)

`tsc` → ESLint → app em dev (cofre destrava, análise roda) → E2E dev (18) →
`npm run dist` → smoke do pacote (4, `HF_E2E_PACOTE=1`) → smoke do órfão
(Job Object mata o llama-server no kill duro do exe congelado).

Quebra em qualquer degrau → consultar a tabela de breaking changes; causa
obscura → **Abordagem B como diagnóstico** (bisect das majors 34..43); causa
= incompatibilidade real da major → degrau **42.x**; nem o 42 couber →
**ciclo abortado sem merge** e C-16 volta a "registrado" com o motivo.

### Regras do ciclo

1. **Correlatas só se exigidas** ("o erro pede o bump"): `electron-builder`,
   `@types/node`, `@playwright/test`, `undici` etc. só sobem se um portão
   comprovar a incompatibilidade; cada bump extra é registrado com a prova.
   React/Vite/ESLint não sobem. Proibido `npm audit fix --force`.
2. **Diálogos preservam o comportamento antigo:** o Electron 43 passa a abrir
   `showSaveDialog`/`showOpenDialog` em Downloads em vez de lembrar a última
   pasta; o `main.ts` guarda `lastUsedPath` **em memória** (por sessão, sem
   persistência nova) e o injeta como `defaultPath` quando o chamador não
   especifica — regra "sem mudança visível" mantida.
3. **Carona C-10:** `chamarSidecar` valida o prefixo `/` do `metodo` antes de
   montar a URL (rejeita sem chegar ao sidecar), com cenário E2E cobrindo.
4. **Critérios de saída:** Electron dentro da janela de suporte; `npm audit`
   sem high/critical (vulnerabilidade transitiva sem fix upstream → registrar
   na ata, não forçar); todos os portões verdes; ata FREEZE v2.10.0.
5. **Recorrência (regra permanente):** o fechamento de TODO ciclo passa a
   incluir `npm audit` + `pip-audit` + conferência da janela de suporte do
   Electron, com resultado **registrado na ata FREEZE**. Não força bump —
   garante que defasagem nunca mais passa despercebida.
6. **Zero regressão** (herdada da ADR-0017 §E): nenhuma feature nova, nenhuma
   mudança de comportamento visível, suíte Python intocada (o sidecar não
   participa do bump), mesma régua de E2E/smokes antes e depois.

## Riscos aceitos

| Risco | Detecção | Resposta |
|---|---|---|
| Playwright 1.61 não lança Electron 43 | Portão E2E dev | bump como correlata comprovada |
| electron-builder 26 não empacota o 43 | Portão `npm run dist` | bump como correlata comprovada |
| Sandbox/preload sutil quebra IPC | E2E dev (fluxo do cofre) | tabela de breaking changes + ajuste mínimo |
| `electron-updater` 6.8 incompatível | changelog (auto-update é opt-in, OFF) | risco residual registrado na ata |
| Instalador muda de tamanho | `npm run dist` | registrar o delta na ata |
| `lastUsedPath` sem automação fiel | — | verificação manual no smoke, registrada |

## Alternativas rejeitadas (Decision Log do brainstorming)

- **42.x / 41.x / 39.8.5:** mesma travessia de majors com menos tempo de
  suporte restante; o 39 já está fora do suporte (sanaria o sintoma, não o
  achado).
- **Abordagem B como plano (degraus por major):** ~10× o custo de build/E2E
  com degraus majoritariamente vazios para a nossa superfície — reservada
  como técnica de diagnóstico.
- **Abordagem C (bump + modernização do main.ts):** viola YAGNI e o
  zero-regressão; modernização é ciclo próprio.
- **Gate bloqueante de `npm audit` no CI:** CVE transitivo sem fix upstream
  quebraria o CI sem ação possível; a checagem registrada no fechamento dá a
  mesma visibilidade sem o ruído.
- **Aceitar o novo default dos diálogos (Downloads):** mudança visível sem
  bug real — vetada pela regra do ciclo.

## Milestone M20

| ID | Task | Conteúdo |
|---|---|---|
| T-2001 | Migração Electron 43 | checklist de breaking changes 34→43 × superfície (tabela anexada aqui) → bump + correlatas comprovadas → `lastUsedPath` → escada de portões completa |
| T-2002 | Carona C-10 + recorrência | validação do prefixo `/` (com E2E); passo permanente de auditoria de deps no checklist de fechamento (TASKS/HARNESS) |
| T-2003 | Fechamento | `npm audit` registrado; build oficial; smokes (pacote + órfão); ata FREEZE v2.10.0; docs sincronizados |

## Tabela de breaking changes 34→43 × superfície (T-2001, 2026-07-13)

Fonte: `breaking-changes.md` oficial. Superfície cruzada: `app`,
`BrowserWindow`, `dialog`, `ipcMain`, `nativeTheme`,
`session.setPermissionRequestHandler`, `webRequest.onHeadersReceived`,
`contextBridge`, `ipcRenderer.invoke`, `webPreferences`, `before-quit`,
`electron-updater`, `undici`.

| Major | Breaking change | Nos toca? | Adaptação |
|---|---|---|---|
| **43** | Dialogs passam a abrir em Downloads sem `defaultPath` | **SIM** | `lastUsedPath` em memória por sessão nos 2 handlers (regra 2) |
| 43 | WCO/rounded corners Linux; `NativeImage.toBitmap()` sRGB; `showHiddenFiles` removido no Linux | Não | app Windows; sem NativeImage/extensões |
| **42** | `electron` não baixa mais o binário no `postinstall` (baixa no 1º uso) | Marginal | só pipeline de install; verificado OK; −32 pacotes líquidos no lock (downloader novo usa undici 7 aninhado) |
| 42 | macOS `UNNotification`; OSR; `clearStorageData.quotas`; `nativeImage.hslShift` | Não | não usamos |
| 41 | PDF sem WebContents próprio; cookie change cause | Não | `setWindowOpenHandler` nega janelas; sem cookies |
| 40 | `clipboard` no renderer deprecado | Não | renderer sandbox sem Node |
| 39 | `--host-rules`; popups sempre resizable; OSR `paint` | Não | sem popups/OSR |
| 38 | env vars Linux removidas; fim macOS 11; `plugin-crashed`; `webFrame.routingId` | Não | não usamos |
| 37 | `utilityProcess` (rejection/exit); blocklist WebUSB/Serial; `ProtocolResponse.session` | Não | sidecar é `child_process.spawn` de Python, não `utilityProcess` |
| 36 | `app.commandLine` minúsculas; `PrinterInfo`; extensões → `session.extensions`; GTK4 | Não | sem switches/impressão/extensões |
| 35 | dialog portal Linux; `setPreloads` deprecado; args de `console-message` | Não | preload é por janela (`webPreferences.preload`); `onHeadersReceived` sem filtro de urls |
| 34 | menu bar oculta em fullscreen (Windows) | Não (cosmético) | sem menu bar custom |

Nenhuma breaking change 34→43 altera assinatura/semântica do perfil
endurecido (`setPermissionRequestHandler`, `contextBridge`,
`ipcRenderer.invoke`, `ipcMain.handle`, `before-quit`, flags de
`webPreferences`) — verificado item a item.

## Registro da execução (T-2001, 2026-07-13)

**Entrega final: `electron@43.1.0`** (o alvo aprovado), com um episódio que
merece registro:

1. O executor entregou inicialmente em **42.6.1**: no 43, a suíte E2E falhava
   2/2 no cenário "planilha: rubricas" (2º clique de remoção perdido durante
   o re-render), diagnosticado como "regressão exclusiva da major 43".
2. A revisão do orquestrador **refutou a atribuição**: a suíte completa no 42
   também falhou (1 em 4 rodadas) com a MESMA assinatura — é o **flake
   histórico do "planilha"** (documentado nas atas v2.4..v2.8, presente já no
   Electron 33), uma corrida do próprio teste (dois `.first().click()`
   consecutivos sobre DOM em re-render) que o Chromium mais novo agrava até
   quase-determinismo.
3. Correção pelo padrão T-1907 (afirma a condição real, régua mais FORTE, sem
   esperas): asserção `toHaveCount(1)` entre os dois cliques em
   `e2e/app.spec.ts`. Validação: se o app perdesse cliques com o DOM
   assentado, o teste continuaria acusando — não perde (43 verde 2/2 no
   arquivo, depois 2 rodadas completas limpas).
4. Escada final no 43.1.0: typecheck ✅ · lint ✅ · E2E dev **18 passed × 2
   rodadas** ✅ · `dist:dir` (electron=43.1.0) ✅ · smoke do pacote **4
   passed** ✅ · smoke do órfão (Job Object no exe congelado, GGUF real) ✅.
5. **Nenhuma correlata subiu** (electron-builder 26.15.3, Playwright 1.61.1,
   undici 6.x de app: intactos — nenhum portão pediu). `npm audit`: **0
   vulnerabilidades**. Bônus: a correção do teste **encerra o flake
   histórico** do "planilha" registrado desde o v2.4.
