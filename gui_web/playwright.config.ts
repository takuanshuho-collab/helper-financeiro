import { defineConfig } from '@playwright/test'

/**
 * E2E do app Electron REAL (T-905): sobe o main process, que por sua vez sobe
 * o sidecar Python (.venv da raiz do repo) — portanto roda o produto inteiro,
 * offline e determinístico (a IA roda em HF_MODO_DEGRADADO).
 *
 * Portão LOCAL (como o smoke da GUI tkinter): exige `npm run build` prévio e
 * o Electron instalado, então NÃO entra no gate-front do CI (ADR-0009/T-706).
 * Rodar com: `npm run e2e`.
 */
export default defineConfig({
  testDir: './e2e',
  timeout: 60_000,
  // Um único app Electron por vez (o sidecar abre porta efêmera, mas a janela
  // e o userData são compartilhados).
  workers: 1,
  fullyParallel: false,
  reporter: [['list']],
  use: {
    trace: 'retain-on-failure',
  },
})
