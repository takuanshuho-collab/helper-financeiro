import { useEffect, useState } from 'react'

import CampoMoeda from '../components/CampoMoeda'
import CampoPercent from '../components/CampoPercent'
import { hf } from '../hf/client'
import type {
  AnaliseOut,
  OportunidadeOut,
  PerfilIn,
  SecaoIaOut,
  UltimaAnaliseOut,
} from '../hf/contract'
import type { Analise as AnaliseApp } from '../hf/useAnalise'
import { brl, carimboBR, corSaude, faixaTaxa, iniciais, pct0, taxaAm } from '../lib/format'

type EstadoIa =
  | { fase: 'ocioso' }
  | { fase: 'rodando' }
  | { fase: 'erro'; msg: string }

/**
 * Tela Análise (T-902, REQ-F-015): estratégias e portabilidade recalculadas ao
 * vivo conforme o extra e a taxa-alvo, análise sênior (IA local, job async no
 * sidecar) e exportações .xlsx/.docx. Toda a aritmética vem do core.
 */
export default function Analise({
  perfil,
  analise,
  secaoIa,
  setSecaoIa,
}: {
  perfil: PerfilIn
  analise: AnaliseApp
  // A última análise sênior vive no App: sobrevive à troca de aba e entra no .docx.
  secaoIa: SecaoIaOut | null
  setSecaoIa: (s: SecaoIaOut | null) => void
}) {
  const [extra, setExtra] = useState(0)
  const [alvo, setAlvo] = useState(0.018)
  const [pacote, setPacote] = useState<AnaliseOut | null>(null)
  const [erro, setErro] = useState('')
  const [ia, setIa] = useState<EstadoIa>({ fase: 'ocioso' })
  const [msgExport, setMsgExport] = useState('')
  // Banner do runtime (T-2503, ADR-0022): preenchido quando o poll do job
  // devolve `aviso_runtime` — a análise que rodou caiu para CPU no boot que a
  // serviu. Informativo: não bloqueia nem esconde o resultado.
  const [avisoRuntime, setAvisoRuntime] = useState<string | null>(null)
  // Persistência visível da última análise (T-2602, ADR-0023): `analiseSalva`
  // é o que o sidecar tem gravado; `assinaturaAtual` é a assinatura dos dados
  // VIVOS (calculada no backend — a GUI só COMPARA strings, REQ-NF-005).
  const [analiseSalva, setAnaliseSalva] = useState<UltimaAnaliseOut | null>(null)
  const [assinaturaAtual, setAssinaturaAtual] = useState('')

  const d = analise.diagnostico

  // Hidrata a última análise salva ao montar e sempre que perfil/extra mudarem
  // (mesmo padrão de debounce do `pacote` acima) — nunca enquanto uma geração
  // está rodando. Quando a assinatura salva bate com a atual, a seção salva
  // vira a seção exibida (e entra no .docx de graça); dados diferentes só
  // atualizam `analiseSalva`/`assinaturaAtual`, para o selo "dados mudaram".
  // Como `ia.fase` está nas deps, terminar uma geração (`gerarIa`) também
  // rechama isto — atualiza carimbo/assinatura sem código extra.
  useEffect(() => {
    if (ia.fase === 'rodando') return
    let vivo = true
    const timer = setTimeout(() => {
      hf.analiseUltima(perfil, extra)
        .then((r) => {
          if (!vivo) return
          setAnaliseSalva(r.analise_salva)
          setAssinaturaAtual(r.assinatura_atual)
          if (r.analise_salva && r.analise_salva.assinatura === r.assinatura_atual) {
            setSecaoIa(r.analise_salva.secao)
          } else if (r.analise_salva) {
            // A seção exibida (se houver) referia-se aos dados ANTERIORES —
            // some daqui para o bloco esmaecido assumir (`analiseSalva` com
            // assinatura divergente), em vez de continuar exibida como se
            // ainda valesse para os dados vivos atuais.
            setSecaoIa(null)
          }
        })
        .catch(() => {
          // best-effort: sem hidratação, a tela segue como hoje
        })
    }, 160)
    return () => {
      vivo = false
      clearTimeout(timer)
    }
  }, [perfil, extra, ia.fase, setSecaoIa])

  // Recalcula o pacote determinístico a cada mudança (debounce como no useAnalise).
  useEffect(() => {
    let vivo = true
    const timer = setTimeout(() => {
      hf.analise(perfil, extra, alvo)
        .then((p) => {
          if (!vivo) return
          setPacote(p)
          setErro('')
        })
        .catch((e: Error) => {
          if (vivo) setErro(e.message)
        })
    }, 160)
    return () => {
      vivo = false
      clearTimeout(timer)
    }
  }, [perfil, extra, alvo])

  async function gerarIa() {
    setIa({ fase: 'rodando' })
    setSecaoIa(null)
    setAvisoRuntime(null)
    try {
      const { job_id } = await hf.analiseIaIniciar(perfil, extra)
      for (;;) {
        await new Promise((r) => setTimeout(r, 1200))
        const st = await hf.analiseIaStatus(job_id)
        if (st.status === 'rodando') continue
        if (st.status === 'pronto' && st.secao) {
          setSecaoIa(st.secao)
          setAvisoRuntime(st.aviso_runtime)
          setIa({ fase: 'ocioso' })
        } else {
          setIa({ fase: 'erro', msg: st.erro || 'falha desconhecida' })
        }
        return
      }
    } catch (e) {
      setIa({ fase: 'erro', msg: e instanceof Error ? e.message : String(e) })
    }
  }

  async function exportar(tipo: 'planilha' | 'relatorio') {
    const planilha = tipo === 'planilha'
    const caminho = await hf.dialogoSalvar({
      sugestao: planilha ? 'diagnostico_financeiro.xlsx' : 'relatorio_financeiro.docx',
      filtroNome: planilha ? 'Planilha do Excel' : 'Documento do Word',
      extensoes: [planilha ? 'xlsx' : 'docx'],
    })
    if (!caminho) return
    try {
      const r = planilha
        ? await hf.exportarPlanilha(perfil, caminho, extra, alvo)
        : await hf.exportarRelatorio(perfil, caminho, extra, alvo, secaoIa)
      setMsgExport(`✔ Salvo em ${r.caminho}`)
    } catch (e) {
      setMsgExport(`Falha ao exportar: ${e instanceof Error ? e.message : e}`)
    }
  }

  if (analise.estado.fase === 'erro') {
    return <div className="aviso-erro">Sem conexão com o núcleo: {analise.estado.erro}</div>
  }
  if (!d) {
    return <div className="sub">Calculando o diagnóstico…</div>
  }

  const cor = corSaude(d.classificacao)
  const est = pacote?.estrategias
  // T-2602: a salva bate com os dados vivos (mesma assinatura) — a GUI só
  // COMPARA as duas strings que já vieram prontas do backend (REQ-NF-005).
  const salvaAtualizada =
    analiseSalva !== null && analiseSalva.assinatura === assinaturaAtual

  return (
    <>
      <div className="head">
        <div>
          <h1 className="titulo">Análise</h1>
          <p className="sub">
            Diagnóstico determinístico e, se quiser, a análise sênior assistida por IA.
          </p>
        </div>
        <span className="pill" style={{ color: cor, borderColor: cor }}>
          {d.classificacao}
        </span>
      </div>

      <section className="card params">
        <CampoMoeda rotulo="Pagamento extra por mês" valor={extra} onValor={setExtra} />
        <CampoPercent rotulo="Taxa-alvo p/ portabilidade" valor={alvo} onValor={setAlvo} />
        {erro && <span className="params-erro">{erro}</span>}
      </section>

      <div className="grid4">
        <div className="mcard">
          <div className="mrotulo">Classificação</div>
          <div className="mvalor" style={{ color: cor }}>{d.classificacao}</div>
          <div className="mnota">{d.classificacao_explicacao}</div>
        </div>
        <div className="mcard">
          <div className="mrotulo">Fluxo de caixa</div>
          <div
            className="mvalor"
            style={{ color: d.fluxo_caixa >= 0 ? 'var(--green)' : 'var(--red)' }}
          >
            {brl(d.fluxo_caixa)}
          </div>
          <div className="mnota">livre por mês</div>
        </div>
        <div className="mcard">
          <div className="mrotulo">Saldo devedor</div>
          <div className="mvalor">{brl(d.saldo_devedor_total)}</div>
          <div className="mnota" style={{ color: 'var(--red)' }}>
            {brl(d.juros_totais_futuros)} em juros futuros
          </div>
        </div>
        <div className="mcard">
          <div className="mrotulo">Comprometimento</div>
          <div className="mvalor" style={{ color: cor }}>
            {pct0(d.comprometimento_renda)}
          </div>
          <div className="mnota">da renda líquida</div>
        </div>
      </div>

      <div className="cols cols-iguais">
        <section className="card">
          <div className="card-titulo">Estratégias de quitação</div>
          <p className="sub-secao">Com {brl(extra)} extra por mês</p>
          {est ? (
            <div className="estrats">
              <div className="scard scard-win">
                <div className="scard-topo">
                  <span className="scard-nome">Avalanche</span>
                  <span className="scard-selo">Recomendada</span>
                </div>
                <div className="scard-meses">
                  {est.avalanche.quitavel ? `${est.avalanche.meses} meses` : 'não quita'}
                </div>
                <div className="scard-juros">
                  {est.avalanche.quitavel
                    ? `${brl(est.avalanche.juros_pagos)} em juros` +
                      (pacote.economia_avalanche != null && pacote.economia_avalanche > 0
                        ? ` · economiza ${brl(pacote.economia_avalanche)} vs. bola de neve`
                        : '')
                    : 'as parcelas mínimas não cobrem os juros'}
                </div>
                <div className="scard-desc">
                  Ataca a taxa mais alta primeiro
                  {est.avalanche.ordem[0] ? ` (${est.avalanche.ordem[0]})` : ''}. Menor
                  custo total.
                </div>
              </div>
              <div className="scard">
                <div className="scard-topo">
                  <span className="scard-nome">Bola de neve</span>
                </div>
                <div className="scard-meses">
                  {est.bola_de_neve.quitavel
                    ? `${est.bola_de_neve.meses} meses`
                    : 'não quita'}
                </div>
                <div className="scard-juros">
                  {est.bola_de_neve.quitavel
                    ? `${brl(est.bola_de_neve.juros_pagos)} em juros`
                    : 'as parcelas mínimas não cobrem os juros'}
                </div>
                <div className="scard-desc">
                  Quita o menor saldo primeiro
                  {est.bola_de_neve.ordem[0] ? ` (${est.bola_de_neve.ordem[0]})` : ''}.
                  Vitória rápida pra manter o ânimo.
                </div>
              </div>
            </div>
          ) : (
            <p className="sub">Simulando…</p>
          )}
        </section>

        <section className="card">
          <div className="card-titulo">Recomendações</div>
          <p className="sub-secao">Ações priorizadas para o seu caso</p>
          {pacote ? (
            <ol className="recs">
              {pacote.recomendacoes.map((r, i) => (
                <li key={i} className="rec">
                  <span className="rec-num">{i + 1}</span>
                  <span>{r}</span>
                </li>
              ))}
            </ol>
          ) : (
            <p className="sub">Calculando…</p>
          )}
        </section>
      </div>

      <section className="card">
        <div className="port-head">
          <div>
            <div className="card-titulo">Oportunidades de portabilidade</div>
            <p className="sub-secao">
              Dívidas acima da taxa-alvo de {taxaAm(alvo)} — leve para outro banco e
              reduza a parcela
            </p>
          </div>
          {pacote && pacote.oportunidades.length > 0 && (
            <div className="port-total">
              <div className="port-total-rotulo">Economia potencial total</div>
              <div className="port-total-valor">
                {brl(pacote.economia_total_portabilidade)}
              </div>
            </div>
          )}
        </div>
        {pacote && pacote.oportunidades.length === 0 ? (
          <p className="sub">
            Nenhuma dívida acima da taxa-alvo de {taxaAm(alvo)}. Suas taxas já estão
            competitivas — ou ajuste a taxa-alvo acima.
          </p>
        ) : (
          <ul className="lista-div">
            {pacote?.oportunidades.map((o) => (
              <LinhaPortabilidade key={o.credor} o={o} alvo={alvo} />
            ))}
          </ul>
        )}
        {pacote && pacote.oportunidades.length > 0 && (
          <p className="port-nota">
            Simulação pelo sistema Price mantendo o mesmo prazo. Confirme a taxa
            efetiva (CET) na proposta do banco concorrente antes de migrar.
          </p>
        )}
      </section>

      <section className="card aibox">
        <div className="aibox-topo">
          <span className="aibadge">Análise sênior · assistida por IA</span>
          <button
            className="btn-add"
            onClick={() => void gerarIa()}
            disabled={ia.fase === 'rodando'}
          >
            {ia.fase === 'rodando'
              ? 'Gerando…'
              : salvaAtualizada
                ? 'Gerar novamente'
                : 'Gerar análise sênior'}
          </button>
        </div>

        {ia.fase === 'rodando' && (
          <div className="ia-status">
            <span className="spinner" aria-hidden="true" />
            Consultando o modelo local — os fatos vão anonimizados (CREDOR_n) e os
            números continuam vindo do núcleo determinístico.
          </div>
        )}
        {ia.fase === 'erro' && (
          <div className="aviso-erro">Erro ao gerar a análise: {ia.msg}</div>
        )}
        {avisoRuntime && <div className="aviso-runtime">⚠ {avisoRuntime}</div>}
        {ia.fase === 'ocioso' && !secaoIa && !analiseSalva && (
          <p className="sub ia-vazia">
            A IA interpreta os números do diagnóstico e sugere prioridades e um
            roteiro de negociação. Nada substitui os cálculos acima.
          </p>
        )}

        {/* T-2602: seção salva desatualizada — esmaecida, com selo âmbar, até
         * o usuário gerar de novo (o clique substitui tudo). */}
        {ia.fase !== 'rodando' && analiseSalva && !salvaAtualizada && !secaoIa && (
          <>
            <div className="ia-selo-desatualizada">
              ⚠ Os dados mudaram desde esta análise.
            </div>
            <div className="ia-secao-desatualizada">
              <SecaoIa secao={analiseSalva.secao} />
            </div>
          </>
        )}

        {secaoIa && secaoIa.modo !== 'completo' && (
          <div className="ia-degradada">
            ⚠ Modo degradado — a IA não está disponível agora; valem os números
            determinísticos acima.
            {secaoIa.motivos.length > 0 && <> Motivos: {secaoIa.motivos.join(', ')}.</>}
          </div>
        )}
        {secaoIa && secaoIa.modo === 'completo' && (
          <>
            {salvaAtualizada && analiseSalva && (
              <p className="ia-carimbo">
                Análise de {carimboBR(analiseSalva.carimbo)} — dados inalterados
              </p>
            )}
            <SecaoIa secao={secaoIa} />
          </>
        )}
      </section>

      <div className="export-linha">
        <button className="btn-secundario" onClick={() => void exportar('planilha')}>
          Gerar planilha (.xlsx)
        </button>
        <button className="btn-secundario" onClick={() => void exportar('relatorio')}>
          Gerar relatório (.docx)
        </button>
        <span className="export-nota">
          {msgExport || 'O relatório inclui a última análise da IA, quando houver.'}
        </span>
      </div>
    </>
  )
}

