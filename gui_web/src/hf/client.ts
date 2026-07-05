/**
 * Cliente tipado da ponte com o sidecar (T-704).
 *
 * Envolve o primitivo `window.hf.invoke` (exposto pelo preload) em métodos
 * tipados e erros tipados. `HfErro.indisponivel` distingue "sidecar fora do ar
 * / fora do Electron" de um erro devolvido pelo backend.
 */
import type {
  DiagnosticoOut,
  EstrategiasOut,
  PerfilIn,
  SaudeOut,
} from './contract'

export class HfErro extends Error {
  constructor(
    mensagem: string,
    readonly indisponivel = false,
  ) {
    super(mensagem)
    this.name = 'HfErro'
  }
}

function ponte(): NonNullable<Window['hf']> {
  const b = window.hf
  if (!b) {
    throw new HfErro('sidecar indisponível (rode dentro do Electron)', true)
  }
  return b
}

async function chamar<T>(metodo: string, payload?: unknown): Promise<T> {
  try {
    return await ponte().invoke<T>(metodo, payload)
  } catch (e) {
    if (e instanceof HfErro) throw e
    throw new HfErro(e instanceof Error ? e.message : String(e))
  }
}

export const hf = {
  saude: (): Promise<SaudeOut> => chamar('/health'),
  diagnostico: (perfil: PerfilIn): Promise<DiagnosticoOut> =>
    chamar('/diagnostico', perfil),
  estrategias: (perfil: PerfilIn, extra = 0): Promise<EstrategiasOut> =>
    chamar('/estrategias', { perfil, extra }),
}
