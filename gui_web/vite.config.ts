import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// base './' → caminhos relativos de asset, necessários ao carregar via file://
// dentro do Electron empacotado (loadFile de dist/index.html).
export default defineConfig({
  base: './',
  plugins: [react()],
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
})
