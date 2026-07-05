import type { ReactNode } from 'react'

import {
  IconeDespesas,
  IconeParcelas,
  IconeRenda,
  IconeSaldo,
} from '../components/Icones'
import type { DividaOut, EstrategiaOut } from '../hf/contract'
import type { Analise } from '../hf/useAnalise'
import { brl, corSaude, faixaTaxa, iniciais, pct0, taxaAm } from '../lib/format'

export default function VisaoGeral({ analise }: { analise: Analise }) {
  const { estado, diagnostico: d, estrategias } = analise

  if (estado.fase === 'erro') {
    return <div className="aviso-erro">Sem conexão com o núcleo: {estado.erro}</div>
  }
  if (!d) {
    return <div className="sub">Calculando o diagnóstico…</div>
  }

  const cor = corSaude(d.classificacao)
  const graus = Math.min(d.comprometimento_renda, 1) * 360

  return (
    <>
      <div className="head">
        <div>
          <h1 className="titulo">Visão geral</h1>
          <p className="sub">Diagnóstico calculado ao vivo a partir do seu orçamento.</p>
        </div>
        <span className="pill" style={{ color: cor, borderColor: cor }}>
          {d.classificacao}
        </span>
      </div>

      <section className="card hero">
        <div>
          <div className="hero-kicker">DIAGNÓSTICO DE SAÚDE FINANCEIRA</div>
          <div className="hero-label" style={{ color: cor }}>
            {d.classificacao}
          </div>
          <p className="hero-desc">
            Suas parcelas comprometem <strong>{pct0(d.comprometimento_renda)}</strong>{' '}
            da renda líquida.{' '}
            {d.fluxo_caixa >= 0 ? (
              <>
                Sobram <strong>{brl(d.fluxo_caixa)}</strong> por mês depois de
                despesas e parcelas.
              </>
            ) : (
              <>
                Faltam <strong>{brl(Math.abs(d.fluxo_caixa))}</strong> por mês —
                as saídas superam as entradas.
              </>
            )}
          </p>
        </div>
        <div className="anel-wrap">
          <div
            className="anel"
            style={{ background: `conic-gradient(${cor} ${graus}deg, var(--trilha) 0deg)` }}
          >
            <div className="anel-centro">
              <div className="anel-num">{pct0(d.comprometimento_renda)}</div>
              <div className="anel-cap">da renda</div>
            </div>
          </div>
        </div>
      </section>

      <div className="grid4">
        <Metrica
          icone={<IconeRenda />}
          cor="var(--green)"
          rotulo="Renda líquida"
          valor={brl(d.renda_liquida)}
          nota="entradas do mês"
        />
        <Metrica
          icone={<IconeDespesas />}
          cor="var(--orange)"
          rotulo="Despesas"
          valor={brl(d.despesas_totais)}
          nota="fixas + variáveis"
        />
        <Metrica
          icone={<IconeParcelas />}
          cor="var(--accent)"
          rotulo="Parcelas / mês"
          valor={brl(d.total_parcelas)}
          nota={`${pct0(d.comprometimento_renda)} da renda`}
        />
        <Metrica
          icone={<IconeSaldo />}
          cor="var(--red)"
          rotulo="Saldo devedor"
          valor={brl(d.saldo_devedor_total)}
          nota={`${d.ranking.length} dívida(s)`}
        />
      </div>

      <div className="cols">
        <section className="card">
          <div className="card-titulo">Suas dívidas</div>
          {d.ranking.length === 0 ? (
            <p className="sub">Nenhuma dívida cadastrada.</p>
          ) : (
            <ul className="lista-div">
              {d.ranking.map((div, i) => (
                <LinhaDivida key={div.credor} divida={div} maisCara={i === 0} />
              ))}
            </ul>
          )}
        </section>

        <section className="card">
          <div className="card-titulo">Estratégia de quitação</div>
          {estrategias ? (
            <div className="estrats">
              <CardEstrategia
                nome="Avalanche"
                selo="Recomendada"
                destaque
                e={estrategias.avalanche}
              />
              <CardEstrategia nome="Bola de neve" e={estrategias.bola_de_neve} />
            </div>
          ) : (
            <p className="sub">Simulando…</p>
          )}
        </section>
      </div>
    </>
  )
}

function Metrica({
  icone,
  cor,
  rotulo,
  valor,
  nota,
}: {
  icone: ReactNode
  cor: string
  rotulo: string
  valor: string
  nota: string
}) {
  return (
    <div className="mcard">
      <span className="mchip" style={{ color: cor, background: 'var(--surface)' }}>
        {icone}
      </span>
      <div className="mrotulo">{rotulo}</div>
      <div className="mvalor">{valor}</div>
      <div className="mnota">{nota}</div>
    </div>
  )
}

function LinhaDivida({ divida, maisCara }: { divida: DividaOut; maisCara: boolean }) {
  const { cor, tint } = faixaTaxa(divida.taxa_mensal)
  return (
    <li className="ldiv">
      <span className="ldiv-chip" style={{ color: cor, background: tint }}>
        {iniciais(divida.tipo)}
      </span>
      <div className="ldiv-info">
        <div className="ldiv-tipo">
          {divida.tipo}
          {maisCara && <span className="selo-cara">Mais cara</span>}
        </div>
        <div className="ldiv-meta">
          {divida.credor} · {divida.parcelas_restantes}x
        </div>
      </div>
      <div className="ldiv-num">
        <div className="ldiv-saldo">{brl(divida.saldo_devedor)}</div>
        <div className="ldiv-taxa" style={{ color: cor }}>
          {taxaAm(divida.taxa_mensal)}
        </div>
      </div>
    </li>
  )
}

function CardEstrategia({
  nome,
  selo,
  destaque,
  e,
}: {
  nome: string
  selo?: string
  destaque?: boolean
  e: EstrategiaOut
}) {
  const quita = e.quitavel && e.meses != null
  return (
    <div className={destaque ? 'scard scard-win' : 'scard'}>
      <div className="scard-topo">
        <span className="scard-nome">{nome}</span>
        {selo && <span className="scard-selo">{selo}</span>}
      </div>
      <div className="scard-meses">{quita ? `${e.meses} meses` : 'não quita'}</div>
      <div className="scard-juros">
        {quita
          ? `${brl(e.juros_pagos)} em juros no caminho`
          : 'as parcelas mínimas não cobrem os juros'}
      </div>
    </div>
  )
}
