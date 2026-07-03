"""
Motor de cálculo financeiro (Python puro, sem dependências externas).

Este módulo é o "cérebro" do programa. Ele não sabe nada sobre janelas,
planilhas ou PDFs — só faz contas. Isso é de propósito: se um dia a interface
mudar, estas funções continuam valendo.

Convenção: `i` é sempre a taxa por período em decimal (0.02 = 2%).
"""
from __future__ import annotations


def parcela_price(pv: float, i: float, n: int) -> float:
    """Parcela fixa no sistema Price (a famosa PMT).

    pv = valor presente (principal) ; i = taxa mensal ; n = nº de parcelas.
    """
    if n <= 0:
        return 0.0
    if i == 0:                      # empréstimo sem juros
        return pv / n
    return pv * i / (1 - (1 + i) ** -n)


def saldo_devedor_price(pv: float, i: float, n: int, k: int) -> float:
    """Saldo devedor após `k` parcelas pagas, no sistema Price."""
    if k >= n:
        return 0.0
    pmt = parcela_price(pv, i, n)
    if i == 0:
        return pv - pmt * k
    # Valor presente das parcelas que ainda faltam
    return pmt * (1 - (1 + i) ** -(n - k)) / i


def custo_total(pv: float, i: float, n: int) -> tuple[float, float]:
    """Retorna (total_pago, total_de_juros) ao longo de todo o contrato."""
    total = parcela_price(pv, i, n) * n
    return total, total - pv


def taxa_mensal_para_anual(i: float) -> float:
    return (1 + i) ** 12 - 1


def taxa_anual_para_mensal(i: float) -> float:
    return (1 + i) ** (1 / 12) - 1


def taxa_implicita(pv: float, pmt: float, n: int) -> float | None:
    """Descobre a taxa mensal `i` a partir de (principal, parcela, nº parcelas).

    Resolve, por bisseção, a equação: pmt = parcela_price(pv, i, n).
    A parcela cresce de forma monótona com a taxa, então a bisseção é segura.

    Serve para dois usos:
      1) achar a taxa quando o contrato só informa valor, parcela e prazo;
      2) calcular o CET (passando o valor LIBERADO em vez do financiado).
    Retorna None se não houver solução plausível.
    """
    if pv <= 0 or pmt <= 0 or n <= 0:
        return None
    # Se a parcela nem cobre o principal dividido pelo prazo, taxa seria negativa.
    if pmt * n <= pv:
        return 0.0

    baixo, alto = 0.0, 1.0          # procura entre 0% e 100% ao mês
    # Garante que a raiz está no intervalo; se não, expande o teto.
    while parcela_price(pv, alto, n) < pmt and alto < 100:
        alto *= 2

    for _ in range(200):            # ~200 iterações dão precisão de sobra
        meio = (baixo + alto) / 2
        if parcela_price(pv, meio, n) < pmt:
            baixo = meio
        else:
            alto = meio
    return (baixo + alto) / 2


def calcular_cet_anual(valor_liberado: float, parcela: float, n: int) -> float | None:
    """CET anual a partir do valor efetivamente recebido e do fluxo de parcelas.

    O CET (Custo Efetivo Total) embute tarifas e seguros: por isso usamos o
    valor LIBERADO (menor que o financiado quando há custos embutidos).
    """
    i_mensal = taxa_implicita(valor_liberado, parcela, n)
    if i_mensal is None:
        return None
    return taxa_mensal_para_anual(i_mensal)


def simular_portabilidade(saldo: float, i_atual: float, i_novo: float,
                          parcelas_restantes: int) -> dict:
    """Compara manter a dívida atual vs. migrar para uma taxa menor (mesmo prazo)."""
    pmt_atual = parcela_price(saldo, i_atual, parcelas_restantes)
    pmt_novo = parcela_price(saldo, i_novo, parcelas_restantes)
    economia_mensal = pmt_atual - pmt_novo
    return {
        "parcela_atual": round(pmt_atual, 2),
        "parcela_nova": round(pmt_novo, 2),
        "economia_mensal": round(economia_mensal, 2),
        "economia_total": round(economia_mensal * parcelas_restantes, 2),
        "vale_a_pena": economia_mensal > 0,
    }
