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

import { app, BrowserWindow, ipcMain, session } from 'electron'

let sidecar: ChildProcess | null = null
let sidecarPort = 0
let sidecarToken = ''

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

function iniciarSidecar(): Promise<void> {
  return new Promise((resolve, reject) => {
    const python = pythonDoProjeto()
    sidecar = spawn(python, ['-m', 'sidecar'], { cwd: repoRoot })
    sidecar.on('error', reject)
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

async function chamarSidecar(metodo: string, payload: unknown): Promise<unknown> {
  const temCorpo = payload !== undefined && payload !== null
  const resp = await fetch(`http://127.0.0.1:${sidecarPort}${metodo}`, {
    method: temCorpo ? 'POST' : 'GET',
    headers: {
      'Content-Type': 'application/json',
      'X-HF-Token': sidecarToken,
    },
    body: temCorpo ? JSON.stringify(payload) : undefined,
  })
  const dados = (await resp.json()) as { detail?: string }
  if (!resp.ok) {
    throw new Error(dados.detail ?? `HTTP ${resp.status}`)
  }
  return dados
}

function aplicarCsp(): void {
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
    backgroundColor: '#f4f1ea',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
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

function encerrarSidecar(): void {
  if (sidecar && !sidecar.killed) sidecar.kill()
  sidecar = null
}

void app.whenReady().then(async () => {
  aplicarCsp()
  ipcMain.handle('hf:invoke', (_evento, metodo: string, payload: unknown) =>
    chamarSidecar(metodo, payload),
  )

  try {
    await iniciarSidecar()
  } catch (err) {
    console.error('Falha ao iniciar o sidecar:', err)
  }
  criarJanela()

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) criarJanela()
  })
})

app.on('window-all-closed', () => {
  encerrarSidecar()
  if (process.platform !== 'darwin') app.quit()
})
app.on('before-quit', encerrarSidecar)
