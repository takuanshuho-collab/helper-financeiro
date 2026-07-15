"""
App FastAPI do sidecar (ADR-0009).

Expõe o núcleo determinístico em `127.0.0.1` para o front Electron/React. Cada
endpoint apenas monta os objetos do `core`, chama a função determinística e
serializa o resultado. A regra de negócio permanece 100% no `core` (REQ-NF-005).
"""
from __future__ import annotations

import base64
import binascii
import io
import logging
import math
import os
import re
import threading
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated
from uuid import uuid4

import qrcode
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from qrcode.image.pure import PyPNGImage

from agent.agente import analisar
from agent.classificacao import Classificador, classificar_grupos
from agent.config import ConfigAgente, carregar_config
from agent.exibicao import ROTULOS_EXTRACAO, campos_para_formulario, preparar_exibicao
from agent.extracao import Extrator, confirmar_extracao, iniciar_extracao
from agent.ingestao import preparar_contexto
from agent.ocr import Motor, OCRIndisponivel, obter_motor, ocr_documento
from agent.provider import LLMProvider
from contracts import SecaoIA
from core.diagnostico import resumo_diagnostico
from core.documento import FonteDocumento, fonte_por_extensao
from core.estrategias import (
    comparar_estrategias,
    gerar_recomendacoes,
    oportunidades_portabilidade,
)
from core.extrato import Extrato, decodificar_csv, ler_extrato_csv, ler_extrato_ocr
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

from .auth import (
    AguardeCofre,
    CodigoRecuperacaoInvalido,
    CofreJaCadastrado,
    CofreNaoCadastrado,
    SenhaFraca,
    SenhaIncorreta,
    TotpIncorreto,
)
from .persistencia import ChaveInvalida, Repositorio
from .schemas import (
    AnaliseIaIn,
    AnaliseIn,
    AplicarImportacaoIn,
    ArquivarMesIn,
    BaixarModeloIn,
    CadastrarCofreIn,
    CartaIn,
    CompararMesesIn,
    ConfirmarContratoIn,
    ContratoIn,
    DefinirModeloIn,
    DividaIn,
    EstrategiasIn,
    ExportarCartaIn,
    ExportarPlanilhaIn,
    ExportarRelatorioIn,
    ImportarCsvIn,
    ImportarOcrIn,
    LoginCofreIn,
    PerfilIn,
    RecuperarCofreIn,
    RubricaEditIn,
    RubricaIn,
    TrocarSenhaCofreIn,
)
from .security import exigir_token
from .sessao import SessaoBloqueada, SessaoCofre
from .sessao import sessao as sessao_processo


@asynccontextmanager
async def _ciclo_de_vida(_app: FastAPI) -> AsyncIterator[None]:
    """Nada a fazer na subida; no encerramento, derruba o `llama-server`
    embarcado (se estiver de pé) — pendência deixada pelo T-1701
    (`sidecar/runtime_llm.py`) e fechada aqui (T-1702). Import tardio: mesmo
    racional de sempre, evita inverter a camada agent/sidecar no import a
    nível de módulo."""
    yield
    from .runtime_llm import encerrar_runtime
    encerrar_runtime()


app = FastAPI(title="Helper Financeiro — sidecar", version="2.13.0",
             lifespan=_ciclo_de_vida)

# Chaves do resumo que carregam objetos `Divida` (precisam de serialização).
_CHAVES_OBJETO = ("divida_mais_cara", "ranking")

log = logging.getLogger("helper_financeiro.sidecar")

