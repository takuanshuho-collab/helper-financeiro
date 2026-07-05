import type { ReactNode } from 'react'

import CampoMoeda from '../components/CampoMoeda'
import type { PerfilIn } from '../hf/contract'
import type { Analise } from '../hf/useAnalise'
import { brl, pct0 } from '../lib/format'

type AtualizarPerfil = (transform: (p: PerfilIn) => PerfilIn) => void

export default function Perfil({
  perfil,
  setPerfil,
  analise,
}: {
  perfil: PerfilIn
  setPerfil: AtualizarPerfil
  analise: Analise
}) {
  const d = analise.diagnostico

  const setRenda = (campo: keyof NonNullable<PerfilIn['renda']>, v: number) =>
    setPerfil((p) => ({ ...p, renda: { ...p.renda, [campo]: v } }))
  const setFixas = (campo: keyof NonNullable<PerfilIn['fixas']>, v: number) =>
    setPerfil((p) => ({ ...p, fixas: { ...p.fixas, [campo]: v } }))
  const setVar = (campo: keyof NonNullable<PerfilIn['variaveis']>, v: number) =>
    setPerfil((p) => ({ ...p, variaveis: { ...p.variaveis, [campo]: v } }))

  const renda = d?.renda_liquida ?? 0
  const fixas = d?.despesas_fixas ?? 0
  const variaveis = d?.despesas_variaveis ?? 0
  const parcelas = d?.total_parcelas ?? 0
  const sobra = d?.fluxo_caixa ?? 0

  return (
    <>
      <h1 className="titulo">Perfil e orçamento</h1>
      <p className="sub">
        Itemize sua renda e despesas — o diagnóstico recalcula ao vivo.
      </p>

      <section className="card">
        <div className="card-titulo">Para onde vai a sua renda</div>
        <BarraAloc
          renda={renda}
          fixas={fixas}
          variaveis={variaveis}
          parcelas={parcelas}
          sobra={sobra}
        />
      </section>

      <div className="perfil-grid">
        <Secao titulo="Renda líquida mensal" cor="var(--green)" total={renda}>
          <CampoMoeda
            rotulo="Salário/benefício líquido"
            valor={perfil.renda?.salario_liquido ?? 0}
            onValor={(v) => setRenda('salario_liquido', v)}
          />
          <CampoMoeda
            rotulo="Renda extra/autônoma"
            valor={perfil.renda?.renda_extra ?? 0}
            onValor={(v) => setRenda('renda_extra', v)}
          />
          <CampoMoeda
            rotulo="Outras rendas"
            valor={perfil.renda?.outras_rendas ?? 0}
            onValor={(v) => setRenda('outras_rendas', v)}
          />
        </Secao>

        <Secao titulo="Despesas fixas" cor="var(--red)" total={fixas}>
          <CampoMoeda
            rotulo="Moradia"
            valor={perfil.fixas?.moradia ?? 0}
            onValor={(v) => setFixas('moradia', v)}
          />
          <CampoMoeda
            rotulo="Contas da casa"
            valor={perfil.fixas?.contas_casa ?? 0}
            onValor={(v) => setFixas('contas_casa', v)}
          />
          <CampoMoeda
            rotulo="Transporte"
            valor={perfil.fixas?.transporte ?? 0}
            onValor={(v) => setFixas('transporte', v)}
          />
          <CampoMoeda
            rotulo="Saúde"
            valor={perfil.fixas?.saude ?? 0}
            onValor={(v) => setFixas('saude', v)}
          />
          <CampoMoeda
            rotulo="Educação"
            valor={perfil.fixas?.educacao ?? 0}
            onValor={(v) => setFixas('educacao', v)}
          />
          <CampoMoeda
            rotulo="Assinaturas/academia"
            valor={perfil.fixas?.assinaturas ?? 0}
            onValor={(v) => setFixas('assinaturas', v)}
          />
          <CampoMoeda
            rotulo="Outras fixas"
            valor={perfil.fixas?.outras_fixas ?? 0}
            onValor={(v) => setFixas('outras_fixas', v)}
          />
        </Secao>

        <Secao titulo="Despesas variáveis" cor="var(--orange)" total={variaveis}>
          <CampoMoeda
            rotulo="Mercado"
            valor={perfil.variaveis?.mercado ?? 0}
            onValor={(v) => setVar('mercado', v)}
          />
          <CampoMoeda
            rotulo="Lazer/delivery"
            valor={perfil.variaveis?.lazer ?? 0}
            onValor={(v) => setVar('lazer', v)}
          />
          <CampoMoeda
            rotulo="Vestuário/cuidados"
            valor={perfil.variaveis?.vestuario ?? 0}
            onValor={(v) => setVar('vestuario', v)}
          />
          <CampoMoeda
            rotulo="Imprevistos"
            valor={perfil.variaveis?.imprevistos ?? 0}
            onValor={(v) => setVar('imprevistos', v)}
          />
          <CampoMoeda
            rotulo="Outras variáveis"
            valor={perfil.variaveis?.outras_variaveis ?? 0}
            onValor={(v) => setVar('outras_variaveis', v)}
          />
        </Secao>

        <Secao
          titulo="Reserva e FGTS"
          cor="var(--accent)"
          total={perfil.reserva_emergencia ?? 0}
        >
          <CampoMoeda
            rotulo="Reserva de emergência"
            valor={perfil.reserva_emergencia ?? 0}
            onValor={(v) => setPerfil((p) => ({ ...p, reserva_emergencia: v }))}
          />
          <CampoMoeda
            rotulo="Saldo de FGTS"
            valor={perfil.saldo_fgts ?? 0}
            onValor={(v) => setPerfil((p) => ({ ...p, saldo_fgts: v }))}
          />
          <div className="cobertura">
            Cobertura da reserva:{' '}
            <strong>
              {d?.meses_reserva == null
                ? '—'
                : `${d.meses_reserva.toFixed(1).replace('.', ',')} meses de despesas`}
            </strong>
          </div>
        </Secao>
      </div>

      <div className="sumbar">
        <ResumoItem
          rotulo="Fluxo de caixa livre"
          valor={brl(sobra)}
          cor={sobra >= 0 ? 'var(--green)' : 'var(--red)'}
        />
        <ResumoItem
          rotulo="Comprometimento com dívidas"
          valor={d ? pct0(d.comprometimento_renda) : '—'}
        />
        <ResumoItem rotulo="Despesas totais" valor={brl(d?.despesas_totais ?? 0)} />
      </div>
    </>
  )
}

