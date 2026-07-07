/**
 * Smoke do app EMPACOTADO (T-1001): abre o executável gerado pelo
 * electron-builder (com o sidecar PyInstaller embarcado — sem Python, sem
 * node_modules) e confere o handshake + diagnóstico na tela.
 *
 * Pré-requisito: `npm run dist:dir` (gera release/win-unpacked). Roda só
 * quando HF_E2E_PACOTE=1 — o e2e normal (app.spec.ts) não depende do build
 * de distribuição.
 */
import * as fs from 'node:fs'
import * as path from 'node:path'

import { _electron as electron, expect, test } from '@playwright/test'

const EXE = path.resolve(
  __dirname,
  '..',
  'release',
  'win-unpacked',
  'Helper Financeiro.exe',
)

test.skip(
  process.env.HF_E2E_PACOTE !== '1' || !fs.existsSync(EXE),
  'smoke do pacote: rode `npm run dist:dir` e defina HF_E2E_PACOTE=1',
)

test('app empacotado sobe o sidecar congelado e mostra o diagnóstico', async () => {
  const app = await electron.launch({ executablePath: EXE, args: [] })
  try {
    const win = await app.firstWindow()
    // O hero só aparece quando o sidecar (exe PyInstaller) respondeu.
    await win.waitForSelector('.hero', { timeout: 45_000 })
    await expect(win.locator('.pill')).toHaveText('Atenção')
    await expect(win.locator('.ldiv')).toHaveCount(3)
  } finally {
    await app.close()
  }
})