# Documento sem texto selecionável (provável digitalização/imagem).
AVISO_PDF_SEM_TEXTO = (
    "O PDF parece não conter texto selecionável (provavelmente é uma imagem/"
    "digitalização). Preencha os campos manualmente na aba Dívidas."
)
AVISO_OCR_INDISPONIVEL = (
    "Não foi possível ler o documento escaneado: o motor de OCR não está "
    "disponível. Preencha os campos manualmente na aba Dívidas."
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


@app.post("/encerrar", dependencies=[Depends(exigir_token)])
def encerrar(request: Request) -> dict:
    """Encerramento GRACIOSO pedido pelo Electron antes do kill duro (C-11).

    No Windows não há SIGTERM: o `sidecar.kill()` do Electron é um
    `TerminateProcess` que nunca roda o lifespan do FastAPI — o SQLCipher não
    fecha e o `encerrar_runtime()` (que derruba o `llama-server`) não executa.
    Este endpoint dá ao processo pai um caminho limpo: sinaliza o uvicorn a sair
    do loop de forma graciosa, o que dispara o shutdown do lifespan. O Electron
    faz este POST e AGUARDA o `exit` com prazo curto; o `kill()` continua sendo
    o último recurso se o prazo estourar.

    Exige só o token (não o cofre): o encerramento tem de funcionar mesmo com a
    sessão bloqueada. O `uvicorn.Server` é injetado em `app.state.servidor` pelo
    launcher (`sidecar/__main__`); sob `TestClient` ele não existe e o endpoint
    apenas responde `ok` (não há loop para encerrar).
    """
    servidor = getattr(request.app.state, "servidor", None)
    if servidor is not None:
        servidor.should_exit = True
    return {"ok": True}


# --------------------------------------------------- sessão do cofre (T-1603)
# O token (`exigir_token`) autentica o PROCESSO Electron; esta sessão
# autentica o USUÁRIO. Ver a docstring de `sidecar/sessao.py` para o modo de
# transição onboarding→cofre e o racional do auto-lock preguiçoso.
def sessao_dependencia() -> SessaoCofre:
    """Dependência da sessão do cofre (sobrescrita nos testes com tmp_path).

    Mesmo padrão de singleton preguiçoso que o antigo `repositorio()` tinha
    para o `Repositorio`: em produção devolve a sessão única do processo; os
    testes trocam por uma sessão isolada via `app.dependency_overrides`.

    Arma (uma vez) o gancho `ao_bloquear` da sessão do processo: quando o cofre
    bloqueia — manual ou por auto-lock — `_descartar_jobs_ia` esvazia `_JOBS_IA`
    para a PII desanonimizada da análise sênior não sobreviver à janela
    desbloqueada (C-04, REQ-SEC-003).
    """
    sess = sessao_processo()
    if sess.ao_bloquear is None:
        sess.ao_bloquear = _descartar_jobs_ia
    return sess


def exigir_cofre(
    sess: Annotated[SessaoCofre, Depends(sessao_dependencia)],
) -> Repositorio:
    """Gate `423 Locked` de TODO endpoint de negócio, ao lado de `exigir_token`.

    Devolve o repositório correto da sessão corrente: legado em claro na
    janela de onboarding (sem cofre cadastrado) ou o cofre cifrado depois do
    login — os endpoints não assumem mais um repositório global fixo. O
    auto-lock preguiçoso é verificado dentro de `repositorio_ativo`.
    """
    try:
        return sess.repositorio_ativo()
    except SessaoBloqueada as e:
        raise HTTPException(status_code=423, detail="cofre bloqueado") from e


@app.exception_handler(AguardeCofre)
def _tratar_aguarde_cofre(_request: object, exc: AguardeCofre) -> JSONResponse:
    """Anti-brute-force (T-1603): `429` com `aguarde_s` no CORPO (a GUI usa
    para o contador) e `Retry-After` no HEADER (o padrão HTTP). Handler
    global — cobre `/auth/login`, `/auth/recuperar` e `/auth/trocar-senha`
    igual, sem repetir o `try/except` em cada endpoint."""
    return JSONResponse(
        status_code=429,
        content={"detail": str(exc), "aguarde_s": exc.segundos},
        headers={"Retry-After": str(math.ceil(exc.segundos))},
    )


@app.exception_handler(RequestValidationError)
def _tratar_validacao(_request: object, exc: RequestValidationError) -> JSONResponse:
    """Normaliza o `detail` da validação automática do Pydantic (C-01/C-07).

    O handler padrão do FastAPI devolve `detail` como LISTA de objetos
    `{loc, msg, ...}`; o contrato da fronteira (`ErroSidecar.detail` em
    `client.ts`) é `string` — sem este handler, `String(list)` vira o
    ilegível `"[object Object]"` na tela assim que um campo monetário nasce
    com `Field(ge=0)`. Junta `loc` (nome do campo, em pt-BR quando possível)
    + `msg` (mensagem do Pydantic, mantida como vem — traduzir robustamente
    seria frágil) numa única frase por erro."""
    mensagens = []
    for erro in exc.errors():
        # `loc` inclui "body" como primeiro elemento; descartado por não
        # ajudar o usuário a identificar o campo.
        caminho = ".".join(str(parte) for parte in erro["loc"] if parte != "body")
        msg = erro.get("msg", "valor inválido")
        mensagens.append(f"campo '{caminho}': {msg}" if caminho else msg)
    detail = "; ".join(mensagens) or "dados inválidos"
    return JSONResponse(status_code=422, content={"detail": detail})


@app.exception_handler(Exception)
def _tratar_erro_nao_mapeado(_request: object, exc: Exception) -> JSONResponse:
    """Rede de segurança para exceções não previstas (C-06, ADR-0017 §E).

    Sem este handler, um 500 imprevisto vira o `PlainTextResponse` padrão do
    Starlette — texto puro, não JSON — e o `chamarSidecar` do Electron
    (`resp.json()`) quebra ao tentar parsear, perdendo o `status` no
    caminho da rejeição da Promise (regressão ao padrão pré-T-1604). Aqui
    todo 500 sai com corpo JSON `{"detail": string}`, coerente com o
    contrato de `ErroSidecar` em `client.ts`.

    `str(exc)` NUNCA vai no corpo: pode conter caminho de arquivo local ou
    outro dado sensível (REQ-SEC-003). O detalhe completo só sai no log
    local (stderr), via `log.exception` — mesma política do T-1603 para
    exceções não mapeadas.

    Nota: FastAPI/Starlette só chama handlers de `Exception` para exceções
    que ESCAPAM da rota; um `HTTPException` (e o `AguardeCofre`/
    `RequestValidationError` acima, que têm handler próprio) nunca cai
    aqui — os 4xx/423/429 existentes continuam com o corpo que já emitem.
    """
    log.exception("Erro não mapeado no sidecar: %s", exc)
    return JSONResponse(status_code=500, content={"detail": "Erro interno do sidecar."})


@app.get("/auth/status", dependencies=[Depends(exigir_token)])
def auth_status(sess: Annotated[SessaoCofre, Depends(sessao_dependencia)]) -> dict:
    """`{cadastrado, desbloqueado, aguarde_s}` — o front decide a tela."""
    return sess.status()


def _qr_png_base64(dados: str) -> str:
    """QR code do `totp_uri` em PNG (base64), gerado 100% local e sem rede —
    a GUI mostra o segredo em texto como alternativa (T-1604). O backend é o
    `PyPNGImage` (pypng, Python puro) fixado de propósito: `qrcode.make` sem
    factory escolhe o Pillow quando presente, e não queremos depender de um
    binário nativo a mais no empacotamento (T-1703)."""
    imagem = qrcode.make(dados, image_factory=PyPNGImage)
    buffer = io.BytesIO()
    imagem.save(buffer)
    return base64.b64encode(buffer.getvalue()).decode("ascii")


@app.post("/auth/cadastrar", dependencies=[Depends(exigir_token)])
def auth_cadastrar(
    entrada: CadastrarCofreIn,
    sess: Annotated[SessaoCofre, Depends(sessao_dependencia)],
) -> dict:
    """Cria o cofre e migra o banco NA HORA; a sessão continua bloqueada — o
    primeiro `/auth/login` confirma que o autenticador foi configurado de
    verdade (ADR-0016 §D). Os segredos (URI do TOTP + QR + códigos) só saem
    aqui."""
    try:
        resultado = sess.cadastrar(entrada.senha)
    except CofreJaCadastrado as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except SenhaFraca as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except ChaveInvalida as e:
        raise HTTPException(
            status_code=500,
            detail="Não foi possível preparar o cofre (banco corrompido?)."
        ) from e
    return {"totp_uri": resultado.totp_uri,
            "qr_png_base64": _qr_png_base64(resultado.totp_uri),
            "codigos_recuperacao": resultado.codigos_recuperacao}


@app.post("/auth/login", dependencies=[Depends(exigir_token)])
def auth_login(
    entrada: LoginCofreIn,
    sess: Annotated[SessaoCofre, Depends(sessao_dependencia)],
) -> dict:
    """Desbloqueia a sessão com senha (1º fator) + TOTP (2º fator)."""
    try:
        sess.login(entrada.senha, entrada.codigo_totp)
    except (SenhaIncorreta, TotpIncorreto) as e:
        raise HTTPException(status_code=401, detail=str(e)) from e
    except CofreNaoCadastrado as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except ChaveInvalida as e:
        raise HTTPException(
            status_code=500, detail="Não foi possível abrir o cofre (banco corrompido?)."
        ) from e
    return {"ok": True}


@app.post("/auth/bloquear", dependencies=[Depends(exigir_token)])
def auth_bloquear(sess: Annotated[SessaoCofre, Depends(sessao_dependencia)]) -> dict:
    """Bloqueio manual — idempotente (bloquear já bloqueado é no-op)."""
    sess.bloquear()
    return {"ok": True}


@app.post("/auth/recuperar", dependencies=[Depends(exigir_token)])
def auth_recuperar(
    entrada: RecuperarCofreIn,
    sess: Annotated[SessaoCofre, Depends(sessao_dependencia)],
) -> dict:
    """Redefine a senha por um código de recuperação de uso único e desbloqueia
    a sessão — o código É o fator de posse; TOTP não é exigido aqui, por
    design da ADR-0016 §A (perder a senha não perde os dados enquanto restar
    um código)."""
    try:
        sess.recuperar(entrada.codigo, entrada.nova_senha)
    except CodigoRecuperacaoInvalido as e:
        raise HTTPException(status_code=401, detail=str(e)) from e
    except SenhaFraca as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except CofreNaoCadastrado as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except ChaveInvalida as e:
        raise HTTPException(
            status_code=500, detail="Não foi possível abrir o cofre (banco corrompido?)."
        ) from e
    return {"ok": True}


@app.post("/auth/trocar-senha",
         dependencies=[Depends(exigir_token), Depends(exigir_cofre)])
def auth_trocar_senha(
    entrada: TrocarSenhaCofreIn,
    sess: Annotated[SessaoCofre, Depends(sessao_dependencia)],
) -> dict:
    """Troca a senha; exige sessão desbloqueada (`423` via `exigir_cofre`) e
    os 2 fatores atuais — `Cofre.trocar_senha` os confere de novo."""
    try:
        sess.trocar_senha(entrada.senha_atual, entrada.codigo_totp, entrada.nova_senha)
    except SessaoBloqueada as e:  # corrida rara com o auto-lock entre o gate e aqui
        raise HTTPException(status_code=423, detail="cofre bloqueado") from e
    except (SenhaIncorreta, TotpIncorreto) as e:
        raise HTTPException(status_code=401, detail=str(e)) from e
    except SenhaFraca as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"ok": True}


