import { useState } from 'react'

import { parsePct, pctBR } from '../lib/format'

/**
 * Campo de taxa mensal com sufixo "% a.m.". O perfil guarda a taxa como fração
 * decimal (0,025); aqui o usuário digita em percentual ("2,5"). Sem foco, exibe
 * a fração formatada; ao focar, mostra o rascunho editável. Nenhuma conta
 * financeira acontece aqui — só conversão de formato (REQ-NF-005).
 */
export default function CampoPercent({
  rotulo,
  valor,
  onValor,
}: {
  rotulo: string
  valor: number
  onValor: (n: number) => void
}) {
  const [foco, setFoco] = useState(false)
  const [rascunho, setRascunho] = useState('')

  const exibicao = foco ? rascunho : valor ? pctBR(valor) : ''

  return (
    <label className="campo">
      <span className="campo-rotulo">{rotulo}</span>
      <span className="campo-input">
        <input
          className="campo-num"
          inputMode="decimal"
          placeholder="0,0"
          value={exibicao}
          onFocus={() => {
            setRascunho(valor ? pctBR(valor) : '')
            setFoco(true)
          }}
          onChange={(ev) => {
            setRascunho(ev.target.value)
            onValor(parsePct(ev.target.value))
          }}
          onBlur={() => setFoco(false)}
        />
        <span className="campo-sufixo">% a.m.</span>
      </span>
    </label>
  )
}
