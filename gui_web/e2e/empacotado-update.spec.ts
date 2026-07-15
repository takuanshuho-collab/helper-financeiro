/**
 * Smoke do auto-update REAL (T-2302, ADR-0020 §M23/T-2302): sobe um feed
 * `generic` do electron-updater servido localmente, com uma `latest.yml` de
 * versão fictícia MAIOR que a do app corrente + um instalador-isca (arquivo
 * pequeno, nunca executado) com o `sha512` correto, aponta o app EMPACOTADO
 * para esse feed via `HF_AUTO_UPDATE=1`/`HF_UPDATE_URL` e confere que o
 * `electron-updater` 6.8 REAL (contra o Electron 43.1.1 do T-2301) reconhece
 * a atualização.
 *
 * Escada do HTTPS (decisão da ADR-0020) — **degrau 1 tentado e descartado
 * com evidência**: um servidor HTTPS local com certificado self-signed e a
 * CA injetada só no processo do teste via `NODE_EXTRA_CA_CERTS` falha
 * sempre com `net::ERR_CERT_AUTHORITY_INVALID` do Chromium. Motivo: o
 * `electron-updater` 6.8 baixa o feed via `electron.net.request`
 * (`electronHttpExecutor.js`), o stack de rede do PRÓPRIO Chromium — não o
 * `https`/`tls` do Node, que é o único que `NODE_EXTRA_CA_CERTS` afeta. Não
 * existe como o processo confiar numa CA de teste nesse caminho sem mudar a
 * validação global de certificados do Electron (superfície bem maior que o
 * necessário). Por isso o teste foi para o **degrau 2**: `main.ts`
 * (`configurarAutoUpdate`/`feedAceito`) passou a aceitar `http://`
 * EXCLUSIVAMENTE para o host literal `127.0.0.1` — mesmo precedente da
 * invariante H2 (o resto do app já só fala com o sidecar em loopback). A
 * segunda `test()` deste arquivo cobre que um `http://` NÃO-loopback
 * continua recusado.
 *
 * Asserção em escada: `update-available` é o mínimo aceitável (fecha o risco
 * documental da ADR); `update-downloaded` é o ideal — sem `.blockmap`
 * publicado no feed de teste, o electron-updater tenta o download
 * diferencial, falha (404) e cai no fallback de download completo (ver
 * `AppUpdater.differentialDownloadInstaller`), que baixa a isca inteira e
 * confere o `sha512` antes de disparar `update-downloaded`. Sem code signing
 * configurado neste build descartável, `verifyUpdateCodeSignature` não tem
 * `publisherName` para conferir (`app-update.yml` sem assinatura) e não
 * bloqueia — a instalação REAL fica fora do escopo (o Windows recusaria
 * trocar o binário sem assinatura, limitação do T-1002/C-15, não deste
 * teste).
 *
 * Os eventos são observados via LOG inofensivo em `main.ts`
 * (`configurarAutoUpdate`, 2 linhas de `console.log`) lido no stdout do
 * processo Electron (`ElectronApplication.process().stdout`) — o caminho de
 * MENOR mudança de produção: o `evaluate` do Playwright não tem `require`
 * disponível no contexto do main process (confirmado por sondagem direta
 * antes de escrever este teste), então não dá para reanexar listeners no
 * singleton do `electron-updater` de fora sem essa instrumentação. Nenhuma
 * mudança de comportamento do updater, só logging.
 *
 * Pré-requisito: `npm run dist` (ou `dist:dir`, que já basta — este smoke só
 * usa `release/win-unpacked`, não o instalador NSIS) em `gui_web/`. O pacote
 * gerado aqui é DESCARTÁVEL — nunca o build oficial do T-2303; não registre
 * hashes deste em lugar nenhum. Roda só com HF_E2E_PACOTE=1.
 */
import { createHash } from 'node:crypto'
import * as fs from 'node:fs'
import * as http from 'node:http'
import * as os from 'node:os'
import * as path from 'node:path'