@app.post("/diagnostico", dependencies=[Depends(exigir_token), Depends(exigir_cofre)])
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
# devolve exatamente o que foi salvo (REQ-F-018, ADR-0012). O repositório em
# si vem do gate `exigir_cofre` (T-1603) — não há mais singleton próprio aqui.
CHAVE_PERFIL = "perfil"


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
def estado_carregar(repo: Annotated[Repositorio, Depends(exigir_cofre)]) -> dict:
    """Estado salvo do usuário; `perfil` é None na primeira execução.

    As rubricas vêm junto: a GUI precisa delas para a planilha e para saber
    quais campos do Perfil estão detalhados (somente-leitura).
    """
    return {"perfil": repo.carregar_estado(CHAVE_PERFIL),
            "rubricas": repo.listar_rubricas()}


@app.post("/estado", dependencies=[Depends(exigir_token)])
def estado_salvar(perfil_in: PerfilIn,
                  repo: Annotated[Repositorio, Depends(exigir_cofre)]) -> dict:
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
                       repo: Annotated[Repositorio, Depends(exigir_cofre)]) -> dict:
    """Arquiva a competência: snapshot do perfil vivo + cópia das rubricas.

    Rearquivar a mesma competência substitui o snapshot (ADR-0013).
    """
    _mes_valido_ou_422(entrada.mes)
    repo.arquivar_mes(entrada.mes, _perfil_vivo(repo))
    return {"ok": True, "mes": entrada.mes, "meses": repo.listar_meses()}


@app.get("/historico", dependencies=[Depends(exigir_token)])
def historico_listar(repo: Annotated[Repositorio, Depends(exigir_cofre)]) -> dict:
    return {"meses": repo.listar_meses()}


@app.get("/historico/evolucao", dependencies=[Depends(exigir_token)])
def historico_evolucao(repo: Annotated[Repositorio, Depends(exigir_cofre)]) -> dict:
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
                       repo: Annotated[Repositorio, Depends(exigir_cofre)]) -> dict:
    """Snapshot completo da competência (perfil + rubricas arquivadas)."""
    _mes_valido_ou_422(mes)
    perfil = repo.carregar_mes(mes)
    if perfil is None:
        raise HTTPException(status_code=404, detail="Competência sem snapshot.")
    return {"mes": mes, "perfil": perfil, "rubricas": repo.rubricas_do_mes(mes)}


@app.post("/historico/comparar", dependencies=[Depends(exigir_token)])
def historico_comparar(entrada: CompararMesesIn,
                       repo: Annotated[Repositorio, Depends(exigir_cofre)]) -> dict:
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


# ---------------------------------------------------------- rubricas (T-1103)  # noqa: ERA001 — cabeçalho de seção, não código comentado
# Toda mutação devolve a lista atualizada E o perfil recalculado: a GUI
# hidrata os dois estados numa resposta só, sem janela de inconsistência.
@app.get("/rubricas", dependencies=[Depends(exigir_token)])
def rubricas_listar(repo: Annotated[Repositorio, Depends(exigir_cofre)]) -> dict:
    return {"rubricas": repo.listar_rubricas()}


@app.post("/rubricas", dependencies=[Depends(exigir_token)])
def rubrica_criar(entrada: RubricaIn,
                  repo: Annotated[Repositorio, Depends(exigir_cofre)]) -> dict:
    """Cria um lançamento; a ancoragem é validada contra o modelo do core."""
    try:
        validar_rubrica(entrada.categoria, entrada.campo_pai, entrada.nome)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    repo.criar_rubrica(entrada.categoria, entrada.campo_pai,
                       entrada.nome.strip(), entrada.valor, entrada.ordem)
    return {"rubricas": repo.listar_rubricas(),
            "perfil": _perfil_apos_mutacao(repo)}


