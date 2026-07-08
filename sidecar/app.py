"""
App FastAPI do sidecar (ADR-0009).

Expõe o núcleo determinístico em `127.0.0.1` para o front Electron/React. Cada
endpoint apenas monta os objetos do `core`, chama a função determinística e
serializa o resultado. A regra de negócio permanece 100% no `core` (REQ-NF-005).
"""
from __future__ import annotations

import base64
import binascii
import re
import threading
from typing import Annotated
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException

from agent.agente import analisar
from agent.classificacao import Classificador, classificar_grupos
from agent.config import ConfigAgente, carregar_config
from agent.exibicao import ROTULOS_EXTRACAO, campos_para_formulario, preparar_exibicao
from agent.extracao import Extrator, confirmar_extracao, iniciar_extracao
from agent.ingestao import preparar_contexto
from agent.provider import LLMProvider
from contracts import SecaoIA
from core.diagnostico import resumo_diagnostico
from core.estrategias import (
    comparar_estrategias,
    gerar_recomendacoes,
    oportunidades_portabilidade,
)
from core.extrato import decodificar_csv, ler_extrato_csv
from core.extrator_pdf import extrair_texto_pdf_bytes, parsear_campos
from core.models import (
    ComposicaoRenda,
    DespesasFixas,
    DespesasVariaveis,
    Divida,
    PerfilFinanceiro,
)
from core.rubricas import (
    Rubrica,
    aplicar_somas,
    comparar_orcamentos,
    serie_evolucao,
    somas_por_campo,
    validar_mes,
    validar_rubrica,
)
from guardrails.pii import anonimizar_credores
from outputs.planilha import gerar_planilha
from outputs.proposta import gerar_proposta, montar_carta
from outputs.relatorio import gerar_relatorio

from .persistencia import Repositorio
from .schemas import (
    AnaliseIaIn,
    AnaliseIn,
    AplicarImportacaoIn,
    ArquivarMesIn,
    CartaIn,
    CompararMesesIn,
    ConfirmarContratoIn,
    ContratoIn,
    DividaIn,
    EstrategiasIn,
    ExportarCartaIn,
    ExportarPlanilhaIn,
    ExportarRelatorioIn,
    ImportarCsvIn,
    PerfilIn,
    RubricaEditIn,
    RubricaIn,
)
from .security import exigir_token

app = FastAPI(title="Helper Financeiro — sidecar", version="2.6.0")

# Chaves do resumo que carregam objetos `Divida` (precisam de serialização).
_CHAVES_OBJETO = ("divida_mais_cara", "ranking")

# Documento sem texto selecionável (provável digitalização/imagem).
AVISO_PDF_SEM_TEXTO = (
    "O PDF parece não conter texto selecionável (provavelmente é uma imagem/"
    "digitalização). Preencha os campos manualmente na aba Dívidas."
)


def _para_divida(d: DividaIn) -> Divida:
    return Divida(
        credor=d.credor,
        tipo=d.tipo,
        saldo_devedor=d.saldo_devedor,
        taxa_mensal=d.taxa_mensal,
        parcela=d.parcela,
        parcelas_restantes=d.parcelas_restantes,
        garantia=d.garantia,
        em_atraso=d.em_atraso,
        dias_atraso=d.dias_atraso,
        cet_anual=d.cet_anual,
    )


def _para_perfil(p: PerfilIn) -> PerfilFinanceiro:
    return PerfilFinanceiro.com_orcamento(
        renda=ComposicaoRenda(**p.renda.model_dump()),
        fixas=DespesasFixas(**p.fixas.model_dump()),
        variaveis=DespesasVariaveis(**p.variaveis.model_dump()),
        reserva_emergencia=p.reserva_emergencia,
        saldo_fgts=p.saldo_fgts,
        dividas=[_para_divida(d) for d in p.dividas],
    )


def _divida_dict(d: Divida) -> dict:
    return {
        "credor": d.credor,
        "tipo": d.tipo,
        "saldo_devedor": d.saldo_devedor,
        "taxa_mensal": d.taxa_mensal,
        "taxa_anual": d.taxa_anual,
        "parcela": d.parcela,
        "parcelas_restantes": d.parcelas_restantes,
        "custo_total_restante": d.custo_total_restante,
        "juros_restantes": d.juros_restantes,
        "em_atraso": d.em_atraso,
    }


@app.get("/health")
def health() -> dict:
    """Liveness — dispensa token para o Electron aferir prontidão."""
    return {"status": "ok", "servico": "helper-financeiro-sidecar"}


