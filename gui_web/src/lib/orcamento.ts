/**
 * Metadados do orçamento por categoria (T-1104, REQ-F-017).
 *
 * Fonte única dos rótulos pt-BR das seções/campos usados pela aba Perfil e
 * pela Planilha de orçamento. Espelha `core.rubricas.CAMPOS_POR_CATEGORIA`
 * (derivado dos dataclasses do ADR-0008) — nenhum cálculo acontece aqui.
 */
import type { Categoria, RubricaOut } from '../hf/contract'

export interface CampoOrcamento {
  campo: string
  rotulo: string
}

export interface SecaoOrcamento {
  categoria: Categoria
  titulo: string
  cor: string
  campos: CampoOrcamento[]
}

export const SECOES_ORCAMENTO: SecaoOrcamento[] = [
  {
    categoria: 'renda',
    titulo: 'Renda líquida mensal',
    cor: 'var(--green)',
    campos: [
      { campo: 'salario_liquido', rotulo: 'Salário/benefício líquido' },
      { campo: 'renda_extra', rotulo: 'Renda extra/autônoma' },
      { campo: 'outras_rendas', rotulo: 'Outras rendas' },
    ],
  },
  {
    categoria: 'fixas',
    titulo: 'Despesas fixas',
    cor: 'var(--red)',
    campos: [
      { campo: 'moradia', rotulo: 'Moradia' },
      { campo: 'contas_casa', rotulo: 'Contas da casa' },
      { campo: 'transporte', rotulo: 'Transporte' },
      { campo: 'saude', rotulo: 'Saúde' },
      { campo: 'educacao', rotulo: 'Educação' },
      { campo: 'assinaturas', rotulo: 'Assinaturas/academia' },
      { campo: 'outras_fixas', rotulo: 'Outras fixas' },
    ],
  },
  {
    categoria: 'variaveis',
    titulo: 'Despesas variáveis',
    cor: 'var(--orange)',
    campos: [
      { campo: 'mercado', rotulo: 'Mercado' },
      { campo: 'lazer', rotulo: 'Lazer/delivery' },
      { campo: 'vestuario', rotulo: 'Vestuário/cuidados' },
      { campo: 'imprevistos', rotulo: 'Imprevistos' },
      { campo: 'outras_variaveis', rotulo: 'Outras variáveis' },
    ],
  },
]

/** Rubricas de um campo específico, na ordem do banco. */
export function rubricasDoCampo(
  rubricas: RubricaOut[],
  categoria: Categoria,
  campo: string,
): RubricaOut[] {
  return rubricas.filter(
    (r) => r.categoria === categoria && r.campo_pai === campo,
  )
}

/** Um campo está "detalhado" quando tem ao menos uma rubrica (ADR-0012). */
export function campoDetalhado(
  rubricas: RubricaOut[],
  categoria: Categoria,
  campo: string,
): boolean {
  return rubricasDoCampo(rubricas, categoria, campo).length > 0
}
