/**
 * E2E do runtime LLM configurável (T-2503, ADR-0022): seção "Ajustes
 * avançados" + painel "Último boot da IA" + callout da dica + banner do
 * `aviso_runtime` na tela Análise.
 *
 * Electron + sidecar Python REAIS (mesmo padrão de `configuracao-ia.spec.ts`).
 * Os estados `gpu`/`cpu_fallback` do painel exigem um boot de verdade do
 * `llama-server` (o `boot_info` é só EM MEMÓRIA, amarrado à instância do
 * runtime — `GET /llm/config` nunca o infere de um arquivo) — não dá para
 * simular via `HF_LLM_CONFIG_PATH` sozinho. Como não há GPU real disponível
 * neste ambiente de teste, `HF_LLAMA_SERVER` aponta para um `.bat` que só
 * repassa para `fixtures/fake-llama-server.py`: um HTTP server real em
 * loopback que finge o `llama-server` — falha a 1ª tentativa (imitando o OOM
 * de campo do ADR-0022) e sobe saudável na retentativa em CPU puro,
 * exercitando a retentativa REAL de `runtime_llm._iniciar_com_retry` (não um
 * mock do HTTP da tela). O endpoint `/chat/completions` devolve 500 de
 * propósito: o grafo do agente degrada com segurança (P8) qualquer falha do
 * provider, então o job da análise ainda chega a "pronto" — o que basta para
 * o `aviso_runtime` (amarrado ao boot, não ao conteúdo da resposta).
 *
 * Batch em vez de um binário de verdade: no Windows, `subprocess.Popen` do
 * sidecar consegue iniciar um `.bat` sem `shell=True` (verificado
 * empiricamente neste checkout) — CreateProcess cai para o interpretador do
 * `.bat` quando o arquivo não é um PE válido. Isso pode não valer em todo
 * ambiente Windows; se um dia isso quebrar em CI, o desvio documentado aqui é
 * a causa mais provável.
 */
import * as fs from 'node:fs'
import * as os from 'node:os'
import * as path from 'node:path'

import { _electron as electron, expect, test, type ElectronApplication, type Page } from '@playwright/test'

import { cadastrarCofreELogin } from './cofre-helpers'

const RAIZ_GUI = path.resolve(__dirname, '..')
const RAIZ_REPO = path.resolve(RAIZ_GUI, '..')
const SCRIPT_FAKE_LLAMA = path.join(__dirname, 'fixtures', 'fake-llama-server.py')

function pythonDoProjeto(): string {
  if (process.env.HF_PYTHON) return process.env.HF_PYTHON
  const candidatos = [
    path.join(RAIZ_REPO, '.venv', 'Scripts', 'python.exe'),
    path.join(RAIZ_REPO, '.venv', 'bin', 'python'),
  ]
  return candidatos.find((c) => fs.existsSync(c)) ?? 'python'
}

/** Gera um `.bat` que só repassa para o script Python FALSO — ver docstring
 * do módulo (Windows consegue lançar `.bat` direto via `subprocess.Popen`,
 * sem `shell=True`, o suficiente para `resolver_binario_llama` aceitar como
 * "binário"). */
function criarBinarioFalso(dirTmp: string): string {
  const python = pythonDoProjeto()
  const bat = path.join(dirTmp, 'llama-server-fake.bat')
  fs.writeFileSync(bat, `@echo off\r\n"${python}" "${SCRIPT_FAKE_LLAMA}" %*\r\n`)
  return bat
}

function aba(win: Page, nome: string) {
  return win.locator('.nav-item', { hasText: nome })
}

/** `process.env` sem `HF_LLAMA_FLAGS`: a máquina do mantenedor roda uma LLM
 * local (LM Studio) com essa variável setada por hábito de dev — se ela
 * vazasse para o app sob teste, "origem env" venceria em TODO cenário (a env
 * sobrepõe tudo, ADR-0022) e os testes de `tela`/boot real perderiam o
 * sentido. Só o teste que EXERCITA a origem `env` a define de propósito. */
function envSemFlags(): Record<string, string | undefined> {
  const resto = { ...process.env }
  delete resto.HF_LLAMA_FLAGS
  return resto
}

function envBase(dirTmp: string, sufixo: string) {
  return {
    ...envSemFlags(),
    HF_DB_PATH: path.join(dirTmp, `dados-${sufixo}.db`),
    HF_AUTH_PATH: path.join(dirTmp, `auth-${sufixo}.json`),
    HF_AUTO_LOCK_MIN: '1440',
    HF_LLM_CONFIG_PATH: path.join(dirTmp, `llm-${sufixo}.json`),
  }
}

