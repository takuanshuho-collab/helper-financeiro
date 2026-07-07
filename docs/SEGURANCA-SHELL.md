# Revisão de segurança do shell web (T-1003, REQ-SEC-004)

- **Escopo:** o shell Electron (`gui_web/`), a ponte IPC e a fronteira com o
  sidecar Python. O núcleo (guardrails, anonimização, H1/H2) tem seus próprios
  controles (ADR-0003/0010/0011) e testes.
- **Data:** 2026-07-07 (ciclo v2.3, pré-freeze). Revisão feita código em mãos;
  cada controle abaixo cita o arquivo que o implementa.

## Modelo de ameaça (resumo)

O app roda **100% local** e lida com PII financeira (dívidas, renda, CPF na
carta). As ameaças relevantes para o *shell* são: (a) execução de código
remoto/injetado no renderer; (b) escalada do renderer para Node/SO; (c) outro
processo local falando com o sidecar; (d) vazamento de PII por rede, logs ou
ferramentas de inspeção; (e) update malicioso.

## Controles verificados

| Controle | Implementação | Estado |
|---|---|---|
| `contextIsolation` + `sandbox` + `nodeIntegration:false` | `electron/main.ts` (webPreferences) | ✅ |
| Superfície do preload mínima e tipada (`invoke`, `dialogoSalvar`) | `electron/preload.ts` via `contextBridge` | ✅ |
| CSP estrita no modo dev (header) | `aplicarCsp()` em `electron/main.ts` | ✅ |
| CSP estrita no app EMPACOTADO (file:// não recebe header) | **meta CSP** em `index.html` (corrigido nesta revisão) | ✅ |
| Nenhum código/asset remoto (fontes/JS embarcados) | `@fontsource` no bundle Vite; `connect-src 'self'` | ✅ |
| Janelas novas negadas + navegação externa bloqueada | `setWindowOpenHandler`/`will-navigate` em `main.ts` | ✅ |
| Permissões web (câmera/mic/geo) negadas por padrão | `setPermissionRequestHandler` (adicionado nesta revisão) | ✅ |
| DevTools desabilitado no pacote | `devTools: !app.isPackaged` (adicionado nesta revisão) | ✅ |
| Sidecar só em loopback + porta efêmera | `sidecar/__main__.py` (`127.0.0.1`, porta 0) | ✅ |
| Token por sessão, só em memória, renderer nunca vê | handshake stdout → `main.ts`; renderer usa IPC | ✅ |
| Comparação de token em tempo constante | `secrets.compare_digest` em `sidecar/security.py` (corrigido nesta revisão) | ✅ |
| PII não sai da máquina (H2 por endpoint) | extração local-only + `verificar_pii` no grafo (ADR-0010) | ✅ |
| PII fora dos logs | logs do agente registram chaves/motivos, nunca valores; uvicorn em `log_level=warning` | ✅ |
| Telemetria: OFF por padrão, só loopback com opt-in | `agent/telemetria.py` (T-1002) + `tests/test_telemetria.py` | ✅ |
| Auto-update: opt-in, HTTPS obrigatório, assinatura no apply | `configurarAutoUpdate()` em `main.ts` (T-1002) | ✅ |
| Segredos só via env (nunca em código/log) | `agent/config.py` (`HF_API_KEY`); denylist CONSTITUTION | ✅ |

Cobertura automatizada da fronteira: `tests/test_sidecar.py` (401 sem/inválido
token, 422 de validação, anonimização da fronteira cloud com provider espião)
e E2E (`gui_web/e2e/`, app real + pacote real).

## Achados corrigidos nesta revisão

1. **CSP ausente no pacote** — o header injetado por `onHeadersReceived` só
   vale no dev server (http). Em produção a página carrega via `file://`, sem
   headers ⇒ o app empacotado rodava **sem CSP**. Correção: meta CSP idêntica
   no `index.html` (validada pelo smoke `e2e/empacotado.spec.ts`).
2. **Comparação de token sujeita a timing** — `!=` retorna no primeiro byte
   divergente. Loopback reduz o risco, mas `secrets.compare_digest` elimina o
   canal. Corrigido.
3. **DevTools acessível no pacote** (Ctrl+Shift+I) — inspeção de um app com
   dados financeiros pessoais. Desabilitado quando `app.isPackaged`.
4. **Permissões web sem handler** — nenhum uso legítimo de câmera/mic/geo;
   agora negadas por padrão.

## Riscos residuais (aceitos/planejados)

- **Sem code signing**: o instalador NSIS não é assinado — SmartScreen alerta
  e o auto-update de produção EXIGE certificado (documentado no T-1002).
  Decisão de negócio antes de distribuir.
- **Sidecar aceita qualquer processo local com o token**: o token só existe na
  memória do Electron/sidecar; um atacante com execução local no mesmo usuário
  já leria os dados diretamente — fora do modelo de ameaça.
- **`style-src 'unsafe-inline'`**: exigido pelos estilos inline do React.
  Sem `script-src` inline, o vetor de XSS relevante permanece bloqueado.
- **Exportações gravam PII em disco** (xlsx/docx/carta): é a função do
  produto, sempre por ação explícita do usuário no diálogo nativo.
