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
import { execFileSync } from 'node:child_process'
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

/**
 * T-2403 (ADR-0021, M24) — degrau final do smoke: feed servindo o
 * INSTALADOR NSIS REAL re-versionado (não mais o buffer-isca acima) e
 * ASSINADO, verificação de assinatura do electron-updater 6.8 real, e
 * instalação real (gated).
 *
 * Como o `verifyUpdateCodeSignature` decide (lido em
 * `node_modules/electron-updater/out/NsisUpdater.js` e
 * `windowsExecutableCodeSignatureVerifier.js`):
 *   1. `NsisUpdater.verifySignature` lê `publisherName` do `app-update.yml`
 *      DO APP INSTALADO/EM EXECUÇÃO (`configOnDisk`, resources\app-update.yml
 *      embarcado — NÃO do `latest.yml` do feed). Se ausente, verificação é
 *      pulada (`return null`) — é o que acontecia no smoke T-2302 (app não
 *      assinado). Aqui o app sob teste FOI assinado com
 *      `-c.win.signtoolOptions.publisherName`, então o app-update.yml
 *      embarcado tem `publisherName: [CN=Helper Financeiro (Teste)]`
 *      (confirmado lendo o arquivo gerado pelo `build_assinado.ps1`) — a
 *      verificação passa a rodar de verdade.
 *   2. Com publisherName presente, baixa o arquivo e roda
 *      `Get-AuthenticodeSignature -LiteralPath <arquivo baixado>` via
 *      PowerShell. Só aceita se `Status -eq 0` (Valid — cadeia de confiança
 *      verificável) E o Subject/CN do signer bater com o publisherName
 *      configurado. Ou seja: um cert de teste NÃO confiado (Root +
 *      TrustedPublisher ausentes) MESMO QUE seja o cert certo nunca dá
 *      `Status = Valid` — cai sempre em `ERR_UPDATER_INVALID_SIGNATURE`.
 *      É por isso que os cenários POSITIVOS abaixo (que dependem de
 *      `Status = Valid`) só passam com o cert confiado manualmente — o
 *      portão da ADR-0021.
 *
 * Artefatos pré-requisito (gerados MANUALMENTE fora do teste — o teste
 * nunca conhece senha nem roda signtool):
 *   release/app-sob-teste/win-unpacked/Helper Financeiro.exe
 *     `pwsh scripts/build_assinado.ps1` (sem -VersaoFake) com HF_CSC_PFX/
 *     HF_CSC_SENHA setados, depois copiar release/win-unpacked inteiro para
 *     release/app-sob-teste/win-unpacked ANTES do próximo build sobrescrever
 *     — é o app 2.13.0 assinado usado como "app sob teste" nos 3 cenários
 *     abaixo.
 *   release/feed-positivo/{latest.yml, "Helper Financeiro Setup 99.0.0.exe"}
 *     `pwsh scripts/build_assinado.ps1 -VersaoFake 99.0.0` (MESMO cert do
 *     app acima) — copiar os dois arquivos de release/ para
 *     release/feed-positivo/.
 *   release/feed-negativo/{latest.yml, "Helper Financeiro Setup 99.0.0.exe"}
 *     `npm run dist -- -c.extraMetadata.version=99.0.0` (SEM as envs
 *     HF_CSC_*) — instalador NÃO assinado; prova a recusa sem precisar de
 *     um segundo certificado descartável (ADR-0021 permite as duas opções;
 *     esta é a mais simples e não deixa um segundo cert no host `My`).
 *
 * Nenhum destes três caminhos é versionado (ficam fora do `.gitignore`
 * porque `release/` já é ignorado inteiro — ver `.gitignore` da gui_web).
 */

const CERT_SUBJECT_TESTE = 'CN=Helper Financeiro (Teste)'
const VERSAO_FICTICIA_REAL = '99.0.0'
const NOME_INSTALADOR_REAL = `Helper Financeiro Setup ${VERSAO_FICTICIA_REAL}.exe`

const APP_SOB_TESTE = path.resolve(
  __dirname, '..', 'release', 'app-sob-teste', 'win-unpacked', 'Helper Financeiro.exe',
)
const FEED_POSITIVO_DIR = path.resolve(__dirname, '..', 'release', 'feed-positivo')
const FEED_NEGATIVO_DIR = path.resolve(__dirname, '..', 'release', 'feed-negativo')

