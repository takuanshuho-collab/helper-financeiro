import { useEffect, useState } from 'react'

import { HfErro, hf } from '../hf/client'
import type { CatalogoItemOut, LlmStatusOut } from '../hf/contract'

/** Tela "Configuração da IA" (T-1702, ADR-0016 §F, REQ-F-028): estado do
 * runtime embarcado, catálogo curado de modelos GGUF com download gerenciado
 * (a ÚNICA exceção de rede do app, REQ-NF-007 — só por clique explícito) e
 * apontamento de um `.gguf` já presente no disco. Nenhum cálculo acontece
 * aqui: tudo vem pronto do sidecar (REQ-NF-005). */

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

export default function ConfiguracaoIa() {
  const [status, setStatus] = useState<LlmStatusOut | null>(null)
  const [catalogo, setCatalogo] = useState<CatalogoItemOut[]>([])
  const [erro, setErro] = useState('')
  const [ocupado, setOcupado] = useState<string | null>(null) // id do item em ação

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
