/**
 * Preload: expõe uma superfície mínima e tipada ao renderer via contextBridge
 * (REQ-SEC-004). Nada de `ipcRenderer` cru nem Node no renderer.
 */
import { contextBridge, ipcRenderer } from 'electron'

contextBridge.exposeInMainWorld('hf', {
  // `metodoHttp` (T-2503, ADR-0022): sobrepõe a inferência padrão do main
  // (GET sem corpo / POST com corpo) — hoje só usado por `PUT /llm/config`.
  invoke: (
    metodo: string,
    payload?: unknown,
    metodoHttp?: 'GET' | 'POST' | 'PUT',
  ): Promise<unknown> => ipcRenderer.invoke('hf:invoke', metodo, payload, metodoHttp),
  // Diálogo nativo de salvar (exportações da tela Análise, T-902). O renderer
  // só recebe o caminho escolhido; quem escreve o arquivo é o sidecar.
  dialogoSalvar: (opcoes: unknown): Promise<string | null> =>
    ipcRenderer.invoke('hf:dialogo-salvar', opcoes),
  // Diálogo nativo de abrir (Configuração da IA, T-1702): aponta um `.gguf`
  // já presente no disco — o renderer só recebe o caminho, nunca o conteúdo.
  dialogoAbrir: (opcoes: unknown): Promise<string | null> =>
    ipcRenderer.invoke('hf:dialogo-abrir', opcoes),
})
