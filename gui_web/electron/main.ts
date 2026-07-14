/**
 * Processo principal do Electron (ADR-0009 / REQ-SEC-004).
 *
 * Sobe o sidecar Python (`python -m sidecar`), lê o handshake com porta + token,
 * cria a janela com secure defaults e faz a ponte IPC: o renderer chama
 * `hf:invoke`, o main repassa ao sidecar em loopback com o token. O token vive
 * só aqui — o renderer nunca o vê nem fala com a rede diretamente.
 */
import { spawn, type ChildProcess } from 'node:child_process'
import * as fs from 'node:fs'
import * as path from 'node:path'
import * as readline from 'node:readline'

import { app, BrowserWindow, dialog, ipcMain, nativeTheme, session } from 'electron'
import { autoUpdater } from 'electron-updater'
import { Agent, fetch as fetchSidecar } from 'undici'

let sidecar: ChildProcess | null = null
let sidecarPort = 0
let sidecarToken = ''

// Última pasta usada nos diálogos de arquivo, mantida SÓ em memória e por sessão
// (ADR-0018, regra 2). O Electron 43 mudou o default de `showSaveDialog`/
// `showOpenDialog`: sem `defaultPath` explícito eles passam a abrir em Downloads
// em vez de lembrar a última pasta. Para preservar o comportamento antigo — o
// diálogo reabrir onde o usuário mexeu por último — guardamos aqui o diretório
// da última escolha não-cancelada e o injetamos como `defaultPath`. Nunca vai a
// disco: é um caminho pessoal (potencial PII), então some ao fechar o app.
let ultimoDiretorio = ''

// Monta o `defaultPath` do diálogo de salvar. A `sugestao` é sempre um nome de
// arquivo (ex.: "diagnostico_financeiro.xlsx"); se algum dia vier um caminho
// absoluto, o chamador está mandando a pasta e o respeitamos como está. Do
// contrário, ancoramos a sugestão no último diretório da sessão para reabrir
// onde o usuário salvou por último (comportamento pré-Electron 43).
function caminhoPadraoSalvar(sugestao: string): string {
  if (path.isAbsolute(sugestao)) return sugestao
  return ultimoDiretorio ? path.join(ultimoDiretorio, sugestao) : sugestao
}

// A extração por LLM local em CPU pode levar minutos. O undici (fetch do Node)
// aborta no headersTimeout/bodyTimeout padrão (~300s), cortando uma extração
// lenta-mas-funcional. Damos folga generosa aqui; o teto real é o HF_TIMEOUT do
// próprio sidecar. Ver ADR-0010.
const TIMEOUT_SIDECAR_MS = 15 * 60 * 1000
const dispatcherSidecar = new Agent({
  headersTimeout: TIMEOUT_SIDECAR_MS,
  bodyTimeout: TIMEOUT_SIDECAR_MS,
})

// dist-electron/ → gui_web/ → raiz do repositório (onde o pacote `sidecar` vive).
const repoRoot = path.resolve(__dirname, '..', '..')
const devUrl = process.env.HF_DEV_URL // ex.: http://localhost:5173 (iteração de UI)

// Interpretador do sidecar: respeita HF_PYTHON; senão prefere o venv do
// projeto (onde fastapi/uvicorn estão instalados); por fim, o python do PATH.
function pythonDoProjeto(): string {
  if (process.env.HF_PYTHON) return process.env.HF_PYTHON
  const candidatos = [
    path.join(repoRoot, '.venv', 'Scripts', 'python.exe'), // Windows
    path.join(repoRoot, '.venv', 'bin', 'python'), // POSIX
  ]
  return candidatos.find((c) => fs.existsSync(c)) ?? 'python'
}

// Comando do sidecar: no app EMPACOTADO é o exe congelado pelo PyInstaller
// (extraResources do electron-builder, T-1001); em desenvolvimento, o Python
// do projeto rodando o pacote.
function comandoSidecar(): { comando: string; args: string[]; cwd: string } {
  if (app.isPackaged) {
    const pasta = path.join(process.resourcesPath, 'sidecar-hf')
    const exe = process.platform === 'win32' ? 'sidecar-hf.exe' : 'sidecar-hf'
    return { comando: path.join(pasta, exe), args: [], cwd: pasta }
  }
  return { comando: pythonDoProjeto(), args: ['-m', 'sidecar'], cwd: repoRoot }
}

