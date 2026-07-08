/**
 * E2E do Helper Financeiro (T-905): Electron + sidecar Python REAIS.
 *
 * Percorre as 6 telas provando a paridade funcional com a GUI tkinter
 * (docs/PARIDADE.md). Tudo offline: os números vêm do core determinístico e a
 * IA roda em HF_MODO_DEGRADADO (o job async degrada rápido e sem rede).
 *
 * Os testes são seriais e compartilham a mesma janela — a ordem importa.
 */
import * as os from 'node:os'
import * as path from 'node:path'

import {
  _electron as electron,
  expect,
  test,
  type ElectronApplication,
  type Page,
} from '@playwright/test'

const RAIZ_GUI = path.resolve(__dirname, '..')

// Banco isolado por RODADA (T-1102): o app agora persiste o estado em SQLite;
// sem isolar, uma rodada herdaria o perfil editado pela anterior (ou pior, o
// banco real do usuário). O mesmo arquivo vale para os relaunches do teste de
// tema/persistência — é exatamente o que queremos provar.
const DB_E2E = path.join(os.tmpdir(), `hf-e2e-${Date.now()}.db`)

test.describe.configure({ mode: 'serial' })

let app: ElectronApplication
let win: Page

async function abrirApp(): Promise<[ElectronApplication, Page]> {
  const instancia = await electron.launch({
    args: ['.'],
    cwd: RAIZ_GUI,
    env: { ...process.env, HF_MODO_DEGRADADO: '1', HF_DB_PATH: DB_E2E },
  })
  const janela = await instancia.firstWindow()
  // O hero só aparece quando o sidecar respondeu o primeiro /diagnostico.
  await janela.waitForSelector('.hero', { timeout: 30_000 })
  return [instancia, janela]
}

/** Input de um CampoMoeda/CampoPercent/CampoTexto pelo rótulo. */
function campo(rotulo: string) {
  return win.locator('label.campo', { hasText: rotulo }).locator('input')
}

/**
 * Digita num campo controlado como um usuário: foca, seleciona tudo e tecla.
 * (`fill()` seta o valor de uma vez e briga com o padrão foco/rascunho do
 * CampoMoeda — o valor acabava concatenado.)
 */
async function preencher(rotulo: string, valor: string) {
  const input = campo(rotulo)
  await input.click()
  await input.press('Control+a')
  await input.pressSequentially(valor)
  await input.blur()
}

function aba(nome: string) {
  return win.locator('.nav-item', { hasText: nome })
}

test.beforeAll(async () => {
  ;[app, win] = await abrirApp()
})

test.afterAll(async () => {
  await app.close().catch(() => {})
})

test('visão geral: diagnóstico do core com o perfil semente', async () => {
  // Seed: parcelas 1.950 / renda 5.000 = 39% ⇒ "Atenção".
  await expect(win.locator('.pill')).toHaveText('Atenção')
  await expect(win.locator('.anel-num')).toHaveText('39%')
  // As 3 dívidas do seed, com a mais cara sinalizada.
  await expect(win.locator('.ldiv')).toHaveCount(3)
  await expect(win.locator('.selo-cara')).toHaveText('Mais cara')
  // Estratégias simuladas no core.
  await expect(win.locator('.scard-win .scard-meses')).toContainText('meses')
})

test('perfil: editar a renda recalcula o diagnóstico ao vivo', async () => {
  await aba('Perfil').click()
  await preencher('Salário/benefício líquido', '10000')
  // O roll-up da seção vem do core via sidecar (nenhuma soma no front).
  await expect(
    win
      .locator('.secao', { hasText: 'Renda líquida mensal' })
      .locator('.secao-total'),
  ).toContainText('10.000,00', { timeout: 5_000 })

  // O diagnóstico global recalculou: 1.950 / 10.000 = 19,5% ⇒ "Saudável".
  await aba('Visão geral').click()
  await expect(win.locator('.pill')).toHaveText('Saudável', { timeout: 5_000 })

  // Volta ao seed para os próximos testes.
  await aba('Perfil').click()
  await preencher('Salário/benefício líquido', '5000')
  await aba('Visão geral').click()
  await expect(win.locator('.pill')).toHaveText('Atenção', { timeout: 5_000 })
})

