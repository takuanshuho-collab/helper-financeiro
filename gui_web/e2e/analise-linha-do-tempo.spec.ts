/**
 * E2E da linha do tempo SSE da análise sênior (T-2604, ADR-0023): Electron +
 * sidecar Python REAIS.
 *
 * ACHADO deste ciclo (registrado no relatório): o brief assumia que
 * `HF_MODO_DEGRADADO=1` ainda emitiria as fases reais do grafo antes de
 * degradar — não é o que o código faz. `agent/agente.py::analisar` devolve
 * `_degradado(...)` ANTES de chamar `executar_analise` quando
 * `cfg.modo_degradado` está ligado, então nenhum `ao_evento` dispara e o SSE
 * só emite `terminal` (sem `fase`). Onde o cenário precisa de fases REAIS
 * terminando degradado (bloco 1), uso o caminho natural do P8 em vez disso:
 * `HF_BASE_URL` apontado para uma porta loopback sem ninguém ouvindo —
 * conexão recusada quase instantânea, o grafo tenta 1 retry e degrada pela
 * via real (`validar_guardrails` → `degradar`), com `ao_evento` emitindo
 * cada fase de verdade pelo caminho do T-2603. `HF_MODO_DEGRADADO=1` segue
 * útil (e usado abaixo) onde só o terminal degradado importa — mais rápido
 * e sem tocar rede.
 *
 * Três blocos:
 *  1) fases chegando pelo SSE (nível de evento — ver nota de raciness na
 *     própria test) + terminal com o aviso de degradado.
 *  2) a correção do T-2602 (revisão do T-2604): uma geração DEGRADADA não
 *     pode ser engolida pelo refetch de `analiseUltima` quando existe uma
 *     salva antiga de assinatura divergente — o aviso de degradado tem
 *     prioridade sobre o bloco esmaecido. Precisa de DOIS lançamentos do app
 *     (mesmo DB/AUTH): o 1º com `HF_PROVIDER=fake` produz uma análise
 *     COMPLETA persistida; o 2º, com `HF_MODO_DEGRADADO=1`, muda os dados
 *     e gera de novo — degradado, sem persistir.
 *  3) queda→polling sem erro na tela: seam de teste `HF_TEST_SSE_QUEDA=1`
 *     (só existe em `electron/main.ts`, opt-in, nunca em produção) força o
 *     stream a cair ANTES de conectar — o mesmo padrão de
 *     `HF_MODO_DEGRADADO`/`HF_PROVIDER=fake`.
 *
 * O contador de tokens (`progresso`) não é coberto aqui: nem `FakeProvider`
 * (síncrono, sem `on_progress`) nem o caminho de conexão recusada (falha
 * ANTES de qualquer token) emitem `progresso` — só a aceitação de campo (c)
 * do fechamento, com LLM local real, exercita o contador (documentado no
 * relatório do T-2604).
 */
import * as os from 'node:os'
import * as path from 'node:path'

import { _electron as electron, expect, test, type ElectronApplication, type Page } from '@playwright/test'

import { cadastrarCofreELogin, desbloquearCofre } from './cofre-helpers'

const RAIZ_GUI = path.resolve(__dirname, '..')

function aba(win: Page, nome: string) {
  return win.locator('.nav-item', { hasText: nome })
}

function campo(win: Page, rotulo: string) {
  return win.locator('label.campo', { hasText: rotulo }).locator('input')
}

async function preencher(win: Page, rotulo: string, valor: string) {
  const input = campo(win, rotulo)
  await input.click()
  await input.press('Control+a')
  await input.pressSequentially(valor)
  await input.blur()
}