@app.post("/diagnostico", dependencies=[Depends(exigir_token)])
def diagnostico(perfil_in: PerfilIn) -> dict:
    """Diagnóstico determinístico a partir do orçamento + dívidas."""
    perfil = _para_perfil(perfil_in)
    resumo = resumo_diagnostico(perfil)
    mais_cara = resumo["divida_mais_cara"]

    resposta = {k: v for k, v in resumo.items() if k not in _CHAVES_OBJETO}
    resposta["divida_mais_cara"] = _divida_dict(mais_cara) if mais_cara else None
    resposta["ranking"] = [_divida_dict(d) for d in resumo["ranking"]]
    resposta["despesas_fixas"] = perfil.despesas_fixas
    resposta["despesas_variaveis"] = perfil.despesas_variaveis
    resposta["meses_reserva"] = perfil.meses_reserva
    return resposta


# ------------------------------------------------ estado persistido (T-1102)
# O perfil completo (orçamento + dívidas) é salvo como documento único: o
# auto-save da GUI manda o estado inteiro com debounce, e a hidratação no boot
# devolve exatamente o que foi salvo (REQ-F-018, ADR-0012).
CHAVE_PERFIL = "perfil"

_REPO: Repositorio | None = None


def repositorio() -> Repositorio:
    """Dependência do banco local (sobrescrita nos testes com um tmp_path).

    Criado sob demanda na primeira chamada — assim os testes que sobrescrevem
    a dependência nunca tocam o banco real do usuário.
    """
    global _REPO
    if _REPO is None:
        _REPO = Repositorio()
    return _REPO


def _rubricas_do_banco(repo: Repositorio) -> list[Rubrica]:
    return [Rubrica(**r) for r in repo.listar_rubricas()]


def _com_roll_up(perfil: dict, repo: Repositorio) -> dict:
    """Aplica o invariante do ADR-0012 ao perfil: campo detalhado = soma.

    A aritmética vem do `core` (REQ-NF-005); aqui só orquestramos banco↔core.
    """
    return aplicar_somas(perfil, somas_por_campo(_rubricas_do_banco(repo)))


def _perfil_apos_mutacao(repo: Repositorio) -> dict:
    """Recalcula e persiste o perfil após criar/editar/remover uma rubrica.

    O perfil salvo continua sendo a fonte única que alimenta os demais
    endpoints — as mutações de rubrica o mantêm consistente por construção.
    """
    bruto = repo.carregar_estado(CHAVE_PERFIL) or PerfilIn().model_dump()
    perfil = PerfilIn(**_com_roll_up(bruto, repo)).model_dump()
    repo.salvar_estado(CHAVE_PERFIL, perfil)
    return perfil


@app.get("/estado", dependencies=[Depends(exigir_token)])
def estado_carregar(repo: Annotated[Repositorio, Depends(repositorio)]) -> dict:
    """Estado salvo do usuário; `perfil` é None na primeira execução.

    As rubricas vêm junto: a GUI precisa delas para a planilha e para saber
    quais campos do Perfil estão detalhados (somente-leitura).
    """
    return {"perfil": repo.carregar_estado(CHAVE_PERFIL),
            "rubricas": repo.listar_rubricas()}


@app.post("/estado", dependencies=[Depends(exigir_token)])
def estado_salvar(perfil_in: PerfilIn,
                  repo: Annotated[Repositorio, Depends(repositorio)]) -> dict:
    """Salva o perfil completo (auto-save da GUI).

    O payload passa pela validação do `PerfilIn` antes de ir ao banco — o que
    está persistido sempre volta a hidratar a GUI sem surpresa de schema. Os
    campos detalhados são reimpostos pela soma das rubricas (ADR-0012): nem
    um front fora de sincronia consegue gravar um total divergente.
    """
    repo.salvar_estado(CHAVE_PERFIL,
                       _com_roll_up(perfil_in.model_dump(), repo))
    return {"ok": True}


# ---------------------------------------------------- histórico mensal (T-1202)
def _mes_valido_ou_422(mes: str) -> None:
    try:
        validar_mes(mes)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


def _perfil_vivo(repo: Repositorio) -> dict:
    return repo.carregar_estado(CHAVE_PERFIL) or PerfilIn().model_dump()


@app.post("/historico/arquivar", dependencies=[Depends(exigir_token)])
def historico_arquivar(entrada: ArquivarMesIn,
                       repo: Annotated[Repositorio, Depends(repositorio)]) -> dict:
    """Arquiva a competência: snapshot do perfil vivo + cópia das rubricas.

    Rearquivar a mesma competência substitui o snapshot (ADR-0013).
    """
    _mes_valido_ou_422(entrada.mes)
    repo.arquivar_mes(entrada.mes, _perfil_vivo(repo))
    return {"ok": True, "mes": entrada.mes, "meses": repo.listar_meses()}


