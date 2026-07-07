/**
 * Preload: expõe uma superfície mínima e tipada ao renderer via contextBridge
 * (REQ-SEC-004). Nada de `ipcRenderer` cru nem Node no renderer.
 */
import { contextBridge, ipcRenderer } from 'electron'

contextBridge.exposeInMainWorld('hf', {
  invoke: (metodo: string, payload?: unknown): Promise<unknown> =>
    ipcRenderer.invoke('hf:invoke', metodo, payload),
  // Diálogo nativo de salvar (exportações da tela Análise, T-902). O renderer
  // só recebe o caminho escolhido; quem escreve o arquivo é o sidecar.
  dialogoSalvar: (opcoes: unknown): Promise<string | null> =>
    ipcRenderer.invoke('hf:dialogo-salvar', opcoes),
})
