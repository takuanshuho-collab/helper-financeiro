/**
 * Contrato de dados entre o front e o sidecar (T-704 / REQ-NF-005).
 *
 * Espelha `sidecar/schemas.py` (entrada) e as respostas de `sidecar/app.py`
 * (saída). A fonte da verdade dos números é o `core` Python — estes tipos só
 * descrevem o formato que trafega pela ponte; nenhum cálculo acontece aqui.
 */

// --- Entrada: orçamento por categoria + dívidas -------------------------------

export interface DividaIn {
  credor: string
  tipo: string
  saldo_devedor?: number
  taxa_mensal?: number
  parcela?: number
  parcelas_restantes?: number
  garantia?: string
  em_atraso?: boolean
  dias_atraso?: number
  cet_anual?: number | null
}

export interface RendaIn {
  salario_liquido?: number
  renda_extra?: number
  outras_rendas?: number
}

export interface FixasIn {
  moradia?: number
  contas_casa?: number
  transporte?: number
  saude?: number
  educacao?: number
  assinaturas?: number
  outras_fixas?: number
}

export interface VariaveisIn {
  mercado?: number
  lazer?: number
  vestuario?: number
  imprevistos?: number
  outras_variaveis?: number
}

export interface PerfilIn {
  renda?: RendaIn
  fixas?: FixasIn
  variaveis?: VariaveisIn
  reserva_emergencia?: number
  saldo_fgts?: number
  dividas?: DividaIn[]
}

// --- Saída: diagnóstico determinístico ---------------------------------------

export interface DividaOut {
  credor: string
  tipo: string
  saldo_devedor: number
  taxa_mensal: number
  taxa_anual: number
  parcela: number
  parcelas_restantes: number
  custo_total_restante: number
  juros_restantes: number
  em_atraso: boolean
}

export interface DiagnosticoOut {
  renda_liquida: number
  despesas_totais: number
  despesas_fixas: number
  despesas_variaveis: number
  total_parcelas: number
  fluxo_caixa: number
  saldo_devedor_total: number
  juros_totais_futuros: number
  custo_total_ate_quitar: number
  taxa_media_ponderada: number
  comprometimento_renda: number
  classificacao: string
  classificacao_explicacao: string
  divida_mais_cara: DividaOut | null
  ranking: DividaOut[]
  tem_deficit: boolean
  meses_reserva: number | null
}

export interface EstrategiaOut {
  meses: number | null
  juros_pagos: number
  quitavel: boolean
  ordem: string[]
}

export interface EstrategiasOut {
  avalanche: EstrategiaOut
  bola_de_neve: EstrategiaOut
}

export interface SaudeOut {
  status: string
  servico: string
}

// --- Estado persistido (T-1102, REQ-F-018) ------------------------------------

export interface EstadoOut {
  /** Perfil salvo na sessão anterior; null na primeira execução. */
  perfil: PerfilIn | null
}

// --- Tela Análise (T-902, REQ-F-015) ------------------------------------------

export interface OportunidadeOut {
  credor: string
  tipo: string
  taxa_mensal: number
  parcelas_restantes: number
  parcela_atual: number
  parcela_nova: number
  economia_mensal: number
  economia_total: number
  vale_a_pena: boolean
}

export interface AnaliseOut {
  estrategias: EstrategiasOut
  economia_avalanche: number | null // juros bola de neve − avalanche (se ambas quitam)
  oportunidades: OportunidadeOut[]
  economia_total_portabilidade: number
  recomendacoes: string[]
}

export interface PassoRoteiroOut {
  credor: string
  abordagem: string
  argumentos: string[]
  concessoes: string[]
}

/** Seção da análise sênior, já com nomes reais (desanonimizada no sidecar). */
export interface SecaoIaOut {
  modo: 'completo' | 'degradado'
  motivos: string[]
  sumario: string
  diagnostico: string
  prioridades: string[]
  roteiro: PassoRoteiroOut[]
  alertas: string[]
  confianca: number
  aviso_legal: string
}

export interface IaJobOut {
  job_id: string
}

export interface IaStatusOut {
  job_id: string
  status: 'rodando' | 'pronto' | 'erro'
  secao: SecaoIaOut | null
  erro: string
}

export interface ExportadoOut {
  caminho: string
}

// --- Carta ao credor (T-903, REQ-F-016) ---------------------------------------

export type TipoProposta = 'quitacao' | 'portabilidade' | 'reducao'

export interface CartaCamposIn {
  divida: DividaIn
  tipo: TipoProposta
  valor_proposto?: number | null
  banco_concorrente?: string
  taxa_concorrente_mensal?: number | null
  nome_usuario?: string
  cpf?: string
  contrato?: string
}

/** Estrutura textual da carta, redigida inteira no core (fonte única). */
export interface CartaPreviaOut {
  tipo: TipoProposta
  titulo: string
  data: string
  destinatario: string
  referencia: string
  paragrafos: string[]
  assinatura: string
  cpf: string
}

// --- Extração de contrato PDF (T-901, REQ-F-014) -----------------------------

export interface CampoExtraidoOut {
  chave: string // "credor" | "tipo" | "saldo" | "taxa" | "parcela" | "restantes"
  rotulo: string
  valor: string // já no formato do formulário (pt-BR, taxa em %)
  fonte: string // citação verbatim do documento ("" na extração clássica)
  confianca: string // "90%" ou ""
}

export interface DiagLlm {
  provider: string
  base_url: string
  model: string
  endpoint_local: boolean
}

export interface ContratoExtraidoOut {
  modo: 'ia' | 'classico' | 'vazio'
  thread_id: string | null
  campos: CampoExtraidoOut[]
  descartados: string[] // ["taxa_mensal:SEM_FONTE", ...]
  inconsistencias: string[] // ["CRUZADA_PRICE:parcela", ...]
  motivos: string[] // por que a IA não rodou (ex.: "ERRO_PROVIDER:URLError")
  aviso: string
  llm: DiagLlm // alvo efetivo da LLM (para diagnóstico)
}

// --- Estado de uma chamada assíncrona (para as telas) ------------------------

export type Estado<T> =
  | { fase: 'ocioso' }
  | { fase: 'carregando' }
  | { fase: 'ok'; dados: T }
  | { fase: 'erro'; erro: string }