@app.get("/historico", dependencies=[Depends(exigir_token)])
def historico_listar(repo: Annotated[Repositorio, Depends(repositorio)]) -> dict:
    return {"meses": repo.listar_meses()}


@app.get("/historico/evolucao", dependencies=[Depends(exigir_token)])
def historico_evolucao(repo: Annotated[Repositorio, Depends(repositorio)]) -> dict:
    """Séries de evolução das competências arquivadas (REQ-F-022, ADR-0014).

    Totais por seção + série por campo, prontos do core (`serie_evolucao`) —
    a GUI só desenha o SVG (REQ-NF-005). Declarada ANTES de
    `/historico/{mes}` para "evolucao" não ser lida como competência.
    """
    snapshots = [(mes, repo.carregar_mes(mes) or {})
                 for mes in repo.listar_meses()]
    return serie_evolucao(snapshots)


@app.get("/historico/{mes}", dependencies=[Depends(exigir_token)])
def historico_snapshot(mes: str,
                       repo: Annotated[Repositorio, Depends(repositorio)]) -> dict:
    """Snapshot completo da competência (perfil + rubricas arquivadas)."""
    _mes_valido_ou_422(mes)
    perfil = repo.carregar_mes(mes)
    if perfil is None:
        raise HTTPException(status_code=404, detail="Competência sem snapshot.")
    return {"mes": mes, "perfil": perfil, "rubricas": repo.rubricas_do_mes(mes)}


@app.post("/historico/comparar", dependencies=[Depends(exigir_token)])
def historico_comparar(entrada: CompararMesesIn,
                       repo: Annotated[Repositorio, Depends(repositorio)]) -> dict:
    """Variação campo a campo entre `mes_a` e `mes_b` (None = orçamento vivo).

    A aritmética inteira vem de `core.rubricas.comparar_orcamentos`
    (REQ-NF-005) — aqui só se resolve de onde vêm os dois perfis.
    """
    _mes_valido_ou_422(entrada.mes_a)
    antes = repo.carregar_mes(entrada.mes_a)
    if antes is None:
        raise HTTPException(status_code=404, detail="Competência sem snapshot.")
    if entrada.mes_b is None:
        depois = _perfil_vivo(repo)
    else:
        _mes_valido_ou_422(entrada.mes_b)
        snapshot = repo.carregar_mes(entrada.mes_b)
        if snapshot is None:
            raise HTTPException(status_code=404,
                                detail="Competência sem snapshot.")
        depois = snapshot
    return {"mes_a": entrada.mes_a, "mes_b": entrada.mes_b,
            "comparacao": comparar_orcamentos(antes, depois)}


# ---------------------------------------------------------- rubricas (T-1103)
# Toda mutação devolve a lista atualizada E o perfil recalculado: a GUI
# hidrata os dois estados numa resposta só, sem janela de inconsistência.
@app.get("/rubricas", dependencies=[Depends(exigir_token)])
def rubricas_listar(repo: Annotated[Repositorio, Depends(repositorio)]) -> dict:
    return {"rubricas": repo.listar_rubricas()}


@app.post("/rubricas", dependencies=[Depends(exigir_token)])
def rubrica_criar(entrada: RubricaIn,
                  repo: Annotated[Repositorio, Depends(repositorio)]) -> dict:
    """Cria um lançamento; a ancoragem é validada contra o modelo do core."""
    try:
        validar_rubrica(entrada.categoria, entrada.campo_pai, entrada.nome)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    rubrica = repo.criar_rubrica(entrada.categoria, entrada.campo_pai,
                                 entrada.nome.strip(), entrada.valor,
                                 entrada.ordem)
    return {"rubrica": rubrica, "rubricas": repo.listar_rubricas(),
            "perfil": _perfil_apos_mutacao(repo)}


@app.post("/rubricas/{rubrica_id}", dependencies=[Depends(exigir_token)])
def rubrica_editar(rubrica_id: int, entrada: RubricaEditIn,
                   repo: Annotated[Repositorio, Depends(repositorio)]) -> dict:
    """Edita nome/valor/ordem. Mover de grupo é remover + criar."""
    if not entrada.nome.strip():
        raise HTTPException(status_code=422,
                            detail="A rubrica precisa de um nome.")
    rubrica = repo.atualizar_rubrica(rubrica_id, entrada.nome.strip(),
                                     entrada.valor, entrada.ordem)
    if rubrica is None:
        raise HTTPException(status_code=404, detail="Rubrica desconhecida.")
    return {"rubrica": rubrica, "rubricas": repo.listar_rubricas(),
            "perfil": _perfil_apos_mutacao(repo)}


