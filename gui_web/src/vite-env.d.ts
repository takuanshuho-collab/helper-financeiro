/// <reference types="vite/client" />

// Ponte exposta pelo preload do Electron (REQ-SEC-004). Ausente fora do Electron.
interface HfBridge {
  invoke<T = unknown>(metodo: string, payload?: unknown): Promise<T>
  dialogoSalvar(opcoes: {
    sugestao: string
    filtroNome: string
    extensoes: string[]
  }): Promise<string | null>
  /** Diálogo nativo de ABRIR (T-1702): aponta um `.gguf` já no disco. */
  dialogoAbrir(opcoes: { filtroNome: string; extensoes: string[] }): Promise<string | null>
}

interface Window {
  hf?: HfBridge
}