function Secao({
  titulo,
  cor,
  total,
  children,
}: {
  titulo: string
  cor: string
  total: number
  children: ReactNode
}) {
  return (
    <section className="secao">
      <div className="secao-topo">
        <span className="secao-titulo">
          <span className="secao-ponto" style={{ background: cor }} />
          {titulo}
        </span>
        <span className="secao-total">{brl(total)}</span>
      </div>
      {children}
    </section>
  )
}

function BarraAloc({
  renda,
  fixas,
  variaveis,
  parcelas,
  sobra,
}: {
  renda: number
  fixas: number
  variaveis: number
  parcelas: number
  sobra: number
}) {
  const base = renda > 0 ? renda : 1
  const larg = (v: number) => `${Math.max(0, (v / base) * 100)}%`
  const sobraPos = Math.max(sobra, 0)

  return (
    <>
      <div className="aloc">
        <div
          className="aloc-seg"
          style={{ width: larg(fixas), background: 'var(--red)' }}
        />
        <div
          className="aloc-seg"
          style={{ width: larg(variaveis), background: 'var(--orange)' }}
        />
        <div
          className="aloc-seg"
          style={{ width: larg(parcelas), background: 'var(--primary)' }}
        />
        <div
          className="aloc-seg"
          style={{ width: larg(sobraPos), background: 'var(--green)' }}
        />
      </div>
      <div className="aloc-legenda">
        <ItemLeg cor="var(--red)" nome="Fixas" valor={fixas} base={base} />
        <ItemLeg cor="var(--orange)" nome="Variáveis" valor={variaveis} base={base} />
        <ItemLeg cor="var(--primary)" nome="Parcelas" valor={parcelas} base={base} />
        <ItemLeg cor="var(--green)" nome="Sobra" valor={sobra} base={base} />
      </div>
    </>
  )
}

function ItemLeg({
  cor,
  nome,
  valor,
  base,
}: {
  cor: string
  nome: string
  valor: number
  base: number
}) {
  return (
    <span className="aloc-item">
      <span className="aloc-cor" style={{ background: cor }} />
      {nome} <span className="aloc-val">{brl(valor)}</span> ({pct0(valor / base)})
    </span>
  )
}

function ResumoItem({
  rotulo,
  valor,
  cor,
}: {
  rotulo: string
  valor: string
  cor?: string
}) {
  return (
    <div className="sumitem">
      <div className="sumitem-rotulo">{rotulo}</div>
      <div className="sumitem-valor" style={cor ? { color: cor } : undefined}>
        {valor}
      </div>
    </div>
  )
}