function iniciarSidecar(): Promise<void> {
  return new Promise((resolve, reject) => {
    const { comando, args, cwd } = comandoSidecar()
    // windowsHide: o exe congelado é console (handshake via stdout) — sem a
    // flag, o Windows abriria uma janela de terminal junto com o app.
    sidecar = spawn(comando, args, { cwd, windowsHide: true })
    sidecar.on('error', reject)
    // Ecoa os logs do sidecar (Python/uvicorn logam em stderr) no terminal do
    // Electron — assim erros de extração/provider ficam visíveis no `npm start`.
    sidecar.stderr?.on('data', (d: Buffer) => process.stderr.write(`[sidecar] ${d}`))
    const rl = readline.createInterface({ input: sidecar.stdout! })
    rl.once('line', (linha) => {
      try {
        const hs = JSON.parse(linha) as { port: number; token: string }
        sidecarPort = hs.port
        sidecarToken = hs.token
        rl.close()
        // Drena o stdout após o handshake (C-24): fechado o readline, ninguém
        // mais consome o pipe. Se o sidecar algum dia escrever >64 KB em stdout,
        // o pipe encheria e o Python bloquearia no write. `resume()` descarta
        // as escritas futuras e mantém o filho livre para prosseguir.
        sidecar?.stdout?.resume()
        resolve()
      } catch (err) {
        reject(err)
      }
    })
  })
}

// Prontidão (T-1001): o handshake diz a porta, mas o uvicorn ainda está
// subindo — só liberamos a janela quando o /health responder.
async function aguardarSaude(timeoutMs = 15_000): Promise<void> {
  const fim = Date.now() + timeoutMs
  for (;;) {
    try {
      const r = await fetchSidecar(`http://127.0.0.1:${sidecarPort}/health`, {
        dispatcher: dispatcherSidecar,
      })
      if (r.ok) return
    } catch {
      // porta ainda não abriu — tenta de novo
    }
    if (Date.now() > fim) {
      throw new Error('o sidecar não respondeu ao /health a tempo')
    }
    await new Promise((r) => setTimeout(r, 200))
  }
}

async function chamarSidecar(metodo: string, payload: unknown): Promise<unknown> {
  // C-10 (ADR-0018): `metodo` vem do renderer via IPC e é concatenado direto
  // na URL (`http://127.0.0.1:${porta}${metodo}`). Sem o `/` inicial a URL
  // fica mal-formada — rejeitamos ANTES de qualquer fetch, no mesmo formato
  // `__hfErro` que os erros HTTP já usam (ver comentário abaixo), para que o
  // `hf/client.ts` relance como `HfErro` tipado sem tratamento novo no
  // renderer. Nenhum chamador legítimo usa `metodo` sem barra hoje — isto só
  // fecha a superfície para uma chamada IPC já inválida.
  if (!metodo.startsWith('/')) {
    return {
      __hfErro: true as const,
      status: 400,
      detail: 'Método inválido (deve começar com "/")',
    }
  }
  const temCorpo = payload !== undefined && payload !== null
  const resp = await fetchSidecar(`http://127.0.0.1:${sidecarPort}${metodo}`, {
    method: temCorpo ? 'POST' : 'GET',
    headers: {
      'Content-Type': 'application/json',
      'X-HF-Token': sidecarToken,
    },
    body: temCorpo ? JSON.stringify(payload) : undefined,
    dispatcher: dispatcherSidecar,
  })
  // O corpo pode não ser JSON (C-06): um 500 imprevisto que escape de algum
  // handler do sidecar sem cair no `exception_handler(Exception)` genérico
  // (ex.: erro dentro do próprio ASGI, fora do alcance do FastAPI) ainda
  // devolveria o `PlainTextResponse` padrão do Starlette. Sem o try/catch, o
  // `resp.json()` lançaria uma exceção de parse crua, que atravessaria o
  // `ipcMain.handle` como rejeição de Promise — o structured-clone do
  // Electron preserva só `.message`, perdendo o `status` (essencial para o
  // gate 423/429, T-1604). Regressão exata ao padrão pré-T-1604.
  let dados: { detail?: string; aguarde_s?: number }
  try {
    dados = (await resp.json()) as { detail?: string; aguarde_s?: number }
  } catch {
    // Corpo não-JSON: nunca deixamos a exceção de parse escapar. Se a
    // resposta já não era `ok`, devolvemos `__hfErro` com o status real e um
    // detalhe genérico (o corpo original pode ser um stack trace do
    // Starlette — não repassamos ao renderer, REQ-SEC-003). Se a resposta
    // ERA `ok` (caso teórico: 2xx com corpo não-JSON, nenhuma rota do
    // sidecar faz isso hoje), tratamos como falha também — um "sucesso" sem
    // corpo interpretável não tem como o chamador consumir sem quebrar, e
    // devolver `__hfErro` aqui é o comportamento são: o renderer já sabe
    // lidar com esse formato em vez de receber `undefined`/lixo.
    return {
      __hfErro: true as const,
      status: resp.status,
      detail: 'Erro interno do serviço (resposta não-JSON)',
    }
  }
  if (!resp.ok) {
    // Erros de HTTP viram um objeto (não uma rejeição): o `ipcRenderer.invoke`
    // do Electron não preserva propriedades extras de um Error lançado através
    // do processo — o `status` (essencial para o gate 423 e o contador do 429,
    // T-1604) se perderia. `hf/client.ts` reconhece o formato `__hfErro` e
    // relança como `HfErro` tipado no renderer.
    return {
      __hfErro: true as const,
      status: resp.status,
      detail: dados.detail ?? `HTTP ${resp.status}`,
      aguarde_s: dados.aguarde_s,
    }
  }
  return dados
}