@app.post("/rubricas/{rubrica_id}/remover", dependencies=[Depends(exigir_token)])
def rubrica_remover(rubrica_id: int,
                    repo: Annotated[Repositorio, Depends(repositorio)]) -> dict:
    """Remove o lançamento. O campo-pai fica com a última soma e volta a ser
    editável quando perde a última rubrica (decisão do ADR-0012)."""
    if not repo.remover_rubrica(rubrica_id):
        raise HTTPException(status_code=404, detail="Rubrica desconhecida.")
    return {"ok": True, "rubricas": repo.listar_rubricas(),
            "perfil": _perfil_apos_mutacao(repo)}


# ------------------------------------- importação de CSV (T-1302, ADR-0014)
def contexto_classificacao() -> tuple[ConfigAgente | None, Classificador | None]:
    """Dependência da classificação (sobrescrita nos testes).

    Em produção devolve (None, None): a classificação usa a config real
    (local-only, H2) e o dialeto do provider. Os testes injetam um
    `FakeClassificador` determinístico.
    """
    return None, None


@app.post("/importar/csv", dependencies=[Depends(exigir_token)])
def importar_csv(
    entrada: ImportarCsvIn,
    ctx: tuple[ConfigAgente | None, Classificador | None] = Depends(
        contexto_classificacao),
) -> dict:
    """Lê o extrato CSV e devolve os grupos classificados PARA REVISÃO.

    Nada é persistido aqui: o usuário confere (e corrige) no painel e só o
    `/importar/aplicar` grava. O parse é 100% determinístico (`core/extrato`);
    a LLM local SÓ rotula grupos — recebe nomes normalizados, sem valores e
    sem datas (H1/H2, ADR-0014). Sem LLM, `modo` degrada para "manual" com os
    motivos (P8) e todos os grupos voltam sem rótulo.
    """
    cfg, classificador = ctx
    try:
        dados = base64.b64decode(entrada.csv_base64, validate=True)
    except (binascii.Error, ValueError) as e:
        raise HTTPException(status_code=422,
                            detail="CSV inválido (base64).") from e

    extrato = ler_extrato_csv(decodificar_csv(dados))
    pares = [(g.nome, g.natureza) for g in extrato.grupos]
    resultado = classificar_grupos(pares, cfg=cfg, classificador=classificador)

    grupos = []
    for i, g in enumerate(extrato.grupos):
        rotulo = resultado.por_indice.get(i)
        grupos.append({
            "indice": i, "nome": g.nome, "total": g.total,
            "quantidade": g.quantidade, "natureza": g.natureza,
            "categoria": rotulo[0] if rotulo else None,
            "campo_pai": rotulo[1] if rotulo else None,
        })
    if not grupos:
        modo = "vazio"
    elif resultado.motivos:
        modo = "manual"
    else:
        modo = "ia"
    return {"modo": modo, "grupos": grupos,
            "competencia_sugerida": extrato.competencia_sugerida,
            "avisos": list(extrato.avisos),
            "descartes": resultado.descartes,
            "motivos": resultado.motivos, "llm": _diag_llm(cfg)}


@app.post("/importar/aplicar", dependencies=[Depends(exigir_token)])
def importar_aplicar(entrada: AplicarImportacaoIn,
                     repo: Annotated[Repositorio, Depends(repositorio)]) -> dict:
    """Grava os itens revisados como rubricas no destino escolhido.

    `mes` None → orçamento vivo (fluxo normal do ADR-0012: roll-up na
    escrita). `mes` 'AAAA-MM' → as rubricas nascem na competência e o
    snapshot do perfil é recalculado (base = snapshot existente, ou perfil
    zerado se a competência é nova). A importação ACRESCENTA, nunca apaga
    (ADR-0014).
    """
    if not entrada.itens:
        raise HTTPException(status_code=422, detail="Nada a importar.")
    for item in entrada.itens:
        try:
            validar_rubrica(item.categoria, item.campo_pai, item.nome)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e)) from e

    if entrada.mes is None:
        for item in entrada.itens:
            repo.criar_rubrica(item.categoria, item.campo_pai,
                               item.nome.strip(), item.valor)
        return {"ok": True, "mes": None, "rubricas": repo.listar_rubricas(),
                "perfil": _perfil_apos_mutacao(repo)}

    _mes_valido_ou_422(entrada.mes)
    base = repo.carregar_mes(entrada.mes) or PerfilIn().model_dump()
    for item in entrada.itens:
        repo.criar_rubrica(item.categoria, item.campo_pai, item.nome.strip(),
                           item.valor, mes=entrada.mes)
    rubricas_mes = repo.rubricas_do_mes(entrada.mes)
    somas = somas_por_campo([Rubrica(**r) for r in rubricas_mes])
    perfil = PerfilIn(**aplicar_somas(base, somas)).model_dump()
    repo.salvar_perfil_do_mes(entrada.mes, perfil)
    return {"ok": True, "mes": entrada.mes, "meses": repo.listar_meses(),
            "rubricas": rubricas_mes, "perfil": perfil}