test('dívidas: adicionar e remover recalculam as estatísticas', async () => {
  await aba('Dívidas').click()
  await expect(win.locator('.dcard')).toHaveCount(3)

  await win.locator('.btn-add', { hasText: 'Adicionar dívida' }).click()
  await expect(win.locator('.dcard')).toHaveCount(4)
  const nova = win.locator('.dcard').last()
  await expect(nova.locator('.dcard-credor')).toHaveValue('Nova dívida')

  await nova.locator('.btn-remover').click()
  await expect(win.locator('.dcard')).toHaveCount(3)
  await expect(
    win.locator('.stat', { hasText: 'Saldo devedor total' }),
  ).toContainText('3 dívida(s)')
})

test('análise: estratégias, portabilidade e IA (degradada) no job async', async () => {
  await aba('Análise').click()
  await preencher('Pagamento extra por mês', '300')

  // Estratégias recalculadas no core com o extra.
  await expect(win.locator('.scard-win .scard-meses')).toContainText('meses', {
    timeout: 5_000,
  })
  // Portabilidade: cartão a 12% a.m. supera a taxa-alvo de 1,8% a.m.
  await expect(
    win.locator('.ldiv', { hasText: 'Cartão Banco A' }),
  ).toBeVisible()
  await expect(win.locator('.port-total-valor')).toContainText('R$')
  // Recomendações determinísticas do core.
  await expect(win.locator('.rec').first()).toBeVisible()

  // IA sênior: dispara o job async; com HF_MODO_DEGRADADO=1 ele degrada
  // rápido e a tela mostra o aviso com o motivo (P8).
  await win.locator('.btn-add', { hasText: 'Gerar análise sênior' }).click()
  await expect(win.locator('.ia-degradada')).toContainText('Modo degradado', {
    timeout: 20_000,
  })
})

test('carta: campos contextuais por tipo e prévia ao vivo do core', async () => {
  await aba('Carta ao credor').click()

  // A prévia nasce no tipo padrão (quitação).
  await expect(win.locator('.letter')).toContainText('Prezados,', {
    timeout: 5_000,
  })
  await expect(win.locator('.letter-titulo')).toContainText('quitação à vista')

  // Trocar para portabilidade revela os campos contextuais.
  await win.locator('.propcard', { hasText: 'Portabilidade' }).click()
  await preencher('Banco concorrente', 'Banco Teste E2E')
  await expect(win.locator('.letter')).toContainText('Banco Teste E2E', {
    timeout: 5_000,
  })
  await expect(win.locator('.letter-titulo')).toContainText('portabilidade')

  // A assinatura entra ao vivo.
  await preencher('Seu nome (assinatura)', 'Fulana E2E')
  await expect(win.locator('.letter-ass')).toContainText('Fulana E2E', {
    timeout: 5_000,
  })
})

test('tema: toggle persiste em hf_dark e reidrata ao reabrir', async () => {
  const anterior = await win.evaluate(() => localStorage.getItem('hf_dark'))

  await win.locator('.btn-tema').click()
  const tema = await win.evaluate(
    () => document.documentElement.dataset.theme ?? '',
  )
  expect(['dark', 'light']).toContain(tema)
  const salvo = await win.evaluate(() => localStorage.getItem('hf_dark'))
  expect(salvo).toBe(tema === 'dark' ? '1' : '0')

  // Reidratação: reabre o app inteiro e o tema escolhido volta aplicado.
  await app.close()
  ;[app, win] = await abrirApp()
  await expect(win.locator('html')).toHaveAttribute('data-theme', tema)

  // Restaura a preferência que existia antes do teste (boa vizinhança).
  await win.evaluate((v) => {
    if (v === null) localStorage.removeItem('hf_dark')
    else localStorage.setItem('hf_dark', v)
  }, anterior)
})

test('persistência: o perfil editado sobrevive à reabertura do app', async () => {
  // Edita a renda para um valor-sentinela e espera o recálculo do core.
  await aba('Perfil').click()
  await preencher('Salário/benefício líquido', '7777')
  await expect(
    win
      .locator('.secao', { hasText: 'Renda líquida mensal' })
      .locator('.secao-total'),
  ).toContainText('7.777,00', { timeout: 5_000 })
  // Dá tempo do auto-save (debounce de 600 ms) chegar ao SQLite.
  await win.waitForTimeout(1_500)

  // Reabre o app inteiro: a hidratação (GET /estado) restaura o que foi salvo.
  await app.close()
  ;[app, win] = await abrirApp()
  await aba('Perfil').click()
  await expect(campo('Salário/benefício líquido')).toHaveValue('7.777,00')

  // Volta ao seed para a próxima rodada não depender desta.
  await preencher('Salário/benefício líquido', '5000')
  await win.waitForTimeout(1_500)
})