const ARTEFATOS_T2403_PRONTOS =
  fs.existsSync(APP_SOB_TESTE) &&
  fs.existsSync(path.join(FEED_POSITIVO_DIR, 'latest.yml')) &&
  fs.existsSync(path.join(FEED_NEGATIVO_DIR, 'latest.yml'))

const MSG_ARTEFATOS_AUSENTES =
  'artefatos do T-2403 ausentes (release/app-sob-teste, release/feed-positivo, ' +
  'release/feed-negativo) — gere-os com scripts/preparar_cert_teste.ps1 + ' +
  'scripts/build_assinado.ps1 (ver docstring deste arquivo).'

// Roda um .ps1 efêmero em vez de `-Command` inline: evita todo o problema de
// escaping de aspas entre shell do teste / PowerShell / valores com espaço
// (o nome do instalador real tem espaços). `powershell.exe` (não `pwsh`) —
// mesmo binário que o electron-updater usa em
// `windowsExecutableCodeSignatureVerifier.js` (`preparePowerShellExec`).
function rodarPowerShell(linhas: string[], timeoutMs = 30_000): string {
  const scriptPath = path.join(
    os.tmpdir(),
    `hf-e2e-ps-${Date.now()}-${Math.random().toString(36).slice(2)}.ps1`,
  )
  // Reseta PSModulePath ANTES de qualquer coisa: mesmo workaround que o
  // electron-updater aplica em `preparePowerShellExec`
  // (windowsExecutableCodeSignatureVerifier.js) para o
  // https://github.com/electron-userland/electron-builder/issues/7127 —
  // sem isso, `Get-ChildItem Cert:\...` falha com "não existe uma unidade
  // chamada Cert" (autoload do módulo Microsoft.PowerShell.Security quebra
  // com um PSModulePath poluído, confirmado neste host).
  const conteudo = ["$env:PSModulePath = ''", ...linhas].join('\n')
  fs.writeFileSync(scriptPath, conteudo, 'utf-8')
  try {
    return execFileSync(
      'powershell.exe',
      ['-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', scriptPath],
      { encoding: 'utf-8', timeout: timeoutMs },
    )
  } finally {
    fs.rmSync(scriptPath, { force: true })
  }
}

// Portão manual do mantenedor (ADR-0021): o teste NUNCA importa o cert em
// Root/TrustedPublisher sozinho — só verifica se alguém (o mantenedor) já
// confiou nele antes.
function certDeTesteConfiado(): boolean {
  try {
    const saida = rodarPowerShell([
      `$s = '${CERT_SUBJECT_TESTE.replace(/'/g, "''")}'`,
      '$r = Get-ChildItem Cert:\\CurrentUser\\Root | Where-Object { $_.Subject -eq $s }',
      '$t = Get-ChildItem Cert:\\CurrentUser\\TrustedPublisher | Where-Object { $_.Subject -eq $s }',
      "if ($r -and $t) { Write-Output 'SIM' } else { Write-Output 'NAO' }",
    ])
    return saida.trim() === 'SIM'
  } catch {
    return false
  }
}

const CERT_CONFIADO = ARTEFATOS_T2403_PRONTOS && certDeTesteConfiado()

const MSG_CERT_NAO_CONFIADO =
  'cert de teste NÃO confiado neste host — portão MANUAL do mantenedor (ADR-0021, ' +
  'nunca automatizado pelo teste). Confie com as instruções impressas por ' +
  'scripts/preparar_cert_teste.ps1 (Export-Certificate + Import-Certificate em ' +
  `Cert:\\CurrentUser\\Root e Cert:\\CurrentUser\\TrustedPublisher, Subject '${CERT_SUBJECT_TESTE}').`

interface InstalacaoExistente {
  displayName: string
  displayVersion: string
  uninstallString: string
  installLocation: string
}

