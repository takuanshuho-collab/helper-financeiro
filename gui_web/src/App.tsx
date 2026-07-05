import { useState } from 'react'

import type { PerfilIn } from './hf/contract'
import { useAnalise } from './hf/useAnalise'
import EmConstrucao from './screens/EmConstrucao'
import Perfil from './screens/Perfil'
import VisaoGeral from './screens/VisaoGeral'

// As 6 telas do redesign "Clareza" (REQ-F-010..016).
const ABAS = [
  'Visão geral',
  'Perfil',
  'Dívidas',
  'Contrato PDF',
  'Análise',
  'Carta ao credor',
] as const

// Perfil semente (M8): dados de exemplo enquanto as telas Perfil (T-803) e
// Dívidas (T-804) ainda não editam este estado. Vira "Atenção" para mostrar o
// diagnóstico colorido.
const PERFIL_SEED: PerfilIn = {
  renda: { salario_liquido: 5000 },
  fixas: { moradia: 1400, contas_casa: 500, transporte: 300 },
  variaveis: { mercado: 800 },
  reserva_emergencia: 3000,
  saldo_fgts: 3000,
  dividas: [
    {
      credor: 'Cartão Banco A',
      tipo: 'Cartão de crédito',
      saldo_devedor: 5000,
      taxa_mensal: 0.12,
      parcela: 900,
      parcelas_restantes: 12,
    },
    {
      credor: 'CDC Veículo',
      tipo: 'CDC (Crédito Direto ao Consumidor)',
      saldo_devedor: 20000,
      taxa_mensal: 0.025,
      parcela: 700,
      parcelas_restantes: 36,
    },
    {
      credor: 'Consignado',
      tipo: 'Consignado',
      saldo_devedor: 6000,
      taxa_mensal: 0.018,
      parcela: 350,
      parcelas_restantes: 20,
    },
  ],
}

export default function App() {
  const [abaAtiva, setAbaAtiva] = useState(0)
  const [perfil, setPerfil] = useState<PerfilIn>(PERFIL_SEED)
  const analise = useAnalise(perfil)

  function tela() {
    switch (abaAtiva) {
      case 0:
        return <VisaoGeral analise={analise} />
      case 1:
        return <Perfil perfil={perfil} setPerfil={setPerfil} analise={analise} />
      default:
        return <EmConstrucao titulo={ABAS[abaAtiva]} />
    }
  }

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

      <main className="conteudo">{tela()}</main>
    </div>
  )
}
