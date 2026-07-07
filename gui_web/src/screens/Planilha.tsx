import {
  useEffect,
  useState,
  type FocusEvent,
  type KeyboardEvent,
} from 'react'

import { hf } from '../hf/client'
import type {
  Categoria,
  HistoricoComparadoOut,
  PerfilIn,
  RubricaMutOut,
  RubricaOut,
  VariacaoSecaoOut,
} from '../hf/contract'
import { brl, numBR, parseBR, pctBR } from '../lib/format'
import {
  SECOES_ORCAMENTO,
  SUGESTOES_RUBRICA,
  rubricasDoCampo,
  type CampoOrcamento,
} from '../lib/orcamento'

/**
 * Planilha de orçamento (T-1104, REQ-F-017): grade editável de rubricas.
 *
 * Cada campo do Perfil vira um grupo expansível; as linhas são as rubricas do
 * usuário (nome + valor). TODO subtotal exibido vem do sidecar: as mutações
 * devolvem o perfil já com o roll-up do core (campo detalhado = soma) — nada
 * é somado aqui (REQ-NF-005).
 */
export default function Planilha({
  perfil,
  rubricas,
  aoMutar,
  aoVoltar,
}: {
  perfil: PerfilIn
  rubricas: RubricaOut[]
  aoMutar: (r: RubricaMutOut) => void
  aoVoltar: () => void
}) {
  const [erro, setErro] = useState('')

  const mutar = (p: Promise<RubricaMutOut>) =>
    p.then((r) => {
      setErro('')
      aoMutar(r)
    }).catch((e: Error) => setErro(e.message))

  return (
    <>
      <div className="titulo-linha">
        <div>
          <h1 className="titulo">Planilha de orçamento</h1>
          <p className="sub">
            Crie rubricas para individualizar cada gasto — o campo do Perfil
            passa a valer a soma delas.
          </p>
        </div>
        <button className="btn-add" onClick={aoVoltar}>
          ← Voltar ao Perfil
        </button>
      </div>

      {erro && <div className="plan-erro">{erro}</div>}

      <div className="plan-grid">
        {SECOES_ORCAMENTO.map((secao) => (
          <section className="secao" key={secao.categoria}>
            <div className="secao-topo">
              <span className="secao-titulo">
                <span className="secao-ponto" style={{ background: secao.cor }} />
                {secao.titulo}
              </span>
            </div>
            {secao.campos.map((campo) => (
              <Grupo
                key={campo.campo}
                categoria={secao.categoria}
                campo={campo}
                valorCampo={valorDoPerfil(perfil, secao.categoria, campo.campo)}
                rubricas={rubricasDoCampo(rubricas, secao.categoria, campo.campo)}
                mutar={mutar}
              />
            ))}
          </section>
        ))}
      </div>

      <Historico aoErro={setErro} />
    </>
  )
}

/** Competência corrente no formato 'AAAA-MM' (apenas texto de data). */
function mesAtual(): string {
  return new Date().toISOString().slice(0, 7)
}

/**
 * Histórico mensal (T-1203, REQ-F-019): arquivar a competência e comparar
 * meses. Toda a aritmética (deltas e %) vem pronta do core via
 * `/historico/comparar` — aqui só se formata.
 */