@app.post("/rubricas/{rubrica_id}", dependencies=[Depends(exigir_token)])
def rubrica_editar(rubrica_id: int, entrada: RubricaEditIn,
                   repo: Annotated[Repositorio, Depends(exigir_cofre)]) -> dict:
    """Edita nome/valor/ordem. Mover de grupo é remover + criar."""
    if not entrada.nome.strip():
        raise HTTPException(status_code=422,
                            detail="A rubrica precisa de um nome.")
    rubrica = repo.atualizar_rubrica(rubrica_id, entrada.nome.strip(),
                                     entrada.valor, entrada.ordem)
    if rubrica is None:
        raise HTTPException(status_code=404, detail="Rubrica desconhecida.")
    return {"rubricas": repo.listar_rubricas(),
            "perfil": _perfil_apos_mutacao(repo)}


@app.post("/rubricas/{rubrica_id}/remover", dependencies=[Depends(exigir_token)])
def rubrica_remover(rubrica_id: int,
                    repo: Annotated[Repositorio, Depends(exigir_cofre)]) -> dict:
    """Remove o lançamento. O campo-pai fica com a última soma e volta a ser
    editável quando perde a última rubrica (decisão do ADR-0012)."""
    if not repo.remover_rubrica(rubrica_id):
        raise HTTPException(status_code=404, detail="Rubrica desconhecida.")
    return {"rubricas": repo.listar_rubricas(),
            "perfil": _perfil_apos_mutacao(repo)}


# ------------------------------------- importação de CSV (T-1302, ADR-0014)
def contexto_classificacao() -> tuple[ConfigAgente | None, Classificador | None]:
    """Dependência da classificação (sobrescrita nos testes).

    Em produção devolve (None, None): a classificação usa a config real
    (local-only, H2) e o dialeto do provider. Os testes injetam um
    `FakeClassificador` determinístico.
    """
    return None, None


def _resposta_importacao(
    extrato: Extrato,
    cfg: ConfigAgente | None,
    classificador: Classificador | None,
) -> dict:
    """Grupos do `Extrato` classificados pela LLM local → resposta de revisão.

    Fonte única do contrato de importação (CSV e OCR): a LLM SÓ rotula (recebe
    nome normalizado + natureza, sem valores/datas — H1/H2); sem LLM degrada
    para "manual" (P8). Nada é persistido aqui — o `/importar/aplicar` grava.
    """
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


