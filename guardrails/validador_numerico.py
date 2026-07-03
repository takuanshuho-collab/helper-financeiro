"""
Guardrail de consistência numérica — a trava mais importante (REQ-GRD-001 / H1).

Regra: todo número citado nos textos da análise do LLM precisa existir nos
FATOS determinísticos, dentro da tolerância. Número órfão = alucinação.

É o "detector de metal" na saída do agente: se aparecer uma cifra que não
passou pela balança calibrada do `core`, soa o alarme.
"""
from __future__ import annotations

import contextlib
import re

from agent.schemas import AnaliseAgente, FatosFinanceiros

TOLERANCIA_RELATIVA = 0.01   # ±1% para moeda/percentual
_EPS = 1e-9

# Captura um "token numérico" inteiro: começa e termina em dígito, admitindo
# pontos e vírgulas no meio. Cobre 1.234,56 | 34000.00 | 8.000 | 12 | 2,5.
_RE_NUMERO = re.compile(r"\d[\d.,]*\d|\d")


def _interpretacoes(bruto: str) -> list[float]:
    """Todas as leituras plausíveis de um token numérico (pt-BR e cru/US).

    A primeira da lista é a interpretação pt-BR (usada para reportar o órfão).
    Como o objetivo é CAÇAR cifra inventada, somos tolerantes na leitura: só
    acusamos quando NENHUMA interpretação bate com os fatos (evita falso alarme).
    """
    cands: list[float] = []
    # pt-BR: ponto = milhar, vírgula = decimal
    with contextlib.suppress(ValueError):
        cands.append(float(bruto.replace(".", "").replace(",", ".")))
    # cru/US: vírgula = milhar, ponto = decimal
    try:
        v = float(bruto.replace(",", ""))
        if v not in cands:
            cands.append(v)
    except ValueError:
        pass
    return cands


def _to_float(bruto: str) -> float:
    """Interpretação pt-BR (mantida para compatibilidade/depuração)."""
    return float(bruto.replace(".", "").replace(",", "."))


def _numeros_permitidos(fatos: FatosFinanceiros) -> set[float]:
    """Monta o conjunto de números legítimos a partir dos fatos.

    Inclui os valores em si e representações equivalentes (ex.: taxa 0.12 também
    como 12 por causa da escrita '12%'; comprometimento 0.39 como 39).
    """
    permitidos: set[float] = set()

    def add(v):
        if v is None:
            return
        permitidos.add(round(float(v), 4))
        # percentuais aparecem como "39" em vez de "0.39"
        permitidos.add(round(float(v) * 100, 4))

    add(fatos.comprometimento_renda)
    add(fatos.fluxo_caixa)
    add(fatos.saldo_devedor_total)
    add(fatos.juros_totais_futuros)
    for d in fatos.dividas:
        for v in (d.saldo_devedor, d.taxa_mensal, d.taxa_anual,
                  d.parcela, d.parcelas_restantes):
            add(v)
    for e in fatos.estrategias:
        add(e.meses)
        add(e.juros_pagos)
    return permitidos


def _bate(valor: float, permitidos: set[float]) -> bool:
    for p in permitidos:
        denom = max(abs(p), _EPS)
        if abs(valor - p) / denom <= TOLERANCIA_RELATIVA:
            return True
        if abs(valor - p) < 0.5:   # contagens (meses/parcelas) ~ exatas
            return True
    return False


def extrair_numeros(texto: str) -> list[float]:
    """Interpretação pt-BR (primária) de cada token numérico do texto."""
    numeros = []
    for m in _RE_NUMERO.findall(texto):
        interps = _interpretacoes(m)
        if interps:
            numeros.append(interps[0])
    return numeros


def coletar_textos(analise: AnaliseAgente) -> list[str]:
    """Todos os campos de texto livre onde o LLM poderia citar um número."""
    textos = [analise.sumario_executivo, analise.diagnostico_interpretado]
    textos += [p.justificativa for p in analise.prioridades]
    for passo in analise.roteiro_negociacao:
        textos += passo.argumentos + passo.concessoes_possiveis
    textos += analise.alertas_risco
    return textos


def validar(fatos: FatosFinanceiros, analise: AnaliseAgente) -> list[float]:
    """Retorna a lista de números ÓRFÃOS (não fundamentados). Vazia = aprovado."""
    permitidos = _numeros_permitidos(fatos)
    orfaos: list[float] = []
    for texto in coletar_textos(analise):
        for token in _RE_NUMERO.findall(texto):
            interps = _interpretacoes(token)
            if not interps:
                continue
            primario = interps[0]
            # Ignora inteiros pequenos usados como enumeração (1., 2., 3.)
            if primario <= 3 and primario == int(primario):
                continue
            # Órfão só se NENHUMA interpretação bater com os fatos.
            if not any(_bate(v, permitidos) for v in interps):
                orfaos.append(primario)
    return orfaos
