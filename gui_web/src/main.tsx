import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'

// Plus Jakarta Sans self-hosted (Fontsource) — o Vite empacota o .woff2 no
// bundle: 100% offline, sem Google Fonts, compatível com a CSP `font-src 'self'`.
import '@fontsource-variable/plus-jakarta-sans'

import App from './App'
import './styles.css'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
