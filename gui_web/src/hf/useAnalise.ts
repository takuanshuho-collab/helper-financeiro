import { useEffect, useState } from 'react'

import { hf } from './client'
import type { DiagnosticoOut, EstrategiasOut, Estado, PerfilIn } from './contract'

export interface Analise {
  estado: Estado<DiagnosticoOut>
  diagnostico: DiagnosticoOut | null
  estrategias: EstrategiasOut | null
}

/**
 * Recalcula o diagnóstico + as estratégias a cada mudança do perfil/extra.
 * Toda a aritmética vem do sidecar (core) — o front só orquestra e apresenta
 * (REQ-NF-005). Mantém os números anteriores durante o recálculo (o sidecar
 * local responde em sub-ms), evitando piscar a tela.
 */
export function useAnalise(perfil: PerfilIn, extra = 0): Analise {
  const [estado, setEstado] = useState<Estado<DiagnosticoOut>>({
    fase: 'carregando',
  })
  const [estrategias, setEstrategias] = useState<EstrategiasOut | null>(null)

  useEffect(() => {
    let vivo = true
    Promise.all([hf.diagnostico(perfil), hf.estrategias(perfil, extra)])
      .then(([d, e]) => {
        if (!vivo) return
        setEstado({ fase: 'ok', dados: d })
        setEstrategias(e)
      })
      .catch((err: Error) => {
        if (vivo) setEstado({ fase: 'erro', erro: err.message })
      })
    return () => {
      vivo = false
    }
  }, [perfil, extra])

  const diagnostico = estado.fase === 'ok' ? estado.dados : null
  return { estado, diagnostico, estrategias }
}