test.describe('linha do tempo SSE (fases + terminal degradado)', () => {
  const DB_E2E = path.join(os.tmpdir(), `hf-e2e-timeline-${Date.now()}.db`)
  const AUTH_E2E = path.join(os.tmpdir(), `hf-e2e-timeline-auth-${Date.now()}.json`)
  const SENHA_COFRE = 'senha-e2e-linha-do-tempo-123'

  let app: ElectronApplication
  let win: Page

  test.beforeAll(async () => {
    app = await electron.launch({
      args: ['.'],
      cwd: RAIZ_GUI,
      env: {
        ...process.env,
        // NOTA (achado do T-2604): `HF_MODO_DEGRADADO=1` NÃO passa pelo grafo
        // — `agent/agente.py::analisar` devolve `_degradado(...)` ANTES de
        // chamar `executar_analise`, então nenhum `ao_evento` dispara e o SSE
        // só emite `terminal` (sem `fase`). O brief do T-2604 assumia fases
        // reais sob esse env; não é o comportamento atual (relatado ao
        // revisor). Para exercitar a linha do tempo com fases REAIS do grafo
        // terminando degradado, uso o caminho natural do P8: `HF_BASE_URL`
        // apontado para uma porta loopback SEM ninguém ouvindo — conexão
        // recusada quase instantânea, o grafo tenta 1 retry e degrada pela
        // via real (`validar_guardrails` → `degradar`), com `ao_evento`
        // emitindo cada fase de verdade pelo caminho do T-2603. NÃO uso o
        // provider padrão ("local", `localhost:11434`) porque a máquina de
        // dev pode ter um Ollama de verdade escutando ali (achado do T-2604
        // — confirmado neste ambiente), o que tornaria o teste dependente do
        // que mais roda na máquina.
        HF_PROVIDER: 'openai_compat',
        HF_BASE_URL: 'http://127.0.0.1:65535/v1',
        HF_DB_PATH: DB_E2E,
        HF_AUTH_PATH: AUTH_E2E,
        HF_AUTO_LOCK_MIN: '1440',
        // Conexão recusada é instantânea, mas o timeout padrão (120s,
        // dimensionado p/ LLM local em CPU) não é — encurta pra este teste
        // não pagar minutos por retry.
        HF_TIMEOUT: '3',
      },
    })
    win = await app.firstWindow()
    await cadastrarCofreELogin(win, SENHA_COFRE)
    await win.waitForSelector('.hero', { timeout: 30_000 })
  })

  test.afterAll(async () => {
    await app.close().catch(() => {})
  })

  test('fases chegam em ordem pelo SSE e o terminal preserva o aviso de degradado', async () => {
    await aba(win, 'Análise').click()

    // `HF_MODO_DEGRADADO=1` faz o grafo inteiro (nós reais, sem LLM) rodar em
    // milissegundos — rápido demais para flagrar a linha do tempo pintada no
    // meio do caminho de forma não-flaky (o poll do backend já entrega
    // fase+terminal juntos no 1º ciclo de 200ms). Por isso a prova aqui é no
    // NÍVEL DO EVENTO (o que a ponte IPC realmente entregou ao renderer, a
    // mesma fonte que alimenta a `LinhaDoTempoIa`), não no DOM efêmero — a
    // aceitação de campo (c), com LLM local real, é quem julga a experiência
    // visual em ritmo humano (ADR-0023).
    await win.evaluate(() => {
      const janela = window as unknown as {
        __sseEventos: unknown[]
        hf: { onSseEvento: (cb: (p: unknown) => void) => () => void }
      }
      janela.__sseEventos = []
      janela.hf.onSseEvento((p) => janela.__sseEventos.push(p))
    })

    await win.locator('.btn-add', { hasText: 'Gerar análise sênior' }).click()

    // Terminal: mesmo comportamento de sempre — aviso de degradado com o
    // motivo (P8).
    await expect(win.locator('.ia-degradada')).toContainText('Modo degradado', {
      timeout: 20_000,
    })
    // A linha do tempo desmonta quando a geração termina (só aparece com
    // `ia.fase === 'rodando'`).
    await expect(win.locator('.ia-timeline-wrap')).toHaveCount(0)

    const eventos = await win.evaluate(
      () => (window as unknown as { __sseEventos: Array<{ evento: string; dados?: { no?: string } }> }).__sseEventos,
    )
    const fases = eventos.filter((e) => e.evento === 'fase').map((e) => e.dados?.no)
    // Fases REAIS do grafo (não um rótulo cru): chega mais de uma, na ordem
    // do grafo, terminando em `degradar` — prova que a linha do tempo teria
    // material de sobra para desenhar ✓ por ✓ (a UI só renderiza o que
    // chega, na ordem de chegada — REQ-NF-005).
    expect(fases.length).toBeGreaterThanOrEqual(2)
    expect(fases).toContain('chamar_llm')
    expect(fases[fases.length - 1]).toBe('degradar')
    expect(eventos.some((e) => e.evento === 'terminal')).toBe(true)
    expect(eventos.some((e) => e.evento === 'erro' || e.evento === 'queda')).toBe(false)
  })
})

