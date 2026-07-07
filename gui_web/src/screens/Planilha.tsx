import { useState, type FocusEvent, type KeyboardEvent } from 'react'

import { hf } from '../hf/client'
import type {
  Categoria,
  PerfilIn,
  RubricaMutOut,
  RubricaOut,
} from '../hf/contract'
import { brl, numBR, parseBR } from '../lib/format'
import {
  SECOES_ORCAMENTO,
  rubricasDoCampo,
  type CampoOrcamento,
} from '../lib/orcamento'

/**
 * Planilha de orçamento (T-1104, REQ-F-017): grade editável de rubricas.
 *
 * Cada campo do Perfil vira um grupo expansível; as linhas são as rubricas do
 * usuário (nome + valor). TODO subtotal exibido vem do sidecar: as mutações
 * devolvem o perfil já com o roll-up do core (campo detalhado = soma) — nada
 * é somado aqui (REQ-NF-005).
 */
export default function Planilha({
  perfil,
  rubricas,
  aoMutar,
  aoVoltar,
}: {
  perfil: PerfilIn
  rubricas: RubricaOut[]
  aoMutar: (r: RubricaMutOut) => void
  aoVoltar: () => void
}) {
  const [erro, setErro] = useState('')

  const mutar = (p: Promise<RubricaMutOut>) =>
    p.then((r) => {
      setErro('')
      aoMutar(r)
    }).catch((e: Error) => setErro(e.message))

  return (
    <>
      <div className="titulo-linha">
        <div>
          <h1 className="titulo">Planilha de orçamento</h1>
          <p className="sub">
            Crie rubricas para individualizar cada gasto — o campo do Perfil
            passa a valer a soma delas.
          </p>
        </div>
        <button className="btn-add" onClick={aoVoltar}>
          ← Voltar ao Perfil
        </button>
      </div>

      {erro && <div className="plan-erro">{erro}</div>}

      <div className="plan-grid">
        {SECOES_ORCAMENTO.map((secao) => (
          <section className="secao" key={secao.categoria}>
            <div className="secao-topo">
              <span className="secao-titulo">
                <span className="secao-ponto" style={{ background: secao.cor }} />
                {secao.titulo}
              </span>
            </div>
            {secao.campos.map((campo) => (
              <Grupo
                key={campo.campo}
                categoria={secao.categoria}
                campo={campo}
                valorCampo={valorDoPerfil(perfil, secao.categoria, campo.campo)}
                rubricas={rubricasDoCampo(rubricas, secao.categoria, campo.campo)}
                mutar={mutar}
              />
            ))}
          </section>
        ))}
      </div>
    </>
  )
}

/** Valor atual do campo no perfil — direto ou já somado pelo core. */
function valorDoPerfil(
  perfil: PerfilIn,
  categoria: Categoria,
  campo: string,
): number {
  const secao = perfil[categoria] as Record<string, number> | undefined
  return secao?.[campo] ?? 0
}

function Grupo({
  categoria,
  campo,
  valorCampo,
  rubricas,
  mutar,
}: {
  categoria: Categoria
  campo: CampoOrcamento
  valorCampo: number
  rubricas: RubricaOut[]
  mutar: (p: Promise<RubricaMutOut>) => void
}) {
  // Grupos já detalhados nascem abertos; os demais, fechados (menos poluição).
  const [aberto, setAberto] = useState(rubricas.length > 0)
  const detalhado = rubricas.length > 0

  const criar = () =>
    mutar(
      hf.rubricaCriar({
        categoria,
        campo_pai: campo.campo,
        nome: 'Nova rubrica',
        valor: 0,
        ordem: rubricas.length,
      }),
    )

  return (
    <div className="plan-grupo">
      <button
        className="plan-grupo-topo"
        onClick={() => setAberto((a) => !a)}
        aria-expanded={aberto}
      >
        <span className={aberto ? 'plan-seta aberta' : 'plan-seta'}>▸</span>
        <span className="plan-grupo-nome">{campo.rotulo}</span>
        {detalhado && (
          <span className="plan-chip">{rubricas.length} rubrica(s)</span>
        )}
        <span className="plan-grupo-total">{brl(valorCampo)}</span>
      </button>

      {aberto && (
        <div className="plan-linhas">
          {rubricas.map((r) => (
            <Linha key={r.id} rubrica={r} mutar={mutar} />
          ))}
          {!detalhado && (
            <div className="plan-dica">
              Sem rubricas: o valor é o digitado direto na aba Perfil.
            </div>
          )}
          <button className="plan-add" onClick={criar}>
            + Rubrica em “{campo.rotulo}”
          </button>
        </div>
      )}
    </div>
  )
}

/**
 * Linha editável (nome + valor). Edição em rascunho local, gravada no blur ou
 * Enter — uma requisição por edição concluída, não por tecla.
 */
function Linha({
  rubrica,
  mutar,
}: {
  rubrica: RubricaOut
  mutar: (p: Promise<RubricaMutOut>) => void
}) {
  // Rascunho por foco: fora de edição a linha exibe o SERVIDOR (valor já
  // formatado e somado no core); ao focar, tira-se um snapshot editável. A
  // gravação acontece quando o foco SAI da linha (relatedTarget fora dela) —
  // o Tab entre nome↔valor não dispara requisição nem perde a digitação.
  const [rascunho, setRascunho] = useState<{
    nome: string
    valor: string
  } | null>(null)

  const doServidor = () => ({
    nome: rubrica.nome,
    valor: rubrica.valor ? numBR(rubrica.valor) : '',
  })
  const nome = rascunho ? rascunho.nome : rubrica.nome
  const valor = rascunho ? rascunho.valor : doServidor().valor

  const aoFocar = () => setRascunho((r) => r ?? doServidor())

  const aoSairDaLinha = (ev: FocusEvent<HTMLDivElement>) => {
    if (ev.currentTarget.contains(ev.relatedTarget as Node | null)) return
    const nomeFinal = nome.trim() || rubrica.nome
    const valorFinal = parseBR(valor)
    setRascunho(null)
    if (nomeFinal !== rubrica.nome || valorFinal !== rubrica.valor) {
      mutar(hf.rubricaEditar(rubrica.id, nomeFinal, valorFinal))
    }
  }

  const aoEnter = (ev: KeyboardEvent<HTMLInputElement>) => {
    if (ev.key === 'Enter') ev.currentTarget.blur()
  }

  return (
    <div className="plan-linha" onFocus={aoFocar} onBlur={aoSairDaLinha}>
      <input
        className="plan-nome"
        value={nome}
        onChange={(ev) =>
          setRascunho((r) => ({ ...(r ?? doServidor()), nome: ev.target.value }))
        }
        onKeyDown={aoEnter}
        aria-label="Nome da rubrica"
      />
      <span className="plan-valor">
        <span className="campo-prefixo">R$</span>
        <input
          className="campo-num"
          inputMode="decimal"
          placeholder="0,00"
          value={valor}
          onChange={(ev) =>
            setRascunho((r) => ({
              ...(r ?? doServidor()),
              valor: ev.target.value,
            }))
          }
          onKeyDown={aoEnter}
          aria-label="Valor da rubrica"
        />
      </span>
      <button
        className="btn-remover"
        title="Remover rubrica"
        onClick={() => mutar(hf.rubricaRemover(rubrica.id))}
      >
        ×
      </button>
    </div>
  )
}