// Usado tanto na salvaguarda de aborto (antes de instalar) quanto na
// verificação pós-instalação e pós-limpeza. Prefixo, NÃO igualdade exata:
// confirmado neste host que instalações reais/antigas do Helper Financeiro
// podem registrar `DisplayName` com a versão embutida (ex.: "Helper
// Financeiro 2.5.0", formato de um instalador anterior ao NSIS atual) —
// uma comparação `-eq 'Helper Financeiro'` teria deixado passar essa
// instalação real batendo direto na salvaguarda (a) da ADR-0021. O prefixo
// pega os dois formatos (o antigo com versão embutida e o atual, sem).
function buscarHelperInstalado(): InstalacaoExistente | null {
  try {
    const saida = rodarPowerShell([
      "$r = Get-ChildItem 'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall' | ForEach-Object {",
      '  $p = Get-ItemProperty $_.PSPath -ErrorAction SilentlyContinue',
      "  if ($p.DisplayName -like 'Helper Financeiro*') { $p }",
      '} | Select-Object -First 1',
      // Chaves em camelCase DE PROPÓSITO: o JSON cruza a fronteira PowerShell→
      // TS e a interface InstalacaoExistente lê displayVersion/uninstallString —
      // com PascalCase tudo viria undefined (bug pego na 1ª rodada real do
      // fechamento: a versão instalada existia, mas a asserção lia undefined e
      // o cleanup não achava o uninstallString).
      'if ($r) { [PSCustomObject]@{ displayName = $r.DisplayName; displayVersion = $r.DisplayVersion; ' +
        'uninstallString = $r.UninstallString; installLocation = $r.InstallLocation } | ConvertTo-Json -Compress }',
    ])
    const texto = saida.trim()
    if (!texto) return null
    return JSON.parse(texto) as InstalacaoExistente
  } catch {
    return null
  }
}

// Caminho onde o electron-updater guarda o instalador baixado (BaseUpdater/
// DownloadedUpdateHelper: `%LOCALAPPDATA%\<updaterCacheDirName>\pending\
// <nome decodificado da URL>` — `updaterCacheDirName` vem do
// app-update.yml embarcado, `helper-financeiro-web-updater` neste build, ver
// docstring acima). Calculado aqui (não exposto pelo app) porque `main.ts`
// só loga a versão, não o caminho — instrumentar mais é o que a task pediu
// para NÃO fazer sem antes reportar.
function caminhoInstaladorPendente(): string {
  const localAppData = process.env.LOCALAPPDATA
  if (!localAppData) throw new Error('LOCALAPPDATA não definido — ambiente Windows inesperado.')
  return path.join(localAppData, 'helper-financeiro-web-updater', 'pending', NOME_INSTALADOR_REAL)
}

// Mesmos args que `NsisUpdater.doInstall` usa no caminho `isSilent` sem
// elevação/diretório customizado (ver node_modules/electron-updater/out/
// NsisUpdater.js) — reproduzido aqui em vez de chamado via `quitAndInstall`
// porque `main.ts` não expõe IPC nenhum para disparar o updater a partir do
// processo de teste (não há `require` no contexto do `evaluate` do
// Playwright para alcançar o singleton diretamente, mesma limitação
// documentada no topo do arquivo para o log). Instrumentar `main.ts` está
// fora do escopo autorizado desta task.
function instalarSilenciosamente(caminhoInstalador: string): void {
  execFileSync(caminhoInstalador, ['--updated', '/S'], { timeout: 120_000 })
}

function desinstalarSilenciosamente(uninstallString: string): void {
  // `UninstallString` do NSIS vem como `"C:\...\Uninstall Helper Financeiro.exe"`
  // (com aspas em volta do caminho).
  const casado = uninstallString.match(/^"([^"]+)"/)
  const exe = casado ? casado[1] : uninstallString.trim()
  execFileSync(exe, ['/S'], { timeout: 120_000 })
}

// O (des)instalador NSIS spawna uma cópia de si mesmo e RETORNA antes de a
// remoção/gravação terminar (comportamento clássico do NSIS sem `_?=`) — o
// exit do processo NÃO é a condição real. Padrão T-1907: poll do registro
// até a condição esperada, nunca checagem única nem sleep fixo. (Pego na 1ª
// rodada real do fechamento: o uninstall funcionava, mas a checagem imediata
// ainda via a entrada.)
async function aguardarRegistro(
  condicao: (entrada: InstalacaoExistente | null) => boolean,
  descricao: string,
  timeoutMs = 60_000,
): Promise<InstalacaoExistente | null> {
  const limite = Date.now() + timeoutMs
  let atual = buscarHelperInstalado()
  while (!condicao(atual)) {
    if (Date.now() > limite) {
      throw new Error(`timeout (${timeoutMs} ms) aguardando: ${descricao}; estado atual: ${JSON.stringify(atual)}`)
    }
    await new Promise((r) => setTimeout(r, 1_000))
    atual = buscarHelperInstalado()
  }
  return atual
}

