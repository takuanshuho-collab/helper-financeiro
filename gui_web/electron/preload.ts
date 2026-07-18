/**
 * Preload: expõe uma superfície mínima e tipada ao renderer via contextBridge
 * (REQ-SEC-004). Nada de `ipcRenderer` cru nem Node no renderer.
 */
import { contextBridge, ipcRenderer, type IpcRendererEvent } from 'electron'

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
  // Linha do tempo da análise sênior (T-2604, ADR-0023): o main abre/fecha o
  // fetch do SSE (token só no main, REQ-SEC-004) e empurra os frames por IPC
  // push — nada de `ipcRenderer` cru no renderer.
  sseIniciar: (jobId: string): Promise<void> => ipcRenderer.invoke('hf:sse-iniciar', jobId),
  sseParar: (jobId: string): Promise<void> => ipcRenderer.invoke('hf:sse-parar', jobId),
  onSseEvento: (cb: (payload: unknown) => void): (() => void) => {
    const ouvinte = (_evento: IpcRendererEvent, payload: unknown): void => cb(payload)
    ipcRenderer.on('hf:sse-evento', ouvinte)
    return () => ipcRenderer.removeListener('hf:sse-evento', ouvinte)
  },
})
