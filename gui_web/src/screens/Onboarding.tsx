import { type FormEvent, useState } from 'react'

import { HfErro, hf } from '../hf/client'
import type { AuthCadastroOut } from '../hf/contract'
import { useContadorEspera } from '../hf/useContadorEspera'

type Passo = 'senha' | 'qr' | 'codigos' | 'login'

/** Extrai o `secret` do provisioning URI do TOTP (RFC 6238) — alternativa em
 * texto ao QR code para quem prefere digitar no autenticador (REQ-SEC-005). */
function segredoDoUri(uri: string): string {
  try {
    return new URL(uri).searchParams.get('secret') ?? ''
  } catch {
    return ''
  }
}

/**
 * Assistente de cadastro do cofre (T-1604, ADR-0016 §D / REQ-SEC-005..007).
 *
 * Forçado pela `App` sempre que `GET /auth/status` devolve `cadastrado:
 * false` — nenhuma tela de negócio é alcançável antes de completar os 4
 * passos: (1) senha mestra, (2) QR/segredo do TOTP, (3) códigos de
 * recuperação (exibidos só aqui), (4) primeiro login real, que confirma que
 * o autenticador foi configurado de verdade (o backend mantém a sessão
 * bloqueada até esse login, por design).
 */
export default function Onboarding({ aoConcluir }: { aoConcluir: () => void }) {
  const [passo, setPasso] = useState<Passo>('senha')
  const [cadastro, setCadastro] = useState<AuthCadastroOut | null>(null)

  // Passo 1: senha
  const [senha, setSenha] = useState('')
  const [confirmar, setConfirmar] = useState('')
  const [erroSenha, setErroSenha] = useState('')
  const [carregandoSenha, setCarregandoSenha] = useState(false)

  // Passo 3: códigos de recuperação
  const [confirmeiCodigos, setConfirmeiCodigos] = useState(false)
  const [copiado, setCopiado] = useState('')

  // Passo 4: primeiro login real
  const [loginSenha, setLoginSenha] = useState('')
  const [loginCodigo, setLoginCodigo] = useState('')
  const [erroLogin, setErroLogin] = useState('')
  const [carregandoLogin, setCarregandoLogin] = useState(false)
  const [esperaS, definirEspera] = useContadorEspera()

  async function criarCofre(e: FormEvent) {
    e.preventDefault()
    setErroSenha('')
    if (senha !== confirmar) {
      setErroSenha('As senhas não coincidem.')
      return
    }
    setCarregandoSenha(true)
    try {
      const resultado = await hf.authCadastrar(senha)
      setCadastro(resultado)
      setPasso('qr')
    } catch (e) {
      setErroSenha(e instanceof HfErro ? e.message : 'Não foi possível criar o cofre.')
    } finally {
      setCarregandoSenha(false)
    }
  }

  async function copiarCodigo(codigo: string) {
    try {
      await navigator.clipboard.writeText(codigo)
      setCopiado(codigo)
      setTimeout(() => setCopiado(''), 1500)
    } catch {
      // sem permissão de clipboard: o usuário ainda pode selecionar o texto
    }
  }

  function baixarCodigos() {
    if (!cadastro) return
    const texto =
      'Helper Financeiro — códigos de recuperação do cofre\n' +
      'Guarde este arquivo em local seguro. Cada código só funciona UMA vez.\n' +
      'Perder a senha E estes códigos perde os dados para sempre — não há recuperação por suporte.\n\n' +
      cadastro.codigos_recuperacao.join('\n') +
      '\n'
    const blob = new Blob([texto], { type: 'text/plain;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'helper-financeiro-codigos-recuperacao.txt'
    a.click()
    URL.revokeObjectURL(url)
  }

  async function confirmarPrimeiroLogin(e: FormEvent) {
    e.preventDefault()
    setErroLogin('')
    setCarregandoLogin(true)
    try {
      await hf.authLogin(loginSenha, loginCodigo)
      aoConcluir()
    } catch (e) {
      if (e instanceof HfErro && e.status === 429) {
        definirEspera(e.aguardeS ?? 0)
        setErroLogin(e.message)
      } else if (e instanceof HfErro && e.status === 401) {
        setErroLogin('Senha ou código do autenticador incorretos.')
      } else {
        setErroLogin(e instanceof HfErro ? e.message : 'Não foi possível entrar.')
      }
    } finally {
      setCarregandoLogin(false)
    }
  }

  return (
    <div className="auth-tela">
      <div className="auth-card">
        {passo === 'senha' && (
          <>
            <div className="auth-passo">Passo 1 de 4 · Bem-vindo(a)</div>
            <h1 className="titulo">Crie a senha mestra do seu cofre</h1>
            <p className="sub">
              Ela cifra todos os seus dados financeiros em repouso. Escolha
              uma senha forte — mais adiante você também recebe códigos de
              recuperação.
            </p>
            <form onSubmit={criarCofre}>
              <label className="campo campo-empilhado">
                <span className="campo-rotulo">Senha mestra</span>
                <span className="campo-input">
                  <input
                    type="password"
                    className="campo-num campo-texto"
                    value={senha}
                    onChange={(e) => setSenha(e.target.value)}
                    autoFocus
                    autoComplete="new-password"
                  />
                </span>
              </label>
              <label className="campo campo-empilhado">
                <span className="campo-rotulo">Confirmar senha</span>
                <span className="campo-input">
                  <input
                    type="password"
                    className="campo-num campo-texto"
                    value={confirmar}
                    onChange={(e) => setConfirmar(e.target.value)}
                    autoComplete="new-password"
                  />
                </span>
              </label>
              {erroSenha && <div className="aviso-erro">{erroSenha}</div>}
              <button type="submit" className="btn-add" disabled={carregandoSenha}>
                {carregandoSenha ? 'Criando…' : 'Criar cofre'}
              </button>
            </form>
          </>
        )}

        {passo === 'qr' && cadastro && (
          <>
            <div className="auth-passo">Passo 2 de 4 · Autenticador (TOTP)</div>
            <h1 className="titulo">Configure o app autenticador</h1>
            <p className="sub">
              Escaneie o QR code com um app autenticador (Google
              Authenticator, Authy, Aegis, 1Password…) ou digite o segredo
              manualmente. Tudo offline — nada disto sai da sua máquina.
            </p>
            <img
              className="auth-qr"
              src={`data:image/png;base64,${cadastro.qr_png_base64}`}
              alt="QR code para configurar o autenticador TOTP"
            />
            <div className="auth-segredo">
              <span className="campo-rotulo">Segredo (alternativa ao QR)</span>
              <code>{segredoDoUri(cadastro.totp_uri)}</code>
            </div>
            <button className="btn-add" onClick={() => setPasso('codigos')}>
              Já configurei — continuar
            </button>
          </>
        )}

        {passo === 'codigos' && cadastro && (
          <>
            <div className="auth-passo">Passo 3 de 4 · Códigos de recuperação</div>
            <h1 className="titulo">Guarde seus 10 códigos de recuperação</h1>
            <div className="aviso-erro">
              Eles só aparecem AGORA. Não há backdoor: se você perder a senha
              E os 10 códigos, os dados do cofre são perdidos para sempre —
              nem a Anthropic nem o desenvolvedor conseguem recuperá-los.
            </div>
            <ul className="auth-codigos">
              {cadastro.codigos_recuperacao.map((codigo) => (
                <li key={codigo} className="auth-codigo-item">
                  <code>{codigo}</code>
                  <button type="button" onClick={() => copiarCodigo(codigo)}>
                    {copiado === codigo ? 'Copiado!' : 'Copiar'}
                  </button>
                </li>
              ))}
            </ul>
            <div className="auth-acoes-codigos">
              <button type="button" className="auth-link" onClick={baixarCodigos}>
                Baixar .txt
              </button>
            </div>
            <label className="auth-confirmacao">
              <input
                type="checkbox"
                checked={confirmeiCodigos}
                onChange={(e) => setConfirmeiCodigos(e.target.checked)}
              />
              Eu salvei os 10 códigos em um lugar seguro.
            </label>
            <button
              className="btn-add"
              disabled={!confirmeiCodigos}
              onClick={() => setPasso('login')}
            >
              Continuar
            </button>
          </>
        )}

        {passo === 'login' && (
          <>
            <div className="auth-passo">Passo 4 de 4 · Confirmar acesso</div>
            <h1 className="titulo">Faça seu primeiro login</h1>
            <p className="sub">
              Confirme a senha e o código do autenticador para provar que ele
              foi configurado corretamente. Sem isso, o cofre permanece
              bloqueado.
            </p>
            <form onSubmit={confirmarPrimeiroLogin}>
              <label className="campo campo-empilhado">
                <span className="campo-rotulo">Senha mestra</span>
                <span className="campo-input">
                  <input
                    type="password"
                    className="campo-num campo-texto"
                    value={loginSenha}
                    onChange={(e) => setLoginSenha(e.target.value)}
                    autoFocus
                    autoComplete="current-password"
                  />
                </span>
              </label>
              <label className="campo campo-empilhado">
                <span className="campo-rotulo">Código do autenticador</span>
                <span className="campo-input">
                  <input
                    inputMode="numeric"
                    className="campo-num campo-texto"
                    value={loginCodigo}
                    onChange={(e) => setLoginCodigo(e.target.value)}
                    autoComplete="one-time-code"
                  />
                </span>
              </label>
              {erroLogin && <div className="aviso-erro">{erroLogin}</div>}
              <button
                type="submit"
                className="btn-add"
                disabled={carregandoLogin || esperaS > 0}
              >
                {esperaS > 0
                  ? `Aguarde ${esperaS}s…`
                  : carregandoLogin
                    ? 'Entrando…'
                    : 'Entrar e concluir'}
              </button>
            </form>
          </>
        )}
      </div>
    </div>
  )
}