@app.post("/estrategias", dependencies=[Depends(exigir_token)])
def estrategias(entrada: EstrategiasIn) -> dict:
    """Compara avalanche vs. bola de neve para o pagamento extra informado."""
    perfil = _para_perfil(entrada.perfil)
    return comparar_estrategias(perfil, entrada.extra)


# ------------------------------------------------------------ análise (T-902)
@app.post("/analise", dependencies=[Depends(exigir_token)])
def analise(entrada: AnaliseIn) -> dict:
    """Pacote determinístico da tela Análise (REQ-F-015).

    Estratégias recalculadas com o pagamento extra, oportunidades de
    portabilidade acima da taxa-alvo e recomendações — tudo do `core`. A
    diferença de juros entre os métodos é agregada aqui (apresentação); os
    números vêm prontos das simulações.
    """
    perfil = _para_perfil(entrada.perfil)
    comp = comparar_estrategias(perfil, entrada.extra)
    ava, bola = comp["avalanche"], comp["bola_de_neve"]
    economia = (round(bola["juros_pagos"] - ava["juros_pagos"], 2)
                if ava["quitavel"] and bola["quitavel"] else None)
    oportunidades = oportunidades_portabilidade(perfil, entrada.taxa_alvo)
    return {
        "estrategias": comp,
        "economia_avalanche": economia,
        "oportunidades": oportunidades,
        "economia_total_portabilidade": round(
            sum(o["economia_total"] for o in oportunidades), 2),
        "recomendacoes": gerar_recomendacoes(perfil, resumo_diagnostico(perfil)),
    }


# ----------------------------------------------- análise sênior (IA, job async)
def contexto_analise() -> tuple[ConfigAgente | None, LLMProvider | None]:
    """Dependência do job da IA sênior (sobrescrita nos testes).

    Em produção devolve (None, None): `analisar` usa a config real (env HF_*)
    e o provider correspondente. Os testes injetam um provider determinístico.
    """
    return None, None


# Jobs em memória: a chamada ao LLM local leva de segundos a minutos, então a
# tela dispara o job e faz poll — o sidecar continua respondendo às demais
# rotas. O resultado é descartado na primeira leitura de estado final.
_JOBS_IA: dict[str, dict] = {}
_JOBS_IA_LOCK = threading.Lock()


def _rodar_job_ia(job_id: str, perfil: PerfilFinanceiro, extra: float,
                  cfg: ConfigAgente | None, provider: LLMProvider | None) -> None:
    try:
        resultado = analisar(perfil, extra_mensal=extra, cfg=cfg, provider=provider)
        # O mapa é reconstruível: os tokens CREDOR_n seguem a ordem das dívidas.
        # A desanonimização acontece SÓ aqui, na fronteira da exibição local
        # (REQ-SEC-003) — o que foi ao LLM só tinha tokens.
        _, mapa = anonimizar_credores([d.credor for d in perfil.dividas])
        secao = preparar_exibicao(resultado, mapa)
        estado: dict[str, object] = {"status": "pronto",
                                     "secao": secao.model_dump(), "erro": ""}
    except Exception as e:  # noqa: BLE001 — o erro vira status consultável no poll
        estado = {"status": "erro", "secao": None,
                  "erro": f"{type(e).__name__}: {e}"}
    with _JOBS_IA_LOCK:
        _JOBS_IA[job_id] = estado


@app.post("/analise/ia", dependencies=[Depends(exigir_token)])
def analise_ia_iniciar(
    entrada: AnaliseIaIn,
    ctx: tuple[ConfigAgente | None, LLMProvider | None] = Depends(contexto_analise),
) -> dict:
    """Dispara a análise sênior (IA, sob guardrails) e devolve o id do job.

    Os fatos vão ANONIMIZADOS ao LLM (tokens CREDOR_n, REQ-GRD-002/H2); toda
    falha degrada para o diagnóstico determinístico (P8) — nunca 500.
    """
    cfg, provider = ctx
    perfil = _para_perfil(entrada.perfil)
    job_id = uuid4().hex
    with _JOBS_IA_LOCK:
        _JOBS_IA[job_id] = {"status": "rodando", "secao": None, "erro": ""}
    threading.Thread(
        target=_rodar_job_ia, args=(job_id, perfil, entrada.extra, cfg, provider),
        daemon=True,
    ).start()
    return {"job_id": job_id}