test.describe('correção T-2602: degradado tem prioridade sobre a salva esmaecida', () => {
  const DB_E2E = path.join(os.tmpdir(), `hf-e2e-timeline-t2602-${Date.now()}.db`)
  const AUTH_E2E = path.join(os.tmpdir(), `hf-e2e-timeline-t2602-auth-${Date.now()}.json`)
  const SENHA_COFRE = 'senha-e2e-t2602-correcao-123'

  test('gerar degradado com salva antiga divergente mostra o aviso, não o bloco esmaecido', async () => {
    // 1º lançamento: HF_PROVIDER=fake (grafo real, sem rede) — gera e persiste
    // uma análise COMPLETA (mesmo padrão de `analise-persistencia.spec.ts`).
    const appCompleto = await electron.launch({
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
    let winCompleto: Page
    let segredoTotp: string
    try {
      winCompleto = await appCompleto.firstWindow()
      const cadastro = await cadastrarCofreELogin(winCompleto, SENHA_COFRE)
      segredoTotp = cadastro.segredoTotp
      await winCompleto.waitForSelector('.hero', { timeout: 30_000 })

      await aba(winCompleto, 'Análise').click()
      await winCompleto.locator('.btn-add', { hasText: /^Gerar análise sênior$/ }).click()
      await expect(winCompleto.locator('.ia-secao')).toContainText('avalanche', { timeout: 20_000 })
      await expect(winCompleto.locator('.ia-carimbo')).toContainText('dados inalterados', {
        timeout: 10_000,
      })
    } finally {
      await appCompleto.close().catch(() => {})
    }

    // 2º lançamento: HF_MODO_DEGRADADO=1, MESMO banco/cofre — a análise salva
    // do passo anterior segue no cofre (persistência sobrevive ao relaunch).
    const appDegradado = await electron.launch({
      args: ['.'],
      cwd: RAIZ_GUI,
      env: {
        ...process.env,
        HF_MODO_DEGRADADO: '1',
        HF_DB_PATH: DB_E2E,
        HF_AUTH_PATH: AUTH_E2E,
        HF_AUTO_LOCK_MIN: '1440',
      },
    })
    try {
      const winDegradado = await appDegradado.firstWindow()
      await desbloquearCofre(winDegradado, SENHA_COFRE, segredoTotp)
      await winDegradado.waitForSelector('.hero', { timeout: 30_000 })

      await aba(winDegradado, 'Análise').click()
      // A assinatura (T-2601) inclui `cfg.provider`/`cfg.model` — este 2º
      // lançamento roda sem `HF_PROVIDER=fake`, então a salva do 1º já
      // aparece divergente aqui, ANTES de qualquer edição (o selo âmbar
      // confirma: a pré-condição do cenário — "existe uma salva antiga de
      // assinatura divergente" — já vale neste ponto).
      await expect(winDegradado.locator('.ia-selo-desatualizada')).toContainText(
        'Os dados mudaram desde esta análise',
        { timeout: 10_000 },
      )

      // Muda os dados vivos também (mesmo padrão de `analise-persistencia
      // .spec.ts`) — reforça que a divergência não depende só do provider.
      await aba(winDegradado, 'Perfil').click()
      await preencher(winDegradado, 'Salário/benefício líquido', '7500')
      await aba(winDegradado, 'Análise').click()
      await expect(winDegradado.locator('.ia-selo-desatualizada')).toContainText(
        'Os dados mudaram desde esta análise',
        { timeout: 10_000 },
      )

      // Gera de novo — HF_MODO_DEGRADADO=1 degrada (P8), sem persistir (só
      // modo completo persiste): a salva do backend CONTINUA sendo a antiga
      // (assinatura ainda divergente da atual).
      await winDegradado.locator('.btn-add', { hasText: /^Gerar análise sênior$/ }).click()
      await expect(winDegradado.locator('.ia-degradada')).toContainText('Modo degradado', {
        timeout: 20_000,
      })

      // A CORREÇÃO em prova: o aviso de degradado prevalece — o bloco
      // esmaecido da salva antiga NÃO reaparece por cima dele.
      await expect(winDegradado.locator('.ia-selo-desatualizada')).toHaveCount(0)
      await expect(winDegradado.locator('.ia-secao-desatualizada')).toHaveCount(0)
      await expect(winDegradado.locator('.ia-degradada')).toBeVisible()
    } finally {
      await appDegradado.close().catch(() => {})
    }
  })
})

test.describe('queda do SSE ⇒ fallback polling gracioso (U5)', () => {
  const DB_E2E = path.join(os.tmpdir(), `hf-e2e-timeline-queda-${Date.now()}.db`)
  const AUTH_E2E = path.join(os.tmpdir(), `hf-e2e-timeline-queda-auth-${Date.now()}.json`)
  const SENHA_COFRE = 'senha-e2e-queda-sse-123'

  let app: ElectronApplication
  let win: Page

  test.beforeAll(async () => {
    app = await electron.launch({
      args: ['.'],
      cwd: RAIZ_GUI,
      env: {
        ...process.env,
        HF_MODO_DEGRADADO: '1',
        HF_DB_PATH: DB_E2E,
        HF_AUTH_PATH: AUTH_E2E,
        HF_AUTO_LOCK_MIN: '1440',
        // Seam de teste SÓ deste arquivo (ver docstring do módulo e
        // `electron/main.ts`): simula queda de rede antes de conectar o SSE.
        HF_TEST_SSE_QUEDA: '1',
      },
    })
    win = await app.firstWindow()
    await cadastrarCofreELogin(win, SENHA_COFRE)
    await win.waitForSelector('.hero', { timeout: 30_000 })
  })

  test.afterAll(async () => {
    await app.close().catch(() => {})
  })

  test('sem erro na tela; o polling assume e entrega o mesmo resultado', async () => {
    await aba(win, 'Análise').click()
    await win.locator('.btn-add', { hasText: 'Gerar análise sênior' }).click()

    // O botão continua em "Gerando…" (o polling assumiu por baixo) e NENHUM
    // erro aparece na tela em momento algum durante a espera.
    await expect(win.locator('.aviso-erro')).toHaveCount(0)
    await expect(win.locator('.btn-add', { hasText: 'Gerando…' })).toBeVisible()

    await expect(win.locator('.ia-degradada')).toContainText('Modo degradado', {
      timeout: 20_000,
    })
    await expect(win.locator('.aviso-erro')).toHaveCount(0)
  })
})
