import { useEffect, useState } from 'react'

import { HfErro, hf } from '../hf/client'
import type {
  CatalogoItemOut,
  ConfigLLMIn,
  ConfigLLMOut,
  LlmStatusOut,
} from '../hf/contract'

/** Tela "Configuração da IA" (T-1702, ADR-0016 §F, REQ-F-028; ajustes
 * avançados e painel do último boot no T-2503, ADR-0022): estado do runtime
 * embarcado, catálogo curado de modelos GGUF com download gerenciado (a
 * ÚNICA exceção de rede do app, REQ-NF-007 — só por clique explícito),
 * apontamento de um `.gguf` já presente no disco, contexto/uso de GPU e
 * diagnóstico do último boot. Nenhum cálculo acontece aqui: tudo vem pronto
 * do sidecar (REQ-NF-005) — inclusive a regra da dica de contexto. */

function bytesLegiveis(n: number): string {
  if (n <= 0) return '0 MB'
  const mb = n / (1024 * 1024)
  return mb >= 1024 ? `${(mb / 1024).toFixed(1)} GB` : `${mb.toFixed(0)} MB`
}

function instrucaoMotivo(motivo: string | null): string {
  if (motivo === 'BINARIO_AUSENTE') {
    return 'O binário do runtime local (llama-server) não foi encontrado — reinstale o app.'
  }
  if (motivo === 'MODELO_AUSENTE') {
    return 'Nenhum modelo instalado ainda. Baixe um do catálogo abaixo ou aponte um arquivo .gguf local.'
  }
  return motivo ? `Runtime local indisponível: ${motivo}.` : ''
}

/** Busca status + catálogo de uma vez; usada tanto nos efeitos (inline,
 * conforme o padrão do resto da GUI — ver `App.tsx::consultarStatusCofre`)
 * quanto nos handlers de clique (`await buscarLlm()`), fora de qualquer efeito. */
function buscarLlm(): Promise<{ status: LlmStatusOut; catalogo: CatalogoItemOut[] }> {
  return Promise.all([hf.llmStatus(), hf.llmCatalogo()]).then(([status, c]) => ({
    status,
    catalogo: c.catalogo,
  }))
}

// --- Ajustes avançados (T-2503, ADR-0022) -------------------------------------

const DEGRAUS_CONTEXTO = [
  { valor: 2048, custo: 'Menor memória, análises mais curtas' },
  { valor: 4096, custo: 'Equilíbrio — validado como padrão' },
  { valor: 8192, custo: 'Mais memória de vídeo/RAM, análises mais longas' },
] as const

/** Tradução em linguagem clara do motivo TIPADO devolvido pelo backend — a
 * mesma classificação de `runtime_llm._TEXTO_MOTIVO_FALHA`, mantida aqui só
 * como rótulo de exibição (nenhuma decisão nova, REQ-NF-005). */
function textoMotivoFalha(motivo: string | null): string {
  if (motivo === 'GPU_SEM_MEMORIA') {
    return 'a GPU não tinha memória de vídeo suficiente para o modelo'
  }
  if (motivo === 'GPU_FIT_ABORTADO') {
    return 'o ajuste automático de camadas na GPU não conseguiu concluir'
  }
  if (motivo === 'GENERICO') {
    return 'a inicialização na GPU falhou por um motivo não identificado'
  }
  return ''
}

function formatarBytes(n: number | null): string | null {
  if (n === null) return null
  return bytesLegiveis(n)
}

type ModoOffloadTela = 'auto' | 'cpu' | 'camadas'

function modoDoValor(v: string | number): ModoOffloadTela {
  if (v === 'auto') return 'auto'
  if (v === 'cpu') return 'cpu'
  return 'camadas'
}

