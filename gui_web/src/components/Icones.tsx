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
