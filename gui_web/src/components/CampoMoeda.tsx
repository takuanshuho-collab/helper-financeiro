import { useState } from 'react'

import { numBR, parseBR } from '../lib/format'

/**
 * Campo monetário com prefixo "R$", alinhado à direita.
 * Sem foco, exibe o valor do perfil formatado ("1.000,00"); ao focar, mostra
 * o número cru para edição livre e reporta o valor interpretado ao pai. A
 * soma/roll-up acontece no core (REQ-NF-005).
 */
export default function CampoMoeda({
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

  const exibicao = foco ? rascunho : valor ? numBR(valor) : ''

  return (
    <label className="campo">
      <span className="campo-rotulo">{rotulo}</span>
      <span className="campo-input">
        <span className="campo-prefixo">R$</span>
        <input
          className="campo-num"
          inputMode="decimal"
          placeholder="0,00"
          value={exibicao}
          onFocus={() => {
            setRascunho(valor ? String(valor).replace('.', ',') : '')
            setFoco(true)
          }}
          onChange={(ev) => {
            setRascunho(ev.target.value)
            onValor(Math.max(0, parseBR(ev.target.value)))
          }}
          onBlur={() => setFoco(false)}
        />
      </span>
    </label>
  )
}
