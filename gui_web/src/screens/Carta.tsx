import { useEffect, useMemo, useState } from 'react'

import CampoMoeda from '../components/CampoMoeda'
import CampoPercent from '../components/CampoPercent'
import { hf } from '../hf/client'
import type {
  CartaCamposIn,
  CartaPreviaOut,
  PerfilIn,
  TipoProposta,
} from '../hf/contract'

const TIPOS: { id: TipoProposta; nome: string; desc: string }[] = [
  {
    id: 'quitacao',
    nome: 'Quitação à vista com desconto',
    desc: 'Pague o saldo à vista com abatimento e encerre a dívida.',
  },
  {
    id: 'portabilidade',
    nome: 'Portabilidade / contraproposta',
    desc: 'Leve a dívida a outro banco com taxa menor; peça contraproposta.',
  },
  {
    id: 'reducao',
    nome: 'Redução de taxa / renegociação',
    desc: 'Repactue parcelas e juros conforme sua capacidade atual.',
  },
]

/**
 * Tela Carta ao credor (T-903, REQ-F-016): tipo de proposta selecionável,
 * campos contextuais e pré-visualização ao vivo. O texto vem inteiro do
 * sidecar (`/carta/previa` = mesma fonte do .docx) — o front só renderiza.
 */
export default function Carta({ perfil }: { perfil: PerfilIn }) {
  const dividas = perfil.dividas ?? []
  const [credor, setCredor] = useState('')
  const [tipo, setTipo] = useState<TipoProposta>('quitacao')
  const [contrato, setContrato] = useState('')
  const [valor, setValor] = useState(0)
  const [banco, setBanco] = useState('')
  const [taxaConc, setTaxaConc] = useState(0.018)
  const [nome, setNome] = useState('')
  const [cpf, setCpf] = useState('')
  const [previa, setPrevia] = useState<CartaPreviaOut | null>(null)
  const [erro, setErro] = useState('')
  const [msg, setMsg] = useState('')

  const divida = dividas.find((d) => d.credor === credor) ?? dividas[0]

  const payload = useMemo<CartaCamposIn | null>(
    () =>
      divida
        ? {
            divida,
            tipo,
            valor_proposto: tipo === 'quitacao' && valor > 0 ? valor : null,
            banco_concorrente: tipo === 'portabilidade' ? banco : '',
            taxa_concorrente_mensal:
              tipo === 'portabilidade' && taxaConc > 0 ? taxaConc : null,
            nome_usuario: nome,
            cpf,
            contrato,
          }
        : null,
    [divida, tipo, contrato, valor, banco, taxaConc, nome, cpf],
  )

  // Prévia ao vivo: recalcula no sidecar a cada mudança (debounce curto).
  useEffect(() => {
    if (!payload) return
    let vivo = true
    const timer = setTimeout(() => {
      hf.cartaPrevia(payload)
        .then((c) => {
          if (!vivo) return
          setPrevia(c)
          setErro('')
        })
        .catch((e: Error) => {
          if (vivo) setErro(e.message)
        })
    }, 200)
    return () => {
      vivo = false
      clearTimeout(timer)
    }
  }, [payload])

  async function exportar() {
    if (!payload) return
    const caminho = await hf.dialogoSalvar({
      sugestao: `proposta_${tipo}.docx`,
      filtroNome: 'Documento do Word',
      extensoes: ['docx'],
    })
    if (!caminho) return
    try {
      const r = await hf.exportarCarta(payload, caminho)
      setMsg(`✔ Carta salva em ${r.caminho}`)
    } catch (e) {
      setMsg(`Falha ao gerar a carta: ${e instanceof Error ? e.message : e}`)
    }
  }

  if (dividas.length === 0) {
    return (
      <>
        <h1 className="titulo">Carta ao credor</h1>
        <p className="sub">Gere a proposta de negociação para o credor escolhido.</p>
        <div className="aviso-erro">
          Cadastre ao menos uma dívida (aba Dívidas ou Contrato PDF) antes de
          gerar a carta.
        </div>
      </>
    )
  }

  return (
    <>
      <div className="head">
        <div>
          <h1 className="titulo">Carta ao credor</h1>
          <p className="sub">Gere a proposta de negociação para o credor escolhido.</p>
        </div>
      </div>

      <div className="cols carta-cols">
        <section className="card">
          <div className="card-titulo">Proposta de negociação</div>
          <p className="sub-secao">Os campos usados variam conforme o tipo</p>

          <label className="campo">
            <span className="campo-rotulo">Dívida (credor)</span>
            <select
              className="campo-select"
              value={divida?.credor ?? ''}
              onChange={(e) => setCredor(e.target.value)}
            >
              {dividas.map((d) => (
                <option key={d.credor} value={d.credor}>
                  {d.credor} — {d.tipo}
                </option>
              ))}
            </select>
          </label>

          <div className="propcards">
            {TIPOS.map((t) => (
              <button
                key={t.id}
                type="button"
                className={t.id === tipo ? 'propcard on' : 'propcard'}
                onClick={() => setTipo(t.id)}
              >
                <span className="propcard-nome">{t.nome}</span>
                <span className="propcard-desc">{t.desc}</span>
              </button>
            ))}
          </div>

          <CampoTexto
            rotulo="Nº do contrato (opcional)"
            valor={contrato}
            onValor={setContrato}
            placeholder="000123-4"
          />

          {tipo === 'quitacao' && (
            <CampoMoeda
              rotulo="Valor proposto à vista"
              valor={valor}
              onValor={setValor}
            />
          )}
          {tipo === 'portabilidade' && (
            <>
              <CampoTexto
                rotulo="Banco concorrente"
                valor={banco}
                onValor={setBanco}
                placeholder="Ex.: Caixa"
              />
              <CampoPercent
                rotulo="Taxa do concorrente"
                valor={taxaConc}
                onValor={setTaxaConc}
              />
            </>
          )}
          {tipo === 'reducao' && (
            <p className="hintbox">
              Este tipo usa apenas os seus dados e o contrato — sem valor à
              vista ou banco concorrente. A carta pede a repactuação das
              parcelas e dos juros.
            </p>
          )}

          <CampoTexto rotulo="Seu nome (assinatura)" valor={nome} onValor={setNome} />
          <CampoTexto rotulo="CPF (opcional)" valor={cpf} onValor={setCpf} />

          <div className="extr-acoes">
            <button className="btn-add" onClick={() => void exportar()}>
              ✉ Gerar carta (.docx)
            </button>
          </div>
          {msg && <p className="export-nota">{msg}</p>}
          {erro && <div className="aviso-erro">Sem conexão com o núcleo: {erro}</div>}
        </section>

        <section className="card letter">
          {previa ? (
            <>
              <div className="letter-topo">
                <div>
                  <div className="letter-kicker">Pré-visualização · atualiza ao vivo</div>
                  <div className="letter-titulo">{previa.titulo}</div>
                </div>
                <div className="letter-data">{previa.data}</div>
              </div>
              <p>
                <strong>À {previa.destinatario}</strong>
                <br />
                Setor de Renegociação / Atendimento ao Cliente
              </p>
              <p className="letter-ref">{previa.referencia}</p>
              <p>Prezados,</p>
              {previa.paragrafos.map((p) => (
                <p key={p}>{p}</p>
              ))}
              <p>Atenciosamente,</p>
              <div className="letter-ass">
                <strong>{previa.assinatura || '________________________________'}</strong>
                {previa.cpf && <div>CPF: {previa.cpf}</div>}
              </div>
              <p className="letter-nota">
                Este é exatamente o texto que sai no .docx.
              </p>
            </>
          ) : (
            <p className="sub">Montando a pré-visualização…</p>
          )}
        </section>
      </div>
    </>
  )
}

function CampoTexto({
  rotulo,
  valor,
  onValor,
  placeholder,
}: {
  rotulo: string
  valor: string
  onValor: (v: string) => void
  placeholder?: string
}) {
  return (
    <label className="campo">
      <span className="campo-rotulo">{rotulo}</span>
      <span className="campo-input">
        <input
          className="campo-num campo-texto"
          value={valor}
          placeholder={placeholder}
          onChange={(e) => onValor(e.target.value)}
        />
      </span>
    </label>
  )
}
