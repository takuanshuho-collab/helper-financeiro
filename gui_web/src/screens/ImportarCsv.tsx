import { useRef, useState } from 'react'

import { hf } from '../hf/client'
import type {
  Categoria,
  CsvImportadoOut,
  GrupoImportadoOut,
  ItemImportacaoIn,
  RubricaMutOut,
} from '../hf/contract'
import { arquivoParaBase64 } from '../lib/arquivo'
import { brl } from '../lib/format'
import { SECOES_ORCAMENTO } from '../lib/orcamento'

/**
 * Importação de extrato/fatura CSV (T-1303, REQ-F-021 / ADR-0014).
 *
 * Fluxo em três estágios, todos locais: o core parseia e agrupa (todo número
 * vem de lá), a LLM local SÓ sugere o campo de cada grupo, e NADA é gravado
 * até o usuário revisar e clicar em Importar — mesma filosofia do "confira
 * antes de adicionar" do Contrato PDF. Sem LLM, o painel degrada para
 * classificação manual (P8): os dropdowns são os mesmos.
 */

type Fase =
  | { tipo: 'ocioso' }
  | { tipo: 'processando'; nome: string }
  | { tipo: 'revisar'; nome: string; resultado: CsvImportadoOut }
  | { tipo: 'feito'; quantos: number; mes: string | null }
  | { tipo: 'erro'; msg: string }

/** Competência corrente 'AAAA-MM' (apenas texto de data — nenhum cálculo). */
function mesAtual(): string {
  return new Date().toISOString().slice(0, 7)
}

/** Valor do dropdown: 'categoria/campo' ('' = não importar este grupo). */
function rotuloInicial(g: GrupoImportadoOut): string {
  return g.categoria && g.campo_pai ? `${g.categoria}/${g.campo_pai}` : ''
}

export default function ImportarCsv({
  aoMutar,
  aoImportarNoMes,
}: {
  aoMutar: (r: RubricaMutOut) => void
  aoImportarNoMes: () => void
}) {
  const [fase, setFase] = useState<Fase>({ tipo: 'ocioso' })
  const [escolhas, setEscolhas] = useState<Record<number, string>>({})
  const [destino, setDestino] = useState<'mes' | 'vivo'>('mes')
  const [mes, setMes] = useState(mesAtual)
  const inputRef = useRef<HTMLInputElement>(null)

  async function processar(file: File | null | undefined) {
    if (!file) return
    if (!file.name.toLowerCase().endsWith('.csv')) {
      setFase({ tipo: 'erro', msg: 'Selecione um arquivo CSV.' })
      return
    }
    setFase({ tipo: 'processando', nome: file.name })
    try {
      const resultado = await hf.importarCsv(await arquivoParaBase64(file), file.name)
      if (resultado.modo === 'vazio') {
        setFase({
          tipo: 'erro',
          msg:
            resultado.avisos[0] ??
            'Não reconheci lançamentos neste arquivo.',
        })
        return
      }
      setEscolhas(
        Object.fromEntries(
          resultado.grupos.map((g) => [g.indice, rotuloInicial(g)]),
        ),
      )
      setDestino('mes')
      setMes(resultado.competencia_sugerida ?? mesAtual())
      setFase({ tipo: 'revisar', nome: file.name, resultado })
    } catch (e) {
      setFase({
        tipo: 'erro',
        msg: e instanceof Error ? e.message : 'Falha ao ler o CSV.',
      })
    }
  }

  function aplicar(resultado: CsvImportadoOut) {
    const itens: ItemImportacaoIn[] = resultado.grupos
      .filter((g) => escolhas[g.indice])
      .map((g) => {
        const [categoria, campo_pai] = escolhas[g.indice].split('/')
        return {
          categoria: categoria as Categoria,
          campo_pai,
          nome: g.nome,
          valor: g.total,
        }
      })
    if (itens.length === 0) {
      setFase({ tipo: 'erro', msg: 'Escolha um campo para ao menos um grupo.' })
      return
    }
    hf.importarAplicar(destino === 'vivo' ? null : mes, itens)
      .then((r) => {
        // No vivo a resposta já traz rubricas + perfil com o roll-up do core
        // (mesma forma das mutações da planilha); na competência, só o
        // histórico precisa recarregar a lista de meses.
        if (r.mes === null) aoMutar({ rubricas: r.rubricas, perfil: r.perfil })
        else aoImportarNoMes()
        setFase({ tipo: 'feito', quantos: itens.length, mes: r.mes })
      })
      .catch((e: Error) => setFase({ tipo: 'erro', msg: e.message }))
  }

  return (
    <section className="secao imp">
      <div className="secao-topo">
        <span className="secao-titulo">
          <span className="secao-ponto" style={{ background: 'var(--accent)' }} />
          Importar extrato (CSV)
        </span>
      </div>

      {fase.tipo === 'ocioso' && (
        <>
          <div className="plan-dica">
            Exporte o extrato ou a fatura do seu banco em CSV — os lançamentos
            viram rubricas depois da sua revisão. Tudo roda localmente.
          </div>
          <div className="imp-acoes">
            <button
              className="btn-add"
              onClick={() => inputRef.current?.click()}
            >
              Escolher arquivo CSV
            </button>
          </div>
          <input
            ref={inputRef}
            type="file"
            accept="text/csv,.csv"
            hidden
            onChange={(ev) => {
              void processar(ev.target.files?.[0])
              ev.target.value = ''
            }}
          />
        </>
      )}

      {fase.tipo === 'processando' && (
        <div className="plan-dica">
          Lendo “{fase.nome}” e consultando o modelo local…
        </div>
      )}

      {fase.tipo === 'erro' && (
        <>
          <div className="plan-erro">{fase.msg}</div>
          <div className="imp-acoes">
            <button
              className="btn-secundario"
              onClick={() => setFase({ tipo: 'ocioso' })}
            >
              Escolher outro CSV
            </button>
          </div>
        </>
      )}

      {fase.tipo === 'feito' && (
        <>
          <div className="imp-feito">
            ✔ {fase.quantos} rubrica(s) importada(s){' '}
            {fase.mes === null
              ? 'no orçamento atual.'
              : `na competência ${fase.mes}.`}
          </div>
          <div className="imp-acoes">
            <button
              className="btn-secundario"
              onClick={() => setFase({ tipo: 'ocioso' })}
            >
              Importar outro CSV
            </button>
          </div>
        </>
      )}

      {fase.tipo === 'revisar' && (
        <Revisao
          resultado={fase.resultado}
          nome={fase.nome}
          escolhas={escolhas}
          aoEscolher={(indice, v) =>
            setEscolhas((e) => ({ ...e, [indice]: v }))
          }
          destino={destino}
          aoDestino={setDestino}
          mes={mes}
          aoMes={setMes}
          aoAplicar={() => aplicar(fase.resultado)}
          aoCancelar={() => setFase({ tipo: 'ocioso' })}
        />
      )}
    </section>
  )
}

