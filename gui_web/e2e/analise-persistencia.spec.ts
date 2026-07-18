/**
 * E2E da persistência visível da última análise sênior (T-2602, ADR-0023):
 * Electron + sidecar Python REAIS — `HF_PROVIDER=fake` troca só o provider do
 * LLM por `agent.provider.FakeProvider` (determinístico, sem rede), então a
 * análise sênior completa de verdade pelo grafo/guardrails/persistência
 * reais. Diferente de `app.spec.ts` (que roda com `HF_MODO_DEGRADADO=1` e
 * portanto NUNCA persiste — a degradação não vale os 2-4 min), este arquivo
 * precisa de uma janela própria porque exige o modo COMPLETO.
 *
 * Cobre a hidratação com carimbo e o selo "dados mudaram" (o desenho de
 * origem — `docs/RELATORIO-PERSISTENCIA-ANALISE.md`); a linha do tempo/SSE
 * fica para o T-2604, que já vai integrar esta mesma tela.
 */
import * as os from 'node:os'
import * as path from 'node:path'

import { _electron as electron, expect, test, type ElectronApplication, type Page } from '@playwright/test'

import { cadastrarCofreELogin } from './cofre-helpers'

const RAIZ_GUI = path.resolve(__dirname, '..')
const DB_E2E = path.join(os.tmpdir(), `hf-e2e-analise-ultima-${Date.now()}.db`)
const AUTH_E2E = path.join(os.tmpdir(), `hf-e2e-analise-ultima-auth-${Date.now()}.json`)
const SENHA_COFRE = 'senha-e2e-persistencia-123'

let app: ElectronApplication
let win: Page

function aba(nome: string) {
  return win.locator('.nav-item', { hasText: nome })
}

function campo(rotulo: string) {
  return win.locator('label.campo', { hasText: rotulo }).locator('input')
}

async function preencher(rotulo: string, valor: string) {
  const input = campo(rotulo)
  await input.click()
  await input.press('Control+a')
  await input.pressSequentially(valor)
  await input.blur()
}

async function gerarAnaliseSenior() {
  await win.locator('.btn-add', { hasText: /^Gerar análise sênior$/ }).click()
  // FakeProvider é instantâneo, mas o job async ainda faz round-trip HTTP.
  await expect(win.locator('.ia-secao')).toContainText('avalanche', { timeout: 20_000 })
}

test.beforeAll(async () => {
  app = await electron.launch({
    args: ['.'],
    cwd: RAIZ_GUI,
    env: {
      ...process.env,
      HF_PROVIDER: 'fake',
      HF_DB_PATH: DB_E2E,
      HF_AUTH_PATH: AUTH_E2E,
      HF_AUTO_LOCK_MIN: '1440',
    },
  })
  win = await app.firstWindow()
  await cadastrarCofreELogin(win, SENHA_COFRE)
  await win.waitForSelector('.hero', { timeout: 30_000 })
})

test.afterAll(async () => {
  await app.close().catch(() => {})
})

test('hidratação com carimbo + selo de dados mudados', async () => {
  await aba('Análise').click()

  // Nada salvo ainda: tela como hoje, sem carimbo nem selo.
  await expect(win.locator('.ia-carimbo')).toHaveCount(0)
  await expect(win.locator('.ia-selo-desatualizada')).toHaveCount(0)

  await gerarAnaliseSenior()

  // Job completo persistiu (T-2602): a hidratação (que roda de novo ao
  // `ia.fase` sair de "rodando") acha a MESMA assinatura e mostra o carimbo
  // discreto; o botão principal vira "Gerar novamente".
  await expect(win.locator('.ia-carimbo')).toContainText('dados inalterados', {
    timeout: 10_000,
  })
  await expect(win.locator('.btn-add', { hasText: 'Gerar novamente' })).toBeVisible()

  // Troca de aba e volta: a Análise REMONTA (React só renderiza a aba ativa)
  // — a hidratação repete do zero, provando que o carimbo veio do BANCO
  // (cofre), não de um estado em memória desta mesma sessão de componente.
  await aba('Visão geral').click()
  await aba('Análise').click()
  await expect(win.locator('.ia-carimbo')).toContainText('dados inalterados', {
    timeout: 10_000,
  })
  await expect(win.locator('.ia-secao')).toContainText('avalanche')

  // Muda os dados vivos (fora da tela Análise) — a assinatura recalculada no
  // backend diverge da salva.
  await aba('Perfil').click()
  await preencher('Salário/benefício líquido', '7500')
  await aba('Análise').click()

  await expect(win.locator('.ia-selo-desatualizada')).toContainText(
    'Os dados mudaram desde esta análise',
    { timeout: 10_000 },
  )
  await expect(win.locator('.ia-secao-desatualizada')).toBeVisible()
  // Botão volta ao rótulo normal (não "Gerar novamente") — os dados divergem.
  await expect(win.locator('.btn-add', { hasText: /^Gerar análise sênior$/ })).toBeVisible()

  // Gerar de novo substitui tudo: o selo some e o carimbo volta a bater.
  await gerarAnaliseSenior()
  await expect(win.locator('.ia-selo-desatualizada')).toHaveCount(0)
  await expect(win.locator('.ia-carimbo')).toContainText('dados inalterados', {
    timeout: 10_000,
  })

  // Volta ao seed para não vazar estado para outros arquivos de E2E (bancos
  // isolados por arquivo, mas por hábito de higiene do próprio teste).
  await aba('Perfil').click()
  await preencher('Salário/benefício líquido', '5000')
})
