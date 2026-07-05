import { useState } from 'react'

import { parseBR } from '../lib/format'

/**
 * Campo monetário com prefixo "R$" e texto alinhado à direita.
 * Mantém o texto exatamente como digitado (vírgula preservada) e reporta o
 * número interpretado ao pai — a soma/roll-up acontece no core (REQ-NF-005).
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
  const [texto, setTexto] = useState(valor ? String(valor) : '')

  return (
    <label className="campo">
      <span className="campo-rotulo">{rotulo}</span>
      <span className="campo-input">
        <span className="campo-prefixo">R$</span>
        <input
          className="campo-num"
          inputMode="decimal"
          placeholder="0"
          value={texto}
          onChange={(ev) => {
            setTexto(ev.target.value)
            onValor(parseBR(ev.target.value))
          }}
        />
      </span>
    </label>
  )
}
