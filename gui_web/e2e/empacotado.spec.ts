/**
 * Smoke do app EMPACOTADO (T-1001, ampliado no T-1404): abre o executável
 * gerado pelo electron-builder (com o sidecar PyInstaller embarcado — sem
 * Python, sem node_modules) e confere (1) o handshake + diagnóstico na tela e
 * (2) o OCR local rodando DE VERDADE a partir do binário congelado.
 *
 * Pré-requisito: `npm run dist:dir` (gera release/win-unpacked). Roda só
 * quando HF_E2E_PACOTE=1 — o e2e normal (app.spec.ts) não depende do build
 * de distribuição.
 */
import * as fs from 'node:fs'
import * as os from 'node:os'
import * as path from 'node:path'

import {
  _electron as electron,
  expect,
  test,
  type ElectronApplication,
  type Page,
} from '@playwright/test'

const EXE = path.resolve(
  __dirname,
  '..',
  'release',
  'win-unpacked',
  'Helper Financeiro.exe',
)

// Contrato "escaneado" com texto nítido (gerado no T-1404): prova que os
// modelos PP-OCRv6 medium foram EMBARCADOS e o OCR lê texto real sem rede.
const FIXTURE_OCR = path.resolve(__dirname, 'fixtures', 'contrato-escaneado.png')

test.describe.configure({ mode: 'serial' })

test.skip(
  process.env.HF_E2E_PACOTE !== '1' || !fs.existsSync(EXE),
  'smoke do pacote: rode `npm run dist:dir` e defina HF_E2E_PACOTE=1',
)

let app: ElectronApplication
let win: Page

test.beforeAll(async () => {
  // Banco ISOLADO (T-1204): desde a persistência (v2.4) o app hidrata o estado
  // salvo — sem HF_DB_PATH o smoke leria (e reescreveria) o banco REAL do
  // usuário em %APPDATA%, e as asserções do seed não valeriam.
  //
  // LLM de extração apontada para um porto MORTO + timeout curto: a extração
  // cai no caminho CLÁSSICO (regex sobre o texto do OCR) de forma determinística
  // e rápida (~23s no exe congelado), sem depender de haver — ou não — um modelo
  // local no ar. Assim o cenário isola o que o T-1404 prova: o OCR do binário
  // congelado. (HF_MODO_DEGRADADO não serve aqui: ele só afeta a análise sênior,
  // não a extração de contrato.)
  app = await electron.launch({
    executablePath: EXE,
    args: [],
    env: {
      ...process.env,
      HF_BASE_URL: 'http://127.0.0.1:1/v1',
      HF_TIMEOUT: '1',
      HF_DB_PATH: path.join(os.tmpdir(), `hf-e2e-pacote-${Date.now()}.db`),
    },
  })
  win = await app.firstWindow()
  // O hero só aparece quando o sidecar (exe PyInstaller) respondeu.
  await win.waitForSelector('.hero', { timeout: 45_000 })
})

test.afterAll(async () => {
  await app.close().catch(() => {})
})

test('app empacotado sobe o sidecar congelado e mostra o diagnóstico', async () => {
  await expect(win.locator('.pill')).toHaveText('Atenção')
  await expect(win.locator('.ldiv')).toHaveCount(3)
})

test('OCR local roda de verdade a partir do binário congelado (T-1404)', async () => {
  await win.locator('.nav-item', { hasText: 'Contrato' }).click()
  await expect(win.locator('.titulo')).toHaveText('Contrato (PDF ou imagem)')

  await win.locator('.dropzone input[type="file"]').setInputFiles(FIXTURE_OCR)

  // Carregar os modelos PP-OCRv6 + OCRizar leva alguns segundos na 1ª vez. O
  // banner de OCR só aparece quando o sidecar leu texto legível da imagem
  // (modo revisão com campos) — prova de que os .onnx foram embarcados e o
  // OCR rodou offline. Se o pacote não trouxesse os modelos, aqui viria o aviso
  // "preencha manualmente" (OCR indisponível), não o banner.
  await expect(win.locator('.extr-ocr')).toBeVisible({ timeout: 90_000 })
  await expect(win.locator('.extr-ocr')).toContainText('OCR local')

  // O parser clássico extraiu campos do texto OCRizado (valor/taxa/parcelas).
  await expect(win.locator('.extr-campo').first()).toBeVisible()
})