@app.get("/analise/ia/{job_id}", dependencies=[Depends(exigir_token)])
def analise_ia_status(job_id: str) -> dict:
    """Estado do job: rodando | pronto (com a seção) | erro. 404 se desconhecido."""
    with _JOBS_IA_LOCK:
        job = _JOBS_IA.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job desconhecido.")
        if job["status"] != "rodando":
            del _JOBS_IA[job_id]  # leitura final: libera a memória do job
    return {"job_id": job_id, **job}


# ------------------------------------------------------- exportações (T-902)
@app.post("/exportar/planilha", dependencies=[Depends(exigir_token)])
def exportar_planilha(entrada: ExportarPlanilhaIn,
                      repo: Annotated[Repositorio, Depends(repositorio)]) -> dict:
    """Gera o .xlsx no caminho escolhido pelo usuário (diálogo do Electron).

    As rubricas salvas entram na aba "Orçamento detalhado" (T-1105) e as
    competências arquivadas na aba "Evolução mensal" (T-1305, REQ-F-023).
    """
    perfil = _para_perfil(entrada.perfil)
    snapshots = [(m, repo.carregar_mes(m) or {}) for m in repo.listar_meses()]
    try:
        caminho = gerar_planilha(perfil, entrada.caminho,
                                 extra_mensal=entrada.extra,
                                 taxa_alvo_mensal=entrada.taxa_alvo,
                                 rubricas=_rubricas_do_banco(repo),
                                 evolucao=serie_evolucao(snapshots))
    except OSError as e:
        raise HTTPException(status_code=400,
                            detail=f"Não foi possível salvar a planilha: {e}") from e
    return {"caminho": caminho}


@app.post("/exportar/relatorio", dependencies=[Depends(exigir_token)])
def exportar_relatorio(entrada: ExportarRelatorioIn) -> dict:
    """Gera o .docx; inclui a última análise sênior quando a tela a enviar."""
    perfil = _para_perfil(entrada.perfil)
    secao = SecaoIA(**entrada.secao_ia) if entrada.secao_ia else None
    try:
        caminho = gerar_relatorio(perfil, entrada.caminho,
                                  extra_mensal=entrada.extra,
                                  taxa_alvo_mensal=entrada.taxa_alvo,
                                  nome_usuario=entrada.nome_usuario,
                                  secao_ia=secao)
    except OSError as e:
        raise HTTPException(status_code=400,
                            detail=f"Não foi possível salvar o relatório: {e}") from e
    return {"caminho": caminho}


# ---------------------------------------------------- carta ao credor (T-903)
def _dados_carta(entrada: CartaIn) -> dict:
    """Campos contextuais no formato que `outputs.proposta` espera."""
    return {
        "valor_proposto": entrada.valor_proposto or None,
        "banco_concorrente": entrada.banco_concorrente.strip() or None,
        "taxa_concorrente_mensal": entrada.taxa_concorrente_mensal or None,
    }


@app.post("/carta/previa", dependencies=[Depends(exigir_token)])
def carta_previa(entrada: CartaIn) -> dict:
    """Pré-visualização ao vivo da carta (REQ-F-016).

    O texto vem inteiro do `core`/`outputs` (fonte única): a tela só renderiza
    a mesma estrutura que o `.docx` usa — nada é redigido no front.
    """
    return montar_carta(_para_divida(entrada.divida), tipo=entrada.tipo,
                        dados=_dados_carta(entrada),
                        nome_usuario=entrada.nome_usuario,
                        cpf=entrada.cpf, contrato=entrada.contrato)


@app.post("/exportar/carta", dependencies=[Depends(exigir_token)])
def exportar_carta(entrada: ExportarCartaIn) -> dict:
    """Gera a carta .docx no caminho escolhido pelo usuário."""
    try:
        caminho = gerar_proposta(_para_divida(entrada.divida), entrada.caminho,
                                 tipo=entrada.tipo, dados=_dados_carta(entrada),
                                 nome_usuario=entrada.nome_usuario,
                                 cpf=entrada.cpf, contrato=entrada.contrato)
    except OSError as e:
        raise HTTPException(status_code=400,
                            detail=f"Não foi possível salvar a carta: {e}") from e
    return {"caminho": caminho}