// Serve um instalador NSIS REAL (não mais o buffer-isca) + o `latest.yml`
// gerado pelo próprio electron-builder — nenhum hash é forjado à mão aqui.
// Nomes de arquivo com espaço (productName "Helper Financeiro") exigem
// decodeURIComponent: o `URL()` do Node usado por
// `newUrlFromBase`/`resolveFiles` do electron-updater percent-encoda o
// pathname (`%20`) ao montar a URL de download a partir do `url:` do
// latest.yml.
function subirServidorFeedReal(dirFeed: string): Promise<{ servidor: http.Server; url: string }> {
  return new Promise((resolve) => {
    const servidor = http.createServer((req, res) => {
      const rota = decodeURIComponent(new URL(req.url ?? '/', 'http://127.0.0.1').pathname)
      const nomeArquivo = rota === '/latest.yml' ? 'latest.yml' : rota.replace(/^\//, '')
      const caminho = path.join(dirFeed, nomeArquivo)
      if (!fs.existsSync(caminho)) {
        res.writeHead(404)
        res.end()
        return
      }
      const tamanho = fs.statSync(caminho).size
      res.writeHead(200, {
        'Content-Type': nomeArquivo.endsWith('.yml') ? 'text/yaml' : 'application/octet-stream',
        'Content-Length': String(tamanho),
      })
      fs.createReadStream(caminho).pipe(res)
    })
    servidor.listen(0, '127.0.0.1', () => {
      const porta = (servidor.address() as { port: number }).port
      resolve({ servidor, url: `http://127.0.0.1:${porta}/` })
    })
  })
}

test.describe('feed assinado — verificação de assinatura e instalação real (T-2403, ADR-0021)', () => {
  test.describe.configure({ mode: 'default' })
  test.skip(!ARTEFATOS_T2403_PRONTOS, MSG_ARTEFATOS_AUSENTES)

  let appAssinado: ElectronApplication
  let servidorPositivo: http.Server
  let dirTmpPositivo: string
  let stdoutPositivo: () => string

  test.beforeAll(async () => {
    dirTmpPositivo = fs.mkdtempSync(path.join(os.tmpdir(), 'hf-e2e-feed-positivo-'))
    const feed = await subirServidorFeedReal(FEED_POSITIVO_DIR)
    servidorPositivo = feed.servidor
    appAssinado = await electron.launch({
      executablePath: APP_SOB_TESTE,
      args: [],
      env: {
        ...ambienteBase(dirTmpPositivo),
        HF_AUTO_UPDATE: '1',
        HF_UPDATE_URL: feed.url,
      },
    })
    stdoutPositivo = (await capturarSaida(appAssinado)).saida
  })

  test.afterAll(async () => {
    await appAssinado?.close().catch(() => {})
    servidorPositivo?.close()
    if (dirTmpPositivo) fs.rmSync(dirTmpPositivo, { recursive: true, force: true })
  })

  test('assinatura confiável: o updater REAL aceita o instalador NSIS assinado com o mesmo publisher', async () => {
    test.skip(!CERT_CONFIADO, MSG_CERT_NAO_CONFIADO)

    const win = await appAssinado.firstWindow()
    await win.waitForSelector('.auth-card, .app', { timeout: 30_000 })

    // Arquivo real de ~350MB por loopback: teto bem mais folgado que o do
    // buffer-isca dos cenários T-2302 acima.
    await expect
      .poll(() => stdoutPositivo(), { timeout: 120_000 })
      .toContain(`[auto-update] update-downloaded: ${VERSAO_FICTICIA_REAL}`)
    expect(stdoutPositivo()).not.toContain('ERR_UPDATER_INVALID_SIGNATURE')
  })

  test('instalação real: 99.0.0 fica instalado e a limpeza remove tudo (gated, HF_E2E_UPDATE_INSTALL=1)', async () => {
    test.skip(!CERT_CONFIADO, MSG_CERT_NAO_CONFIADO)
    test.skip(
      process.env.HF_E2E_UPDATE_INSTALL !== '1',
      'instalação real: defina HF_E2E_UPDATE_INSTALL=1 (além de HF_E2E_PACOTE=1) para rodar ' +
        'este cenário — ele instala e desinstala de verdade nesta máquina.',
    )

    // Salvaguarda (a), ANTES de qualquer coisa: nunca sobrescrever uma
    // instalação real do usuário (ADR-0021, risco aceito #1).
    const existenteAntes = buscarHelperInstalado()
    if (existenteAntes) {
      throw new Error(
        `ABORTADO: Helper Financeiro já está instalado nesta máquina (versão ` +
          `${existenteAntes.displayVersion}, em ${existenteAntes.installLocation}). Este cenário ` +
          'NUNCA sobrescreve uma instalação existente — rode-o só numa máquina/VM limpa, sem o ' +
          'Helper Financeiro instalado.',
      )
    }

    await expect
      .poll(() => stdoutPositivo(), { timeout: 120_000 })
      .toContain(`[auto-update] update-downloaded: ${VERSAO_FICTICIA_REAL}`)

    const instaladorPendente = caminhoInstaladorPendente()
    expect(
      fs.existsSync(instaladorPendente),
      `instalador pendente não encontrado em ${instaladorPendente}`,
    ).toBe(true)

    try {
      instalarSilenciosamente(instaladorPendente)

      const instalado = await aguardarRegistro(
        (e) => e !== null,
        'a instalação aparecer no registro de programas após o /S',
      )
      expect(instalado?.displayVersion).toBe(VERSAO_FICTICIA_REAL)
    } finally {
      // Salvaguarda (b), incondicional mesmo se a asserção acima falhar:
      // desinstala + confere remoção + limpa restos que o NSIS não apaga
      // sozinho (pasta e atalhos).
      const paraRemover = buscarHelperInstalado()
      if (paraRemover) {
        desinstalarSilenciosamente(paraRemover.uninstallString)
        const depoisDeRemover = await aguardarRegistro(
          (e) => e === null,
          'a desinstalação silenciosa remover a entrada do registro',
        )
        expect(depoisDeRemover, 'desinstalação silenciosa não removeu a entrada do registro').toBeNull()

        if (paraRemover.installLocation && fs.existsSync(paraRemover.installLocation)) {
          fs.rmSync(paraRemover.installLocation, { recursive: true, force: true })
        }
        const atalhos = [
          path.join(os.homedir(), 'Desktop', 'Helper Financeiro.lnk'),
          path.join(
            process.env.APPDATA ?? '',
            'Microsoft', 'Windows', 'Start Menu', 'Programs', 'Helper Financeiro.lnk',
          ),
        ]
        for (const atalho of atalhos) fs.rmSync(atalho, { force: true })
      }
    }
  })
})

test.describe('feed assinado — verificação negativa (roda SEM confiança do cert)', () => {
  test.describe.configure({ mode: 'default' })
  test.skip(!ARTEFATOS_T2403_PRONTOS, MSG_ARTEFATOS_AUSENTES)

  let appAssinado: ElectronApplication
  let servidorNegativo: http.Server
  let dirTmpNegativo: string
  let stdoutNegativo: () => string

  test.beforeAll(async () => {
    dirTmpNegativo = fs.mkdtempSync(path.join(os.tmpdir(), 'hf-e2e-feed-negativo-'))
    const feed = await subirServidorFeedReal(FEED_NEGATIVO_DIR)
    servidorNegativo = feed.servidor
    appAssinado = await electron.launch({
      executablePath: APP_SOB_TESTE,
      args: [],
      env: {
        ...ambienteBase(dirTmpNegativo),
        HF_AUTO_UPDATE: '1',
        HF_UPDATE_URL: feed.url,
      },
    })
    stdoutNegativo = (await capturarSaida(appAssinado)).saida
  })

  test.afterAll(async () => {
    await appAssinado?.close().catch(() => {})
    servidorNegativo?.close()
    if (dirTmpNegativo) fs.rmSync(dirTmpNegativo, { recursive: true, force: true })
  })

  // Este cenário NÃO depende de confiar o cert — um instalador não assinado
  // nunca passa em `Get-AuthenticodeSignature` (Status != Valid) e é
  // recusado independentemente da cadeia de confiança do host. É o único
  // cenário do T-2403 que a validação do executor confirma PASSED de
  // verdade (os dois acima ficam SKIPPED até o mantenedor confiar o cert).
  test('update NÃO assinado é recusado: o app sob teste (assinado) nunca aceita um pacote sem assinatura', async () => {
    const win = await appAssinado.firstWindow()
    await win.waitForSelector('.auth-card, .app', { timeout: 30_000 })

    await expect
      .poll(() => stdoutNegativo(), { timeout: 120_000 })
      .toContain('Auto-update indisponível')
    expect(stdoutNegativo()).toContain('is not signed by the application owner')
    expect(stdoutNegativo()).not.toContain(`[auto-update] update-downloaded: ${VERSAO_FICTICIA_REAL}`)
  })
})
