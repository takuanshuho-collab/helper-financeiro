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
