/** Formatação pt-BR e cores do diagnóstico (regras do Design/README.md). */

export const brl = (v: number): string =>
  v.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })

/** Número no padrão pt-BR com 2 casas ("1.000,00"), sem o símbolo R$. */
export const numBR = (v: number): string =>
  v.toLocaleString('pt-BR', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })

/** Interpreta um texto pt-BR ("1.234,56", "R$ 800") como número (0 se vazio). */
export function parseBR(s: string): number {
  const limpo = s
    .replace(/\s|R\$/g, '')
    .replace(/\./g, '')
    .replace(',', '.')
  const n = Number.parseFloat(limpo)
  return Number.isFinite(n) ? n : 0
}

export const pct0 = (frac: number): string => `${(frac * 100).toFixed(0)}%`

export const taxaAm = (taxaMensal: number): string =>
  `${(taxaMensal * 100).toFixed(1)}% a.m.`

/** Formata uma fração decimal como percentual pt-BR sem símbolo ("0,025" → "2,5"). */
export const pctBR = (frac: number): string =>
  (frac * 100).toLocaleString('pt-BR', { maximumFractionDigits: 2 })

/** Interpreta um percentual pt-BR ("2,5") como fração decimal (0,025). */
export const parsePct = (s: string): number => parseBR(s) / 100

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

/** Carimbo da última análise sênior (T-2602) em pt-BR ("17/07/2026 21:34") a
 * partir do ISO-8601 que o sidecar já grava em horário LOCAL — a GUI só
 * FORMATA, nunca recalcula a assinatura nem interpreta o carimbo (REQ-NF-005).
 * ISO inválido devolve o texto cru (degradação segura: mostra algo, não quebra). */
export function carimboBR(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString('pt-BR', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}
