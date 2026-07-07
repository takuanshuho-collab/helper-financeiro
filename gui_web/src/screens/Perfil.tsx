import { useState, type ReactNode } from 'react'

import CampoMoeda from '../components/CampoMoeda'
import type {
  Categoria,
  PerfilIn,
  RubricaMutOut,
  RubricaOut,
} from '../hf/contract'
import type { Analise } from '../hf/useAnalise'
import { brl, numBR, pct0 } from '../lib/format'
import { SECOES_ORCAMENTO, campoDetalhado } from '../lib/orcamento'
import Planilha from './Planilha'

type AtualizarPerfil = (transform: (p: PerfilIn) => PerfilIn) => void

export default function Perfil({
  perfil,
  setPerfil,
  analise,
  rubricas,
  aoMutarRubricas,
}: {
  perfil: PerfilIn
  setPerfil: AtualizarPerfil
  analise: Analise
  rubricas: RubricaOut[]
  aoMutarRubricas: (r: RubricaMutOut) => void
}) {
  const d = analise.diagnostico
  // Planilha de orçamento (T-1104): sub-tela aberta pelo botão ou pelos selos
  // "detalhado ▸" — volta ao Perfil sem perder o estado das outras abas.
  const [planilha, setPlanilha] = useState(false)

  const setCampo = (categoria: Categoria, campo: string, v: number) =>
    setPerfil((p) => ({
      ...p,
      [categoria]: { ...(p[categoria] ?? {}), [campo]: v },
    }))

  const renda = d?.renda_liquida ?? 0
  const fixas = d?.despesas_fixas ?? 0
  const variaveis = d?.despesas_variaveis ?? 0
  const parcelas = d?.total_parcelas ?? 0
  const sobra = d?.fluxo_caixa ?? 0
  const totais: Record<Categoria, number> = { renda, fixas, variaveis }

  if (planilha) {
    return (
      <Planilha
        perfil={perfil}
        rubricas={rubricas}
        aoMutar={aoMutarRubricas}
        aoVoltar={() => setPlanilha(false)}
      />
    )
  }

  return (
    <>
      <div className="titulo-linha">
        <div>
          <h1 className="titulo">Perfil e orçamento</h1>
          <p className="sub">
            Itemize sua renda e despesas — o diagnóstico recalcula ao vivo.
          </p>
        </div>
        <button className="btn-add" onClick={() => setPlanilha(true)}>
          Detalhar orçamento
        </button>
      </div>

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
        {SECOES_ORCAMENTO.map((secao) => (
          <Secao
            key={secao.categoria}
            titulo={secao.titulo}
            cor={secao.cor}
            total={totais[secao.categoria]}
          >
            {secao.campos.map(({ campo, rotulo }) => {
              const valor =
                (perfil[secao.categoria] as Record<string, number> | undefined)
                  ?.[campo] ?? 0
              return campoDetalhado(rubricas, secao.categoria, campo) ? (
                <CampoDetalhado
                  key={campo}
                  rotulo={rotulo}
                  valor={valor}
                  aoAbrir={() => setPlanilha(true)}
                />
              ) : (
                <CampoMoeda
                  key={campo}
                  rotulo={rotulo}
                  valor={valor}
                  onValor={(v) => setCampo(secao.categoria, campo, v)}
                />
              )
            })}
          </Secao>
        ))}

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

/**
 * Campo detalhado em rubricas (ADR-0012): somente-leitura, exibindo a soma
 * feita no core; o selo leva à planilha, onde a edição acontece.
 */
function CampoDetalhado({
  rotulo,
  valor,
  aoAbrir,
}: {
  rotulo: string
  valor: number
  aoAbrir: () => void
}) {
  return (
    <button
      type="button"
      className="campo campo-detalhado"
      onClick={aoAbrir}
      title="Campo detalhado em rubricas — clique para abrir a planilha"
    >
      <span className="campo-rotulo">
        {rotulo} <span className="selo-det">detalhado ▸</span>
      </span>
      <span className="campo-input">
        <span className="campo-prefixo">R$</span>
        <span className="campo-num campo-num-fixo">{numBR(valor)}</span>
      </span>
    </button>
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
