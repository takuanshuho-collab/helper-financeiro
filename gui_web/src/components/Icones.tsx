/** Ícones de linha (stroke, sem preenchimento), estilo Lucide/Feather. */
import type { ReactNode } from 'react'

function Svg({ children }: { children: ReactNode }) {
  return (
    <svg
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.9"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {children}
    </svg>
  )
}

export const IconeRenda = () => (
  <Svg>
    <path d="M3 17l6-6 4 4 7-7" />
    <path d="M14 8h6v6" />
  </Svg>
)

export const IconeDespesas = () => (
  <Svg>
    <path d="M6 2l1.5 3h9L18 2" />
    <path d="M4 5h16l-1.5 15H5.5L4 5z" />
    <path d="M9 10v5M15 10v5" />
  </Svg>
)

export const IconeParcelas = () => (
  <Svg>
    <rect x="3" y="4" width="18" height="17" rx="2" />
    <path d="M3 9h18M8 2v4M16 2v4" />
  </Svg>
)

export const IconeSaldo = () => (
  <Svg>
    <rect x="2" y="5" width="20" height="14" rx="2" />
    <path d="M2 10h20" />
  </Svg>
)

export const IconeSol = () => (
  <Svg>
    <circle cx="12" cy="12" r="4" />
    <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
  </Svg>
)

export const IconeLua = () => (
  <Svg>
    <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" />
  </Svg>
)

/** Cofre aberto (T-1604): indicador na navegação + botão de bloqueio manual. */
export const IconeCadeadoAberto = () => (
  <Svg>
    <rect x="3" y="11" width="14" height="10" rx="2" />
    <path d="M7 11V7a5 5 0 0 1 9-3" />
  </Svg>
)

/** Cofre bloqueado (tela de desbloqueio / onboarding, REQ-SEC-005). */
export const IconeCadeadoFechado = () => (
  <Svg>
    <rect x="4" y="11" width="16" height="10" rx="2" />
    <path d="M8 11V7a4 4 0 0 1 8 0v4" />
    <circle cx="12" cy="16" r="1.5" />
  </Svg>
)
