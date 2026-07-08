/**
 * Cliente tipado da ponte com o sidecar (T-704).
 *
 * Envolve o primitivo `window.hf.invoke` (exposto pelo preload) em métodos
 * tipados e erros tipados. `HfErro.indisponivel` distingue "sidecar fora do ar
 * / fora do Electron" de um erro devolvido pelo backend.
 */
import type {
  AnaliseOut,
  ArquivadoOut,
  CartaCamposIn,
  CartaPreviaOut,
  ContratoExtraidoOut,
  CsvImportadoOut,
  DiagnosticoOut,
  EstadoOut,
  EstrategiasOut,
  EvolucaoOut,
  ExportadoOut,
  HistoricoComparadoOut,
  HistoricoOut,
  IaJobOut,
  IaStatusOut,
  ImportacaoAplicadaOut,
  ItemImportacaoIn,
  PerfilIn,
  RubricaMutOut,
  RubricaNovaIn,
  SaudeOut,
  SecaoIaOut,
} from './contract'

export class HfErro extends Error {
  constructor(
    mensagem: string,
    readonly indisponivel = false,
  ) {
    super(mensagem)
    this.name = 'HfErro'
  }
}

function ponte(): NonNullable<Window['hf']> {
  const b = window.hf
  if (!b) {
    throw new HfErro('sidecar indisponível (rode dentro do Electron)', true)
  }
  return b
}

async function chamar<T>(metodo: string, payload?: unknown): Promise<T> {
  try {
    return await ponte().invoke<T>(metodo, payload)
  } catch (e) {
    if (e instanceof HfErro) throw e
    throw new HfErro(e instanceof Error ? e.message : String(e))
  }
}

export const hf = {
  saude: (): Promise<SaudeOut> => chamar('/health'),
  /** Estado salvo da sessão anterior (hidratação no boot, REQ-F-018). */
  estadoCarregar: (): Promise<EstadoOut> => chamar('/estado'),
  /** Auto-save do perfil completo (o sidecar valida e persiste no SQLite). */
  estadoSalvar: (perfil: PerfilIn): Promise<{ ok: boolean }> =>
    chamar('/estado', perfil),
  /** Rubricas (T-1104): toda mutação volta com o perfil recalculado no core. */
  rubricaCriar: (rubrica: RubricaNovaIn): Promise<RubricaMutOut> =>
    chamar('/rubricas', rubrica),
  rubricaEditar: (
    id: number,
    nome: string,
    valor: number,
  ): Promise<RubricaMutOut> => chamar(`/rubricas/${id}`, { nome, valor }),
  rubricaRemover: (id: number): Promise<RubricaMutOut> =>
    chamar(`/rubricas/${id}/remover`, {}),
  /** Histórico mensal (T-1203): arquivar competência e comparar meses. */
  historicoListar: (): Promise<HistoricoOut> => chamar('/historico'),
  historicoArquivar: (mes: string): Promise<ArquivadoOut> =>
    chamar('/historico/arquivar', { mes }),
  historicoComparar: (
    mesA: string,
    mesB: string | null = null,
  ): Promise<HistoricoComparadoOut> =>
    chamar('/historico/comparar', { mes_a: mesA, mes_b: mesB }),
  /** Séries prontas do core para o gráfico de evolução (T-1304). */
  historicoEvolucao: (): Promise<EvolucaoOut> => chamar('/historico/evolucao'),
  /** Importação de CSV (T-1303): parse + rótulos PARA REVISÃO, nada persiste. */
  importarCsv: (csvBase64: string, nome: string): Promise<CsvImportadoOut> =>
    chamar('/importar/csv', { csv_base64: csvBase64, nome }),
  /** Importação de comprovante/extrato ESCANEADO via OCR local (T-1405):
   * mesma revisão do CSV, só a entrada muda (imagem/PDF). */
  importarOcr: (arquivoBase64: string, nome: string): Promise<CsvImportadoOut> =>
    chamar('/importar/ocr', { arquivo_base64: arquivoBase64, nome }),
  /** Grava os itens revisados; `mes` null = orçamento vivo. */
  importarAplicar: (
    mes: string | null,
    itens: ItemImportacaoIn[],
  ): Promise<ImportacaoAplicadaOut> =>
    chamar('/importar/aplicar', { mes, itens }),
  diagnostico: (perfil: PerfilIn): Promise<DiagnosticoOut> =>
    chamar('/diagnostico', perfil),
  estrategias: (perfil: PerfilIn, extra = 0): Promise<EstrategiasOut> =>
    chamar('/estrategias', { perfil, extra }),
  contratoExtrair: (
    pdfBase64: string,
    nome: string,
  ): Promise<ContratoExtraidoOut> =>
    chamar('/contrato/extrair', { pdf_base64: pdfBase64, nome }),
  contratoConfirmar: (
    threadId: string,
    confirmacao: Record<string, string>,
  ): Promise<{ ok: boolean }> =>
    chamar('/contrato/confirmar', { thread_id: threadId, confirmacao }),
  analise: (perfil: PerfilIn, extra = 0, taxaAlvo = 0.018): Promise<AnaliseOut> =>
    chamar('/analise', { perfil, extra, taxa_alvo: taxaAlvo }),
  analiseIaIniciar: (perfil: PerfilIn, extra = 0): Promise<IaJobOut> =>
    chamar('/analise/ia', { perfil, extra }),
  analiseIaStatus: (jobId: string): Promise<IaStatusOut> =>
    chamar(`/analise/ia/${jobId}`),
  exportarPlanilha: (
    perfil: PerfilIn,
    caminho: string,
    extra = 0,
    taxaAlvo = 0.018,
  ): Promise<ExportadoOut> =>
    chamar('/exportar/planilha', { perfil, caminho, extra, taxa_alvo: taxaAlvo }),
  exportarRelatorio: (
    perfil: PerfilIn,
    caminho: string,
    extra = 0,
    taxaAlvo = 0.018,
    secaoIa: SecaoIaOut | null = null,
  ): Promise<ExportadoOut> =>
    chamar('/exportar/relatorio', {
      perfil,
      caminho,
      extra,
      taxa_alvo: taxaAlvo,
      secao_ia: secaoIa,
    }),
  cartaPrevia: (campos: CartaCamposIn): Promise<CartaPreviaOut> =>
    chamar('/carta/previa', campos),
  exportarCarta: (
    campos: CartaCamposIn,
    caminho: string,
  ): Promise<ExportadoOut> => chamar('/exportar/carta', { ...campos, caminho }),
  /** Diálogo nativo de salvar (Electron). Devolve o caminho ou null. */
  dialogoSalvar: (opcoes: {
    sugestao: string
    filtroNome: string
    extensoes: string[]
  }): Promise<string | null> => ponte().dialogoSalvar(opcoes),
}
