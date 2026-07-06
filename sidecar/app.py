"""
App FastAPI do sidecar (ADR-0009).

Expõe o núcleo determinístico em `127.0.0.1` para o front Electron/React. Cada
endpoint apenas monta os objetos do `core`, chama a função determinística e
serializa o resultado. A regra de negócio permanece 100% no `core` (REQ-NF-005).
"""
from __future__ import annotations

import base64
import binascii

from fastapi import Depends, FastAPI, HTTPException

from agent.config import ConfigAgente, carregar_config
from agent.exibicao import ROTULOS_EXTRACAO, campos_para_formulario
from agent.extracao import Extrator, confirmar_extracao, iniciar_extracao
from agent.ingestao import LIMITE_DIRETO_CHARS, preparar_contexto
from core.diagnostico import resumo_diagnostico
from core.estrategias import comparar_estrategias
from core.extrator_pdf import (
    extrair_markdown_pdf_bytes,
    extrair_texto_pdf_bytes,
    parsear_campos,
)
from core.models import (
    ComposicaoRenda,
    DespesasFixas,
    DespesasVariaveis,
    Divida,
    PerfilFinanceiro,
)

from .schemas import ConfirmarContratoIn, ContratoIn, DividaIn, EstrategiasIn, PerfilIn
from .security import exigir_token

app = FastAPI(title="Helper Financeiro — sidecar", version="2.3.0")

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


@app.post("/estrategias", dependencies=[Depends(exigir_token)])
def estrategias(entrada: EstrategiasIn) -> dict:
    """Compara avalanche vs. bola de neve para o pagamento extra informado."""
    perfil = _para_perfil(entrada.perfil)
    return comparar_estrategias(perfil, entrada.extra)


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


def _contexto_seguro(texto: str, cfg: ConfigAgente | None) -> str:
    """Prepara o contexto p/ a extração: retrieval no Ollama; truncagem no resto.

    Documento curto vai inteiro (o `preparar_contexto` já decide isso). Documento
    longo: só o Ollama faz retrieval por embeddings; para OpenAI-compat local,
    trunca em `LIMITE_DIRETO_CHARS` — determinístico, sem `/api/embed` e com um
    prompt enxuto (crucial em modelos locais lentos).
    """
    conf = cfg or carregar_config()
    if conf.provider.strip().lower() not in _PROVIDERS_COM_EMBEDDINGS:
        return texto[:LIMITE_DIRETO_CHARS]
    try:
        return preparar_contexto(texto, conf)
    except Exception:  # noqa: BLE001 — sem embeddings ⇒ melhor esforço (texto direto)
        return texto[:LIMITE_DIRETO_CHARS]


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

    # Markdown (tabelas preservadas) para a LLM; texto plano para o regex.
    markdown = extrair_markdown_pdf_bytes(dados) or texto_plano
    contexto = _contexto_seguro(markdown, cfg)
    _tid, estado = iniciar_extracao(contexto, cfg=cfg, extrator=extrator)
    if "__interrupt__" in estado:  # o grafo pausou para a confirmação humana
        payload = estado["__interrupt__"][0].value
        form = campos_para_formulario(payload["campos"])
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
