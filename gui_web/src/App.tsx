import { useState } from 'react'

import type { DividaIn, PerfilIn, SecaoIaOut } from './hf/contract'
import { useAnalise } from './hf/useAnalise'
import Analise from './screens/Analise'
import Carta from './screens/Carta'
import Contrato from './screens/Contrato'
import Dividas from './screens/Dividas'
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

// Perfil semente (M8): ponto de partida editável pelas telas Perfil (T-803) e
// Dívidas (T-804). Começa em "Atenção" para mostrar o diagnóstico colorido.
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
  // Última análise sênior da sessão (T-902): vive aqui para sobreviver à troca
  // de aba e entrar no relatório .docx — paridade com a GUI tkinter.
  const [secaoIa, setSecaoIa] = useState<SecaoIaOut | null>(null)
  const analise = useAnalise(perfil)

  // Contrato PDF (T-901): a dívida confirmada entra no perfil e a navegação
  // segue para Dívidas, onde o usuário ajusta saldo atual e parcelas restantes.
  const adicionarDivida = (divida: DividaIn) => {
    setPerfil((p) => ({ ...p, dividas: [...(p.dividas ?? []), divida] }))
    setAbaAtiva(2)
  }

  function tela() {
    switch (abaAtiva) {
      case 0:
        return <VisaoGeral analise={analise} />
      case 1:
        return <Perfil perfil={perfil} setPerfil={setPerfil} analise={analise} />
      case 2:
        return <Dividas perfil={perfil} setPerfil={setPerfil} analise={analise} />
      case 3:
        return <Contrato onNovaDivida={adicionarDivida} />
      case 4:
        return (
          <Analise
            perfil={perfil}
            analise={analise}
            secaoIa={secaoIa}
            setSecaoIa={setSecaoIa}
          />
        )
      default:
        return <Carta perfil={perfil} />
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
