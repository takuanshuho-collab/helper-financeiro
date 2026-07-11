import { useEffect, useRef, useState } from 'react'

import { IconeCadeadoAberto, IconeLua, IconeSol } from './components/Icones'
import { HfErro, aoBloquear, hf } from './hf/client'
import type {
  AuthStatusOut,
  DividaIn,
  PerfilIn,
  RubricaMutOut,
  RubricaOut,
  SecaoIaOut,
} from './hf/contract'
import { useAnalise } from './hf/useAnalise'
import Analise from './screens/Analise'
import Carta from './screens/Carta'
import ConfiguracaoIa from './screens/ConfiguracaoIa'
import Contrato from './screens/Contrato'
import Desbloqueio from './screens/Desbloqueio'
import Dividas from './screens/Dividas'
import Onboarding from './screens/Onboarding'
import Perfil from './screens/Perfil'
import VisaoGeral from './screens/VisaoGeral'

// As 6 telas do redesign "Clareza" (REQ-F-010..016) + Configuração da IA
// (T-1702, ADR-0016 §F).
const ABAS = [
  'Visão geral',
  'Perfil',
  'Dívidas',
  'Contrato',
  'Análise',
  'Carta ao credor',
  'Configuração da IA',
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

// Tema (T-904, REQ-F-010): `hf_dark` no localStorage guarda a escolha do
// usuário ('1' escuro, '0' claro); sem escolha salva, o app segue o SO
// (@media prefers-color-scheme no CSS — nenhum data-theme é aplicado).
const CHAVE_TEMA = 'hf_dark'

function escolhaSalva(): boolean | null {
  const salvo = localStorage.getItem(CHAVE_TEMA)
  return salvo === null ? null : salvo === '1'
}

function temaDoSo(): boolean {
  return window.matchMedia('(prefers-color-scheme: dark)').matches
}

export default function App() {
  // Cofre (T-1604, ADR-0016 §D / REQ-SEC-005): nenhuma tela de negócio
  // aparece antes do gate resolver. `authStatus === null` = ainda
  // consultando `/auth/status`; `semGate` = sidecar inalcançável (fora do
  // Electron, iteração de UI) — não há dado real para proteger nesse caso.
  const [authStatus, setAuthStatus] = useState<AuthStatusOut | null>(null)
  const [semGate, setSemGate] = useState(false)
  // Auto-lock expirado (423) em pleno uso: sobrepõe a tela de desbloqueio
  // SEM desmontar o app — nada do que o usuário digitou se perde.
  const [bloqueioNoMeio, setBloqueioNoMeio] = useState(false)

  async function consultarStatusCofre() {
    try {
      const status = await hf.authStatus()
      setAuthStatus(status)
    } catch (e) {
      if (e instanceof HfErro && e.indisponivel) setSemGate(true)
    }
  }

  useEffect(() => {
    let ativo = true
    hf.authStatus()
      .then((status) => {
        if (ativo) setAuthStatus(status)
      })
      .catch((e) => {
        if (ativo && e instanceof HfErro && e.indisponivel) setSemGate(true)
      })
    return () => {
      ativo = false
    }
  }, [])

  const cadastrado = semGate || authStatus?.cadastrado === true
  const desbloqueado = semGate || authStatus?.desbloqueado === true
  const podeVerNegocio = cadastrado && desbloqueado

  // Só conta como "auto-lock em pleno uso" (overlay) um 423 que chegou DEPOIS
  // do cofre já estar utilizável — telas de negócio ficam mantidas montadas
  // mesmo antes do gate resolver (Rules of Hooks: `useAnalise` roda sempre),
  // então elas também podem levar 423 durante o onboarding/desbloqueio
  // inicial; esses são esperados e não devem acionar o overlay. Usa `ref`
  // (em vez de deps) para o listener sempre ler o valor mais recente sem
  // reinscrever a cada render.
  const podeVerNegocioRef = useRef(podeVerNegocio)
  useEffect(() => {
    podeVerNegocioRef.current = podeVerNegocio
  }, [podeVerNegocio])
  useEffect(
    () =>
      aoBloquear(() => {
        if (podeVerNegocioRef.current) setBloqueioNoMeio(true)
      }),
    [],
  )

  const [abaAtiva, setAbaAtiva] = useState(0)
  const [escuro, setEscuro] = useState<boolean | null>(escolhaSalva)

  // Reidratação + aplicação: com escolha salva, o data-theme força o tema;
  // sem escolha, o atributo sai e o CSS volta a seguir o SO.
  useEffect(() => {
    const raiz = document.documentElement
    if (escuro === null) {
      delete raiz.dataset.theme
    } else {
      raiz.dataset.theme = escuro ? 'dark' : 'light'
    }
  }, [escuro])

  const escuroEfetivo = escuro ?? temaDoSo()

  function alternarTema() {
    const novo = !escuroEfetivo
    localStorage.setItem(CHAVE_TEMA, novo ? '1' : '0')
    setEscuro(novo)
  }
  const [perfil, setPerfil] = useState<PerfilIn>(PERFIL_SEED)
  // Rubricas do orçamento (T-1104, REQ-F-017): vivem no App porque a aba
  // Perfil precisa delas (selos "detalhado") e as mutações também atualizam
  // o perfil (roll-up devolvido pelo sidecar).
  const [rubricas, setRubricas] = useState<RubricaOut[]>([])
  // Persistência (T-1102, REQ-F-018): o auto-save só liga DEPOIS da
  // hidratação — senão o seed sobrescreveria o banco antes da carga chegar.
  const [hidratado, setHidratado] = useState(false)

  useEffect(() => {
    // Sem cofre pronto ainda não há repositório de negócio a carregar (a
    // janela de onboarding do backend existe, mas a GUI força o assistente
    // antes de mostrar qualquer tela — REQ-SEC-005) — evita um 423 inútil.
    if (!podeVerNegocio) return
    let ativo = true
    hf.estadoCarregar()
      .then((estado) => {
        if (!ativo) return
        if (estado.perfil) setPerfil(estado.perfil)
        setRubricas(estado.rubricas ?? [])
      })
      .catch(() => {
        // sidecar sem banco/fora do Electron: segue o seed em memória
      })
      .finally(() => {
        if (ativo) setHidratado(true)
      })
    return () => {
      ativo = false
    }
  }, [podeVerNegocio])

  // Auto-save com debounce: qualquer edição (Perfil, Dívidas, contrato
  // confirmado) persiste o estado inteiro — sem botão "salvar".
  useEffect(() => {
    if (!hidratado) return
    const timer = setTimeout(() => {
      hf.estadoSalvar(perfil).catch(() => {
        // falha de gravação não pode derrubar a edição; a próxima tenta de novo
      })
    }, 600)
    return () => clearTimeout(timer)
  }, [perfil, hidratado])

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

  // Mutações de rubrica: o sidecar devolve a lista E o perfil já recalculado
  // no core (campo detalhado = soma) — hidratamos os dois de uma vez.
  const aoMutarRubricas = (r: RubricaMutOut) => {
    setRubricas(r.rubricas)
    setPerfil(r.perfil)
  }

  async function bloquearCofre() {
    try {
      await hf.authBloquear()
    } catch {
      // best-effort: o gate 423 do próximo /estado já cobre a segurança
    }
    setBloqueioNoMeio(true)
  }

  async function aoDesbloquear() {
    setBloqueioNoMeio(false)
    await consultarStatusCofre()
  }

  // Assistente de cadastro: força-se ANTES de qualquer tela de negócio
  // (REQ-SEC-005) — nem a Visão Geral é alcançável sem um cofre cadastrado.
  if (!semGate && authStatus === null) {
    return <div className="auth-tela" aria-busy="true" />
  }
  if (!cadastrado) {
    return <Onboarding aoConcluir={() => void consultarStatusCofre()} />
  }
  if (!desbloqueado) {
    return <Desbloqueio aoDesbloquear={() => void consultarStatusCofre()} />
  }

  function tela() {
    switch (abaAtiva) {
      case 0:
        return <VisaoGeral analise={analise} />
      case 1:
        return (
          <Perfil
            perfil={perfil}
            setPerfil={setPerfil}
            analise={analise}
            rubricas={rubricas}
            aoMutarRubricas={aoMutarRubricas}
          />
        )
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
      case 5:
        return <Carta perfil={perfil} />
      default:
        return <ConfiguracaoIa />
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
        {!semGate && (
          <button
            className="cofre-indicador"
            onClick={() => void bloquearCofre()}
            title="Bloquear o cofre agora"
            aria-label="Cofre aberto — clique para bloquear"
          >
            <IconeCadeadoAberto /> Cofre aberto
          </button>
        )}
        <button
          className="btn-tema"
          onClick={alternarTema}
          title={escuroEfetivo ? 'Mudar para o tema claro' : 'Mudar para o tema escuro'}
          aria-label={escuroEfetivo ? 'Mudar para o tema claro' : 'Mudar para o tema escuro'}
        >
          {escuroEfetivo ? <IconeSol /> : <IconeLua />}
        </button>
      </header>

      <main className="conteudo">{tela()}</main>

      {bloqueioNoMeio && (
        <Desbloqueio
          overlay
          aviso="O cofre bloqueou por inatividade (auto-lock). O que você digitou continua aqui — desbloqueie para continuar."
          aoDesbloquear={() => void aoDesbloquear()}
        />
      )}
    </div>
  )
}