@app.post("/importar/csv", dependencies=[Depends(exigir_token), Depends(exigir_cofre)])
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
    motivos (P8) e todos os grupos voltam sem rótulo. O irmão escaneado é o
    `/importar/ocr` (mora junto da maquinaria de OCR).
    """
    cfg, classificador = ctx
    try:
        dados = base64.b64decode(entrada.csv_base64, validate=True)
    except (binascii.Error, ValueError) as e:
        raise HTTPException(status_code=422,
                            detail="CSV inválido (base64).") from e

    extrato = ler_extrato_csv(decodificar_csv(dados))
    return _resposta_importacao(extrato, cfg, classificador)


@app.post("/importar/aplicar", dependencies=[Depends(exigir_token)])
def importar_aplicar(entrada: AplicarImportacaoIn,
                     repo: Annotated[Repositorio, Depends(exigir_cofre)]) -> dict:
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


@app.post("/estrategias", dependencies=[Depends(exigir_token), Depends(exigir_cofre)])
def estrategias(entrada: EstrategiasIn) -> dict:
    """Compara avalanche vs. bola de neve para o pagamento extra informado."""
    perfil = _para_perfil(entrada.perfil)
    return comparar_estrategias(perfil, entrada.extra)


# ------------------------------------------------------------ análise (T-902)  # noqa: ERA001 — cabeçalho de seção, não código comentado
@app.post("/analise", dependencies=[Depends(exigir_token), Depends(exigir_cofre)])
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


# ------------------------------------------------ coleta preguiçosa de jobs
# TTL dos jobs em memória (análise sênior e download) que chegaram ao estado
# final mas nunca foram lidos no poll — a GUI pode ter fechado, o auto-lock pode
# ter disparado, ou a tela só faz poll do catálogo agregado (nunca do
# `GET /llm/baixar/{job_id}`). Sem isso, cada job terminal abandonado fica preso
# pela vida do processo: no caso da IA, com PII DESANONIMIZADA em claro (C-04);
# no do download, com a entrada e o `threading.Event` (C-08). A cada acesso aos
# dicionários varremos as entradas terminais mais velhas que o TTL, sem thread
# de fundo. 10 min cobrem com folga qualquer poll legítimo da tela.
_TTL_JOBS_S = 600.0


def _relogio_jobs() -> float:
    """Relógio monotônico da coleta de jobs. Função nomeada de propósito: os
    testes a substituem via monkeypatch para avançar o tempo sem `sleep` real."""
    return time.monotonic()


def _varrer_jobs_terminais(jobs: dict[str, dict], termino: dict[str, float]) -> list[str]:
    """Remove os jobs cujo instante de término passou do TTL e devolve os ids
    varridos (o chamador limpa estruturas satélite, p.ex. o `Event` de
    cancelamento do download). O chamador deve segurar o lock do dicionário."""
    agora = _relogio_jobs()
    expirados = [jid for jid, t in termino.items() if agora - t > _TTL_JOBS_S]
    for jid in expirados:
        jobs.pop(jid, None)
        termino.pop(jid, None)
    return expirados


# Jobs em memória: a chamada ao LLM local leva de segundos a minutos, então a
# tela dispara o job e faz poll — o sidecar continua respondendo às demais
# rotas. O resultado é descartado na primeira leitura de estado final; o TTL
# acima cobre os jobs terminais que essa leitura nunca alcança. `_JOBS_IA_FIM`
# guarda, à parte do dict de estado, o instante em que cada job virou terminal
# (não vaza no JSON do contrato, que é `{status, secao, erro}`).
_JOBS_IA: dict[str, dict] = {}
_JOBS_IA_LOCK = threading.Lock()
_JOBS_IA_FIM: dict[str, float] = {}


def _descartar_jobs_ia() -> None:
    """Esvazia `_JOBS_IA` — armado como `ao_bloquear` da sessão do cofre, roda
    quando ela bloqueia (manual OU auto-lock). A seção da análise sênior guarda
    credores DESANONIMIZADOS (REQ-SEC-003): a PII não pode sobreviver à janela
    desbloqueada, então some junto com a DEK (C-04)."""
    with _JOBS_IA_LOCK:
        _JOBS_IA.clear()
        _JOBS_IA_FIM.clear()


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
        # C-34: nunca engolir em silêncio. `perfil` carrega dados financeiros
        # do usuário (credores, valores) — `str(e)` pode ecoar fragmentos dele
        # se a exceção vier de validação/serialização, então o log fica só com
        # o tipo (espelha `_rodar_job_download`, que loga `str(e)` porque ali a
        # exceção só carrega dados de catálogo de modelo, não PII do perfil).
        log.warning("Análise IA %s falhou: %s", job_id, type(e).__name__)
        estado = {"status": "erro", "secao": None,
                  "erro": f"{type(e).__name__}: {e}"}
    with _JOBS_IA_LOCK:
        # Só grava se a entrada AINDA existe: se o cofre bloqueou no meio do
        # job, `_descartar_jobs_ia` já a removeu — regravar aqui ressuscitaria
        # a seção DESANONIMIZADA depois do bloqueio (C-04). O poll seguinte
        # recebe 404 e a tela trata como job encerrado.
        if job_id in _JOBS_IA:
            _JOBS_IA[job_id] = estado
            _JOBS_IA_FIM[job_id] = _relogio_jobs()  # terminal: conta o TTL


@app.post("/analise/ia", dependencies=[Depends(exigir_token), Depends(exigir_cofre)])
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
        _varrer_jobs_terminais(_JOBS_IA, _JOBS_IA_FIM)  # coleta preguiçosa
        _JOBS_IA[job_id] = {"status": "rodando", "secao": None, "erro": ""}
    threading.Thread(
        target=_rodar_job_ia, args=(job_id, perfil, entrada.extra, cfg, provider),
        daemon=True,
    ).start()
    return {"job_id": job_id}


@app.get("/analise/ia/{job_id}", dependencies=[Depends(exigir_token), Depends(exigir_cofre)])
def analise_ia_status(job_id: str) -> dict:
    """Estado do job: rodando | pronto (com a seção) | erro. 404 se desconhecido."""
    with _JOBS_IA_LOCK:
        _varrer_jobs_terminais(_JOBS_IA, _JOBS_IA_FIM)  # coleta preguiçosa
        job = _JOBS_IA.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job desconhecido.")
        if job["status"] != "rodando":
            del _JOBS_IA[job_id]  # leitura final: libera a memória do job
            _JOBS_IA_FIM.pop(job_id, None)
    return {"job_id": job_id, **job}


# ------------------------------------------------------- exportações (T-902)  # noqa: ERA001 — cabeçalho de seção, não código comentado
@app.post("/exportar/planilha", dependencies=[Depends(exigir_token)])
def exportar_planilha(entrada: ExportarPlanilhaIn,
                      repo: Annotated[Repositorio, Depends(exigir_cofre)]) -> dict:
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


@app.post("/exportar/relatorio", dependencies=[Depends(exigir_token), Depends(exigir_cofre)])
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


@app.post("/carta/previa", dependencies=[Depends(exigir_token), Depends(exigir_cofre)])
def carta_previa(entrada: CartaIn) -> dict:
    """Pré-visualização ao vivo da carta (REQ-F-016).

    O texto vem inteiro do `core`/`outputs` (fonte única): a tela só renderiza
    a mesma estrutura que o `.docx` usa — nada é redigido no front.
    """
    return montar_carta(_para_divida(entrada.divida), tipo=entrada.tipo,
                        dados=_dados_carta(entrada),
                        nome_usuario=entrada.nome_usuario,
                        cpf=entrada.cpf, contrato=entrada.contrato)


@app.post("/exportar/carta", dependencies=[Depends(exigir_token), Depends(exigir_cofre)])
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


def contexto_ocr() -> Motor | None:
    """Dependência do motor de OCR (sobrescrita nos testes).

    Produção devolve `None`: o motor real é construído **sob demanda** por
    `_motor_ocr_singleton` (só quando há um scan de verdade — carregar os modelos
    PP-OCRv6 é caro), nunca no DI. Os testes injetam um motor falso.
    """
    return None


_motor_ocr: Motor | None = None
_motor_ocr_tentado = False
_LOCK_MOTOR_OCR = threading.Lock()


def _motor_ocr_singleton() -> Motor | None:
    """Singleton preguiçoso do RapidOCR: cria uma vez, reusa entre requisições.
    Devolve `None` se o motor não puder ser criado (o endpoint degrada, P8).

    Mesmo padrão de `_LOCK_SINGLETON` em `runtime_llm.py` (C-13): a checagem e
    a construção do motor SEMPRE acontecem dentro do lock. Sem ele, duas
    requisições concorrentes na primeira chamada poderiam tanto construir
    DOIS motores RapidOCR quanto (pior) uma delas devolver `None` prematuro —
    a flag `_motor_ocr_tentado` marcada pela primeira thread antes de
    terminar de construir faria a segunda pular a construção e ler
    `_motor_ocr` ainda vazio. Carregar os modelos PP-OCRv6 é raro (uma vez por
    processo), então pagar o lock em toda chamada é custo desprezível.
    """
    global _motor_ocr, _motor_ocr_tentado  # noqa: PLW0603 — singleton lazy sob lock
    with _LOCK_MOTOR_OCR:
        if not _motor_ocr_tentado:
            _motor_ocr_tentado = True
            try:
                _motor_ocr = obter_motor()
            except OCRIndisponivel as e:
                log.warning("Motor de OCR indisponível: %s", e)
                _motor_ocr = None
    return _motor_ocr


@app.post("/importar/ocr", dependencies=[Depends(exigir_token), Depends(exigir_cofre)])
def importar_ocr(
    entrada: ImportarOcrIn,
    ctx: tuple[ConfigAgente | None, Classificador | None] = Depends(
        contexto_classificacao),
    motor_ocr: Annotated[Motor | None, Depends(contexto_ocr)] = None,
) -> dict:
    """Comprovante/extrato ESCANEADO → grupos classificados PARA REVISÃO (REQ-F-026).

    Fica aqui, junto da maquinaria de OCR que compartilha com `/contrato/extrair`
    (o singleton preguiçoso `contexto_ocr`); o irmão determinístico é o
    `/importar/csv`. OCRiza LOCALMENTE (H2/H7), reconstrói os lançamentos pelo
    mesmo `core/extrato` (`ler_extrato_ocr`) e reusa a classificação e o
    `/importar/aplicar` do v2.6 — só a ENTRADA muda (ADR-0015 §E). Sem motor de
    OCR, degrada (P8): `modo` 'vazio' com o motivo. Nunca 500.
    """
    cfg, classificador = ctx
    try:
        dados = base64.b64decode(entrada.arquivo_base64, validate=True)
    except (binascii.Error, ValueError) as e:
        raise HTTPException(status_code=422,
                            detail="Arquivo inválido (base64).") from e

    def _degradado(motivo: str) -> dict:
        return {"modo": "vazio", "grupos": [], "competencia_sugerida": None,
                "avisos": [AVISO_OCR_INDISPONIVEL], "descartes": [],
                "motivos": [motivo], "llm": _diag_llm(cfg), "ocr": False}

    motor = motor_ocr if motor_ocr is not None else _motor_ocr_singleton()
    if motor is None:  # sem motor de OCR ⇒ P8
        return _degradado("OCR_INDISPONIVEL")
    try:
        texto = ocr_documento(dados, entrada.nome, motor=motor).texto
    except Exception as e:  # noqa: BLE001 — documento ilegível ⇒ P8, nunca 500
        # C-22: nome do arquivo é PII do usuário — não vai ao log, só a extensão.
        log.warning("Falha no OCR (arquivo %s): %s: %s",
                    Path(entrada.nome).suffix, type(e).__name__, e)
        return _degradado(f"OCR_FALHOU:{type(e).__name__}")

    resposta = _resposta_importacao(ler_extrato_ocr(texto), cfg, classificador)
    resposta["ocr"] = True
    return resposta


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


# C-19: `preparar_contexto` (agent/ingestao.py) não faz mais retrieval — o ramo
# RAG por embeddings foi removido no portão M19 (código quase-morto, sem teste
# offline). O gate abaixo já não é "quem tem embeddings": Ollama/local ganham o
# teto mais folgado de `LIMITE_DIRETO_CHARS` (6000, de `preparar_contexto`);
# os demais (OpenAI-compat local — LM Studio/llama.cpp) ficam no teto mais
# curto de `LIMITE_EXTRACAO_LLM` (4000) — CPU paga o custo no PROCESSAMENTO DO
# PROMPT, então um contexto mais curto acelera a extração sem perder os campos
# (ficam nas primeiras páginas). Os dois tetos continuam distintos DE PROPÓSITO:
# colapsá-los num só mudaria o valor efetivo já aplicado hoje num dos dois
# caminhos — mantidos separados por decisão consciente (C-19/C-26).
_PROVIDERS_COM_EMBEDDINGS = {"local", "ollama"}

LIMITE_EXTRACAO_LLM = 4000


def _contexto_seguro(texto: str, cfg: ConfigAgente | None) -> str:
    """Prepara o contexto p/ a extração, truncando por provider (C-19).

    Documento curto vai inteiro nos dois caminhos. Documento longo: Ollama/local
    usa o teto de `preparar_contexto` (`LIMITE_DIRETO_CHARS`, 6000); os demais
    truncam em `LIMITE_EXTRACAO_LLM` (4000). Truncagem pura, sem I/O de rede —
    não há mais "melhor esforço" a proteger com try/except.
    """
    conf = cfg or carregar_config()
    if conf.provider.strip().lower() not in _PROVIDERS_COM_EMBEDDINGS:
        return texto[:LIMITE_EXTRACAO_LLM]
    return preparar_contexto(texto, conf)


def _diag_llm(cfg: ConfigAgente | None) -> dict:
    """Alvo efetivo da LLM (sem segredos) — para diagnosticar a queda p/ clássico."""
    conf = cfg or carregar_config()
    return {"provider": conf.provider, "base_url": conf.base_url,
            "model": conf.model, "endpoint_local": conf.endpoint_local}


@app.post("/contrato/extrair", dependencies=[Depends(exigir_token), Depends(exigir_cofre)])
def contrato_extrair(
    entrada: ContratoIn,
    ctx: tuple[ConfigAgente | None, Extrator | None] = Depends(contexto_extracao),
    motor_ocr: Annotated[Motor | None, Depends(contexto_ocr)] = None,
) -> dict:
    """Extrai os campos de um contrato LOCALMENTE, com citação (REQ-F-014/024).

    O documento (com PII) é decodificado em memória e nunca sai da máquina (H2).
    PDF com texto: lê direto. **PDF escaneado ou imagem**: OCR local (RapidOCR +
    PP-OCRv6, ADR-0015) — se o motor faltar, degrada para preenchimento manual
    (P8). Depois tenta a extração assistida por IA local — quote-check tolerante
    ao ruído de glifo do OCR + checagem cruzada + `interrupt` para confirmação
    humana; senão, extração clássica por regex. O texto cru nunca vira fato: só
    campos tipados e confirmados alimentam o perfil (REQ-GRD-005).
    """
    cfg, extrator = ctx
    llm = _diag_llm(cfg)
    try:
        dados = base64.b64decode(entrada.pdf_base64, validate=True)
    except (binascii.Error, ValueError) as e:
        raise HTTPException(status_code=422, detail="Documento invalido (base64).") from e

    # Fonte do documento (ADR-0015, detecção determinística): imagem pela
    # extensão; PDF sem camada de texto (< 40 chars) = escaneado. Ambos ⇒ OCR.
    eh_imagem = fonte_por_extensao(entrada.nome) is FonteDocumento.IMAGEM
    texto_plano = "" if eh_imagem else extrair_texto_pdf_bytes(dados)
    ocr_usado = False
    if eh_imagem or len(texto_plano.strip()) < 40:
        motor = motor_ocr if motor_ocr is not None else _motor_ocr_singleton()
        if motor is None:  # documento escaneado, mas sem motor de OCR ⇒ P8
            return {"modo": "vazio", "thread_id": None, "campos": [],
                    "descartados": [], "inconsistencias": [],
                    "motivos": ["OCR_INDISPONIVEL"], "aviso": AVISO_OCR_INDISPONIVEL,
                    "ocr": False, "llm": llm}
        try:
            texto_plano = ocr_documento(dados, entrada.nome, motor=motor).texto
        except Exception as e:  # noqa: BLE001 — documento ilegível ⇒ P8, nunca 500
            # C-22: nome do arquivo é PII do usuário — não vai ao log, só a extensão.
            log.warning("Falha no OCR (arquivo %s): %s: %s",
                        Path(entrada.nome).suffix, type(e).__name__, e)
            return {"modo": "vazio", "thread_id": None, "campos": [],
                    "descartados": [], "inconsistencias": [],
                    "motivos": [f"OCR_FALHOU:{type(e).__name__}"],
                    "aviso": AVISO_OCR_INDISPONIVEL, "ocr": False, "llm": llm}
        ocr_usado = True

    if len(texto_plano.strip()) < 40:  # nem OCR achou texto legível
        return {"modo": "vazio", "thread_id": None, "campos": [],
                "descartados": [], "inconsistencias": [], "motivos": [],
                "aviso": AVISO_PDF_SEM_TEXTO, "ocr": ocr_usado, "llm": llm}

    # Texto plano (não Markdown) para a LLM: prompt mais enxuto e citações limpas
    # (sem `#`/`**`), decisivo em modelos locais lentos. O texto CRU vira o
    # `documento` do quote-check e alimenta o regex clássico; a pré-marcação por
    # tipo (REQ-F-025) é aplicada só no PROMPT, dentro de `montar_prompt_extracao`
    # (não pode entrar no quote-check — a tag partiria a citação). Ver ADR-0010/0015.
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
                "aviso": "", "ocr": ocr_usado, "llm": llm}

    # IA local indisponível ⇒ extração clássica (regex, sem citação verificável).
    # `motivos` diz POR QUE a IA não rodou (ex.: ERRO_PROVIDER:URLError = servidor
    # local fora do ar/porta errada; REQ-LLM-002:SCHEMA = structured output falhou).
    form = campos_para_formulario(_classico_para_campos(parsear_campos(texto_plano)))
    return {"modo": "classico", "thread_id": None, "campos": _form_para_lista(form),
            "descartados": [], "inconsistencias": [],
            "motivos": estado.get("motivos") or [], "aviso": "", "ocr": ocr_usado, "llm": llm}


@app.post("/contrato/confirmar", dependencies=[Depends(exigir_token), Depends(exigir_cofre)])
def contrato_confirmar(
    entrada: ConfirmarContratoIn,
    ctx: tuple[ConfigAgente | None, Extrator | None] = Depends(contexto_extracao),
) -> dict:
    """Retoma o grafo pausado com os campos confirmados (interrupt→resume)."""
    cfg, extrator = ctx
    estado = confirmar_extracao(entrada.thread_id, entrada.confirmacao,
                                cfg=cfg, extrator=extrator)
    return {"ok": True, "confirmada": estado.get("confirmada")}


# ------------------------------- gestor de modelos GGUF (T-1702, ADR-0016 §F)
# Atrás de `exigir_cofre` como todo o resto de negócio: a GUI só chega na tela
# de Configuração da IA já logada, então não há motivo para abrir exceção
# nenhuma aqui (nem o `/llm/status`, que não expõe PII, mas mantém a regra
# simples — "tudo depois do login" — em vez de uma exceção caso a caso).
def _status_llm() -> dict:
    """Estado consolidado do runtime embarcado: é o que a tela renderiza.

    Import tardio de `.runtime_llm` (mesmo racional do resto do arquivo).
    `runtime_embarcado().ativo()` só CONSULTA o processo — nunca sobe o
    `llama-server` (isso só acontece sob demanda, na 1ª análise/extração
    real); então este endpoint nunca paga o custo de carregar um modelo.
    """
    from .runtime_llm import resolver_binario_llama, resolver_modelo, runtime_embarcado

    servidor_usuario = "HF_BASE_URL" in os.environ
    binario = resolver_binario_llama()
    modelo = resolver_modelo()

    motivo: str | None = None
    if not servidor_usuario:
        if binario is None:
            motivo = "BINARIO_AUSENTE"
        elif modelo is None:
            motivo = "MODELO_AUSENTE"

    return {
        "servidor_usuario": servidor_usuario,
        "base_url": os.environ.get("HF_BASE_URL", "") if servidor_usuario else "",
        "binario_presente": binario is not None,
        "modelo_ativo": str(modelo) if modelo else None,
        "runtime_ativo": (not servidor_usuario) and runtime_embarcado().ativo(),
        "motivo_indisponivel": motivo,
    }


@app.get("/llm/status", dependencies=[Depends(exigir_token), Depends(exigir_cofre)])
def llm_status() -> dict:
    return _status_llm()


@app.get("/llm/catalogo", dependencies=[Depends(exigir_token), Depends(exigir_cofre)])
def llm_catalogo() -> dict:
    """Catálogo curado + estado de cada item (baixado/baixando/ausente).

    "baixando" só é conhecido pelos jobs em memória deste processo — o estado
    em disco (`listar_catalogo_com_estado`) não sabe de downloads em curso.
    """
    from .gestor_modelos import listar_catalogo_com_estado

    itens = listar_catalogo_com_estado()
    with _JOBS_DOWNLOAD_LOCK:
        _varrer_jobs_download_sem_lock()  # coleta preguiçosa dos jobs terminais
        em_andamento = {j["catalogo_id"]: j for j in _JOBS_DOWNLOAD.values()
                        if j["status"] == "baixando"}
    for item in itens:
        job = em_andamento.get(item["id"])
        if job is not None:
            item["estado"] = "baixando"
            item["job_id"] = job["job_id"]
            item["bytes_baixados"] = job["bytes_baixados"]
            item["bytes_total"] = job["bytes_total"]
    return {"catalogo": itens}


# Jobs de download em memória — mesmo padrão do job da análise sênior
# (`_JOBS_IA`, acima): o download de um `.gguf` de ~1-2 GB leva minutos, então
# a tela dispara e faz poll. `_CANCELAMENTOS_DOWNLOAD` guarda um `Event` por
# job — `baixar_modelo` checa `evento.is_set` a cada bloco (cancelamento
# cooperativo, sem matar a thread à força).
_JOBS_DOWNLOAD: dict[str, dict] = {}
_JOBS_DOWNLOAD_LOCK = threading.Lock()
_CANCELAMENTOS_DOWNLOAD: dict[str, threading.Event] = {}
# Instante em que cada job de download virou terminal — mesmo papel de
# `_JOBS_IA_FIM` (à parte do dict de estado, para o TTL não vazar no JSON).
_JOBS_DOWNLOAD_FIM: dict[str, float] = {}


def _varrer_jobs_download_sem_lock() -> None:
    """Aplica o TTL aos jobs de download terminais (C-08). O `Event` de
    cancelamento correspondente sai junto — já costuma ter sido removido ao fim
    do job, mas garantimos aqui para quem nunca chega ao poll final. O chamador
    deve segurar `_JOBS_DOWNLOAD_LOCK`."""
    for jid in _varrer_jobs_terminais(_JOBS_DOWNLOAD, _JOBS_DOWNLOAD_FIM):
        _CANCELAMENTOS_DOWNLOAD.pop(jid, None)


def _rodar_job_download(job_id: str, catalogo_id: str) -> None:
    from .gestor_modelos import (
        CatalogoIdDesconhecido,
        ModeloDownloadCancelado,
        ModeloDownloadFalhou,
        ModeloHashInvalido,
        baixar_modelo,
        item_do_catalogo,
    )

    evento = _CANCELAMENTOS_DOWNLOAD[job_id]

    def progresso(baixados: int, total: int) -> None:
        with _JOBS_DOWNLOAD_LOCK:
            job = _JOBS_DOWNLOAD.get(job_id)
            if job is not None:
                job["bytes_baixados"], job["bytes_total"] = baixados, total

    try:
        item = item_do_catalogo(catalogo_id)
        baixar_modelo(item, cancelado=evento.is_set, progresso=progresso)
        estado = {"status": "pronto", "erro": ""}
    except ModeloDownloadCancelado:
        estado = {"status": "cancelado", "erro": ""}
    except (ModeloDownloadFalhou, ModeloHashInvalido, CatalogoIdDesconhecido) as e:
        estado = {"status": "erro", "erro": f"{type(e).__name__}: {e}"}
    except Exception as e:  # noqa: BLE001 — a thread nunca deve morrer silenciosa
        log.warning("Download de modelo %r falhou de forma inesperada: %s", catalogo_id, e)
        estado = {"status": "erro", "erro": f"{type(e).__name__}: {e}"}
    with _JOBS_DOWNLOAD_LOCK:
        job = _JOBS_DOWNLOAD.get(job_id)
        if job is not None:
            job.update(estado)
            _JOBS_DOWNLOAD_FIM[job_id] = _relogio_jobs()  # terminal: conta o TTL
    _CANCELAMENTOS_DOWNLOAD.pop(job_id, None)


@app.post("/llm/baixar", dependencies=[Depends(exigir_token), Depends(exigir_cofre)])
def llm_baixar(entrada: BaixarModeloIn) -> dict:
    """Dispara o download (job async) de um item do catálogo — única exceção
    de rede do app (REQ-NF-007), só por este clique explícito do usuário."""
    from .gestor_modelos import CatalogoIdDesconhecido, item_do_catalogo

    try:
        item_do_catalogo(entrada.catalogo_id)  # 404 cedo se o id não existir
    except CatalogoIdDesconhecido as e:
        raise HTTPException(status_code=404, detail=str(e)) from e

    job_id = uuid4().hex
    evento = threading.Event()
    with _JOBS_DOWNLOAD_LOCK:
        _varrer_jobs_download_sem_lock()  # coleta preguiçosa dos jobs terminais
        # Idempotente por modelo: um segundo POST para o mesmo `catalogo_id`
        # com job em curso devolve o job existente em vez de abrir outro —
        # dois jobs concorrentes escreveriam no MESMO `.parcial` e
        # corromperiam o download (a GUI desabilita o botão, mas o contrato
        # não pode depender disso).
        for job in _JOBS_DOWNLOAD.values():
            if (job["catalogo_id"] == entrada.catalogo_id
                    and job["status"] == "baixando"):
                return {"job_id": job["job_id"]}
        _JOBS_DOWNLOAD[job_id] = {
            "job_id": job_id, "catalogo_id": entrada.catalogo_id,
            "status": "baixando", "bytes_baixados": 0, "bytes_total": 0, "erro": "",
        }
        _CANCELAMENTOS_DOWNLOAD[job_id] = evento
    threading.Thread(target=_rodar_job_download, args=(job_id, entrada.catalogo_id),
                     daemon=True).start()
    return {"job_id": job_id}


@app.get("/llm/baixar/{job_id}", dependencies=[Depends(exigir_token), Depends(exigir_cofre)])
def llm_baixar_status(job_id: str) -> dict:
    """Progresso do job: baixando (com bytes) | pronto | erro | cancelado."""
    with _JOBS_DOWNLOAD_LOCK:
        _varrer_jobs_download_sem_lock()  # coleta preguiçosa dos jobs terminais
        job = _JOBS_DOWNLOAD.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job de download desconhecido.")
        if job["status"] == "baixando":
            return dict(job)
        resultado = dict(job)
        del _JOBS_DOWNLOAD[job_id]  # leitura final: libera a memória do job
        _JOBS_DOWNLOAD_FIM.pop(job_id, None)
    return resultado


@app.post("/llm/baixar/{job_id}/cancelar",
         dependencies=[Depends(exigir_token), Depends(exigir_cofre)])
def llm_baixar_cancelar(job_id: str) -> dict:
    """Pede o cancelamento cooperativo; o `.parcial` fica no disco p/ retomar."""
    evento = _CANCELAMENTOS_DOWNLOAD.get(job_id)
    if evento is None:
        raise HTTPException(status_code=404, detail="Job de download desconhecido.")
    evento.set()
    return {"ok": True}


@app.post("/llm/modelo", dependencies=[Depends(exigir_token), Depends(exigir_cofre)])
def llm_definir_modelo(entrada: DefinirModeloIn) -> dict:
    """Define o modelo ativo (do catálogo baixado OU um `.gguf` local) e
    encerra o runtime corrente — a próxima chamada sobe já com o modelo novo.
    """
    from .gestor_modelos import (
        CatalogoIdDesconhecido,
        ModeloLocalInvalido,
        caminho_final,
        definir_modelo_ativo,
        item_do_catalogo,
    )

    if bool(entrada.catalogo_id) == bool(entrada.caminho):
        raise HTTPException(
            status_code=422, detail="Informe catalogo_id OU caminho (exatamente um).")
    try:
        caminho: str | Path
        if entrada.catalogo_id:
            caminho = caminho_final(item_do_catalogo(entrada.catalogo_id))
        else:
            assert entrada.caminho is not None  # garantido pelo XOR acima
            caminho = entrada.caminho
        modelo = definir_modelo_ativo(caminho)
    except CatalogoIdDesconhecido as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ModeloLocalInvalido as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return {"ok": True, "modelo_ativo": str(modelo)}
