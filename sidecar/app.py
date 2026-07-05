"""
App FastAPI do sidecar (ADR-0009).

Expõe o núcleo determinístico em `127.0.0.1` para o front Electron/React. Cada
endpoint apenas monta os objetos do `core`, chama a função determinística e
serializa o resultado. A regra de negócio permanece 100% no `core` (REQ-NF-005).
"""
from __future__ import annotations

from fastapi import Depends, FastAPI

from core.diagnostico import resumo_diagnostico
from core.models import (
    ComposicaoRenda,
    DespesasFixas,
    DespesasVariaveis,
    Divida,
    PerfilFinanceiro,
)

from .schemas import DividaIn, PerfilIn
from .security import exigir_token

app = FastAPI(title="Helper Financeiro — sidecar", version="2.3.0")

# Chaves do resumo que carregam objetos `Divida` (precisam de serialização).
_CHAVES_OBJETO = ("divida_mais_cara", "ranking")


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
    resposta["meses_reserva"] = perfil.meses_reserva
    return resposta