import { _electron as electron, expect, test, type ElectronApplication } from '@playwright/test'

const EXE = path.resolve(__dirname, '..', 'release', 'win-unpacked', 'Helper Financeiro.exe')

test.skip(
  process.env.HF_E2E_PACOTE !== '1' || !fs.existsSync(EXE),
  'smoke do pacote: rode `npm run dist` (ou `dist:dir`) e defina HF_E2E_PACOTE=1',
)

// Versão fictícia SEMPRE maior que a do app corrente (2.x do package.json) —
// o updater só dispara update-available se a comparação semver for maior.
const VERSAO_FICTICIA = '99.0.0'
const NOME_INSTALADOR = `HelperFinanceiro-Setup-${VERSAO_FICTICIA}.exe`

// "Instalador" isca: conteúdo mínimo, só para o updater ter algo pra baixar
// e conferir por hash. NUNCA é executado — a instalação real fica fora
// (ver docstring do arquivo).
const CONTEUDO_INSTALADOR = Buffer.concat([Buffer.from('MZ'), Buffer.alloc(4096, 9)])
const SHA512_BASE64 = createHash('sha512').update(CONTEUDO_INSTALADOR).digest('base64')

function subirServidorFeed(dirTmp: string): Promise<{ servidor: http.Server; url: string }> {
  return new Promise((resolve) => {
    const servidor = http.createServer((req, res) => {
      // O provider `generic` do electron-updater anexa `?noCache=...` no
      // arquivo de canal (`newUrlFromBase`, `addRandomQueryToAvoidCaching`)
      // — compara só o pathname, não a URL crua.
      const rota = new URL(req.url ?? '/', 'http://127.0.0.1').pathname
      if (rota === '/latest.yml') {
        const corpo = fs.readFileSync(path.join(dirTmp, 'latest.yml'))
        res.writeHead(200, { 'Content-Type': 'text/yaml', 'Content-Length': String(corpo.length) })
        res.end(corpo)
      } else if (rota === `/${NOME_INSTALADOR}`) {
        res.writeHead(200, { 'Content-Length': String(CONTEUDO_INSTALADOR.length) })
        res.end(CONTEUDO_INSTALADOR)
      } else {
        res.writeHead(404)
        res.end()
      }
    })
    // 127.0.0.1 explícito (não localhost): é exatamente o host que o degrau
    // 2 de `main.ts` aceita sobre http:// — o teste teria que servir por
    // HTTPS de novo se usasse outro host.
    servidor.listen(0, '127.0.0.1', () => {
      const porta = (servidor.address() as { port: number }).port
      resolve({ servidor, url: `http://127.0.0.1:${porta}/` })
    })
  })
}

function ambienteBase(dirTmp: string) {
  return {
    ...process.env,
    // Ambiente isolado (mesmo padrão dos smokes irmãos): nada toca o
    // perfil real do usuário nem precisa do onboarding do cofre — o
    // auto-update roda independente da tela mostrada.
    HF_DB_PATH: path.join(dirTmp, 'dados.db'),
    HF_AUTH_PATH: path.join(dirTmp, 'auth.json'),
    HF_AUTO_LOCK_MIN: '1440',
    HF_MODELOS_DIR: path.join(dirTmp, 'modelos'),
    HF_LLM_CONFIG_PATH: path.join(dirTmp, 'llm.json'),
  }
}

async function capturarSaida(app: ElectronApplication): Promise<{ saida: () => string }> {
  let capturado = ''
  app.process().stdout?.on('data', (d: Buffer) => {
    capturado += d.toString()
  })
  app.process().stderr?.on('data', (d: Buffer) => {
    capturado += d.toString()
  })
  return { saida: () => capturado }
}

test.describe.configure({ mode: 'serial' })

let app: ElectronApplication
let servidor: http.Server
let dirTmp: string
let stdout: () => string

