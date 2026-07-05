# gui_web — GUI web do Helper Financeiro (ADR-0009)

Front **Electron + React + TypeScript (Vite)** do redesign "Clareza". Nasce
**ao lado** da GUI `tkinter` (migração paralela/incremental, M7..M10); o
`tkinter` segue como entrypoint até a paridade das 6 telas.

## Arquitetura (resumo)

```
renderer (React)  ──window.hf.invoke──►  preload (contextBridge)
                                              │  IPC
                                              ▼
                                         main (Electron)
                                              │  HTTP loopback + X-HF-Token
                                              ▼
                                     sidecar Python (FastAPI)  ──►  core/ (FONTE DA VERDADE)
```

- **Cálculo em TS é proibido** (REQ-NF-005): todo número vem do `core` via
  sidecar. O React só apresenta e formata.
- **Segurança** (REQ-SEC-004): `contextIsolation`/`sandbox` ligados,
  `nodeIntegration` desligado, CSP estrita, sem código remoto. O sidecar
  escuta só em `127.0.0.1` (porta efêmera) e exige **token de sessão**; o token
  fica no processo `main`, o renderer nunca o vê.

## Pré-requisitos

- Node + npm (front) e o Python do projeto com o pacote `sidecar` instalável
  (`uv sync` na raiz — inclui `fastapi`/`uvicorn`).

## Scripts

```bash
npm install            # instala o front
npm run typecheck      # tsc do renderer + do processo Electron
npm run build          # vite build (dist/) + tsc do Electron (dist-electron/)
npm start              # build + electron .  (sobe o sidecar e abre a janela)
```

O `main` do Electron sobe o sidecar com `python -m sidecar` a partir da raiz do
repositório. Ajuste o interpretador com a env `HF_PYTHON` (ex.: o Python do
`.venv`). Para iterar só a UI, `HF_DEV_URL=http://localhost:5173` + `npm run
dev:renderer` em outro terminal (a ponte `window.hf` só existe dentro do
Electron).

## Empacotamento

Fica para o **M10**: `electron-builder` + sidecar congelado com PyInstaller
(`extraResource`), telemetria/updater opt-in. Não versionamos `node_modules/`,
`dist/` nem `dist-electron/`.
