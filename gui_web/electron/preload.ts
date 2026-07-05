/**
 * Preload: expõe uma superfície mínima e tipada ao renderer via contextBridge
 * (REQ-SEC-004). Nada de `ipcRenderer` cru nem Node no renderer.
 */
import { contextBridge, ipcRenderer } from 'electron'

contextBridge.exposeInMainWorld('hf', {
  invoke: (metodo: string, payload?: unknown): Promise<unknown> =>
    ipcRenderer.invoke('hf:invoke', metodo, payload),
})
