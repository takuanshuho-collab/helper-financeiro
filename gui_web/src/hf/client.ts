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
  AuthCadastroOut,
  AuthStatusOut,
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
  LlmBaixarStatusOut,
  LlmCatalogoOut,
  LlmJobOut,
  LlmModeloDefinidoOut,
  LlmStatusOut,
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
    /** Código HTTP do sidecar, quando conhecido (423 = cofre bloqueado, 429 =
     * anti-brute-force, 401 = fator incorreto, 400 = política/validação). */
    readonly status?: number,
    /** Só presente no 429 (`aguarde_s` do corpo, REQ-SEC-005) — contador da GUI. */
    readonly aguardeS?: number,
  ) {
    super(mensagem)
    this.name = 'HfErro'
  }
}

/** Formato que `electron/main.ts` devolve para uma resposta HTTP não-ok — o
 * IPC do Electron não preserva propriedades extras de um Error lançado
 * através do processo, então o main resolve com este objeto em vez de
 * rejeitar (ver a docstring de `chamarSidecar`). */
interface ErroSidecar {
  __hfErro: true
  status: number
  detail: string
  aguarde_s?: number
}

function ehErroSidecar(x: unknown): x is ErroSidecar {
  return !!x && typeof x === 'object' && (x as { __hfErro?: unknown }).__hfErro === true
}

// Ouvintes do bloqueio 423 global (auto-lock expirado em qualquer chamada de
// negócio) — o App se inscreve para trocar de tela sem perder o estado em
// memória das telas de negócio (elas continuam montadas, só a tela de
// desbloqueio entra por cima).
type OuvinteBloqueio = () => void
const ouvintesBloqueio = new Set<OuvinteBloqueio>()

export function aoBloquear(ouvinte: OuvinteBloqueio): () => void {
  ouvintesBloqueio.add(ouvinte)
  return () => ouvintesBloqueio.delete(ouvinte)
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
    const resultado = await ponte().invoke<unknown>(metodo, payload)
    if (ehErroSidecar(resultado)) {
      if (resultado.status === 423) {
        ouvintesBloqueio.forEach((ouvinte) => ouvinte())
      }
      throw new HfErro(resultado.detail, false, resultado.status, resultado.aguarde_s)
    }
    return resultado as T
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
  /** Diálogo nativo de ABRIR (Electron) — usado para apontar um `.gguf`
   * local na tela de Configuração da IA (T-1702). Devolve o caminho ou null. */
  dialogoAbrir: (opcoes: {
    filtroNome: string
    extensoes: string[]
  }): Promise<string | null> => ponte().dialogoAbrir(opcoes),

  // --- cofre local (T-1604, ADR-0016 §D) --------------------------------
  /** `{cadastrado, desbloqueado, aguarde_s}` — decide qual tela mostrar. */
  authStatus: (): Promise<AuthStatusOut> => chamar('/auth/status'),
  /** Cria o cofre; a sessão permanece bloqueada (o 1º login é que confirma
   * o autenticador). Devolve o URI/QR do TOTP e os 10 códigos — só aqui. */
  authCadastrar: (senha: string): Promise<AuthCadastroOut> =>
    chamar('/auth/cadastrar', { senha }),
  authLogin: (senha: string, codigoTotp: string): Promise<{ ok: boolean }> =>
    chamar('/auth/login', { senha, codigo_totp: codigoTotp }),
  authBloquear: (): Promise<{ ok: boolean }> => chamar('/auth/bloquear', {}),
  authRecuperar: (codigo: string, novaSenha: string): Promise<{ ok: boolean }> =>
    chamar('/auth/recuperar', { codigo, nova_senha: novaSenha }),

  // --- gestor de modelos GGUF (T-1702, ADR-0016 §F, REQ-F-028) -----------
  llmStatus: (): Promise<LlmStatusOut> => chamar('/llm/status'),
  llmCatalogo: (): Promise<LlmCatalogoOut> => chamar('/llm/catalogo'),
  /** Único ponto de rede fora do sidecar local — só dispara por este clique
   * explícito do usuário (REQ-NF-007). */
  llmBaixar: (catalogoId: string): Promise<LlmJobOut> =>
    chamar('/llm/baixar', { catalogo_id: catalogoId }),
  llmBaixarStatus: (jobId: string): Promise<LlmBaixarStatusOut> =>
    chamar(`/llm/baixar/${jobId}`),
  llmBaixarCancelar: (jobId: string): Promise<{ ok: boolean }> =>
    chamar(`/llm/baixar/${jobId}/cancelar`, {}),
  /** Define o modelo ativo: `catalogoId` (já baixado) OU `caminho` (.gguf
   * local apontado pelo usuário) — exatamente um dos dois. */
  llmDefinirModelo: (args: {
    catalogoId?: string
    caminho?: string
  }): Promise<LlmModeloDefinidoOut> =>
    chamar('/llm/modelo', { catalogo_id: args.catalogoId, caminho: args.caminho }),
}