function aplicarCsp(): void {
  // Permissões web (câmera/microfone/geolocalização...): negadas por padrão —
  // o app é 100% local e não usa nenhuma (T-1003).
  session.defaultSession.setPermissionRequestHandler((_wc, _permissao, cb) =>
    cb(false),
  )
  // CSP por header cobre o modo dev (HF_DEV_URL/http); o app empacotado
  // (file://) é coberto pela META equivalente no index.html.
  session.defaultSession.webRequest.onHeadersReceived((detalhes, cb) => {
    cb({
      responseHeaders: {
        ...detalhes.responseHeaders,
        'Content-Security-Policy': [
          "default-src 'self'; script-src 'self'; " +
            "style-src 'self' 'unsafe-inline'; img-src 'self' data:; " +
            "font-src 'self' data:; connect-src 'self'; " +
            "object-src 'none'; base-uri 'none'",
        ],
      },
    })
  })
}

function criarJanela(): void {
  const win = new BrowserWindow({
    width: 1280,
    height: 840,
    // Cor de fundo ANTES do primeiro paint (evita flash branco no escuro).
    // Segue o SO; a escolha persistida (hf_dark) é do renderer (T-904).
    backgroundColor: nativeTheme.shouldUseDarkColors ? '#15131e' : '#f4f1ea',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      // DevTools só em desenvolvimento (T-1003): no pacote, Ctrl+Shift+I
      // não abre inspeção de um app que exibe dados financeiros pessoais.
      devTools: !app.isPackaged,
    },
  })

  // Nunca abrir janelas novas nem navegar para fora do app.
  win.webContents.setWindowOpenHandler(() => ({ action: 'deny' }))
  win.webContents.on('will-navigate', (evento, url) => {
    if (devUrl && url.startsWith(devUrl)) return
    evento.preventDefault()
  })

  if (devUrl) {
    void win.loadURL(devUrl)
  } else {
    void win.loadFile(path.join(__dirname, '..', 'dist', 'index.html'))
  }
}

/**
 * Auto-updater OPT-IN (T-1002, REQ-SEC-004): desligado por padrão; só roda
 * no app empacotado, com HF_AUTO_UPDATE=1 e feed HTTPS (HF_UPDATE_URL, que
 * sobrepõe o placeholder do app-update.yml). No Windows o electron-updater
 * só aplica pacote com assinatura compatível com a do app instalado — a
 * distribuição de produção deve ser assinada (code signing).
 */
function configurarAutoUpdate(): void {
  if (!app.isPackaged || process.env.HF_AUTO_UPDATE !== '1') return
  const feed = process.env.HF_UPDATE_URL ?? ''
  if (!feed.startsWith('https://')) {
    console.warn(
      'HF_AUTO_UPDATE=1 ignorado: defina HF_UPDATE_URL com o feed HTTPS.',
    )
    return
  }
  autoUpdater.setFeedURL({ provider: 'generic', url: feed })
  autoUpdater.on('error', (err) =>
    console.warn('Auto-update indisponível:', err.message),
  )
  void autoUpdater.checkForUpdatesAndNotify()
}

// Prazo do encerramento gracioso do sidecar antes do kill duro. Curto de
// propósito: o quit do app nunca pode ficar preso esperando o filho.
const PRAZO_ENCERRAR_SIDECAR_MS = 3_000

let sidecarEncerrado = false

/**
 * Encerramento GRACIOSO do sidecar (C-11), com prazo e kill como último recurso.
 *
 * No Windows não existe SIGTERM: um `sidecar.kill()` seco é TerminateProcess e
 * o lifespan do FastAPI nunca roda — o SQLCipher não fecha e o `llama-server`
 * neto fica órfão (coberto na raiz pelo Job Object do sidecar, C-02; aqui
 * garantimos também o caminho limpo). Por isso pedimos `POST /encerrar` (o
 * sidecar sai do loop do uvicorn e roda o shutdown) e AGUARDAMOS o `exit` até
 * `PRAZO_ENCERRAR_SIDECAR_MS`. Se estourar, `kill()`. Idempotente e nunca
 * lança — é chamado no caminho de quit.
 */
