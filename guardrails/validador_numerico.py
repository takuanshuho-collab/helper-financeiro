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

from contracts import AnaliseAgente, FatosFinanceiros

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


def _numeros_permitidos(fatos: FatosFinanceiros) -> set[float]:
    """Monta o conjunto de números legítimos a partir dos fatos.

    Inclui os valores em si e representações equivalentes (ex.: taxa 0.12 também
    como 12 por causa da escrita '12%'; comprometimento 0.39 como 39).
    """
    permitidos: set[float] = set()

    def add(v):
        if v is None:
            return
        # O token numérico do texto nunca carrega sinal ("R$ -2.200,00" rende
        # "2.200,00"), então um fato negativo deve valer pelo módulo.
        valor = abs(float(v))
        permitidos.add(round(valor, 4))
        # percentuais aparecem como "39" em vez de "0.39"
        permitidos.add(round(valor * 100, 4))

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


def coletar_textos(analise: AnaliseAgente) -> list[str]:
    """Todos os campos de texto livre onde o LLM poderia citar um número."""
    textos = [analise.sumario_executivo, analise.diagnostico_interpretado]
    textos += [p.justificativa for p in analise.prioridades]
    for passo in analise.roteiro_negociacao:
        textos += passo.argumentos + passo.concessoes_possiveis
    textos += analise.alertas_risco
    return textos


# Fim de frase: pontuação seguida de espaço (ou fim). Mantém "R$ 1.234,56" e
# "1,8" intactos porque exige o espaço após o ponto/exclamação/interrogação.
_RE_FIM_FRASE = re.compile(r"(?<=[.!?])\s+")


def _frase_fundamentada(frase: str, permitidos: set[float]) -> bool:
    for token in _RE_NUMERO.findall(frase):
        interps = _interpretacoes(token)
        if not interps:
            continue
        primario = interps[0]
        if primario <= 3 and primario == int(primario):
            continue
        if not any(_bate(v, permitidos) for v in interps):
            return False
    return True


def remover_frases_orfas(fatos: FatosFinanceiros,
                         analise: AnaliseAgente) -> AnaliseAgente:
    """Redação determinística (último recurso antes de degradar, ADR-0011).

    Modelos locais pequenos fabricam números sobretudo em EXEMPLOS acessórios
    ("ex.: R$ 200/mês") — descartar a análise inteira por causa deles joga fora
    conteúdo fundamentado. Esta função remove as FRASES que contêm números
    órfãos e preserva o resto; o H1 segue valendo: nenhum número fabricado
    chega ao usuário. O chamador decide se o que sobrou ainda sustenta a
    análise (revalidação + campos essenciais não vazios).
    """
    permitidos = _numeros_permitidos(fatos)
    limpa = analise.model_copy(deep=True)

    def texto(t: str) -> str:
        frases = _RE_FIM_FRASE.split(t)
        return " ".join(f for f in frases
                        if _frase_fundamentada(f, permitidos)).strip()

    def lista(itens: list[str]) -> list[str]:
        return [x for x in (texto(i) for i in itens) if x]

    limpa.sumario_executivo = texto(limpa.sumario_executivo)
    limpa.diagnostico_interpretado = texto(limpa.diagnostico_interpretado)
    for p in limpa.prioridades:
        p.justificativa = texto(p.justificativa)
    for passo in limpa.roteiro_negociacao:
        passo.argumentos = lista(passo.argumentos)
        passo.concessoes_possiveis = lista(passo.concessoes_possiveis)
    limpa.alertas_risco = lista(limpa.alertas_risco)
    return limpa


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
