/**
 * Smoke do runtime LLM EMBARCADO no app EMPACOTADO (T-1703, ADR-0016 §E/F).
 *
 * Complementa `empacotado.spec.ts` (cofre + OCR congelados) provando o que é
 * exclusivo do pacote desta task: o binário `llama-server` (llama.cpp, build
 * Vulkan) viajou como *extraResource* e é RESOLVIDO pela convenção
 * `resources/llama/` ao lado do exe do sidecar. Como a inferência real de um
 * modelo custa minutos (e é validada offline no pytest opt-in `HF_LLAMA_REAL`
 * e no smoke de pacote do T-1703), aqui asseguramos, de forma rápida e
 * estável, os fatos de EMPACOTAMENTO:
 *
 *  1. Sem `HF_BASE_URL`, o sidecar congelado ACHA o binário embarcado — o
 *     estado do runtime cai em MODELO_AUSENTE ("baixe um modelo"), NÃO em
 *     BINARIO_AUSENTE ("reinstale o app"). Essa é a diferença observável entre
 *     o pacote (com binário) e o checkout de dev (sem binário).
 *  2. O download gerenciado + ativação funcionam ponta a ponta contra o pacote,
 *     usando um catálogo FAKE local (`HF_CATALOGO_TESTE`) — sem tocar a rede
 *     externa (REQ-NF-007).
 *
 * Pré-requisito: `python scripts/preparar_llama.py` + `npm run dist:dir`. Roda
 * só com HF_E2E_PACOTE=1.
 */
import { createHash } from 'node:crypto'
import * as fs from 'node:fs'
import * as http from 'node:http'
import * as os from 'node:os'
import * as path from 'node:path'

import {
  _electron as electron,
  expect,
  test,
  type ElectronApplication,
  type Page,
} from '@playwright/test'

import { cadastrarCofreELogin } from './cofre-helpers'

const EXE = path.resolve(
  __dirname,
  '..',
  'release',
  'win-unpacked',
  'Helper Financeiro.exe',
)

// "Modelo" fake minúsculo, só para exercitar o download/ativação ponta a ponta
// (retomada/hash reais são cobertos no pytest do gestor de modelos).
const CONTEUDO = Buffer.concat([Buffer.from('GGUF'), Buffer.alloc(4096, 7)])
const SHA256 = createHash('sha256').update(CONTEUDO).digest('hex')

function subirServidorFake(): Promise<{ servidor: http.Server; url: string }> {
  return new Promise((resolve) => {
    const servidor = http.createServer((_req, res) => {
      res.writeHead(200, { 'Content-Length': String(CONTEUDO.length) })
      res.end(CONTEUDO)
    })
    servidor.listen(0, '127.0.0.1', () => {
      const porta = (servidor.address() as { port: number }).port
      resolve({ servidor, url: `http://127.0.0.1:${porta}/fake-e2e.gguf` })
    })
  })
}

test.describe.configure({ mode: 'serial' })

test.skip(
  process.env.HF_E2E_PACOTE !== '1' || !fs.existsSync(EXE),
  'smoke do pacote: rode `python scripts/preparar_llama.py`, `npm run dist:dir` e defina HF_E2E_PACOTE=1',
)

let app: ElectronApplication
let win: Page
let servidor: http.Server
let dirTmp: string

test.beforeAll(async () => {
  const fake = await subirServidorFake()
  servidor = fake.servidor
  dirTmp = fs.mkdtempSync(path.join(os.tmpdir(), 'hf-e2e-pacote-llm-'))
  const catalogoJson = path.join(dirTmp, 'catalogo.json')
  fs.writeFileSync(
    catalogoJson,
    JSON.stringify([
      {
        id: 'fake-e2e',
        nome: 'Fake E2E',
        descricao: 'Modelo fake só para o teste E2E do pacote.',
        licenca: 'MIT',
        url: fake.url,
        sha256: SHA256,
        tamanho_bytes: CONTEUDO.length,
        arquivo: 'fake-e2e.gguf',
      },
    ]),
  )

  const env = {
    ...process.env,
    // SEM HF_BASE_URL de propósito: força o caminho do runtime EMBARCADO, que
    // depende do binário empacotado (resources/llama do extraResource).
    HF_DB_PATH: path.join(dirTmp, 'dados.db'),
    HF_AUTH_PATH: path.join(dirTmp, 'auth.json'),
    HF_AUTO_LOCK_MIN: '1440',
    HF_CATALOGO_TESTE: catalogoJson,
    HF_MODELOS_DIR: path.join(dirTmp, 'modelos'),
    HF_LLM_CONFIG_PATH: path.join(dirTmp, 'llm.json'),
  }
  delete (env as Record<string, unknown>).HF_BASE_URL
  app = await electron.launch({ executablePath: EXE, args: [], env })
  win = await app.firstWindow()
  await cadastrarCofreELogin(win, 'senha-e2e-pacote-llm-secreta')
  await win.waitForSelector('.hero', { timeout: 45_000 })
})

test.afterAll(async () => {
  await app?.close().catch(() => {})
  servidor?.close()
})

test('o binário llama-server embarcado é resolvido pelo pacote (não BINARIO_AUSENTE)', async () => {
  await win.locator('.nav-item', { hasText: 'Configuração da IA' }).click()
  await expect(win.locator('.titulo')).toHaveText('Configuração da IA')

  // Binário presente no pacote ⇒ o motivo é MODELO_AUSENTE ("baixe um modelo"),
  // e NUNCA a instrução de reinstalar (que seria BINARIO_AUSENTE, o estado do
  // checkout de dev SEM binário embarcado). Este é o fato de empacotamento.
  const status = win.locator('.cfgia-status')
  await expect(status.locator('.aviso-erro')).toContainText('Baixe um do catálogo', {
    timeout: 15_000,
  })
  await expect(status.locator('.aviso-erro')).not.toContainText('reinstale o app')
})

test('download gerenciado + ativação funcionam contra o pacote (catálogo fake, sem rede real)', async () => {
  const item = win.locator('.cfgia-item', { hasText: 'Fake E2E' })
  await expect(item).toBeVisible()
  await item.locator('.btn-add', { hasText: 'Baixar' }).click()

  const usar = item.locator('.btn-secundario', { hasText: 'Usar este modelo' })
  await expect(usar).toBeVisible({ timeout: 20_000 })
  await usar.click()

  // Ativado: o status vira "Modelo pronto" (runtime sobe sob demanda) e o item
  // ganha o selo "· ativo". Prova que, com binário + modelo, o pacote está apto
  // a subir o runtime embarcado na 1ª análise (a geração real é validada no
  // pytest opt-in HF_LLAMA_REAL e no smoke de pacote do T-1703).
  await expect(win.locator('.cfgia-status .status-ok')).toContainText('Modelo pronto', {
    timeout: 15_000,
  })
  await expect(item.locator('.cfgia-item-meta')).toContainText('ativo', { timeout: 10_000 })

  const llmJson = JSON.parse(fs.readFileSync(path.join(dirTmp, 'llm.json'), 'utf-8')) as {
    modelo_ativo: string
  }
  expect(llmJson.modelo_ativo.endsWith('fake-e2e.gguf')).toBe(true)
})
