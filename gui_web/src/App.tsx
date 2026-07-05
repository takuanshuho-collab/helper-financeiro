import { useEffect, useState } from 'react'

// As 6 telas do redesign "Clareza" (REQ-F-010..016). No M7 são placeholders;
// M8/M9 constroem cada uma consumindo o sidecar.
const ABAS = [
  'Visão geral',
  'Perfil',
  'Dívidas',
  'Contrato PDF',
  'Análise',
  'Carta ao credor',
] as const

// Perfil de exemplo — só para provar a ponte com o sidecar no andaime.
const PERFIL_EXEMPLO = {
  renda: { salario_liquido: 5000 },
  fixas: { moradia: 1500, contas_casa: 500 },
  variaveis: { mercado: 800 },
  reserva_emergencia: 6000,
  dividas: [
    {
      credor: 'Banco X',
      tipo: 'Cartão de crédito',
      saldo_devedor: 10000,
      taxa_mensal: 0.09,
      parcela: 1200,
      parcelas_restantes: 12,
    },
  ],
}

interface Diagnostico {
  classificacao: string
  comprometimento_renda: number
  fluxo_caixa: number
  despesas_totais: number
  total_parcelas: number
  meses_reserva: number | null
}

export default function App() {
  const [abaAtiva, setAbaAtiva] = useState(0)
  const [status, setStatus] = useState('conectando…')
  const [diag, setDiag] = useState<Diagnostico | null>(null)

  useEffect(() => {
    const ponte = window.hf
    if (!ponte) {
      setStatus('sidecar indisponível (rode dentro do Electron)')
      return
    }
    ponte
      .invoke('/health')
      .then(() => ponte.invoke<Diagnostico>('/diagnostico', PERFIL_EXEMPLO))
      .then((d) => {
        setDiag(d)
        setStatus('conectado ao sidecar')
      })
      .catch((e: Error) => setStatus(`erro: ${e.message}`))
  }, [])

  return (
    <div className="app">
      <header className="topbar">
        <div className="marca">
          <span className="marca-quadro">R$</span>
          <div>
            <div className="marca-nome">Helper Financeiro</div>
            <div className="marca-kicker">DIAGNÓSTICO · ESTRATÉGIAS · PROPOSTAS</div>
          </div>
        </div>
        <nav className="nav">
          {ABAS.map((aba, i) => (
            <button
              key={aba}
              className={i === abaAtiva ? 'nav-item on' : 'nav-item'}
              onClick={() => setAbaAtiva(i)}
            >
              {aba}
            </button>
          ))}
        </nav>
      </header>

      <main className="conteudo">
        <h1 className="titulo">{ABAS[abaAtiva]}</h1>
        <p className="sub">Andaime do redesign "Clareza" (ADR-0009) — M7.</p>

        <section className="card">
          <div className="card-rotulo">Ponte com o núcleo (sidecar)</div>
          <div className={`status status-${diag ? 'ok' : 'wait'}`}>{status}</div>
          {diag && (
            <div className="metricas">
              <Metrica titulo="Classificação" valor={diag.classificacao} />
              <Metrica
                titulo="Comprometimento"
                valor={`${(diag.comprometimento_renda * 100).toFixed(0)}%`}
              />
              <Metrica titulo="Fluxo de caixa" valor={brl(diag.fluxo_caixa)} />
              <Metrica
                titulo="Cobertura da reserva"
                valor={
                  diag.meses_reserva == null
                    ? '—'
                    : `${diag.meses_reserva.toFixed(1)} meses`
                }
              />
            </div>
          )}
        </section>
      </main>
    </div>
  )
}

function Metrica({ titulo, valor }: { titulo: string; valor: string }) {
  return (
    <div className="metrica">
      <div className="metrica-titulo">{titulo}</div>
      <div className="metrica-valor">{valor}</div>
    </div>
  )
}

function brl(v: number): string {
  return v.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })
}
