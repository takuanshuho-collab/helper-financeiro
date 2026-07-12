/**
 * E2E da tela "Configuração da IA" (T-1702, ADR-0016 §F, REQ-F-028):
 * Electron + sidecar Python REAIS, mas o catálogo é substituído por um item
 * FAKE via `HF_CATALOGO_TESTE` apontando para um servidor HTTP LOCAL (Node,
 * loopback + porta efêmera) — nenhuma chamada bate no Hugging Face de
 * verdade (REQ-NF-007: nada de rede externa nos testes).
 *
 * Janela isolada (não reusa a de `app.spec.ts`): o estado do runtime/catálogo
 * é o próprio objeto sob teste, como em `cofre.spec.ts`.
 */
import { createHash } from 'node:crypto'
import * as fs from 'node:fs'
import * as http from 'node:http'
import * as os from 'node:os'
import * as path from 'node:path'

import { _electron as electron, expect, test, type ElectronApplication, type Page } from '@playwright/test'

import { cadastrarCofreELogin } from './cofre-helpers'

const RAIZ_GUI = path.resolve(__dirname, '..')

// Conteúdo determinístico do "modelo" fake — pequeno, só para exercitar o
// download de ponta a ponta (retomada/hash reais são cobertos no pytest).
const CONTEUDO = Buffer.concat([Buffer.from('GGUF'), Buffer.alloc(4096, 7)])
const SHA256 = createHash('sha256').update(CONTEUDO).digest('hex')

function subirServidorFake(): Promise<{ servidor: http.Server; url: string }> {
  return new Promise((resolve) => {
    const servidor = http.createServer((req, res) => {
      res.writeHead(200, { 'Content-Length': String(CONTEUDO.length) })
      res.end(CONTEUDO)
    })
    servidor.listen(0, '127.0.0.1', () => {
      const porta = (servidor.address() as { port: number }).port
      resolve({ servidor, url: `http://127.0.0.1:${porta}/fake-e2e.gguf` })
    })
  })
}

function aba(win: Page, nome: string) {
  return win.locator('.nav-item', { hasText: nome })
}

test('catálogo fake: baixa, ativa e reflete no status — sem tocar a rede real', async () => {
  const { servidor, url } = await subirServidorFake()
  const dirTmp = fs.mkdtempSync(path.join(os.tmpdir(), 'hf-e2e-cfgia-'))
  const catalogoJson = path.join(dirTmp, 'catalogo.json')
  fs.writeFileSync(
    catalogoJson,
    JSON.stringify([
      {
        id: 'fake-e2e',
        nome: 'Fake E2E',
        descricao: 'Modelo fake só para o teste E2E.',
        licenca: 'MIT',
        url,
        sha256: SHA256,
        tamanho_bytes: CONTEUDO.length,
        arquivo: 'fake-e2e.gguf',
      },
    ]),
  )

  const app: ElectronApplication = await electron.launch({
    args: ['.'],
    cwd: RAIZ_GUI,
    env: {
      ...process.env,
      HF_MODO_DEGRADADO: '1',
      HF_DB_PATH: path.join(dirTmp, 'dados.db'),
      HF_AUTH_PATH: path.join(dirTmp, 'auth.json'),
      HF_AUTO_LOCK_MIN: '1440',
      HF_CATALOGO_TESTE: catalogoJson,
      HF_MODELOS_DIR: path.join(dirTmp, 'modelos'),
      HF_LLM_CONFIG_PATH: path.join(dirTmp, 'llm.json'),
      // Força BINARIO_AUSENTE de forma determinística (T-1703): a partir desta
      // task, `scripts/preparar_llama.py` pode ter materializado o binário em
      // resources/llama/ NESTE checkout de dev — então não dá mais para inferir
      // "sem binário" pela ausência do arquivo. Um HF_LLAMA_SERVER apontando
      // para caminho inexistente faz `resolver_binario_llama` devolver None
      // (ver runtime_llm.py), reproduzindo o cenário "app sem binário" que este
      // teste (T-1702) exercita — independente de o binário estar no checkout.
      HF_LLAMA_SERVER: path.join(dirTmp, 'sem-binario-llama-server.exe'),
    },
  })
  const win = await app.firstWindow()
  try {
    await cadastrarCofreELogin(win, 'senha-configuracao-ia-123')
    await win.waitForSelector('.hero', { timeout: 30_000 })

    await aba(win, 'Configuração da IA').click()
    await expect(win.locator('.titulo')).toHaveText('Configuração da IA')

    // Sem binário empacotado no checkout de dev/E2E: motivo BINARIO_AUSENTE,
    // traduzido em instrução acionável (não o código cru).
    await expect(win.locator('.cfgia-status .aviso-erro')).toContainText(
      'reinstale o app',
      { timeout: 10_000 },
    )

    // O catálogo fake aparece com a licença e o botão de baixar.
    const item = win.locator('.cfgia-item', { hasText: 'Fake E2E' })
    await expect(item).toBeVisible()
    await expect(item.locator('.pill')).toHaveText('MIT')
    await item.locator('.btn-add', { hasText: 'Baixar' }).click()

    // Download completo (poll de catálogo) ⇒ vira "Usar este modelo".
    const usar = item.locator('.btn-secundario', { hasText: 'Usar este modelo' })
    await expect(usar).toBeVisible({ timeout: 20_000 })
    await usar.click()

    // Ativado: o item ganha o selo "· ativo" — o caminho persistido em
    // llm.json bateu com o arquivo baixado (REQ-F-028).
    await expect(item.locator('.cfgia-item-meta')).toContainText('ativo', {
      timeout: 10_000,
    })

    const llmJson = JSON.parse(
      fs.readFileSync(path.join(dirTmp, 'llm.json'), 'utf-8'),
    ) as { modelo_ativo: string }
    expect(llmJson.modelo_ativo.endsWith('fake-e2e.gguf')).toBe(true)
    expect(fs.existsSync(llmJson.modelo_ativo)).toBe(true)
  } finally {
    await app.close().catch(() => {})
    servidor.close()
  }
})
