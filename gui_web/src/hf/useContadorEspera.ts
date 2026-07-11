/**
 * Contador regressivo do anti-brute-force do cofre (429, REQ-SEC-005).
 *
 * O sidecar devolve `aguarde_s` (float) no corpo do 429 — as telas de
 * desbloqueio/onboarding chamam `definir(aguardeS)` no catch e usam
 * `segundos` para desabilitar o submit até zerar, sem novo `setInterval` por
 * tela (a mesma lógica seria repetida em Onboarding e Desbloqueio).
 */
import { useEffect, useState } from 'react'

export function useContadorEspera(): [number, (segundos: number) => void] {
  const [segundos, setSegundos] = useState(0)

  useEffect(() => {
    if (segundos <= 0) return
    const id = setTimeout(() => setSegundos((s) => Math.max(0, s - 1)), 1000)
    return () => clearTimeout(id)
  }, [segundos])

  const definir = (novo: number) => setSegundos(Math.max(0, Math.ceil(novo)))
  return [segundos, definir]
}