# ------------------------------------------------------------ contrato PDF (T-901)
def contexto_extracao() -> tuple[ConfigAgente | None, Extrator | None]:
    """Dependência de execução da extração (sobrescrita nos testes).

    Em produção devolve (None, None): a extração usa a config real (local-only,
    H2) e o extrator Ollama. Os testes injetam um `FakeExtrator` determinístico.
    """
    return None, None


def _campo(valor: object) -> dict:
    """Adapta um valor do parse clássico ao formato de `campos_para_formulario`."""
    return {"valor": valor, "trecho_fonte": "", "confianca": 0.0}


def _classico_para_campos(parse: dict) -> dict:
    """Mapeia o parse regex (sem citação) para o formato da extração assistida."""
    campos: dict[str, dict] = {}
    if parse.get("tipo"):
        campos["tipo"] = _campo(parse["tipo"])
    if parse.get("valor_financiado") is not None:
        campos["saldo_devedor"] = _campo(parse["valor_financiado"])
    if parse.get("taxa_mensal") is not None:
        campos["taxa_mensal"] = _campo(parse["taxa_mensal"])
    if parse.get("valor_parcela") is not None:
        campos["parcela"] = _campo(parse["valor_parcela"])
    if parse.get("num_parcelas") is not None:
        campos["parcelas_restantes"] = _campo(parse["num_parcelas"])
    return campos


# "96x de R$ 899,47": nº de parcelas embutido no trecho citado para a parcela.
_RE_PARCELAS_NO_TRECHO = re.compile(r"(\d{1,3})\s*x\b", re.IGNORECASE)

_CAMPOS_EXTRACAO = ("credor", "tipo", "saldo_devedor", "taxa_mensal",
                    "parcela", "parcelas_restantes")


def _fundir_com_classico(campos: dict, texto_plano: str) -> dict:
    """Completa com fontes determinísticas os campos que a LLM devolveu null.

    Modelos locais pequenos falham no MAPEAMENTO semântico mesmo com o dado no
    contexto (caso real: citaram "96x de R$ 899,47" na parcela e devolveram
    parcelas_restantes=null). Dois resgates, ambos sem LLM: (1) derivar
    `parcelas_restantes` do trecho já citado — e verificado pelo quote-check —
    da parcela; (2) preencher o que faltar com a extração clássica por regex no
    texto plano. A IA nunca é sobrescrita, só completada; o usuário confirma
    tudo na tela (REQ-F-014).
    """
    campos = dict(campos)
    if not campos.get("parcelas_restantes") and (p := campos.get("parcela")):
        m = _RE_PARCELAS_NO_TRECHO.search(str(p.get("trecho_fonte", "")))
        if m:
            campos["parcelas_restantes"] = {
                "valor": int(m.group(1)),
                "trecho_fonte": p.get("trecho_fonte", ""),
                "confianca": p.get("confianca", 0.0),
            }
    if faltantes := [c for c in _CAMPOS_EXTRACAO if not campos.get(c)]:
        classico = _classico_para_campos(parsear_campos(texto_plano))
        for chave in faltantes:
            if chave in classico:
                campos[chave] = classico[chave]
    return campos


def _form_para_lista(form: dict) -> list[dict]:
    """Serializa o formulário na ordem canônica dos rótulos (credor→restantes)."""
    return [
        {"chave": chave, "rotulo": ROTULOS_EXTRACAO[chave], **form[chave]}
        for chave in ROTULOS_EXTRACAO
        if chave in form
    ]


# O retrieval (embeddings via LlamaIndex) só existe no Ollama (`/api/embed`).
# Servidores locais OpenAI-compatible (LM Studio/llama.cpp) não têm embeddings
# compatíveis — tentar o retrieval bate num endpoint inexistente e ainda joga o
# documento inteiro no prompt (lento no modelo local). Nesses casos, truncamos.
_PROVIDERS_COM_EMBEDDINGS = {"local", "ollama"}

# Teto de caracteres do documento entregue à LLM na extração. Bem abaixo do
# `LIMITE_DIRETO_CHARS` (6000) do retrieval: modelos locais em CPU pagam o custo
# no PROCESSAMENTO DO PROMPT (~min p/ milhares de tokens), então um contexto mais
# curto — os dados do contrato ficam nas primeiras páginas — acelera a extração
# sem perder os campos. Documento longo de verdade deve usar Ollama + embeddings.
LIMITE_EXTRACAO_LLM = 4000


