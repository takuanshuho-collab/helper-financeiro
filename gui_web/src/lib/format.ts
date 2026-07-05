/** Formatação pt-BR e cores do diagnóstico (regras do Design/README.md). */

export const brl = (v: number): string =>
  v.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })

export const pct0 = (frac: number): string => `${(frac * 100).toFixed(0)}%`

export const taxaAm = (taxaMensal: number): string =>
  `${(taxaMensal * 100).toFixed(1)}% a.m.`

/** Cor da saúde financeira pela classificação do core. */
export function corSaude(classificacao: string): string {
  if (classificacao === 'Saudável') return 'var(--green)'
  if (classificacao === 'Atenção') return 'var(--orange)'
  return 'var(--red)'
}

/** Faixa de cor por taxa a.m.: ≥8% vermelho, ≥2,5% laranja, senão verde. */
export function faixaTaxa(taxaMensal: number): { cor: string; tint: string } {
  if (taxaMensal >= 0.08) return { cor: 'var(--red)', tint: 'var(--tint-red)' }
  if (taxaMensal >= 0.025)
    return { cor: 'var(--orange)', tint: 'var(--tint-orange)' }
  return { cor: 'var(--green)', tint: 'var(--tint-green)' }
}

/** Iniciais do tipo de dívida para o chip (ex.: "Cartão de crédito" → "CC"). */
export function iniciais(tipo: string): string {
  const palavras = tipo.split(/[\s(]+/).filter(Boolean)
  const letras = palavras.slice(0, 2).map((p) => p[0] ?? '')
  return letras.join('').toUpperCase() || '?'
}
