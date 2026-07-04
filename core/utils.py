"""
Utilitários de conversão e formatação de valores no padrão brasileiro.

A ideia central: dentro do programa, todo número é um `float` "puro"
(ex.: 1234.56 e 0.02 para 2%). As funções aqui traduzem entre esse formato
interno e o que o usuário digita/lê (ex.: "1.234,56" e "2%").
"""
from __future__ import annotations


def parse_valor(texto: str | float | int | None) -> float:
    """Converte texto em padrão brasileiro para float.

    Aceita "1.234,56", "1234,56", "R$ 1.234,56", "1234.56", números etc.
    Retorna 0.0 se o campo estiver vazio ou não for numérico.
    """
    if texto is None:
        return 0.0
    if isinstance(texto, (int, float)):
        return float(texto)

    limpo = str(texto).strip()
    if not limpo:
        return 0.0

    # Remove símbolos de moeda, espaços e o "%" (se houver)
    for simbolo in ("R$", "r$", "%", " ", "\u00a0"):
        limpo = limpo.replace(simbolo, "")

    # Padrão BR: ponto é separador de milhar, vírgula é decimal.
    # Se tem vírgula, tratamos a vírgula como decimal e removemos os pontos.
    if "," in limpo:
        limpo = limpo.replace(".", "").replace(",", ".")
    # Se só tem ponto, assumimos que já é decimal no padrão internacional.

    try:
        return float(limpo)
    except ValueError:
        return 0.0


def parse_taxa(texto: str | float | int | None) -> float:
    """Converte uma taxa digitada (ex.: "2,3" ou "2,3%") para decimal (0.023).

    Regra: o usuário digita em PONTO PERCENTUAL (2,3 = 2,3%).
    """
    valor = parse_valor(texto)
    return valor / 100.0


def formatar_brl(valor: float) -> str:
    """Formata um float como moeda brasileira: 1234.5 -> 'R$ 1.234,50'."""
    inteiro, decimal = f"{abs(valor):,.2f}".split(".")
    inteiro = inteiro.replace(",", ".")  # troca separador de milhar para ponto
    sinal = "-" if valor < 0 else ""
    return f"{sinal}R$ {inteiro},{decimal}"


def formatar_pct(decimal: float, casas: int = 2) -> str:
    """Formata um decimal como percentual: 0.023 -> '2,30%'."""
    txt = f"{decimal * 100:.{casas}f}"
    return txt.replace(".", ",") + "%"


def texto_numerico_valido(texto: str | None) -> bool:
    """Diz se o texto de um campo numérico é interpretável (REQ-F-009).

    Vazio conta como válido (o campo vale zero por design); texto não
    interpretável ("abc", "1,2,3") é inválido — a GUI usa isso para
    SINALIZAR o campo em vez de tratá-lo silenciosamente como zero.
    Aplica a mesma normalização brasileira do `parse_valor`.
    """
    if texto is None:
        return True
    limpo = str(texto).strip()
    if not limpo:
        return True
    for simbolo in ("R$", "r$", "%", " ", "\u00a0"):
        limpo = limpo.replace(simbolo, "")
    if "," in limpo:
        limpo = limpo.replace(".", "").replace(",", ".")
    try:
        float(limpo)
    except ValueError:
        return False
    return True
