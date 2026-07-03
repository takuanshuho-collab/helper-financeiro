"""
Estratégias de quitação e recomendações.

Duas ideias centrais:
  - AVALANCHE: paga primeiro a dívida de MAIOR juro. Economiza mais dinheiro.
  - BOLA DE NEVE: paga primeiro a de MENOR saldo. Dá vitórias rápidas (motivação).

O simulador "roda o filme" mês a mês: paga o mínimo de todas e joga a sobra
na dívida prioritária; quando uma quita, a parcela dela vira sobra para a
próxima (efeito bola de neve de verdade).
"""
from __future__ import annotations

from copy import deepcopy

from .calculos import simular_portabilidade
from .models import Divida, PerfilFinanceiro

MESES_MAXIMO = 600  # trava de segurança: 50 anos


def ordenar_avalanche(dividas: list[Divida]) -> list[Divida]:
    return sorted(dividas, key=lambda d: d.taxa_mensal, reverse=True)


def ordenar_bola_de_neve(dividas: list[Divida]) -> list[Divida]:
    return sorted(dividas, key=lambda d: d.saldo_devedor)


def simular_quitacao(perfil: PerfilFinanceiro, extra_mensal: float,
                     metodo: str = "avalanche") -> dict:
    """Simula quanto tempo até zerar as dívidas e quanto de juro será pago.

    extra_mensal: valor além das parcelas mínimas que o usuário consegue pagar.
    metodo: "avalanche" ou "bola_de_neve".
    """
    dividas = deepcopy(perfil.dividas)
    if not dividas:
        return {"meses": 0, "juros_pagos": 0.0, "quitavel": True, "ordem": []}

    ordenar = ordenar_avalanche if metodo == "avalanche" else ordenar_bola_de_neve
    ordem_nomes = [d.credor for d in ordenar(dividas)]

    juros_pagos = 0.0
    meses = 0

    while any(d.saldo_devedor > 0.005 for d in dividas):
        meses += 1
        if meses > MESES_MAXIMO:
            # Provavelmente as parcelas mínimas não cobrem os juros.
            return {"meses": None, "juros_pagos": round(juros_pagos, 2),
                    "quitavel": False, "ordem": ordem_nomes}

        # 1) Aplica juros do mês sobre cada saldo em aberto.
        for d in dividas:
            if d.saldo_devedor > 0:
                juro = d.saldo_devedor * d.taxa_mensal
                juros_pagos += juro
                d.saldo_devedor += juro

        # 2) Orçamento do mês = soma das parcelas mínimas + extra.
        orcamento = sum(d.parcela for d in dividas if d.saldo_devedor > 0) + extra_mensal

        # 3) Paga o mínimo de cada dívida ativa.
        ativas = [d for d in dividas if d.saldo_devedor > 0]
        for d in ativas:
            pago = min(d.parcela, d.saldo_devedor)
            d.saldo_devedor -= pago
            orcamento -= pago

        # 4) Joga o que sobrou na dívida prioritária, em cascata.
        for d in ordenar([x for x in dividas if x.saldo_devedor > 0]):
            if orcamento <= 0:
                break
            abate = min(orcamento, d.saldo_devedor)
            d.saldo_devedor -= abate
            orcamento -= abate

    return {"meses": meses, "juros_pagos": round(juros_pagos, 2),
            "quitavel": True, "ordem": ordem_nomes}


def comparar_estrategias(perfil: PerfilFinanceiro, extra_mensal: float) -> dict:
    """Roda avalanche e bola de neve lado a lado para o usuário escolher."""
    return {
        "avalanche": simular_quitacao(perfil, extra_mensal, "avalanche"),
        "bola_de_neve": simular_quitacao(perfil, extra_mensal, "bola_de_neve"),
    }


def oportunidades_portabilidade(perfil: PerfilFinanceiro,
                                taxa_alvo_mensal: float) -> list[dict]:
    """Para cada dívida mais cara que a taxa-alvo, calcula a economia potencial."""
    oportunidades = []
    for d in perfil.dividas:
        if d.taxa_mensal > taxa_alvo_mensal and d.parcelas_restantes > 0:
            sim = simular_portabilidade(
                d.saldo_devedor, d.taxa_mensal, taxa_alvo_mensal, d.parcelas_restantes
            )
            if sim["vale_a_pena"]:
                oportunidades.append({"credor": d.credor, "tipo": d.tipo, **sim})
    # Ordena pela maior economia total.
    return sorted(oportunidades, key=lambda x: x["economia_total"], reverse=True)


def gerar_recomendacoes(perfil: PerfilFinanceiro, diagnostico: dict) -> list[str]:
    """Gera recomendações textuais com base em regras simples e transparentes."""
    recs: list[str] = []

    if diagnostico["tem_deficit"]:
        recs.append(
            "Seu fluxo de caixa está NEGATIVO: as saídas superam as entradas. "
            "Antes de qualquer estratégia de quitação, é preciso cortar despesas "
            "ou aumentar a renda para gerar sobra mensal."
        )

    comp = diagnostico["comprometimento_renda"]
    if comp > 0.50:
        recs.append(
            f"O comprometimento de renda está em {comp*100:.0f}% (crítico). "
            "Priorize renegociar ou portar as dívidas mais caras para reduzir a "
            "parcela mensal e recuperar fôlego."
        )
    elif comp > 0.30:
        recs.append(
            f"O comprometimento de renda está em {comp*100:.0f}% (atenção). "
            "Evite contrair novas dívidas e concentre esforços em quitar as caras."
        )

    mais_cara = diagnostico["divida_mais_cara"]
    if mais_cara and mais_cara.taxa_mensal > 0.04:
        recs.append(
            f"A dívida mais cara é '{mais_cara.credor}' "
            f"({mais_cara.taxa_mensal*100:.1f}% a.m.). Dívidas acima de ~4% a.m. "
            "(típico de cartão rotativo e cheque especial) devem ser o primeiro alvo."
        )

    tem_consignado = any("Consignado" in d.tipo for d in perfil.dividas)
    tem_cara = any(d.taxa_mensal > 0.04 for d in perfil.dividas)
    if not tem_consignado and tem_cara:
        recs.append(
            "Você tem dívida cara mas nenhum consignado. Se tiver margem "
            "consignável disponível, trocar dívida cara por consignado (juros "
            "menores) costuma reduzir bastante o custo — confirme a margem vigente."
        )

    if perfil.reserva_emergencia <= 0:
        recs.append(
            "Você não tem reserva de emergência. Após controlar as dívidas caras, "
            "montar uma reserva evita recorrer a crédito caro no próximo imprevisto."
        )

    if not recs:
        recs.append(
            "Sua situação está sob controle. Mantenha o comprometimento de renda "
            "baixo e considere antecipar a quitação das dívidas mais caras."
        )

    return recs
