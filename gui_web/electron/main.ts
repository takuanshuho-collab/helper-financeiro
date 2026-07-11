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
  const dados = (await resp.json()) as { detail?: string; aguarde_s?: number }
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

function encerrarSidecar(): void {
  if (sidecar && !sidecar.killed) sidecar.kill()
  sidecar = null
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
        defaultPath: opcoes.sugestao,
        filters: [{ name: opcoes.filtroNome, extensions: opcoes.extensoes }],
      }
      const r = win
        ? await dialog.showSaveDialog(win, escolha)
        : await dialog.showSaveDialog(escolha)
      return r.canceled || !r.filePath ? null : r.filePath
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

app.on('window-all-closed', () => {
  encerrarSidecar()
  if (process.platform !== 'darwin') app.quit()
})
app.on('before-quit', encerrarSidecar)
