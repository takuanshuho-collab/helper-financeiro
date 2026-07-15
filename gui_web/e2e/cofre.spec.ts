/**
 * E2E do cofre local (T-1604, ADR-0016 §D / REQ-SEC-005..007): Electron +
 * sidecar Python REAIS, banco e `auth.json` isolados por cenário.
 *
 * Cada teste sobe uma instância própria do app (sem reuso de janela) porque
 * o estado do cofre (cadastrado/bloqueado) é o próprio objeto sob teste —
 * diferente de `app.spec.ts`, que reusa uma janela já autenticada para
 * percorrer as telas de negócio.
 */
import * as os from 'node:os'
import * as path from 'node:path'

import { _electron as electron, expect, test, type ElectronApplication } from '@playwright/test'

import { cadastrarCofreELogin, preencherAuth } from './cofre-helpers'

const RAIZ_GUI = path.resolve(__dirname, '..')

function ambienteIsolado() {
  const sufixo = `${Date.now()}-${Math.random().toString(36).slice(2)}`
  return {
    HF_MODO_DEGRADADO: '1',
    HF_DB_PATH: path.join(os.tmpdir(), `hf-e2e-cofre-db-${sufixo}.db`),
    HF_AUTH_PATH: path.join(os.tmpdir(), `hf-e2e-cofre-auth-${sufixo}.json`),
    HF_AUTO_LOCK_MIN: '1440',
  }
}

async function abrirAppIsolado(): Promise<ElectronApplication> {
  return electron.launch({
    args: ['.'],
    cwd: RAIZ_GUI,
    env: { ...process.env, ...ambienteIsolado() },
  })
}

test('cadastro completo + login com TOTP válido libera as telas de negócio', async () => {
  const app = await abrirAppIsolado()
  const win = await app.firstWindow()
  try {
    await cadastrarCofreELogin(win, 'senha-cadastro-valida-123')
    // O onboarding terminou: a Visão Geral (tela de negócio) aparece.
    await win.waitForSelector('.hero', { timeout: 30_000 })
    await expect(win.locator('.pill')).toBeVisible()
    // O indicador de cofre aberto entra na navegação.
    await expect(win.locator('.cofre-indicador')).toContainText('Cofre aberto')
  } finally {
    await app.close().catch(() => {})
  }
})

test('login com código TOTP errado: 401 genérico, sem detalhar o fator', async () => {
  const app = await abrirAppIsolado()
  const win = await app.firstWindow()
  try {
    const senha = 'senha-com-totp-errado-123'
    await expect(win.locator('.auth-card .titulo')).toHaveText('Crie a senha mestra do seu cofre', {
      timeout: 30_000,
    })
    await preencherAuth(win, 'Senha mestra', senha)
    await preencherAuth(win, 'Confirmar senha', senha)
    await win.locator('.btn-add', { hasText: 'Criar cofre' }).click()

    await win.waitForSelector('.auth-segredo code', { timeout: 10_000 })
    await win.locator('.btn-add', { hasText: 'Já configurei' }).click()

    await win.waitForSelector('.auth-codigos', { timeout: 10_000 })
    await win.locator('.auth-confirmacao input[type="checkbox"]').check()
    await win.locator('.btn-add', { hasText: 'Continuar' }).click()

    await expect(win.locator('.auth-card .titulo')).toHaveText('Faça seu primeiro login', {
      timeout: 10_000,
    })
    await preencherAuth(win, 'Senha mestra', senha)
    // Código deliberadamente errado (não corresponde ao segredo emitido).
    await preencherAuth(win, 'Código do autenticador', '000000')
    await win.locator('.btn-add', { hasText: 'Entrar e concluir' }).click()

    const aviso = win.locator('.auth-card form .aviso-erro')
    await expect(aviso).toContainText('Senha ou código do autenticador incorretos', {
      timeout: 10_000,
    })
    // A mensagem NÃO diz qual dos 2 fatores falhou (REQ-SEC-005).
    await expect(aviso).not.toContainText('TOTP')
    await expect(aviso).not.toContainText('Senha mestra incorreta')
    // Continua bloqueado — nenhuma tela de negócio apareceu.
    await expect(win.locator('.hero')).toHaveCount(0)
  } finally {
    await app.close().catch(() => {})
  }
})

test('recuperação por código de uso único redefine a senha e invalida o código', async () => {
  const app = await abrirAppIsolado()
  const win = await app.firstWindow()
  try {
    const { codigosRecuperacao } = await cadastrarCofreELogin(win, 'senha-original-123')
    await win.waitForSelector('.hero', { timeout: 30_000 })

    // Bloqueio manual (indicador na navegação) para chegar à tela de login.
    await win.locator('.cofre-indicador').click()
    await expect(win.locator('.auth-card .titulo')).toHaveText('Cofre bloqueado', { timeout: 10_000 })

    await win.locator('.auth-link', { hasText: 'Esqueci a senha' }).click()
    const novaSenha = 'senha-recuperada-nova-456'
    await preencherAuth(win, 'Código de recuperação', codigosRecuperacao[0])
    await preencherAuth(win, 'Nova senha', novaSenha)
    await preencherAuth(win, 'Confirmar nova senha', novaSenha)
    await win.locator('.btn-add', { hasText: 'Redefinir senha' }).click()

    // A recuperação já desbloqueia a sessão (mesmo racional do login).
    await win.waitForSelector('.hero', { timeout: 15_000 })

    // Bloqueia de novo e tenta REUSAR o mesmo código: uso único (REQ-SEC-007).
    await win.locator('.cofre-indicador').click()
    await expect(win.locator('.auth-card .titulo')).toHaveText('Cofre bloqueado', { timeout: 10_000 })
    await win.locator('.auth-link', { hasText: 'Esqueci a senha' }).click()
    await preencherAuth(win, 'Código de recuperação', codigosRecuperacao[0])
    await preencherAuth(win, 'Nova senha', 'outra-tentativa-789')
    await preencherAuth(win, 'Confirmar nova senha', 'outra-tentativa-789')
    await win.locator('.btn-add', { hasText: 'Redefinir senha' }).click()
    await expect(win.locator('.auth-card form .aviso-erro')).toBeVisible({ timeout: 10_000 })
    // Diagnóstico do flake (v2.11, ata de fechamento): `App.tsx` tem DOIS
    // caminhos que renderizam "bloqueado" — o gate de topo, dirigido por
    // `authStatus.desbloqueado` (`.auth-tela`, tela cheia), e o overlay
    // dirigido por `bloqueioNoMeio` (`.auth-overlay`, sobre o app já montado).
    // O 1º desbloqueio bem-sucedido desta função (`aoDesbloquear`) faz
    // `setBloqueioNoMeio(false)` de forma síncrona e só DEPOIS aguarda
    // `consultarStatusCofre()` (assíncrono) — então o `.hero` pode aparecer
    // ANTES desse `authStatus` assentar. Se essa chamada demorar o bastante
    // para resolver só depois do 2º bloqueio (linha acima), o gate de topo
    // passa a ganhar do overlay no próximo render, trocando `.auth-overlay`
    // por `.auth-tela` — mesmo conteúdo (`.auth-card`), wrapper diferente.
    // Por isso a asserção certa (T-1907) é a condição real que a UI garante
    // nos dois caminhos — o cartão de recuperação segue na tela com o erro —
    // e não o wrapper específico, que depende dessa corrida entre os dois
    // gates e não é o que REQ-SEC-007 promete.
    await expect(win.locator('.auth-card .titulo')).toHaveText('Esqueci a senha')
  } finally {
    await app.close().catch(() => {})
  }
})
