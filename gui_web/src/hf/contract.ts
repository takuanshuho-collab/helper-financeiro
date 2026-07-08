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
  /** Rubricas do orçamento vivo (T-1103): a planilha e os selos "detalhado". */
  rubricas: RubricaOut[]
}

// --- Rubricas do orçamento (T-1103/T-1104, REQ-F-017) --------------------------

export type Categoria = 'renda' | 'fixas' | 'variaveis'

export interface RubricaOut {
  id: number
  categoria: Categoria
  campo_pai: string
  nome: string
  valor: number
  ordem: number
}

export interface RubricaNovaIn {
  categoria: Categoria
  campo_pai: string
  nome: string
  valor?: number
  ordem?: number
}

/** Toda mutação devolve a lista + o perfil já com o roll-up do core. */
export interface RubricaMutOut {
  rubricas: RubricaOut[]
  perfil: PerfilIn
}

// --- Histórico mensal (T-1203, REQ-F-019 / ADR-0013) ---------------------------

export interface VariacaoCampoOut {
  campo: string
  rotulo: string
  antes: number
  depois: number
  delta: number
  /** Fração (0.125 = +12,5%); null quando não havia base no mês anterior. */
  variacao_pct: number | null
}

export interface VariacaoSecaoOut {
  categoria: Categoria
  rotulo: string
  antes: number
  depois: number
  delta: number
  variacao_pct: number | null
  campos: VariacaoCampoOut[]
}

export interface ComparacaoOut {
  secoes: VariacaoSecaoOut[]
}

export interface HistoricoOut {
  meses: string[]
}

export interface ArquivadoOut {
  ok: boolean
  mes: string
  meses: string[]
}

export interface HistoricoComparadoOut {
  mes_a: string
  /** null = comparação contra o orçamento vivo. */
  mes_b: string | null
  comparacao: ComparacaoOut
}

// --- Evolução mensal (T-1304, REQ-F-022 / ADR-0014) ----------------------------

export interface SerieCampoOut {
  campo: string
  rotulo: string
  /** Um valor por competência, alinhado a `EvolucaoOut.meses` (core). */
  valores: number[]
}

export interface SerieSecaoOut {
  categoria: Categoria
  rotulo: string
  /** Total da seção por competência (sempre presente — eixo estável). */
  totais: number[]
  /** Só os campos com algum valor no período (zoom). */
  campos: SerieCampoOut[]
}

export interface EvolucaoOut {
  meses: string[]
  secoes: SerieSecaoOut[]
}

// --- Importação de CSV (T-1303, REQ-F-021 / ADR-0014) ---------------------------

/** Lançamentos do mesmo estabelecimento somados pelo core — candidato a rubrica. */
export interface GrupoImportadoOut {
  indice: number
  nome: string
  /** Soma absoluta calculada no parser determinístico (nunca pela LLM). */
  total: number
  quantidade: number
  natureza: 'credito' | 'debito'
  /** Rótulo sugerido pela LLM local; null = não classificado (revisão manual). */
  categoria: Categoria | null
  campo_pai: string | null
}

export interface CsvImportadoOut {
  /** 'ia' = classificado; 'manual' = LLM indisponível (P8); 'vazio' = sem grupos. */
  modo: 'ia' | 'manual' | 'vazio'
  grupos: GrupoImportadoOut[]
  /** 'AAAA-MM' detectada pela moda das datas do CSV; null sem datas. */
  competencia_sugerida: string | null
  avisos: string[]
  descartes: string[]
  motivos: string[]
  llm: DiagLlm
}

export interface ItemImportacaoIn {
  categoria: Categoria
  campo_pai: string
  nome: string
  valor: number
}

export interface ImportacaoAplicadaOut {
  ok: boolean
  /** null = aplicado no orçamento vivo; 'AAAA-MM' = na competência. */
  mes: string | null
  meses?: string[]
  rubricas: RubricaOut[]
  perfil: PerfilIn
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
  ocr: boolean // documento escaneado/imagem lido por OCR local (ADR-0015)
  llm: DiagLlm // alvo efetivo da LLM (para diagnóstico)
}

// --- Estado de uma chamada assíncrona (para as telas) ------------------------

export type Estado<T> =
  | { fase: 'ocioso' }
  | { fase: 'carregando' }
  | { fase: 'ok'; dados: T }
  | { fase: 'erro'; erro: string }
