"""
Rubricas do orçamento (ADR-0012, REQ-F-017).

Uma rubrica é um lançamento nomeado pelo usuário DENTRO de um campo do
orçamento — ex.: "Conta de luz — R$ 180" dentro de `contas_casa`. A regra do
roll-up é por construção: **campo com rubricas vale a soma das rubricas**
(e fica somente-leitura na GUI); campo sem rubricas continua editável direto.

Este módulo é a única fonte da aritmética e da validação (REQ-NF-005): o
sidecar aplica as somas ao perfil salvo a cada mutação de rubrica, e os
demais endpoints seguem recebendo o perfil simples, já consistente.
"""
from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, fields

from .models import ComposicaoRenda, DespesasFixas, DespesasVariaveis

# Campos que aceitam rubricas, por seção do Perfil (ADR-0012: reserva/FGTS
# ficam de fora — são saldos, não fluxos). Derivado dos dataclasses do
# ADR-0008 para nunca divergir do modelo.
CAMPOS_POR_CATEGORIA: dict[str, tuple[str, ...]] = {
    "renda": tuple(f.name for f in fields(ComposicaoRenda)),
    "fixas": tuple(f.name for f in fields(DespesasFixas)),
    "variaveis": tuple(f.name for f in fields(DespesasVariaveis)),
}

# Rótulos pt-BR canônicos (exports e telas; `gui_web/src/lib/orcamento.ts`
# espelha estes textos).
ROTULO_CATEGORIA: dict[str, str] = {
    "renda": "Renda líquida mensal",
    "fixas": "Despesas fixas",
    "variaveis": "Despesas variáveis",
}

ROTULO_CAMPO: dict[str, dict[str, str]] = {
    "renda": {
        "salario_liquido": "Salário/benefício líquido",
        "renda_extra": "Renda extra/autônoma",
        "outras_rendas": "Outras rendas",
    },
    "fixas": {
        "moradia": "Moradia",
        "contas_casa": "Contas da casa",
        "transporte": "Transporte",
        "saude": "Saúde",
        "educacao": "Educação",
        "assinaturas": "Assinaturas/academia",
        "outras_fixas": "Outras fixas",
    },
    "variaveis": {
        "mercado": "Mercado",
        "lazer": "Lazer/delivery",
        "vestuario": "Vestuário/cuidados",
        "imprevistos": "Imprevistos",
        "outras_variaveis": "Outras variáveis",
    },
}


@dataclass(frozen=True)
class Rubrica:
    """Lançamento individual de um campo do orçamento."""

    categoria: str   # 'renda' | 'fixas' | 'variaveis'
    campo_pai: str   # ex.: 'contas_casa'
    nome: str        # ex.: 'Conta de luz'
    valor: float = 0.0
    ordem: int = 0
    id: int | None = None  # atribuído pelo banco; None antes de persistir


def validar_rubrica(categoria: str, campo_pai: str, nome: str) -> None:
    """Valida a ancoragem da rubrica no orçamento; levanta ValueError.

    A validação é estrutural (categoria/campo existem no modelo e o nome não é
    vazio) — o VALOR é livre, como nos campos diretos do Perfil.
    """
    campos = CAMPOS_POR_CATEGORIA.get(categoria)
    if campos is None:
        validas = ", ".join(CAMPOS_POR_CATEGORIA)
        raise ValueError(f"Categoria desconhecida: {categoria!r} (válidas: {validas}).")
    if campo_pai not in campos:
        raise ValueError(
            f"Campo desconhecido em {categoria!r}: {campo_pai!r} "
            f"(válidos: {', '.join(campos)})."
        )
    if not nome.strip():
        raise ValueError("A rubrica precisa de um nome.")


def somas_por_campo(rubricas: Iterable[Rubrica]) -> dict[str, dict[str, float]]:
    """Soma das rubricas por campo — SÓ os campos que têm rubricas.

    Ex.: {'fixas': {'contas_casa': 480.0}}. Campo ausente do resultado não é
    tocado no perfil (continua com o valor digitado direto). Arredonda a 2
    casas, como todo valor monetário do core.
    """
    somas: dict[str, dict[str, float]] = {}
    for r in rubricas:
        validar_rubrica(r.categoria, r.campo_pai, r.nome)
        secao = somas.setdefault(r.categoria, {})
        secao[r.campo_pai] = secao.get(r.campo_pai, 0.0) + r.valor
    return {
        categoria: {campo: round(total, 2) for campo, total in secao.items()}
        for categoria, secao in somas.items()
    }


# --- Histórico mensal (ADR-0013, REQ-F-019) --------------------------------

_RE_MES = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def validar_mes(mes: str) -> None:
    """Competência no formato 'AAAA-MM' (ex.: '2026-07'); ValueError se não."""
    if not _RE_MES.match(mes):
        raise ValueError(f"Competência inválida: {mes!r} (use 'AAAA-MM').")


def _variacao(antes: float, depois: float) -> tuple[float, float | None]:
    """Delta e variação fracionária; pct é None quando não havia base (0)."""
    delta = round(depois - antes, 2)
    pct = round(delta / abs(antes), 4) if antes else None
    return delta, pct


def comparar_orcamentos(antes: dict, depois: dict) -> dict:
    """Compara dois perfis (dicts do contrato) campo a campo e por seção.

    "Seu mercado subiu 12%": para cada campo do orçamento, o valor anterior,
    o atual, o delta e a variação fracionária (None quando o anterior é 0 —
    sem divisão por zero). Campos zerados nos DOIS perfis ficam de fora
    (ruído). Funciona igual com campos detalhados ou diretos: o valor do
    campo já é a soma em ambos os casos (invariante do ADR-0012).
    """
    secoes = []
    for categoria, campos in CAMPOS_POR_CATEGORIA.items():
        secao_antes = antes.get(categoria) or {}
        secao_depois = depois.get(categoria) or {}
        linhas = []
        total_antes = total_depois = 0.0
        for campo in campos:
            v_antes = float(secao_antes.get(campo) or 0.0)
            v_depois = float(secao_depois.get(campo) or 0.0)
            total_antes += v_antes
            total_depois += v_depois
            if v_antes == 0.0 and v_depois == 0.0:
                continue
            delta, pct = _variacao(v_antes, v_depois)
            linhas.append({
                "campo": campo,
                "rotulo": ROTULO_CAMPO[categoria][campo],
                "antes": round(v_antes, 2), "depois": round(v_depois, 2),
                "delta": delta, "variacao_pct": pct,
            })
        delta, pct = _variacao(total_antes, total_depois)
        secoes.append({
            "categoria": categoria,
            "rotulo": ROTULO_CATEGORIA[categoria],
            "antes": round(total_antes, 2), "depois": round(total_depois, 2),
            "delta": delta, "variacao_pct": pct,
            "campos": linhas,
        })
    return {"secoes": secoes}


def aplicar_somas(perfil: dict, somas: dict[str, dict[str, float]]) -> dict:
    """Devolve o perfil (dict do contrato) com os campos detalhados = soma.

    Não muta a entrada; seções/campos sem rubricas passam intactos — inclusive
    dívidas, reserva e FGTS, que nunca participam do roll-up.
    """
    novo = dict(perfil)
    for categoria, secao in somas.items():
        atual = dict(novo.get(categoria) or {})
        atual.update(secao)
        novo[categoria] = atual
    return novo