test.beforeAll(async () => {
  dirTmp = fs.mkdtempSync(path.join(os.tmpdir(), 'hf-e2e-pacote-update-'))

  fs.writeFileSync(
    path.join(dirTmp, 'latest.yml'),
    [
      `version: ${VERSAO_FICTICIA}`,
      'files:',
      `  - url: ${NOME_INSTALADOR}`,
      `    sha512: ${SHA512_BASE64}`,
      `    size: ${CONTEUDO_INSTALADOR.length}`,
      `path: ${NOME_INSTALADOR}`,
      `sha512: ${SHA512_BASE64}`,
      `releaseDate: '${new Date().toISOString()}'`,
      '',
    ].join('\n'),
  )

  const feed = await subirServidorFeed(dirTmp)
  servidor = feed.servidor

  app = await electron.launch({
    executablePath: EXE,
    args: [],
    env: {
      ...ambienteBase(dirTmp),
      HF_AUTO_UPDATE: '1',
      // Degrau 2 da escada HTTPS (ver docstring do arquivo): http://
      // aceito só porque o host é 127.0.0.1 literal.
      HF_UPDATE_URL: feed.url,
    },
  })
  stdout = (await capturarSaida(app)).saida
})

test.afterAll(async () => {
  await app?.close().catch(() => {})
  servidor?.close()
  fs.rmSync(dirTmp, { recursive: true, force: true })
})

test('auto-update: feed http://127.0.0.1 aceito e o updater real reporta a atualização', async () => {
  // O app precisa terminar de subir (janela + sidecar) para o boot chegar a
  // `configurarAutoUpdate()`; não depende do cofre, então só confere a
  // janela inicial.
  const win = await app.firstWindow()
  await win.waitForSelector('.auth-card, .app', { timeout: 30_000 })

  // Régua mínima (fecha o risco documental da ADR-0020): o updater REAL viu
  // a versão fictícia como disponível. Condição real observada no stdout do
  // main process — nenhum timeout arbitrário além do teto do próprio teste.
  await expect
    .poll(() => stdout(), { timeout: 30_000 })
    .toContain(`[auto-update] update-available: ${VERSAO_FICTICIA}`)

  // Régua ideal: download completo (fallback ao diferencial, que falha sem
  // .blockmap publicado) + sha512 conferido.
  const chegouADownloaded = await expect
    .poll(() => stdout(), { timeout: 30_000 })
    .toContain(`[auto-update] update-downloaded: ${VERSAO_FICTICIA}`)
    .then(() => true)
    .catch(() => false)
  if (!chegouADownloaded) {
    // Não falha o teste (a régua mínima já fechou o risco) — só documenta.
    console.warn(
      '[smoke auto-update] não chegou a update-downloaded dentro do prazo; stdout capturado:\n' + stdout(),
    )
  }
})

test('auto-update: http:// não-loopback continua recusado (degrau 2 não abre exceção geral)', async () => {
  const dirTmp2 = fs.mkdtempSync(path.join(os.tmpdir(), 'hf-e2e-pacote-update-rejeicao-'))
  const app2 = await electron.launch({
    executablePath: EXE,
    args: [],
    env: {
      ...ambienteBase(dirTmp2),
      HF_AUTO_UPDATE: '1',
      // IP público qualquer (não precisa responder — a rejeição acontece
      // ANTES de qualquer request, na validação de `feedAceito`).
      HF_UPDATE_URL: 'http://93.184.216.34/latest.yml',
    },
  })
  try {
    const { saida } = await capturarSaida(app2)
    const win2 = await app2.firstWindow()
    await win2.waitForSelector('.auth-card, .app', { timeout: 30_000 })
    await expect.poll(() => saida(), { timeout: 15_000 }).toContain('HF_AUTO_UPDATE=1 ignorado')
    // Nunca chega a configurar o feed nem a checar atualização.
    expect(saida()).not.toContain('[auto-update] update-available')
  } finally {
    await app2.close().catch(() => {})
    fs.rmSync(dirTmp2, { recursive: true, force: true })
  }
})