test.describe.configure({ mode: 'serial' })

test('painel "nunca_subiu": texto neutro sem nenhuma análise ter rodado', async () => {
  const dirTmp = fs.mkdtempSync(path.join(os.tmpdir(), 'hf-e2e-cfgia-rt-neutro-'))
  const app: ElectronApplication = await electron.launch({
    args: ['.'],
    cwd: RAIZ_GUI,
    env: { ...envBase(dirTmp, 'neutro'), HF_MODO_DEGRADADO: '1' },
  })
  const win = await app.firstWindow()
  try {
    await cadastrarCofreELogin(win, 'senha-cfgia-runtime-neutro')
    await win.waitForSelector('.hero', { timeout: 30_000 })
    await aba(win, 'Configuração da IA').click()

    await expect(win.locator('.card-titulo', { hasText: 'Último boot da IA' })).toBeVisible()
    await expect(
      win.locator('.cfgia-boot', { hasText: 'A IA ainda não foi iniciada nesta sessão.' }),
    ).toBeVisible({ timeout: 10_000 })
    // Sem badge nenhum nesse estado (nunca_subiu sem motivo).
    await expect(win.locator('.cfgia-badge')).toHaveCount(0)
  } finally {
    await app.close().catch(() => {})
  }
})

test('origem "env" (HF_LLAMA_FLAGS): controles desabilitados com o aviso', async () => {
  const dirTmp = fs.mkdtempSync(path.join(os.tmpdir(), 'hf-e2e-cfgia-rt-env-'))
  const app: ElectronApplication = await electron.launch({
    args: ['.'],
    cwd: RAIZ_GUI,
    env: { ...envBase(dirTmp, 'env'), HF_MODO_DEGRADADO: '1', HF_LLAMA_FLAGS: '' },
  })
  const win = await app.firstWindow()
  try {
    await cadastrarCofreELogin(win, 'senha-cfgia-runtime-env')
    await win.waitForSelector('.hero', { timeout: 30_000 })
    await aba(win, 'Configuração da IA').click()

    await expect(win.locator('.cfgia-aviso-env')).toBeVisible({ timeout: 10_000 })
    await expect(win.locator('.cfgia-aviso-env')).toContainText('HF_LLAMA_FLAGS')
    // Todos os degraus de contexto/GPU ficam desabilitados — nenhum clique
    // teria efeito enquanto a env vencer.
    const degraus = win.locator('.cfgia-degrau')
    const total = await degraus.count()
    expect(total).toBeGreaterThan(0)
    for (let i = 0; i < total; i++) {
      await expect(degraus.nth(i)).toBeDisabled()
    }
    await expect(win.locator('.cfgia-salvar-linha .btn-add')).toBeDisabled()
  } finally {
    await app.close().catch(() => {})
  }
})

test('salvar (PUT) persiste no llm.json e mostra o toast', async () => {
  const dirTmp = fs.mkdtempSync(path.join(os.tmpdir(), 'hf-e2e-cfgia-rt-salvar-'))
  const llmJson = path.join(dirTmp, 'llm-salvar.json')
  const app: ElectronApplication = await electron.launch({
    args: ['.'],
    cwd: RAIZ_GUI,
    env: {
      ...envSemFlags(),
      HF_DB_PATH: path.join(dirTmp, 'dados-salvar.db'),
      HF_AUTH_PATH: path.join(dirTmp, 'auth-salvar.json'),
      HF_AUTO_LOCK_MIN: '1440',
      HF_LLM_CONFIG_PATH: llmJson,
      HF_MODO_DEGRADADO: '1',
    },
  })
  const win = await app.firstWindow()
  try {
    await cadastrarCofreELogin(win, 'senha-cfgia-runtime-salvar')
    await win.waitForSelector('.hero', { timeout: 30_000 })
    await aba(win, 'Configuração da IA').click()

    // Padrão efetivo é 4096 (sem llm.json ainda) — muda para 2048 e "Só CPU".
    await expect(win.locator('.cfgia-degrau', { hasText: '4096' })).toHaveClass(/on/, {
      timeout: 10_000,
    })
    await win.locator('.cfgia-degrau', { hasText: '2048' }).click()
    await win.locator('.cfgia-degrau', { hasText: 'Só CPU' }).click()
    await win.locator('.cfgia-salvar-linha .btn-add').click()

    await expect(win.locator('.cfgia-toast')).toContainText(
      'vale a partir da próxima análise',
      { timeout: 10_000 },
    )

    const salvo = JSON.parse(fs.readFileSync(llmJson, 'utf-8')) as {
      ctx_size?: number
      gpu_offload?: string | number
    }
    expect(salvo.ctx_size).toBe(2048)
    expect(salvo.gpu_offload).toBe('cpu')

    // O card reidrata com o valor persistido (origem "tela").
    await expect(win.locator('.cfgia-degrau', { hasText: '2048' })).toHaveClass(/on/)
    await expect(win.locator('.cfgia-degrau', { hasText: 'Só CPU' })).toHaveClass(/on/)
  } finally {
    await app.close().catch(() => {})
  }
})

