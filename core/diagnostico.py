"""
Diagnóstico financeiro: transforma o perfil em indicadores interpretáveis.
"""
from __future__ import annotations

from .models import Divida, PerfilFinanceiro

# Faixas de comprometimento de renda (parcelas / renda líquida).
# Referência de bolso amplamente usada em educação financeira.
LIMITE_SAUDAVEL = 0.30
LIMITE_ATENCAO = 0.50

# Eixo do fluxo de caixa (T-2606, achado da aceitação de campo do v2.15): um
# déficit mensal de até esta fração da renda rebaixa para "Atenção"; acima,
# "Crítico". Antes o rótulo só olhava as parcelas — um orçamento com déficit de
# milhares de reais mas parcelas baixas saía "Saudável" no dashboard.
LIMITE_DEFICIT_ATENCAO = 0.10

# Severidade ordinal dos rótulos para o "pior entre os dois eixos".
_NIVEIS = {"Saudável": 0, "Atenção": 1, "Crítico": 2}


def _eixo_parcelas(comprometimento: float) -> tuple[str, str]:
    """Eixo clássico: comprometimento da renda com parcelas de dívida."""
    if comprometimento <= LIMITE_SAUDAVEL:
        return ("Saudável", "As parcelas cabem no orçamento com folga.")
    if comprometimento <= LIMITE_ATENCAO:
        return ("Atenção", "As parcelas já pesam; margem de manobra pequena.")
    return ("Crítico", "As parcelas consomem grande parte da renda; risco alto.")


def _eixo_fluxo(fluxo_caixa: float, renda_liquida: float) -> tuple[str, str]:
    """Eixo do orçamento inteiro: sobra (ou falta) mensal após TUDO.

    Déficit relativo à renda: até `LIMITE_DEFICIT_ATENCAO` ⇒ "Atenção"; acima ⇒
    "Crítico". Renda zero (ou negativa) com déficit é "Crítico" direto — não há
    denominador que relativize um orçamento sem renda gastando dinheiro.
    """
    if fluxo_caixa >= 0:
        return ("Saudável", "O orçamento fecha o mês no azul.")
    if renda_liquida <= 0 or (-fluxo_caixa / renda_liquida) > LIMITE_DEFICIT_ATENCAO:
        return ("Crítico", "As despesas superam a renda em valor relevante: "
                           "o mês fecha no vermelho.")
    return ("Atenção", "O orçamento fecha o mês no vermelho, ainda que por pouco.")


def classificar_saude(comprometimento: float, fluxo_caixa: float = 0.0,
                      renda_liquida: float = 0.0) -> tuple[str, str]:
    """Retorna (rótulo, explicação) da saúde financeira — o PIOR entre dois eixos.

    T-2606 (decisão do mantenedor na aceitação de campo do v2.15): o rótulo
    reflete a situação INTEIRA — (a) o eixo das parcelas (regra clássica) e
    (b) o eixo do fluxo de caixa (renda − despesas − parcelas). A explicação é
    a do eixo que puxou para baixo; empatados num nível ruim, as duas frases
    são combinadas. Os defaults (`fluxo_caixa=0`, sem déficit) preservam o
    comportamento antigo para chamadas legadas de um argumento só.
    """
    rotulo_p, expl_p = _eixo_parcelas(comprometimento)
    rotulo_f, expl_f = _eixo_fluxo(fluxo_caixa, renda_liquida)
    if _NIVEIS[rotulo_f] > _NIVEIS[rotulo_p]:
        return (rotulo_f, expl_f)
    if _NIVEIS[rotulo_f] == _NIVEIS[rotulo_p] and rotulo_p != "Saudável":
        return (rotulo_p, f"{expl_p} {expl_f}")
    return (rotulo_p, expl_p)


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
    rotulo, explicacao = classificar_saude(
        comprometimento, perfil.fluxo_caixa, perfil.renda_liquida)

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