def _contexto_seguro(texto: str, cfg: ConfigAgente | None) -> str:
    """Prepara o contexto p/ a extração: retrieval no Ollama; truncagem no resto.

    Documento curto vai inteiro. Documento longo: só o Ollama faz retrieval por
    embeddings; para OpenAI-compat local, trunca em `LIMITE_EXTRACAO_LLM` —
    determinístico, sem `/api/embed` e com um prompt enxuto (crucial em modelos
    locais lentos).
    """
    conf = cfg or carregar_config()
    if conf.provider.strip().lower() not in _PROVIDERS_COM_EMBEDDINGS:
        return texto[:LIMITE_EXTRACAO_LLM]
    try:
        return preparar_contexto(texto, conf)
    except Exception:  # noqa: BLE001 — sem embeddings ⇒ melhor esforço (texto direto)
        return texto[:LIMITE_EXTRACAO_LLM]


def _diag_llm(cfg: ConfigAgente | None) -> dict:
    """Alvo efetivo da LLM (sem segredos) — para diagnosticar a queda p/ clássico."""
    conf = cfg or carregar_config()
    return {"provider": conf.provider, "base_url": conf.base_url,
            "model": conf.model, "endpoint_local": conf.endpoint_local}


@app.post("/contrato/extrair", dependencies=[Depends(exigir_token)])
def contrato_extrair(
    entrada: ContratoIn,
    ctx: tuple[ConfigAgente | None, Extrator | None] = Depends(contexto_extracao),
) -> dict:
    """Extrai os campos de um contrato PDF LOCALMENTE, com citação (REQ-F-014).

    O PDF (com PII) é decodificado em memória e nunca sai da máquina (H2).
    Tenta a extração assistida por IA local — quote-check + checagem cruzada +
    `interrupt` para confirmação humana; se indisponível, cai na extração
    clássica por regex (determinística, sem citação). O texto cru nunca vira
    fato: só campos tipados e confirmados alimentam o perfil (REQ-GRD-005).
    """
    cfg, extrator = ctx
    llm = _diag_llm(cfg)
    try:
        dados = base64.b64decode(entrada.pdf_base64, validate=True)
    except (binascii.Error, ValueError) as e:
        raise HTTPException(status_code=422, detail="PDF invalido (base64).") from e

    texto_plano = extrair_texto_pdf_bytes(dados)
    if len(texto_plano.strip()) < 40:
        return {"modo": "vazio", "thread_id": None, "campos": [],
                "descartados": [], "inconsistencias": [], "motivos": [],
                "aviso": AVISO_PDF_SEM_TEXTO, "llm": llm}

    # Texto plano (não Markdown) para a LLM: prompt mais enxuto e citações limpas
    # (sem `#`/`**`), decisivo em modelos locais lentos. O mesmo texto plano
    # alimenta o regex clássico. Ver ADR-0010 (refinamento).
    contexto = _contexto_seguro(texto_plano, cfg)
    _tid, estado = iniciar_extracao(contexto, cfg=cfg, extrator=extrator)
    if "__interrupt__" in estado:  # o grafo pausou para a confirmação humana
        payload = estado["__interrupt__"][0].value
        # Fusão: campos que a IA não achou são completados pelo regex clássico
        # (determinístico, sem citação) antes de irem à tela de confirmação.
        form = campos_para_formulario(
            _fundir_com_classico(payload["campos"], texto_plano)
        )
        return {"modo": "ia", "thread_id": _tid,
                "campos": _form_para_lista(form),
                "descartados": payload["descartados"],
                "inconsistencias": payload["inconsistencias"], "motivos": [],
                "aviso": "", "llm": llm}

    # IA local indisponível ⇒ extração clássica (regex, sem citação verificável).
    # `motivos` diz POR QUE a IA não rodou (ex.: ERRO_PROVIDER:URLError = servidor
    # local fora do ar/porta errada; REQ-LLM-002:SCHEMA = structured output falhou).
    form = campos_para_formulario(_classico_para_campos(parsear_campos(texto_plano)))
    return {"modo": "classico", "thread_id": None, "campos": _form_para_lista(form),
            "descartados": [], "inconsistencias": [],
            "motivos": estado.get("motivos") or [], "aviso": "", "llm": llm}


@app.post("/contrato/confirmar", dependencies=[Depends(exigir_token)])
def contrato_confirmar(
    entrada: ConfirmarContratoIn,
    ctx: tuple[ConfigAgente | None, Extrator | None] = Depends(contexto_extracao),
) -> dict:
    """Retoma o grafo pausado com os campos confirmados (interrupt→resume)."""
    cfg, extrator = ctx
    estado = confirmar_extracao(entrada.thread_id, entrada.confirmacao,
                                cfg=cfg, extrator=extrator)
    return {"ok": True, "confirmada": estado.get("confirmada")}