function Revisao({
  resultado,
  nome,
  escolhas,
  aoEscolher,
  destino,
  aoDestino,
  mes,
  aoMes,
  aoAplicar,
  aoCancelar,
}: {
  resultado: CsvImportadoOut
  nome: string
  escolhas: Record<number, string>
  aoEscolher: (indice: number, v: string) => void
  destino: 'mes' | 'vivo'
  aoDestino: (d: 'mes' | 'vivo') => void
  mes: string
  aoMes: (m: string) => void
  aoAplicar: () => void
  aoCancelar: () => void
}) {
  const ehIA = resultado.modo === 'ia'
  return (
    <>
      <div className={ehIA ? 'imp-banner ia' : 'imp-banner manual'}>
        {ehIA ? (
          <>
            <strong>Classificação assistida por IA local.</strong> A LLM só
            sugeriu os campos — os valores vêm do arquivo. Confira e ajuste
            antes de importar.
          </>
        ) : (
          <>
            <strong>Modelo local indisponível — classificação manual.</strong>{' '}
            Escolha o campo de cada grupo nos seletores.
            {resultado.motivos.length > 0 && (
              <span className="extr-diag">
                {' '}
                motivo: <code>{resultado.motivos.join(', ')}</code>
              </span>
            )}
          </>
        )}
      </div>

      <div className="card-titulo">Lançamentos de “{nome}”</div>

      {resultado.avisos.length > 0 && (
        <div className="extr-alerta">
          {resultado.avisos.length} linha(s) do arquivo ignorada(s):{' '}
          {resultado.avisos.join(' ')}
        </div>
      )}

      <div className="imp-linhas">
        {resultado.grupos.map((g) => (
          <div className="imp-linha" key={g.indice}>
            <span className="imp-nome">
              {g.nome}
              {g.quantidade > 1 && (
                <span className="plan-chip">{g.quantidade} lançamentos</span>
              )}
            </span>
            <span
              className={
                g.natureza === 'credito' ? 'imp-total credito' : 'imp-total'
              }
            >
              {brl(g.total)}
            </span>
            <select
              className="hist-sel imp-sel"
              value={escolhas[g.indice] ?? ''}
              onChange={(ev) => aoEscolher(g.indice, ev.target.value)}
              aria-label={`Campo do orçamento para ${g.nome}`}
            >
              <OpcoesCampo natureza={g.natureza} />
            </select>
          </div>
        ))}
      </div>

      <div className="imp-acoes">
        Importar para{' '}
        <select
          className="hist-sel imp-destino"
          value={destino}
          onChange={(ev) => aoDestino(ev.target.value as 'mes' | 'vivo')}
          aria-label="Destino da importação"
        >
          <option value="mes">
            a competência{resultado.competencia_sugerida ? ' (detectada)' : ''}
          </option>
          <option value="vivo">o orçamento atual</option>
        </select>
        {destino === 'mes' && (
          <input
            className="hist-mes"
            type="month"
            value={mes}
            onChange={(ev) => aoMes(ev.target.value)}
            aria-label="Competência de destino"
          />
        )}
        <button className="btn-add" onClick={aoAplicar}>
          Importar
        </button>
        <button className="btn-secundario" onClick={aoCancelar}>
          Cancelar
        </button>
      </div>
      <div className="plan-dica">
        Grupos marcados como “não importar” ficam de fora. A importação
        acrescenta rubricas — nada é apagado.
      </div>
    </>
  )
}

/**
 * Campos válidos para a natureza do grupo: crédito só classifica em renda;
 * débito, em despesas (mesma trava que o backend reimpõe — ADR-0014).
 */
function OpcoesCampo({ natureza }: { natureza: 'credito' | 'debito' }) {
  const secoes = SECOES_ORCAMENTO.filter((s) =>
    natureza === 'credito' ? s.categoria === 'renda' : s.categoria !== 'renda',
  )
  return (
    <>
      <option value="">— não importar —</option>
      {secoes.map((s) => (
        <optgroup key={s.categoria} label={s.titulo}>
          {s.campos.map((c) => (
            <option key={c.campo} value={`${s.categoria}/${c.campo}`}>
              {c.rotulo}
            </option>
          ))}
        </optgroup>
      ))}
    </>
  )
}
