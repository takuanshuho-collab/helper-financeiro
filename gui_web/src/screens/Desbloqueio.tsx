import { type FormEvent, useState } from 'react'

import { IconeCadeadoFechado } from '../components/Icones'
import { HfErro, hf } from '../hf/client'
import { useContadorEspera } from '../hf/useContadorEspera'

interface Props {
  /** `true`: sobrepõe o app já montado (auto-lock em pleno uso) sem
   * desmontar as telas de negócio — nenhum dado digitado se perde
   * silenciosamente. `false` (padrão): tela cheia, usada no boot. */
  overlay?: boolean
  /** Mensagem de contexto (ex.: aviso de auto-lock por inatividade). */
  aviso?: string
  aoDesbloquear: () => void
}

/**
 * Tela de desbloqueio do cofre (T-1604, ADR-0016 §D / REQ-SEC-005).
 *
 * Senha + TOTP; 401 não distingue qual fator falhou (a mensagem é genérica de
 * propósito). 429 (anti-brute-force) desabilita o submit com um contador
 * regressivo usando `aguarde_s` do corpo. Inclui o fluxo "esqueci a senha"
 * via código de recuperação de uso único (`POST /auth/recuperar`).
 */
export default function Desbloqueio({ overlay = false, aviso, aoDesbloquear }: Props) {
  const [modoRecuperar, setModoRecuperar] = useState(false)

  // Login (senha + TOTP)
  const [senha, setSenha] = useState('')
  const [codigo, setCodigo] = useState('')
  const [erro, setErro] = useState('')
  const [carregando, setCarregando] = useState(false)
  const [esperaS, definirEspera] = useContadorEspera()

  // Recuperação (código de uso único + nova senha)
  const [codigoRec, setCodigoRec] = useState('')
  const [novaSenha, setNovaSenha] = useState('')
  const [confirmarNovaSenha, setConfirmarNovaSenha] = useState('')
  const [erroRec, setErroRec] = useState('')
  const [carregandoRec, setCarregandoRec] = useState(false)

  async function entrar(e: FormEvent) {
    e.preventDefault()
    setErro('')
    setCarregando(true)
    try {
      await hf.authLogin(senha, codigo)
      setSenha('')
      setCodigo('')
      aoDesbloquear()
    } catch (e) {
      if (e instanceof HfErro && e.status === 429) {
        definirEspera(e.aguardeS ?? 0)
        setErro(e.message)
      } else if (e instanceof HfErro && e.status === 401) {
        // Nunca detalha qual dos 2 fatores falhou (senha ou TOTP).
        setErro('Senha ou código do autenticador incorretos.')
      } else {
        setErro(e instanceof HfErro ? e.message : 'Não foi possível desbloquear o cofre.')
      }
    } finally {
      setCarregando(false)
    }
  }

  async function recuperar(e: FormEvent) {
    e.preventDefault()
    setErroRec('')
    if (novaSenha !== confirmarNovaSenha) {
      setErroRec('As senhas não coincidem.')
      return
    }
    setCarregandoRec(true)
    try {
      await hf.authRecuperar(codigoRec, novaSenha)
      setCodigoRec('')
      setNovaSenha('')
      setConfirmarNovaSenha('')
      aoDesbloquear()
    } catch (e) {
      if (e instanceof HfErro && e.status === 429) {
        definirEspera(e.aguardeS ?? 0)
        setErroRec(e.message)
      } else {
        setErroRec(
          e instanceof HfErro ? e.message : 'Não foi possível redefinir a senha.',
        )
      }
    } finally {
      setCarregandoRec(false)
    }
  }

  const conteudo = (
    <div className="auth-card">
      <div className="auth-cadeado">
        <IconeCadeadoFechado />
      </div>
      {!modoRecuperar ? (
        <>
          <h1 className="titulo">Cofre bloqueado</h1>
          <p className="sub">Digite a senha mestra e o código do autenticador.</p>
          {aviso && <div className="aviso-erro">{aviso}</div>}
          <form onSubmit={entrar}>
            <label className="campo campo-empilhado">
              <span className="campo-rotulo">Senha mestra</span>
              <span className="campo-input">
                <input
                  type="password"
                  className="campo-num campo-texto"
                  value={senha}
                  onChange={(e) => setSenha(e.target.value)}
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
                  value={codigo}
                  onChange={(e) => setCodigo(e.target.value)}
                  autoComplete="one-time-code"
                />
              </span>
            </label>
            {erro && <div className="aviso-erro">{erro}</div>}
            <button type="submit" className="btn-add" disabled={carregando || esperaS > 0}>
              {esperaS > 0 ? `Aguarde ${esperaS}s…` : carregando ? 'Entrando…' : 'Entrar'}
            </button>
            <button
              type="button"
              className="auth-link"
              onClick={() => {
                setModoRecuperar(true)
                setErro('')
              }}
            >
              Esqueci a senha
            </button>
          </form>
        </>
      ) : (
        <>
          <h1 className="titulo">Esqueci a senha</h1>
          <p className="sub">
            Use um dos 10 códigos de recuperação (emitidos só no cadastro) para
            redefinir a senha. O código usado será invalidado.
          </p>
          <form onSubmit={recuperar}>
            <label className="campo campo-empilhado">
              <span className="campo-rotulo">Código de recuperação</span>
              <span className="campo-input">
                <input
                  className="campo-num campo-texto"
                  value={codigoRec}
                  onChange={(e) => setCodigoRec(e.target.value)}
                  autoFocus
                />
              </span>
            </label>
            <label className="campo campo-empilhado">
              <span className="campo-rotulo">Nova senha</span>
              <span className="campo-input">
                <input
                  type="password"
                  className="campo-num campo-texto"
                  value={novaSenha}
                  onChange={(e) => setNovaSenha(e.target.value)}
                  autoComplete="new-password"
                />
              </span>
            </label>
            <label className="campo campo-empilhado">
              <span className="campo-rotulo">Confirmar nova senha</span>
              <span className="campo-input">
                <input
                  type="password"
                  className="campo-num campo-texto"
                  value={confirmarNovaSenha}
                  onChange={(e) => setConfirmarNovaSenha(e.target.value)}
                  autoComplete="new-password"
                />
              </span>
            </label>
            {erroRec && <div className="aviso-erro">{erroRec}</div>}
            <button
              type="submit"
              className="btn-add"
              disabled={carregandoRec || esperaS > 0}
            >
              {esperaS > 0
                ? `Aguarde ${esperaS}s…`
                : carregandoRec
                  ? 'Redefinindo…'
                  : 'Redefinir senha e entrar'}
            </button>
            <button
              type="button"
              className="auth-link"
              onClick={() => {
                setModoRecuperar(false)
                setErroRec('')
              }}
            >
              Voltar ao login
            </button>
          </form>
        </>
      )}
    </div>
  )

  return overlay ? (
    <div className="auth-overlay">{conteudo}</div>
  ) : (
    <div className="auth-tela">{conteudo}</div>
  )
}
