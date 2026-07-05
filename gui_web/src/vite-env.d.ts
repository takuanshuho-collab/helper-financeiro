/// <reference types="vite/client" />

// Ponte exposta pelo preload do Electron (REQ-SEC-004). Ausente fora do Electron.
interface HfBridge {
  invoke<T = unknown>(metodo: string, payload?: unknown): Promise<T>
}

interface Window {
  hf?: HfBridge
}