test('planilha: rubricas detalham o campo e o roll-up vem do core', async () => {
  await aba('Perfil').click()
  await win.locator('.btn-add', { hasText: 'Detalhar orçamento' }).click()
  await expect(win.locator('.titulo')).toHaveText('Planilha de orçamento')

  // Abre o grupo "Contas da casa" e cria a primeira rubrica (Luz, 180).
  const grupo = win.locator('.plan-grupo', { hasText: 'Contas da casa' })
  await grupo.locator('.plan-grupo-topo').click()
  await grupo.locator('.plan-add').click()
  const linha1 = grupo.locator('.plan-linha').first()
  await linha1.locator('.plan-nome').click()
  await linha1.locator('.plan-nome').press('Control+a')
  await linha1.locator('.plan-nome').pressSequentially('Conta de luz')
  await linha1.locator('.campo-num').click()
  await linha1.locator('.campo-num').pressSequentially('180')
  await win.locator('.titulo').click() // foco sai da linha ⇒ grava no sidecar
  await expect(grupo.locator('.plan-grupo-total')).toContainText('180,00', {
    timeout: 5_000,
  })

  // Segunda rubrica (Internet, 120): o subtotal do grupo vem do core (300).
  await grupo.locator('.plan-add').click()
  const linha2 = grupo.locator('.plan-linha').nth(1)
  await linha2.locator('.campo-num').click()
  await linha2.locator('.campo-num').pressSequentially('120')
  await win.locator('.titulo').click()
  await expect(grupo.locator('.plan-grupo-total')).toContainText('300,00', {
    timeout: 5_000,
  })

  // De volta ao Perfil: o campo virou somente-leitura com o selo e a soma,
  // e a seção recalculou no core (1.400 + 300 + 300 = 2.000).
  await win.locator('.btn-add', { hasText: 'Voltar ao Perfil' }).click()
  const detalhado = win.locator('.campo-detalhado', { hasText: 'Contas da casa' })
  await expect(detalhado).toContainText('detalhado')
  await expect(detalhado).toContainText('300,00')
  await expect(
    win.locator('.secao', { hasText: 'Despesas fixas' }).locator('.secao-total'),
  ).toContainText('2.000,00', { timeout: 5_000 })

  // Limpeza: sem rubricas o campo conserva a última soma e volta a ser
  // editável (ADR-0012); restaura o seed (500) para as rodadas seguintes.
  await detalhado.click()
  const grupo2 = win.locator('.plan-grupo', { hasText: 'Contas da casa' })
  await grupo2.locator('.btn-remover').first().click()
  await grupo2.locator('.btn-remover').first().click()
  await expect(grupo2.locator('.plan-linha')).toHaveCount(0)
  await win.locator('.btn-add', { hasText: 'Voltar ao Perfil' }).click()
  await preencher('Contas da casa', '500')
  await win.waitForTimeout(1_500)
})

test('histórico: arquivar competência e comparar com o orçamento vivo', async () => {
  // Mercado está no seed (800) e o auto-save já persistiu o perfil.
  await aba('Perfil').click()
  await win.locator('.btn-add', { hasText: 'Detalhar orçamento' }).click()

  // Arquiva a competência corrente (o input já vem com o mês de hoje).
  await win.locator('.hist .btn-add', { hasText: 'Arquivar' }).click()
  await expect(win.locator('.hist-comp')).toBeVisible({ timeout: 5_000 })

  // O mercado sobe no orçamento vivo (espera o auto-save chegar ao banco).
  await win.locator('.btn-add', { hasText: 'Voltar ao Perfil' }).click()
  await preencher('Mercado', '900')
  await win.waitForTimeout(1_500)

  // Compara o mês arquivado com o orçamento atual: +R$ 100 (+12,5%).
  await win.locator('.btn-add', { hasText: 'Detalhar orçamento' }).click()
  await win.locator('.hist-sel').first().selectOption({ index: 1 })
  const secao = win.locator('.hist-secao', { hasText: 'Despesas variáveis' })
  const linha = secao.locator('.hist-linha', { hasText: 'Mercado' })
  await expect(linha).toContainText('R$ 800,00 → R$ 900,00', {
    timeout: 5_000,
  })
  await expect(linha.locator('.hist-delta')).toContainText('12,5')
  // Despesa que sobe é sinalizada como ruim (vermelho semântico).
  await expect(linha.locator('.hist-delta')).toHaveClass(/ruim/)
})