async function encerrarSidecar(): Promise<void> {
  const proc = sidecar
  sidecar = null
  if (!proc || proc.killed || proc.exitCode !== null) return

  const saiu = new Promise<void>((resolve) => proc.once('exit', () => resolve()))
  // O POST é disparado SEM await: só o `exit` (ou o prazo) decide a espera.
  // Aguardá-lo aqui reintroduziria o travamento que o prazo existe para
  // impedir — um sidecar deadlockado aceita a conexão e nunca responde,
  // prendendo o quit no timeout de 15 min do undici.
  chamarSidecar('/encerrar', {}).catch(() => {
    // O sidecar pode já ter caído/cortado a conexão — o prazo/kill resolve.
  })
  const prazo = new Promise<void>((resolve) =>
    setTimeout(resolve, PRAZO_ENCERRAR_SIDECAR_MS),
  )
  await Promise.race([saiu, prazo])
  if (!proc.killed && proc.exitCode === null) proc.kill() // último recurso
}

void app.whenReady().then(async () => {
  aplicarCsp()
  ipcMain.handle('hf:invoke', (_evento, metodo: string, payload: unknown) =>
    chamarSidecar(metodo, payload),
  )
  // Exportações (T-902): o renderer pede o diálogo nativo e recebe só o
  // caminho; o arquivo em si é escrito pelo sidecar (núcleo Python).
  ipcMain.handle(
    'hf:dialogo-salvar',
    async (
      _evento,
      opcoes: { sugestao: string; filtroNome: string; extensoes: string[] },
    ) => {
      const win = BrowserWindow.getFocusedWindow()
      const escolha = {
        defaultPath: caminhoPadraoSalvar(opcoes.sugestao),
        filters: [{ name: opcoes.filtroNome, extensions: opcoes.extensoes }],
      }
      const r = win
        ? await dialog.showSaveDialog(win, escolha)
        : await dialog.showSaveDialog(escolha)
      const caminho = r.canceled || !r.filePath ? null : r.filePath
      // Lembra a pasta escolhida para o próximo diálogo da sessão (ver
      // `ultimoDiretorio`). Só na escolha efetiva; cancelar não mexe.
      if (caminho) ultimoDiretorio = path.dirname(caminho)
      return caminho
    },
  )
  // Gestor de modelos GGUF (T-1702): aponta um `.gguf` já baixado pelo
  // usuário fora do catálogo — o main só devolve o caminho escolhido, nunca
  // lê o conteúdo (quem valida existência/extensão é o sidecar).
  ipcMain.handle(
    'hf:dialogo-abrir',
    async (_evento, opcoes: { filtroNome: string; extensoes: string[] }) => {
      const win = BrowserWindow.getFocusedWindow()
      const escolha = {
        properties: ['openFile'] as Array<'openFile'>,
        filters: [{ name: opcoes.filtroNome, extensions: opcoes.extensoes }],
        // Sem sugestão de nome aqui: injetamos só o último diretório da sessão
        // quando houver, para reabrir onde o usuário apontou por último
        // (comportamento pré-Electron 43). Vazio ⇒ default do SO.
        ...(ultimoDiretorio ? { defaultPath: ultimoDiretorio } : {}),
      }
      const r = win
        ? await dialog.showOpenDialog(win, escolha)
        : await dialog.showOpenDialog(escolha)
      const caminho =
        r.canceled || r.filePaths.length === 0 ? null : r.filePaths[0]
      if (caminho) ultimoDiretorio = path.dirname(caminho)
      return caminho
    },
  )

  try {
    await iniciarSidecar()
    await aguardarSaude()
  } catch (err) {
    console.error('Falha ao iniciar o sidecar:', err)
  }
  criarJanela()
  configurarAutoUpdate()

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) criarJanela()
  })
})

// Fechar todas as janelas pede o quit (fora do macOS, onde o app segue vivo);
// o encerramento do sidecar acontece uma única vez no `before-quit`.
app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') void app.quit()
})

// Encerramento gracioso com trava contra reentrância: `before-quit` dispara,
// seguramos o quit (`preventDefault`), aguardamos o sidecar encerrar e então
// chamamos `app.quit()` de novo — na 2ª passada a trava deixa o quit seguir.
// O prazo dentro de `encerrarSidecar` garante que isto nunca prende o app.
app.on('before-quit', (evento) => {
  if (sidecarEncerrado) return
  evento.preventDefault()
  sidecarEncerrado = true
  void encerrarSidecar().finally(() => app.quit())
})