function Historico({ aoErro }: { aoErro: (m: string) => void }) {
  const [meses, setMeses] = useState<string[]>([])
  const [mes, setMes] = useState(mesAtual)
  const [mesA, setMesA] = useState('')
  const [mesB, setMesB] = useState('') // '' = orçamento vivo
  const [comp, setComp] = useState<HistoricoComparadoOut | null>(null)

  useEffect(() => {
    hf.historicoListar()
      .then((h) => setMeses(h.meses))
      .catch(() => {}) // fora do Electron/primeiro uso: seção fica vazia
  }, [])

  const comparar = (a: string, b: string) => {
    if (!a) {
      setComp(null)
      return
    }
    hf.historicoComparar(a, b || null)
      .then(setComp)
      .catch((e: Error) => aoErro(e.message))
  }

  const arquivar = () =>
    hf.historicoArquivar(mes)
      .then((r) => {
        setMeses(r.meses)
        setMesA(r.mes)
        comparar(r.mes, mesB)
      })
      .catch((e: Error) => aoErro(e.message))

  return (
    <section className="secao hist">
      <div className="secao-topo">
        <span className="secao-titulo">
          <span className="secao-ponto" style={{ background: 'var(--accent)' }} />
          Histórico mensal
        </span>
      </div>

      <div className="hist-acoes">
        <input
          className="hist-mes"
          type="month"
          value={mes}
          onChange={(ev) => setMes(ev.target.value)}
          aria-label="Competência a arquivar"
        />
        <button className="btn-add" onClick={arquivar}>
          Arquivar {mes}
        </button>
      </div>
      <div className="plan-dica">
        Arquive quando fechar os lançamentos do mês — rearquivar a mesma
        competência substitui o registro anterior.
      </div>

      {meses.length > 0 && (
        <div className="hist-comp">
          Comparar{' '}
          <select
            className="hist-sel"
            value={mesA}
            onChange={(ev) => {
              setMesA(ev.target.value)
              comparar(ev.target.value, mesB)
            }}
            aria-label="Competência base"
          >
            <option value="">— escolha o mês —</option>
            {meses.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>{' '}
          com{' '}
          <select
            className="hist-sel"
            value={mesB}
            onChange={(ev) => {
              setMesB(ev.target.value)
              comparar(mesA, ev.target.value)
            }}
            aria-label="Competência de comparação"
          >
            <option value="">Orçamento atual</option>
            {meses.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
        </div>
      )}

      {comp &&
        comp.comparacao.secoes
          .filter((s) => s.campos.length > 0)
          .map((s) => <SecaoComparada key={s.categoria} secao={s} />)}
    </section>
  )
}

function SecaoComparada({ secao }: { secao: VariacaoSecaoOut }) {
  return (
    <div className="hist-secao">
      <div className="hist-secao-topo">
        <span className="hist-secao-nome">{secao.rotulo}</span>
        <Delta
          categoria={secao.categoria}
          delta={secao.delta}
          pct={secao.variacao_pct}
        />
      </div>
      {secao.campos.map((c) => (
        <div className="hist-linha" key={c.campo}>
          <span className="hist-rotulo">{c.rotulo}</span>
          <span className="hist-vals">
            {brl(c.antes)} → {brl(c.depois)}
          </span>
          <Delta categoria={secao.categoria} delta={c.delta} pct={c.variacao_pct} />
        </div>
      ))}
    </div>
  )
}

/**
 * Delta colorido pela semântica da seção: renda subir é bom (verde);
 * despesa subir é ruim (vermelho). Zero fica neutro.
 */
function Delta({
  categoria,
  delta,
  pct,
}: {
  categoria: Categoria
  delta: number
  pct: number | null
}) {
  if (delta === 0) {
    return <span className="hist-delta zero">sem variação</span>
  }
  const bom = categoria === 'renda' ? delta > 0 : delta < 0
  const sinal = delta > 0 ? '+' : ''
  const pctTexto = pct === null ? '' : ` (${pct > 0 ? '+' : ''}${pctBR(pct)}%)`
  return (
    <span className={bom ? 'hist-delta bom' : 'hist-delta ruim'}>
      {sinal}
      {brl(delta)}
      {pctTexto}
    </span>
  )
}

/** Valor atual do campo no perfil — direto ou já somado pelo core. */
function valorDoPerfil(
  perfil: PerfilIn,
  categoria: Categoria,
  campo: string,
): number {
  const secao = perfil[categoria] as Record<string, number> | undefined
  return secao?.[campo] ?? 0
}

function Grupo({
  categoria,
  campo,
  valorCampo,
  rubricas,
  mutar,
}: {
  categoria: Categoria
  campo: CampoOrcamento
  valorCampo: number
  rubricas: RubricaOut[]
  mutar: (p: Promise<RubricaMutOut>) => void
}) {
  // Grupos já detalhados nascem abertos; os demais, fechados (menos poluição).
  const [aberto, setAberto] = useState(rubricas.length > 0)
  const detalhado = rubricas.length > 0

  const criar = () =>
    mutar(
      hf.rubricaCriar({
        categoria,
        campo_pai: campo.campo,
        nome: 'Nova rubrica',
        valor: 0,
        ordem: rubricas.length,
      }),
    )

  return (
    <div className="plan-grupo">
      <button
        className="plan-grupo-topo"
        onClick={() => setAberto((a) => !a)}
        aria-expanded={aberto}
      >
        <span className={aberto ? 'plan-seta aberta' : 'plan-seta'}>▸</span>
        <span className="plan-grupo-nome">{campo.rotulo}</span>
        {detalhado && (
          <span className="plan-chip">{rubricas.length} rubrica(s)</span>
        )}
        <span className="plan-grupo-total">{brl(valorCampo)}</span>
      </button>

      {aberto && (
        <div className="plan-linhas">
          {/* Sugestões de nome (REQ-F-020): autocompletar nativo, local. */}
          <datalist id={`sug-${categoria}-${campo.campo}`}>
            {(SUGESTOES_RUBRICA[campo.campo] ?? []).map((s) => (
              <option key={s} value={s} />
            ))}
          </datalist>
          {rubricas.map((r) => (
            <Linha
              key={r.id}
              rubrica={r}
              mutar={mutar}
              sugestoesId={`sug-${categoria}-${campo.campo}`}
            />
          ))}
          {!detalhado && (
            <div className="plan-dica">
              Sem rubricas: o valor é o digitado direto na aba Perfil.
            </div>
          )}
          <button className="plan-add" onClick={criar}>
            + Rubrica em “{campo.rotulo}”
          </button>
        </div>
      )}
    </div>
  )
}

/**
 * Linha editável (nome + valor). Edição em rascunho local, gravada no blur ou
 * Enter — uma requisição por edição concluída, não por tecla.
 */
function Linha({
  rubrica,
  mutar,
  sugestoesId,
}: {
  rubrica: RubricaOut
  mutar: (p: Promise<RubricaMutOut>) => void
  sugestoesId: string
}) {
  // Rascunho por foco: fora de edição a linha exibe o SERVIDOR (valor já
  // formatado e somado no core); ao focar, tira-se um snapshot editável. A
  // gravação acontece quando o foco SAI da linha (relatedTarget fora dela) —
  // o Tab entre nome↔valor não dispara requisição nem perde a digitação.
  const [rascunho, setRascunho] = useState<{
    nome: string
    valor: string
  } | null>(null)

  const doServidor = () => ({
    nome: rubrica.nome,
    valor: rubrica.valor ? numBR(rubrica.valor) : '',
  })
  const nome = rascunho ? rascunho.nome : rubrica.nome
  const valor = rascunho ? rascunho.valor : doServidor().valor

  const aoFocar = () => setRascunho((r) => r ?? doServidor())

  const aoSairDaLinha = (ev: FocusEvent<HTMLDivElement>) => {
    if (ev.currentTarget.contains(ev.relatedTarget as Node | null)) return
    const nomeFinal = nome.trim() || rubrica.nome
    const valorFinal = parseBR(valor)
    setRascunho(null)
    if (nomeFinal !== rubrica.nome || valorFinal !== rubrica.valor) {
      mutar(hf.rubricaEditar(rubrica.id, nomeFinal, valorFinal))
    }
  }

  const aoEnter = (ev: KeyboardEvent<HTMLInputElement>) => {
    if (ev.key === 'Enter') ev.currentTarget.blur()
  }

  return (
    <div className="plan-linha" onFocus={aoFocar} onBlur={aoSairDaLinha}>
      <input
        className="plan-nome"
        list={sugestoesId}
        value={nome}
        onChange={(ev) =>
          setRascunho((r) => ({ ...(r ?? doServidor()), nome: ev.target.value }))
        }
        onKeyDown={aoEnter}
        aria-label="Nome da rubrica"
      />
      <span className="plan-valor">
        <span className="campo-prefixo">R$</span>
        <input
          className="campo-num"
          inputMode="decimal"
          placeholder="0,00"
          value={valor}
          onChange={(ev) =>
            setRascunho((r) => ({
              ...(r ?? doServidor()),
              valor: ev.target.value,
            }))
          }
          onKeyDown={aoEnter}
          aria-label="Valor da rubrica"
        />
      </span>
      <button
        className="btn-remover"
        title="Remover rubrica"
        onClick={() => mutar(hf.rubricaRemover(rubrica.id))}
      >
        ×
      </button>
    </div>
  )
}
