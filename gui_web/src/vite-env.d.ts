/// <reference types="vite/client" />

// Ponte exposta pelo preload do Electron (REQ-SEC-004). Ausente fora do Electron.
interface HfBridge {
  invoke<T = unknown>(metodo: string, payload?: unknown): Promise<T>
  dialogoSalvar(opcoes: {
    sugestao: string
    filtroNome: string
    extensoes: string[]
  }): Promise<string | null>
}

interface Window {
  hf?: HfBridge
}
