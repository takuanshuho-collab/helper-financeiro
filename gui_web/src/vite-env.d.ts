/// <reference types="vite/client" />

// Ponte exposta pelo preload do Electron (REQ-SEC-004). Ausente fora do Electron.
interface HfBridge {
  /** `metodoHttp` sobrepõe a inferência padrão do main (GET sem corpo, POST com
   * corpo) — hoje só usado por `PUT /llm/config` (T-2503, ADR-0022). */
  invoke<T = unknown>(
    metodo: string,
    payload?: unknown,
    metodoHttp?: 'GET' | 'POST' | 'PUT',
  ): Promise<T>
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
