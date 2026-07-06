import { useRef, useState } from 'react'

import { hf } from '../hf/client'
import type { ContratoExtraidoOut, DividaIn } from '../hf/contract'
import { parseBR, parsePct } from '../lib/format'

type Fase =
  | { tipo: 'ocioso' }
  | { tipo: 'processando'; nome: string }
  | {
      tipo: 'revisar'
      nome: string
      resultado: ContratoExtraidoOut
      valores: Record<string, string>
    }
  | { tipo: 'erro'; msg: string }

/** Lê o arquivo e devolve o conteúdo em base64 (em blocos, sem estourar a pilha). */
async function arquivoParaBase64(file: File): Promise<string> {
  const bytes = new Uint8Array(await file.arrayBuffer())
  let binario = ''
  const BLOCO = 0x8000
  for (let i = 0; i < bytes.length; i += BLOCO) {
    binario += String.fromCharCode(...bytes.subarray(i, i + BLOCO))
  }
  return btoa(binario)
}

function montarDivida(valores: Record<string, string>): DividaIn {
  return {
    credor: valores.credor?.trim() || 'Contrato importado',
    tipo: valores.tipo?.trim() || 'Outro',
    saldo_devedor: parseBR(valores.saldo ?? ''),
    taxa_mensal: parsePct(valores.taxa ?? ''),
    parcela: parseBR(valores.parcela ?? ''),
    parcelas_restantes: Math.max(
      0,
      Math.trunc(Number((valores.restantes ?? '').replace(/\D/g, '')) || 0),
    ),
  }
}

export default function Contrato({
  onNovaDivida,
}: {
  onNovaDivida: (divida: DividaIn) => void
}) {
  const [fase, setFase] = useState<Fase>({ tipo: 'ocioso' })
  const [arrastando, setArrastando] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  async function processar(file: File | null | undefined) {
    if (!file) return
    if (!file.name.toLowerCase().endsWith('.pdf')) {
      setFase({ tipo: 'erro', msg: 'Selecione um arquivo PDF.' })
      return
    }
    setFase({ tipo: 'processando', nome: file.name })
    try {
      const pdf = await arquivoParaBase64(file)
      const resultado = await hf.contratoExtrair(pdf, file.name)
      if (resultado.modo === 'vazio' || resultado.campos.length === 0) {
        setFase({
          tipo: 'erro',
          msg:
            resultado.aviso ||
            'Nenhum campo com fonte verificável foi encontrado. Preencha manualmente na aba Dívidas.',
        })
        return
      }
      const valores = Object.fromEntries(
        resultado.campos.map((c) => [c.chave, c.valor]),
      )
      setFase({ tipo: 'revisar', nome: file.name, resultado, valores })
    } catch (e) {
      setFase({
        tipo: 'erro',
        msg: e instanceof Error ? e.message : 'Falha ao ler o contrato.',
      })
    }
  }

  function confirmar(estado: Extract<Fase, { tipo: 'revisar' }>) {
    const { resultado, valores } = estado
    // Retoma o grafo pausado (interrupt→resume); o registro não pode travar o
    // fluxo do usuário, então uma falha aqui é silenciosa (P8).
    if (resultado.thread_id) {
      void hf.contratoConfirmar(resultado.thread_id, valores).catch(() => {})
    }
    onNovaDivida(montarDivida(valores))
    setFase({ tipo: 'ocioso' })
  }

  return (
    <>
      <h1 className="titulo">Contrato PDF</h1>
      <p className="sub">
        Selecione um contrato — a leitura e a extração acontecem{' '}
        <strong>localmente</strong>. O documento nunca sai da sua máquina; nada
        entra sem a sua confirmação.
      </p>

      {fase.tipo === 'ocioso' && (
        <div
          className={arrastando ? 'dropzone arrastando' : 'dropzone'}
          onClick={() => inputRef.current?.click()}
          onDragOver={(e) => {
            e.preventDefault()
            setArrastando(true)
          }}
          onDragLeave={() => setArrastando(false)}
          onDrop={(e) => {
            e.preventDefault()
            setArrastando(false)
            void processar(e.dataTransfer.files?.[0])
          }}
        >
          <div className="dz-icone">
            <svg
              width="40"
              height="40"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.7"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <path d="M14 3v5h5" />
              <path d="M7 3h7l5 5v11a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z" />
              <path d="M12 18v-6M9.5 14.5 12 12l2.5 2.5" />
            </svg>
          </div>
          <div className="dz-titulo">Arraste o contrato aqui ou clique para escolher</div>
          <div className="dz-hint">PDF com texto selecionável · extração local com citação da fonte</div>
          <input
            ref={inputRef}
            type="file"
            accept="application/pdf,.pdf"
            hidden
            onChange={(e) => {
              void processar(e.target.files?.[0])
              e.target.value = ''
            }}
          />
        </div>
      )}

      {fase.tipo === 'processando' && (
        <section className="card processando">
          <span className="spinner" aria-hidden="true" />
          <div>
            <div className="proc-titulo">Lendo “{fase.nome}” e consultando o modelo local…</div>
            <div className="proc-sub">
              A extração roda no seu computador e pode levar alguns minutos.
            </div>
          </div>
        </section>
      )}

      {fase.tipo === 'erro' && (
        <>
          <div className="aviso-erro">{fase.msg}</div>
          <div className="extr-acoes">
            <button className="btn-secundario" onClick={() => setFase({ tipo: 'ocioso' })}>
              Escolher outro PDF
            </button>
          </div>
        </>
      )}

      {fase.tipo === 'revisar' && (
        <Revisao
          estado={fase}
          onValor={(chave, v) =>
            setFase({ ...fase, valores: { ...fase.valores, [chave]: v } })
          }
          onConfirmar={() => confirmar(fase)}
          onCancelar={() => setFase({ tipo: 'ocioso' })}
        />
      )}
    </>
  )
}