export default function ConfiguracaoIa() {
  const [status, setStatus] = useState<LlmStatusOut | null>(null)
  const [catalogo, setCatalogo] = useState<CatalogoItemOut[]>([])
  const [erro, setErro] = useState('')
  const [ocupado, setOcupado] = useState<string | null>(null) // id do item em ação

  // Ajustes avançados + painel do último boot (T-2503, ADR-0022): estado
  // próprio, independente do catálogo — a tela pode mostrar um sem o outro.
  const [cfg, setCfg] = useState<ConfigLLMOut | null>(null)
  const [erroCfg, setErroCfg] = useState('')
  const [ctxSelecionado, setCtxSelecionado] = useState<2048 | 4096 | 8192>(4096)
  const [modoOffload, setModoOffload] = useState<ModoOffloadTela>('auto')
  const [camadasTexto, setCamadasTexto] = useState('')
  const [salvandoCfg, setSalvandoCfg] = useState(false)
  const [toastCfg, setToastCfg] = useState('')

  // Hidrata os seletores com a config efetiva do backend (nunca inventa um
  // valor default próprio — reflete o que `GET /llm/config` devolveu).
  function hidratarSelecoes(c: ConfigLLMOut) {
    setCtxSelecionado(c.config.ctx_size as 2048 | 4096 | 8192)
    const modo = modoDoValor(c.config.gpu_offload)
    setModoOffload(modo)
    setCamadasTexto(modo === 'camadas' ? String(c.config.gpu_offload) : '')
  }

  useEffect(() => {
    let ativo = true
    hf.llmConfig()
      .then((c) => {
        if (!ativo) return
        setCfg(c)
        hidratarSelecoes(c)
        setErroCfg('')
      })
      .catch((e: unknown) => {
        if (ativo) {
          setErroCfg(
            e instanceof HfErro ? e.message : 'Não foi possível consultar a configuração da IA.',
          )
        }
      })
    return () => {
      ativo = false
    }
  }, [])

  const origemEnv = cfg?.config.ctx_size_origem === 'env'

  async function salvarCfg() {
    if (!cfg) return
    setSalvandoCfg(true)
    setErroCfg('')
    try {
      const patch: ConfigLLMIn = {}
      if (ctxSelecionado !== cfg.config.ctx_size) patch.ctx_size = ctxSelecionado
      const gpuAtual: 'auto' | 'cpu' | number =
        modoOffload === 'camadas' ? Number(camadasTexto) : modoOffload
      if (gpuAtual !== cfg.config.gpu_offload) patch.gpu_offload = gpuAtual
      const novo = await hf.llmConfigSalvar(patch)
      setCfg(novo)
      hidratarSelecoes(novo)
      setToastCfg('Salvo — vale a partir da próxima análise.')
    } catch (e) {
      setErroCfg(e instanceof HfErro ? e.message : 'Não foi possível salvar a configuração.')
    } finally {
      setSalvandoCfg(false)
    }
  }

  function aplicarSugestao() {
    if (cfg?.dica_ctx_sugerido) {
      setCtxSelecionado(cfg.dica_ctx_sugerido as 2048 | 4096 | 8192)
    }
  }

  useEffect(() => {
    if (!toastCfg) return
    const timer = setTimeout(() => setToastCfg(''), 4000)
    return () => clearTimeout(timer)
  }, [toastCfg])

  useEffect(() => {
    let ativo = true
    buscarLlm()
      .then((r) => {
        if (!ativo) return
        setStatus(r.status)
        setCatalogo(r.catalogo)
      })
      .catch((e: unknown) => {
        if (ativo) {
          setErro(e instanceof HfErro ? e.message : 'Não foi possível consultar a IA local.')
        }
      })
    return () => {
      ativo = false
    }
  }, [])

  // Enquanto algum item está baixando, faz poll do catálogo (progresso vem
  // pronto do sidecar — a barra só reflete os bytes recebidos).
  const algumBaixando = catalogo.some((i) => i.estado === 'baixando')
  useEffect(() => {
    if (!algumBaixando) return
    let ativo = true
    const timer = setInterval(() => {
      buscarLlm()
        .then((r) => {
          if (ativo) {
            setStatus(r.status)
            setCatalogo(r.catalogo)
          }
        })
        .catch(() => {}) // poll silencioso: a próxima rodada tenta de novo
    }, 900)
    return () => {
      ativo = false
      clearInterval(timer)
    }
  }, [algumBaixando])

  async function recarregar() {
    try {
      const r = await buscarLlm()
      setStatus(r.status)
      setCatalogo(r.catalogo)
      setErro('')
    } catch (e) {
      setErro(e instanceof HfErro ? e.message : 'Não foi possível consultar a IA local.')
    }
  }

  async function baixar(item: CatalogoItemOut) {
    setErro('')
    try {
      await hf.llmBaixar(item.id)
      await recarregar()
    } catch (e) {
      setErro(e instanceof HfErro ? e.message : 'Não foi possível iniciar o download.')
    }
  }

  async function cancelar(item: CatalogoItemOut) {
    if (!item.job_id) return
    try {
      await hf.llmBaixarCancelar(item.job_id)
    } catch {
      // best-effort: o próximo poll do catálogo reflete o estado real
    } finally {
      await recarregar()
    }
  }

  async function usarDoCatalogo(item: CatalogoItemOut) {
    setOcupado(item.id)
    setErro('')
    try {
      await hf.llmDefinirModelo({ catalogoId: item.id })
      await recarregar()
    } catch (e) {
      setErro(e instanceof HfErro ? e.message : 'Não foi possível ativar o modelo.')
    } finally {
      setOcupado(null)
    }
  }

  async function apontarLocal() {
    const caminho = await hf.dialogoAbrir({ filtroNome: 'Modelo GGUF', extensoes: ['gguf'] })
    if (!caminho) return
    setOcupado('__local__')
    setErro('')
    try {
      await hf.llmDefinirModelo({ caminho })
      await recarregar()
    } catch (e) {
      setErro(e instanceof HfErro ? e.message : 'Arquivo .gguf inválido.')
    } finally {
      setOcupado(null)
    }
  }

  return (
    <>
      <div className="titulo-linha">
        <div>
          <h1 className="titulo">Configuração da IA</h1>
          <p className="sub">
            O Helper Financeiro roda a IA localmente, sem depender de nenhum serviço
            externo. Escolha um modelo do catálogo ou aponte um arquivo .gguf já no
            seu computador.
          </p>
        </div>
      </div>

      {erro && <div className="aviso-erro">{erro}</div>}

      <section className="card cfgia-status">
        <div className="card-rotulo">Estado do runtime</div>
        {!status ? (
          <p className="sub">Consultando…</p>
        ) : status.servidor_usuario ? (
          <div className="status status-ok">
            Usando o seu servidor local ({status.base_url}) — configurado via HF_BASE_URL.
          </div>
        ) : status.motivo_indisponivel ? (
          <div className="aviso-erro">{instrucaoMotivo(status.motivo_indisponivel)}</div>
        ) : (
          <div className="status status-ok">
            Modelo pronto: <code>{status.modelo_ativo}</code>
            {status.runtime_ativo ? ' · runtime no ar' : ' · sobe sob demanda na 1ª análise'}
          </div>
        )}
      </section>

      {!status?.servidor_usuario && (
        <>
          {erroCfg && <div className="aviso-erro">{erroCfg}</div>}

          <section className="card">
            <div className="card-titulo">Ajustes avançados</div>
            {!cfg ? (
              <p className="sub">Consultando…</p>
            ) : (
              <>
                {origemEnv && (
                  <div className="cfgia-aviso-env">
                    A variável <code>HF_LLAMA_FLAGS</code> está definida e sobrepõe estes
                    ajustes — os controles abaixo ficam desabilitados porque salvar aqui
                    não teria efeito enquanto ela existir.
                  </div>
                )}

                {cfg.dica && (
                  <div className="cfgia-dica">
                    <span>{cfg.dica}</span>
                    {cfg.dica_ctx_sugerido && (
                      <button
                        className="btn-secundario"
                        disabled={origemEnv}
                        onClick={aplicarSugestao}
                      >
                        Aplicar sugestão
                      </button>
                    )}
                  </div>
                )}

                <div className="cfgia-campo-avancado">
                  <div className="cfgia-campo-rotulo">Contexto</div>
                  <div className="cfgia-degraus">
                    {DEGRAUS_CONTEXTO.map((d) => (
                      <button
                        key={d.valor}
                        className={
                          ctxSelecionado === d.valor
                            ? 'cfgia-degrau on'
                            : 'cfgia-degrau'
                        }
                        disabled={origemEnv}
                        onClick={() => setCtxSelecionado(d.valor)}
                      >
                        <span className="cfgia-degrau-valor">{d.valor}</span>
                        <span className="cfgia-degrau-custo">{d.custo}</span>
                      </button>
                    ))}
                  </div>
                </div>

                <div className="cfgia-campo-avancado">
                  <div className="cfgia-campo-rotulo">Uso da GPU</div>
                  <div className="cfgia-degraus">
                    <button
                      className={modoOffload === 'auto' ? 'cfgia-degrau on' : 'cfgia-degrau'}
                      disabled={origemEnv}
                      onClick={() => setModoOffload('auto')}
                    >
                      <span className="cfgia-degrau-valor">Auto</span>
                      <span className="cfgia-degrau-custo">Recomendado</span>
                    </button>
                    <button
                      className={modoOffload === 'cpu' ? 'cfgia-degrau on' : 'cfgia-degrau'}
                      disabled={origemEnv}
                      onClick={() => setModoOffload('cpu')}
                    >
                      <span className="cfgia-degrau-valor">Só CPU</span>
                      <span className="cfgia-degrau-custo">Sem usar a GPU</span>
                    </button>
                    <button
                      className={
                        modoOffload === 'camadas' ? 'cfgia-degrau on' : 'cfgia-degrau'
                      }
                      disabled={origemEnv}
                      onClick={() => setModoOffload('camadas')}
                    >
                      <span className="cfgia-degrau-valor">Fixar camadas</span>
                      <span className="cfgia-degrau-custo">Escolha o número abaixo</span>
                    </button>
                  </div>
                  {modoOffload === 'camadas' && (
                    <input
                      className="cfgia-camadas-input"
                      type="number"
                      min={1}
                      max={999}
                      placeholder="Nº de camadas (1–999)"
                      value={camadasTexto}
                      disabled={origemEnv}
                      onChange={(e) => setCamadasTexto(e.target.value)}
                    />
                  )}
                </div>

                <div className="cfgia-salvar-linha">
                  <button
                    className="btn-add"
                    disabled={
                      origemEnv ||
                      salvandoCfg ||
                      (modoOffload === 'camadas' &&
                        (!camadasTexto || Number(camadasTexto) < 1 || Number(camadasTexto) > 999))
                    }
                    onClick={() => void salvarCfg()}
                  >
                    {salvandoCfg ? 'Salvando…' : 'Salvar'}
                  </button>
                  {toastCfg && <span className="cfgia-toast">{toastCfg}</span>}
                </div>
              </>
            )}
          </section>

          <section className="card">
            <div className="card-titulo">Último boot da IA</div>
            {!cfg ? (
              <p className="sub">Consultando…</p>
            ) : (
              <PainelBoot cfg={cfg} />
            )}
          </section>
        </>
      )}

      {!status?.servidor_usuario && (
        <section className="card">
          <div className="card-titulo">Catálogo de modelos</div>
          <p className="sub-secao">
            3-4B parâmetros, quantizados (Q4), com licença que permite uso comercial.
            O download é a única conexão de rede deste app — só acontece se você
            clicar em "Baixar".
          </p>
          <ul className="cfgia-lista">
            {catalogo.map((item) => (
              <li key={item.id} className="cfgia-item">
                <div className="cfgia-item-topo">
                  <div>
                    <div className="cfgia-item-nome">{item.nome}</div>
                    <div className="cfgia-item-desc">{item.descricao}</div>
                  </div>
                  <span className="pill">{item.licenca}</span>
                </div>
                <div className="cfgia-item-meta">
                  {bytesLegiveis(item.tamanho_bytes)}
                  {status?.modelo_ativo?.endsWith(item.arquivo) && ' · ativo'}
                </div>

                {item.estado === 'baixando' && (
                  <div className="cfgia-progresso">
                    <div className="cfgia-progresso-trilha">
                      <div
                        className="cfgia-progresso-barra"
                        style={{
                          width: `${
                            item.bytes_total
                              ? Math.min(
                                  100,
                                  ((item.bytes_baixados ?? 0) / item.bytes_total) * 100,
                                )
                              : 0
                          }%`,
                        }}
                      />
                    </div>
                    <span className="cfgia-progresso-txt">
                      {bytesLegiveis(item.bytes_baixados ?? 0)} de{' '}
                      {bytesLegiveis(item.bytes_total ?? item.tamanho_bytes)}
                    </span>
                    <button className="btn-secundario" onClick={() => void cancelar(item)}>
                      Cancelar
                    </button>
                  </div>
                )}

                {item.estado === 'ausente' && (
                  <button
                    className="btn-add"
                    title="Baixa da internet — única exceção de rede do app"
                    onClick={() => void baixar(item)}
                  >
                    Baixar (rede) — {bytesLegiveis(item.tamanho_bytes)}
                  </button>
                )}

                {item.estado === 'baixado' && (
                  <button
                    className="btn-secundario"
                    disabled={ocupado === item.id}
                    onClick={() => void usarDoCatalogo(item)}
                  >
                    {ocupado === item.id ? 'Ativando…' : 'Usar este modelo'}
                  </button>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}

      {!status?.servidor_usuario && (
        <section className="card">
          <div className="card-titulo">Modelo local (.gguf)</div>
          <p className="sub-secao">
            Já tem um arquivo .gguf no seu computador? Aponte-o diretamente — nada é
            copiado, o app só passa a referenciar o caminho.
          </p>
          <button
            className="btn-secundario"
            disabled={ocupado === '__local__'}
            onClick={() => void apontarLocal()}
          >
            {ocupado === '__local__' ? 'Ativando…' : 'Escolher arquivo .gguf…'}
          </button>
        </section>
      )}
    </>
  )
}

/** Painel "Último boot da IA" (T-2503, ADR-0022): badge de modo + métricas do
 * boot, todas prontas do backend (`GET /llm/config`) — a tela só formata
 * bytes/rotula o motivo tipado, nunca decide o modo ou a falha.
 *
 * Achado de UX (docs/TASKS.md, T-2503): `motivo_fallback` é a FALHA
 * CLASSIFICADA do último boot, não necessariamente "a GPU falhou" — um boot
 * CPU puro que morre por falta de memória também ganha `GPU_SEM_MEMORIA`
 * (o classificador olha o stderr, não a config pedida). Por isso o texto
 * nunca afirma "a GPU falhou": fala em "falha classificada do último boot". */
function PainelBoot({ cfg }: { cfg: ConfigLLMOut }) {
  const { boot_info: boot } = cfg
  const m = boot.metricas

  if (boot.modo === 'nunca_subiu') {
    return (
      <div className="cfgia-boot">
        <p className="sub">A IA ainda não foi iniciada nesta sessão.</p>
        {boot.motivo_fallback && (
          <p className="sub cfgia-boot-motivo">
            A última tentativa de inicialização não subiu. Falha classificada do
            último boot: {textoMotivoFalha(boot.motivo_fallback)}.
          </p>
        )}
      </div>
    )
  }

  const badge =
    boot.modo === 'gpu'
      ? { emoji: '🟢', texto: 'GPU', classe: 'cfgia-badge-gpu' }
      : boot.modo === 'cpu_configurado'
        ? { emoji: '🔵', texto: 'CPU (configurado)', classe: 'cfgia-badge-cpu' }
        : { emoji: '🟠', texto: 'CPU por falha na GPU', classe: 'cfgia-badge-fallback' }

  const vramAlocada = formatarBytes(m.vram_bytes)

  return (
    <div className="cfgia-boot">
      <span className={`cfgia-badge ${badge.classe}`}>
        {badge.emoji} {badge.texto}
      </span>
      {boot.modo === 'cpu_fallback' && boot.motivo_fallback && (
        <p className="sub cfgia-boot-motivo">
          Falha classificada do último boot: {textoMotivoFalha(boot.motivo_fallback)}.
        </p>
      )}
      <div className="cfgia-boot-lista">
        {m.dispositivo !== null && (
          <div className="cfgia-boot-item">
            <div className="cfgia-boot-item-rotulo">Dispositivo</div>
            <div className="cfgia-boot-item-valor">{m.dispositivo}</div>
          </div>
        )}
        {m.camadas_offload !== null && m.camadas_total !== null && (
          <div className="cfgia-boot-item">
            <div className="cfgia-boot-item-rotulo">Camadas na GPU</div>
            <div className="cfgia-boot-item-valor">
              {m.camadas_offload} de {m.camadas_total}
            </div>
          </div>
        )}
        {vramAlocada !== null && (
          <div className="cfgia-boot-item">
            <div className="cfgia-boot-item-rotulo">VRAM alocada</div>
            <div className="cfgia-boot-item-valor">{vramAlocada}</div>
          </div>
        )}
        {m.ctx_efetivo !== null && (
          <div className="cfgia-boot-item">
            <div className="cfgia-boot-item-rotulo">Contexto efetivo</div>
            <div className="cfgia-boot-item-valor">{m.ctx_efetivo}</div>
          </div>
        )}
      </div>
    </div>
  )
}