test('boot real com fallback CPU: badge, motivo, dica, "Aplicar sugestão" e banner da análise', async () => {
  const dirTmp = fs.mkdtempSync(path.join(os.tmpdir(), 'hf-e2e-cfgia-rt-fallback-'))
  const binario = criarBinarioFalso(dirTmp)
  const modelo = path.join(dirTmp, 'modelo-fake.gguf')
  fs.writeFileSync(modelo, Buffer.from('GGUF-fake-e2e'))

  const app: ElectronApplication = await electron.launch({
    args: ['.'],
    cwd: RAIZ_GUI,
    env: {
      ...envBase(dirTmp, 'fallback'),
      // SEM HF_MODO_DEGRADADO: precisa entrar no grafo de verdade para o
      // runtime embarcado subir e o boot_info ser registrado.
      HF_LLAMA_SERVER: binario,
      HF_LLM_MODELO: modelo,
      HF_FAKE_LLAMA_MODE: 'cpu_fallback',
    },
  })
  const win = await app.firstWindow()
  try {
    await cadastrarCofreELogin(win, 'senha-cfgia-runtime-fallback')
    await win.waitForSelector('.hero', { timeout: 30_000 })

    await aba(win, 'Análise').click()
    await win.locator('.btn-add', { hasText: 'Gerar análise sênior' }).click()

    // Duas tentativas de boot (auto → retry -ngl 0) + poll do job: folga generosa.
    await expect(win.locator('.aviso-runtime')).toBeVisible({ timeout: 60_000 })
    await expect(win.locator('.aviso-runtime')).toContainText('modo CPU')
    await expect(win.locator('.aviso-runtime')).toContainText(
      'a GPU não tinha memória de vídeo suficiente para o modelo',
    )

    await aba(win, 'Configuração da IA').click()

    const badge = win.locator('.cfgia-badge')
    await expect(badge).toBeVisible({ timeout: 10_000 })
    await expect(badge).toContainText('CPU por falha na GPU')
    await expect(win.locator('.cfgia-boot-motivo')).toContainText(
      'Falha classificada do último boot',
    )
    await expect(win.locator('.cfgia-boot-motivo')).toContainText(
      'a GPU não tinha memória de vídeo suficiente para o modelo',
    )
    // Nunca afirma "a GPU falhou" cru (achado de UX do TASKS.md, T-2503).
    await expect(win.locator('.cfgia-boot')).not.toContainText('a GPU falhou')

    await expect(
      win.locator('.cfgia-boot-item', { hasText: 'Camadas na GPU' }),
    ).toContainText('0 de 32')
    await expect(
      win.locator('.cfgia-boot-item', { hasText: 'Contexto efetivo' }),
    ).toContainText('4096')
    await expect(
      win.locator('.cfgia-boot-item', { hasText: 'Dispositivo' }),
    ).toContainText('GTX 1650')

    // Dica: offload real (0/32) ficou abaixo de 50% ⇒ sugere o degrau abaixo
    // do contexto efetivo (4096 → 2048).
    const dica = win.locator('.cfgia-dica')
    await expect(dica).toBeVisible({ timeout: 10_000 })
    await expect(win.locator('.cfgia-degrau', { hasText: '4096' })).toHaveClass(/on/)
    await dica.locator('button', { hasText: 'Aplicar sugestão' }).click()
    await expect(win.locator('.cfgia-degrau', { hasText: '2048' })).toHaveClass(/on/)
    // "Aplicar sugestão" só pré-seleciona — nada foi salvo ainda.
    const llmJson = path.join(dirTmp, 'llm-fallback.json')
    expect(fs.existsSync(llmJson)).toBe(false)
  } finally {
    await app.close().catch(() => {})
  }
})
