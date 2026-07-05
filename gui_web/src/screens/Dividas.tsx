import CampoMoeda from '../components/CampoMoeda'
import CampoPercent from '../components/CampoPercent'
import type { DividaIn, PerfilIn } from '../hf/contract'
import type { Analise } from '../hf/useAnalise'
import { brl, faixaTaxa, iniciais, pct0, taxaAm } from '../lib/format'

type AtualizarPerfil = (transform: (p: PerfilIn) => PerfilIn) => void

// Espelha core.models.TIPOS_DIVIDA — é enumeração de UI (o `select`), não conta.
const TIPOS_DIVIDA = [
  'CDC (Crédito Direto ao Consumidor)',
  'Consignado',
  'Cartão de crédito',
  'Cheque especial',
  'Financiamento',
  'Empréstimo pessoal',
  'Outro',
]

const NOVA_DIVIDA: DividaIn = {
  credor: 'Nova dívida',
  tipo: 'Cartão de crédito',
  saldo_devedor: 0,
  taxa_mensal: 0,
  parcela: 0,
  parcelas_restantes: 0,
}

export default function Dividas({
  perfil,
  setPerfil,
  analise,
}: {
  perfil: PerfilIn
  setPerfil: AtualizarPerfil
  analise: Analise
}) {
  const d = analise.diagnostico
  const dividas = perfil.dividas ?? []
  const saldoTotal = d?.saldo_devedor_total ?? 0
  const maisCara = d?.divida_mais_cara?.credor ?? null

  const setCampo = <K extends keyof DividaIn>(i: number, campo: K, v: DividaIn[K]) =>
    setPerfil((p) => {
      const lista = [...(p.dividas ?? [])]
      lista[i] = { ...lista[i], [campo]: v }
      return { ...p, dividas: lista }
    })
  const remover = (i: number) =>
    setPerfil((p) => ({
      ...p,
      dividas: (p.dividas ?? []).filter((_, j) => j !== i),
    }))
  const adicionar = () =>
    setPerfil((p) => ({ ...p, dividas: [...(p.dividas ?? []), { ...NOVA_DIVIDA }] }))

  if (analise.estado.fase === 'erro') {
    return (
      <div className="aviso-erro">
        Sem conexão com o núcleo: {analise.estado.erro}
      </div>
    )
  }

  const corMedia = d ? faixaTaxa(d.taxa_media_ponderada).cor : undefined

  return (
    <>
      <h1 className="titulo">Dívidas</h1>
      <p className="sub">
        Cadastre cada dívida — as estatísticas recalculam ao vivo no núcleo.
      </p>

      <section className="stats-band">
        <Stat
          rotulo="Saldo devedor total"
          valor={brl(saldoTotal)}
          nota={`${dividas.length} dívida(s)`}
        />
        <Stat
          rotulo="Parcelas por mês"
          valor={brl(d?.total_parcelas ?? 0)}
          nota={d ? `${pct0(d.comprometimento_renda)} da renda` : '—'}
        />
        <Stat
          rotulo="Taxa média (pelo saldo)"
          valor={d ? taxaAm(d.taxa_media_ponderada) : '—'}
          nota="ponderada pelo saldo devedor"
          cor={corMedia}
        />
        <Stat
          rotulo="Custo até quitar"
          valor={brl(d?.custo_total_ate_quitar ?? 0)}
          nota={d ? `${brl(d.juros_totais_futuros)} só de juros` : '—'}
        />
      </section>

      <div className="dhead">
        <div className="card-titulo">Suas dívidas</div>
        <button className="btn-add" onClick={adicionar}>
          + Adicionar dívida
        </button>
      </div>

      {dividas.length === 0 ? (
        <section className="card placeholder">
          <div className="placeholder-emoji">🎉</div>
          <div>
            Nenhuma dívida cadastrada. Use <strong>+ Adicionar dívida</strong>{' '}
            para incluir a primeira.
          </div>
        </section>
      ) : (
        <div className="dividas-lista">
          {dividas.map((dv, i) => (
            <CartaoDivida
              key={i}
              divida={dv}
              saldoTotal={saldoTotal}
              maisCara={!!dv.credor && dv.credor === maisCara}
              onCampo={(campo, v) => setCampo(i, campo, v)}
              onRemover={() => remover(i)}
            />
          ))}
        </div>
      )}
    </>
  )
}

function CartaoDivida({
  divida,
  saldoTotal,
  maisCara,
  onCampo,
  onRemover,
}: {
  divida: DividaIn
  saldoTotal: number
  maisCara: boolean
  onCampo: <K extends keyof DividaIn>(campo: K, v: DividaIn[K]) => void
  onRemover: () => void
}) {
  const { cor, tint } = faixaTaxa(divida.taxa_mensal ?? 0)
  const saldo = divida.saldo_devedor ?? 0
  const part = saldoTotal > 0 ? saldo / saldoTotal : 0

  return (
    <section className="dcard">
      <div className="dcard-topo">
        <span className="dcard-chip" style={{ color: cor, background: tint }}>
          {iniciais(divida.tipo)}
        </span>
        <input
          className="dcard-credor"
          value={divida.credor}
          placeholder="Nome do credor"
          onChange={(ev) => onCampo('credor', ev.target.value)}
        />
        {maisCara && <span className="selo-cara">Mais cara</span>}
        <button
          className="btn-remover"
          onClick={onRemover}
          aria-label="Remover dívida"
          title="Remover dívida"
        >
          ✕
        </button>
      </div>

      <div className="dcard-grid">
        <label className="campo">
          <span className="campo-rotulo">Tipo</span>
          <select
            className="campo-select"
            value={divida.tipo}
            onChange={(ev) => onCampo('tipo', ev.target.value)}
          >
            {TIPOS_DIVIDA.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </label>

        <CampoMoeda
          rotulo="Saldo devedor"
          valor={saldo}
          onValor={(v) => onCampo('saldo_devedor', v)}
        />
        <CampoPercent
          rotulo="Taxa de juros"
          valor={divida.taxa_mensal ?? 0}
          onValor={(v) => onCampo('taxa_mensal', v)}
        />
        <CampoMoeda
          rotulo="Parcela mensal"
          valor={divida.parcela ?? 0}
          onValor={(v) => onCampo('parcela', v)}
        />

        <label className="campo">
          <span className="campo-rotulo">Parcelas restantes</span>
          <span className="campo-input">
            <input
              className="campo-num"
              inputMode="numeric"
              placeholder="0"
              value={divida.parcelas_restantes || ''}
              onChange={(ev) =>
                onCampo(
                  'parcelas_restantes',
                  Math.max(0, Math.trunc(Number(ev.target.value) || 0)),
                )
              }
            />
            <span className="campo-sufixo">x</span>
          </span>
        </label>
      </div>

      <div className="part">
        <div className="part-bar">
          <div
            className="part-fill"
            style={{ width: `${Math.min(part, 1) * 100}%`, background: cor }}
          />
        </div>
        <span className="part-cap">{pct0(part)} do saldo total</span>
      </div>
    </section>
  )
}

function Stat({
  rotulo,
  valor,
  nota,
  cor,
}: {
  rotulo: string
  valor: string
  nota: string
  cor?: string
}) {
  return (
    <div className="stat">
      <div className="stat-rotulo">{rotulo}</div>
      <div className="stat-valor" style={cor ? { color: cor } : undefined}>
        {valor}
      </div>
      <div className="stat-nota">{nota}</div>
    </div>
  )
}