function LinhaPortabilidade({ o, alvo }: { o: OportunidadeOut; alvo: number }) {
  const { cor, tint } = faixaTaxa(o.taxa_mensal)
  return (
    <li className="ldiv">
      <span className="ldiv-chip" style={{ color: cor, background: tint }}>
        {iniciais(o.tipo)}
      </span>
      <div className="ldiv-info">
        <div className="ldiv-tipo">{o.tipo}</div>
        <div className="ldiv-meta">
          {o.credor} · {o.parcelas_restantes}x · parcela {brl(o.parcela_atual)} →{' '}
          <strong style={{ color: 'var(--green)' }}>{brl(o.parcela_nova)}</strong>
        </div>
      </div>
      <div className="port-taxas">
        <div>
          de <strong style={{ color: cor }}>{taxaAm(o.taxa_mensal)}</strong> p/{' '}
          {taxaAm(alvo)}
        </div>
        <div>−{brl(o.economia_mensal)}/mês</div>
      </div>
      <div className="ldiv-num">
        <div className="ldiv-saldo" style={{ color: 'var(--green)' }}>
          {brl(o.economia_total)}
        </div>
        <div className="ldiv-taxa">economia total</div>
      </div>
    </li>
  )
}

function SecaoIa({ secao }: { secao: SecaoIaOut }) {
  return (
    <div className="ia-secao">
      <h4>Sumário executivo</h4>
      <p>{secao.sumario}</p>
      <h4>Diagnóstico interpretado</h4>
      <p>{secao.diagnostico}</p>
      {secao.prioridades.length > 0 && (
        <>
          <h4>Prioridades sugeridas</h4>
          <ul>
            {secao.prioridades.map((p) => (
              <li key={p}>{p}</li>
            ))}
          </ul>
        </>
      )}
      {secao.roteiro.length > 0 && (
        <>
          <h4>Roteiro de negociação</h4>
          {secao.roteiro.map((passo) => (
            <div key={passo.credor} className="ia-passo">
              <strong>
                {passo.credor} — {passo.abordagem}
              </strong>
              <ul>
                {passo.argumentos.map((a) => (
                  <li key={a}>{a}</li>
                ))}
              </ul>
              {passo.concessoes.length > 0 && (
                <p className="ia-concessoes">
                  Concessões possíveis: {passo.concessoes.join('; ')}
                </p>
              )}
            </div>
          ))}
        </>
      )}
      {secao.alertas.length > 0 && (
        <>
          <h4>Alertas de risco</h4>
          <ul>
            {secao.alertas.map((a) => (
              <li key={a}>⚠ {a}</li>
            ))}
          </ul>
        </>
      )}
      <p className="ia-rodape">
        Confiança auto-avaliada do modelo: {pct0(secao.confianca)} · Conteúdo
        assistido por IA — revise antes de agir. Entra no relatório .docx.
        {secao.aviso_legal && <> {secao.aviso_legal}</>}
      </p>
    </div>
  )
}