function Revisao({
  estado,
  onValor,
  onConfirmar,
  onCancelar,
}: {
  estado: Extract<Fase, { tipo: 'revisar' }>
  onValor: (chave: string, v: string) => void
  onConfirmar: () => void
  onCancelar: () => void
}) {
  const { resultado, nome, valores } = estado
  const ehIA = resultado.modo === 'ia'

  return (
    <section className="card">
      <div className={ehIA ? 'extr-banner ia' : 'extr-banner classico'}>
        {ehIA ? (
          <>
            <strong>Extração assistida por IA local.</strong> Cada campo cita o
            trecho de onde saiu — confira e ajuste antes de adicionar.
          </>
        ) : (
          <>
            <strong>Modelo local indisponível — extração clássica.</strong> Sem
            citação de fonte; confira todos os valores com atenção.
            <div className="extr-diag">
              Alvo da LLM: <code>{resultado.llm.base_url}</code> · modelo{' '}
              <code>{resultado.llm.model}</code> ·{' '}
              {resultado.llm.endpoint_local ? 'local' : 'remoto'}
              {resultado.motivos.length > 0 && (
                <> · motivo: <code>{resultado.motivos.join(', ')}</code></>
              )}
            </div>
          </>
        )}
      </div>

      <div className="card-titulo">Campos de “{nome}”</div>

      {resultado.descartados.length > 0 && (
        <div className="extr-alerta">
          Descartados por falta de fonte verificável:{' '}
          {resultado.descartados.map((d) => d.split(':')[0]).join(', ')}.
        </div>
      )}
      {resultado.inconsistencias.length > 0 && (
        <div className="extr-alerta">
          A parcela não fecha com o recálculo (saldo, taxa e prazo) — confira os
          valores.
        </div>
      )}

      <div className="extr-campos">
        {resultado.campos.map((c) => (
          <label key={c.chave} className="extr-campo">
            <span className="extr-rotulo">
              {c.rotulo}
              {c.confianca && <span className="extr-conf">confiança {c.confianca}</span>}
            </span>
            <input
              className="extr-input"
              value={valores[c.chave] ?? ''}
              onChange={(e) => onValor(c.chave, e.target.value)}
            />
            <span className="extr-fonte">
              {c.fonte ? `fonte: “${c.fonte}”` : 'sem citação (extração clássica)'}
            </span>
          </label>
        ))}
      </div>

      <p className="extr-nota">
        O contrato traz os valores <em>originais</em>. Ao adicionar, ajuste o{' '}
        <strong>saldo devedor atual</strong> e as <strong>parcelas restantes</strong>{' '}
        na aba Dívidas.
      </p>

      <div className="extr-acoes">
        <button className="btn-add" onClick={onConfirmar}>
          ✔ Confirmar e adicionar às dívidas
        </button>
        <button className="btn-secundario" onClick={onCancelar}>
          Cancelar
        </button>
      </div>
    </section>
  )
}
