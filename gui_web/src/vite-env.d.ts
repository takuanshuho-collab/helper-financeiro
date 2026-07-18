/// <reference types="vite/client" />

import type { SseEventoRecebido } from './hf/contract'

// Ponte exposta pelo preload do Electron (REQ-SEC-004). Ausente fora do
// Electron. `declare global` porque este arquivo virou módulo (o `import
// type` acima) — sem o bloco, as interfaces ficariam locais ao módulo em vez
// de aumentar o escopo global.
declare global {
  interface HfBridge {
    /** `metodoHttp` sobrepõe a inferência padrão do main (GET sem corpo, POST
     * com corpo) — hoje só usado por `PUT /llm/config` (T-2503, ADR-0022). */
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
    /** Linha do tempo da análise sênior (T-2604, ADR-0023): o main abre/fecha
     * o `fetch` do SSE (token só no main, REQ-SEC-004) e empurra os frames
     * parseados por IPC push — o renderer nunca chama a rede diretamente. */
    sseIniciar(jobId: string): Promise<void>
    /** Aborta a leitura do stream (unmount/troca de aba/nova geração). */
    sseParar(jobId: string): Promise<void>
    /** Assina os eventos SSE de TODOS os jobs (a tela filtra pelo `jobId`
     * corrente). Devolve a função de remoção do listener. */
    onSseEvento(cb: (payload: SseEventoRecebido) => void): () => void
  }

  interface Window {
    hf?: HfBridge
  }
}
