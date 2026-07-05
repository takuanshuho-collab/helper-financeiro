"""
Diagnóstico financeiro: transforma o perfil em indicadores interpretáveis.
"""
from __future__ import annotations

from .models import Divida, PerfilFinanceiro

# Faixas de comprometimento de renda (parcelas / renda líquida).
# Referência de bolso amplamente usada em educação financeira.
LIMITE_SAUDAVEL = 0.30
LIMITE_ATENCAO = 0.50


def classificar_saude(comprometimento: float) -> tuple[str, str]:
    """Retorna (rótulo, explicação) para o nível de comprometimento de renda."""
    if comprometimento <= LIMITE_SAUDAVEL:
        return ("Saudável", "As parcelas cabem no orçamento com folga.")
    if comprometimento <= LIMITE_ATENCAO:
        return ("Atenção", "As parcelas já pesam; margem de manobra pequena.")
    return ("Crítico", "As parcelas consomem grande parte da renda; risco alto.")


def ranking_dividas(perfil: PerfilFinanceiro) -> list[Divida]:
    """Ordena as dívidas da mais cara para a mais barata (por taxa mensal)."""
    return sorted(perfil.dividas, key=lambda d: d.taxa_mensal, reverse=True)


def taxa_media_ponderada(perfil: PerfilFinanceiro) -> float:
    """Taxa mensal média das dívidas, ponderada pelo saldo devedor.

    Uma média simples pesaria igual uma dívida de R$ 100 e outra de R$ 50.000;
    ponderar pelo saldo revela a taxa que de fato dói no bolso. Retorna 0.0
    quando não há saldo devedor.
    """
    saldo_total = perfil.saldo_devedor_total
    if saldo_total <= 0:
        return 0.0
    return sum(d.taxa_mensal * d.saldo_devedor for d in perfil.dividas) / saldo_total


def resumo_diagnostico(perfil: PerfilFinanceiro) -> dict:
    """Consolida todos os números do diagnóstico em um dicionário."""
    comprometimento = perfil.comprometimento_renda
    rotulo, explicacao = classificar_saude(comprometimento)

    ranking = ranking_dividas(perfil)
    divida_mais_cara = ranking[0] if ranking else None
    juros_totais_futuros = sum(d.juros_restantes for d in perfil.dividas)
    custo_total_ate_quitar = sum(d.custo_total_restante for d in perfil.dividas)

    return {
        "renda_liquida": perfil.renda_liquida,
        "despesas_totais": perfil.despesas_totais,
        "total_parcelas": perfil.total_parcelas,
        "fluxo_caixa": perfil.fluxo_caixa,
        "saldo_devedor_total": perfil.saldo_devedor_total,
        "juros_totais_futuros": juros_totais_futuros,
        "custo_total_ate_quitar": custo_total_ate_quitar,
        "taxa_media_ponderada": taxa_media_ponderada(perfil),
        "comprometimento_renda": comprometimento,
        "classificacao": rotulo,
        "classificacao_explicacao": explicacao,
        "divida_mais_cara": divida_mais_cara,
        "ranking": ranking,
        "tem_deficit": perfil.fluxo_caixa < 0,
    }