test('planilha: sugestões de nome de rubrica via datalist', async () => {
  // Continuamos na planilha (teste anterior). Abre um grupo sem rubricas.
  const grupo = win.locator('.plan-grupo', { hasText: 'Contas da casa' })
  await grupo.locator('.plan-grupo-topo').click()
  expect(
    await win.locator('#sug-fixas-contas_casa option').count(),
  ).toBeGreaterThan(3)

  // A linha criada aponta para o datalist do campo.
  await grupo.locator('.plan-add').click()
  const nome = grupo.locator('.plan-linha .plan-nome').first()
  await expect(nome).toHaveAttribute('list', 'sug-fixas-contas_casa')

  // Limpeza: remove a rubrica de teste.
  await grupo.locator('.btn-remover').first().click()
  await expect(grupo.locator('.plan-linha')).toHaveCount(0)
})

test('importação: CSV do extrato vira rubricas após revisão', async () => {
  // Continuamos na planilha. Sobe um CSV pelo input escondido da seção —
  // dois lançamentos de débito, agrupáveis por estabelecimento.
  await win.locator('.imp input[type="file"]').setInputFiles({
    name: 'extrato.csv',
    mimeType: 'text/csv',
    buffer: Buffer.from(
      'Data,Descrição,Valor\n' +
        '05/06/2026,Conta de luz Enel,-180.50\n' +
        '12/06/2026,PADARIA SAO JOAO,-45.00\n',
    ),
  })

  // Com HF_MODO_DEGRADADO=1 não há LLM: o painel degrada para a
  // classificação manual (P8) — os grupos chegam do parser do core.
  await expect(win.locator('.imp-banner')).toContainText(
    'classificação manual',
    { timeout: 10_000 },
  )
  await expect(win.locator('.imp-linha')).toHaveCount(2)
  const linha = win.locator('.imp-linha', { hasText: 'Conta de luz Enel' })
  await expect(linha).toContainText('180,50') // total vem do core, formatado

  // Classifica só a luz (a padaria fica "não importar") e grava no vivo.
  await linha.locator('.imp-sel').selectOption('fixas/contas_casa')
  await win.locator('.imp-destino').selectOption('vivo')
  await win.locator('.imp .btn-add', { hasText: 'Importar' }).click()
  await expect(win.locator('.imp-feito')).toContainText('1 rubrica(s)', {
    timeout: 5_000,
  })

  // A rubrica entrou e o campo passou a valer a soma (roll-up do core).
  const grupo = win.locator('.plan-grupo', { hasText: 'Contas da casa' })
  await expect(grupo.locator('.plan-grupo-total')).toContainText('180,50')
  await expect(grupo.locator('.plan-chip')).toContainText('1 rubrica')

  // Limpeza: remove a rubrica importada e restaura o seed (500).
  const topo = grupo.locator('.plan-grupo-topo')
  if ((await topo.getAttribute('aria-expanded')) !== 'true') await topo.click()
  await grupo.locator('.btn-remover').first().click()
  await expect(grupo.locator('.plan-linha')).toHaveCount(0)
  await win.locator('.btn-add', { hasText: 'Voltar ao Perfil' }).click()
  await preencher('Contas da casa', '500')
  await win.waitForTimeout(1_500)
})

test('evolução: gráfico das competências arquivadas com zoom por campo', async () => {
  await win.locator('.btn-add', { hasText: 'Detalhar orçamento' }).click()

  // O teste "histórico" arquivou a competência corrente (mercado 800). O
  // gráfico pede 2+ meses: arquiva o mês ANTERIOR com o orçamento vivo
  // atual (mercado 900) — cronologicamente, o mês corrente fica por último.
  const hoje = new Date()
  const ant = new Date(hoje.getFullYear(), hoje.getMonth() - 1, 1)
  const mesAnterior = `${ant.getFullYear()}-${String(ant.getMonth() + 1).padStart(2, '0')}`
  await win.locator('.hist .hist-mes').fill(mesAnterior)
  await win.locator('.hist .btn-add', { hasText: 'Arquivar' }).click()

  // As 3 séries de totais (renda/fixas/variáveis) — tudo do core.
  await expect(win.locator('.evo-svg')).toBeVisible({ timeout: 5_000 })
  await expect(win.locator('.evo-linha')).toHaveCount(3)
  await expect(win.locator('.evo-legenda')).toContainText('Despesas variáveis')
  await expect(win.locator('.evo-mes')).toHaveCount(2)

  // Zoom no Mercado: uma série só; o rótulo final é o valor do core no
  // último mês arquivado (a competência corrente, com 800).
  await win.locator('.evo-zoom').selectOption('variaveis/mercado')
  await expect(win.locator('.evo-linha')).toHaveCount(1)
  await expect(win.locator('.evo-valor')).toContainText('800,00')
  await expect(win.locator('.evo-legenda')).toContainText('Mercado')
})
