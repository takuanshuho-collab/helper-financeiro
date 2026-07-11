/**
 * Helpers de E2E do cofre (T-1604, ADR-0016 §D / REQ-SEC-005..007).
 *
 * Com a GUI forçando o onboarding, TODO cenário que chega às telas de
 * negócio precisa antes cadastrar um cofre e fazer o primeiro login — este
 * módulo faz isso pela UI de verdade (sem atalho de backend: não existe
 * "porta dos fundos" para pular o cofre, por decisão do mantenedor).
 *
 * O código TOTP é gerado aqui em Node (`node:crypto`, HMAC-SHA1, RFC 6238) a
 * partir do segredo mostrado na tela "alternativa ao QR" — sem depender de
 * nenhuma lib de terceiros nem duplicar o pacote Python `pyotp`.
 */
import { createHmac } from 'node:crypto'

import { expect, type Page } from '@playwright/test'

const ALFABETO_BASE32 = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567'

function base32Decodificar(base32: string): Buffer {
  const limpo = base32.replace(/=+$/, '').toUpperCase()
  let bits = ''
  for (const caractere of limpo) {
    const valor = ALFABETO_BASE32.indexOf(caractere)
    if (valor === -1) continue
    bits += valor.toString(2).padStart(5, '0')
  }
  const bytes: number[] = []
  for (let i = 0; i + 8 <= bits.length; i += 8) {
    bytes.push(parseInt(bits.slice(i, i + 8), 2))
  }
  return Buffer.from(bytes)
}

/** TOTP padrão (RFC 6238): SHA-1, passo de 30 s, 6 dígitos — o mesmo formato
 * que `pyotp.TOTP` usa no sidecar (`sidecar/auth.py`). */
export function gerarTotp(segredoBase32: string, epocaMs: number = Date.now()): string {
  const chave = base32Decodificar(segredoBase32)
  const passo = Math.floor(epocaMs / 1000 / 30)
  const contador = Buffer.alloc(8)
  contador.writeBigUInt64BE(BigInt(passo))
  const hmac = createHmac('sha1', chave).update(contador).digest()
  const offset = hmac[hmac.length - 1] & 0x0f
  const codigo =
    ((hmac[offset] & 0x7f) << 24) |
    ((hmac[offset + 1] & 0xff) << 16) |
    ((hmac[offset + 2] & 0xff) << 8) |
    (hmac[offset + 3] & 0xff)
  return String(codigo % 1_000_000).padStart(6, '0')
}

// Anti-replay do TOTP (`sidecar/auth.py`, `_verificar_totp`): o mesmo passo
// de 30s não pode logar 2 vezes no mesmo cofre. Relançamentos rápidos do app
// (fechar+abrir em segundos, como no teste de tema/persistência) caem no
// mesmo passo do login anterior — este helper espera o PRÓXIMO passo em vez
// de gerar um código que o servidor recusaria como replay.
let ultimoPassoUsado = -1

async function totpSemReplay(win: Page, segredoBase32: string): Promise<string> {
  let agora = Date.now()
  let passo = Math.floor(agora / 1000 / 30)
  if (passo <= ultimoPassoUsado) {
    const esperaMs = (ultimoPassoUsado + 1) * 30_000 - agora + 100
    await win.waitForTimeout(Math.max(0, esperaMs))
    agora = Date.now()
    passo = Math.floor(agora / 1000 / 30)
  }
  ultimoPassoUsado = passo
  return gerarTotp(segredoBase32, agora)
}

/** Input de um `label.campo` pelo rótulo EXATO (mesma técnica do `campo()` do
 * `app.spec.ts`, mas com âncoras — "Nova senha" não pode casar com
 * "Confirmar nova senha"). */
export function campoAuth(win: Page, rotulo: string) {
  const exato = new RegExp(`^${rotulo.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}$`)
  return win.locator('label.campo', { hasText: exato }).locator('input')
}

export async function preencherAuth(win: Page, rotulo: string, valor: string) {
  const input = campoAuth(win, rotulo)
  await input.click()
  await input.fill(valor)
}

/**
 * Cadastra um cofre novo (senha fixa de teste) e conclui os 4 passos do
 * assistente, terminando com o primeiro login real — a GUI só libera as
 * telas de negócio depois disso (REQ-SEC-005). Devolve o segredo TOTP (para
 * o chamador poder desbloquear em relançamentos futuros do mesmo app) e os
 * 10 códigos de recuperação (para os cenários de "esqueci a senha").
 */
export async function cadastrarCofreELogin(
  win: Page,
  senha: string,
): Promise<{ segredoTotp: string; codigosRecuperacao: string[] }> {
  await expect(win.locator('.auth-card .titulo')).toHaveText('Crie a senha mestra do seu cofre', {
    timeout: 30_000,
  })
  await preencherAuth(win, 'Senha mestra', senha)
  await preencherAuth(win, 'Confirmar senha', senha)
  await win.locator('.btn-add', { hasText: 'Criar cofre' }).click()

  await win.waitForSelector('.auth-segredo code', { timeout: 10_000 })
  const segredoTotp = ((await win.locator('.auth-segredo code').textContent()) ?? '').trim()
  await win.locator('.btn-add', { hasText: 'Já configurei' }).click()

  await win.waitForSelector('.auth-codigos', { timeout: 10_000 })
  const codigosRecuperacao = await win.locator('.auth-codigo-item code').allTextContents()
  expect(codigosRecuperacao).toHaveLength(10)
  await win.locator('.auth-confirmacao input[type="checkbox"]').check()
  await win.locator('.btn-add', { hasText: 'Continuar' }).click()

  await expect(win.locator('.auth-card .titulo')).toHaveText('Faça seu primeiro login', { timeout: 10_000 })
  await preencherAuth(win, 'Senha mestra', senha)
  await preencherAuth(win, 'Código do autenticador', await totpSemReplay(win, segredoTotp))
  await win.locator('.btn-add', { hasText: 'Entrar e concluir' }).click()

  return { segredoTotp, codigosRecuperacao }
}

/** Desbloqueia um cofre JÁ cadastrado (relançamento do app) com senha + TOTP
 * válido gerado a partir do segredo capturado no cadastro. */
export async function desbloquearCofre(
  win: Page,
  senha: string,
  segredoTotp: string,
): Promise<void> {
  await expect(win.locator('.auth-card .titulo')).toHaveText('Cofre bloqueado', { timeout: 30_000 })
  await preencherAuth(win, 'Senha mestra', senha)
  await preencherAuth(win, 'Código do autenticador', await totpSemReplay(win, segredoTotp))
  await win.locator('.btn-add', { hasText: 'Entrar' }).click()
}
