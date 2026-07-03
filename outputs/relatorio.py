"""
Geração do relatório de análise em .docx (python-docx).
"""
from __future__ import annotations

from datetime import date

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt, RGBColor

from core.diagnostico import resumo_diagnostico
from core.estrategias import comparar_estrategias, gerar_recomendacoes, oportunidades_portabilidade
from core.models import PerfilFinanceiro
from core.utils import formatar_brl, formatar_pct

AZUL = RGBColor(0x1F, 0x4E, 0x79)
CINZA = RGBColor(0x59, 0x59, 0x59)


def _titulo(doc, texto, nivel=1):
    h = doc.add_heading(texto, level=nivel)
    for run in h.runs:
        run.font.color.rgb = AZUL
    return h


def _tabela_indicadores(doc, dados: list[tuple[str, str]]):
    tab = doc.add_table(rows=0, cols=2)
    tab.style = "Light Grid Accent 1"
    for rotulo, valor in dados:
        linha = tab.add_row().cells
        linha[0].text = rotulo
        linha[1].text = valor
        linha[0].paragraphs[0].runs[0].bold = True
    return tab


def gerar_relatorio(perfil: PerfilFinanceiro, caminho_saida: str,
                    extra_mensal: float = 0.0, taxa_alvo_mensal: float = 0.018,
                    nome_usuario: str = "") -> str:
    diag = resumo_diagnostico(perfil)
    doc = Document()

    # Fonte padrão
    style = doc.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(11)

    # --- Capa / cabeçalho ---
    cab = doc.add_paragraph()
    cab.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = cab.add_run("Relatório de Saúde Financeira")
    run.bold = True
    run.font.size = Pt(20)
    run.font.color.rgb = AZUL

    sub = doc.add_paragraph()
    sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    linha_sub = f"Emitido em {date.today().strftime('%d/%m/%Y')}"
    if nome_usuario:
        linha_sub = f"{nome_usuario} — " + linha_sub
    r = sub.add_run(linha_sub)
    r.font.color.rgb = CINZA
    r.font.size = Pt(10)

    # --- Resumo executivo ---
    _titulo(doc, "1. Resumo executivo")
    classe = diag["classificacao"]
    p = doc.add_paragraph()
    p.add_run(f"Situação: {classe}. ").bold = True
    p.add_run(diag["classificacao_explicacao"] + " ")
    p.add_run(
        f"O comprometimento de renda com parcelas é de "
        f"{formatar_pct(diag['comprometimento_renda'])}, e o fluxo de caixa mensal "
        f"é de {formatar_brl(diag['fluxo_caixa'])}."
    )
    if diag["tem_deficit"]:
        alerta = doc.add_paragraph()
        run = alerta.add_run(
            "⚠ Atenção: o fluxo de caixa está negativo. As saídas superam as "
            "entradas, o que precisa ser resolvido antes de qualquer estratégia."
        )
        run.font.color.rgb = RGBColor(0xC0, 0x00, 0x00)
        run.bold = True

    # --- Diagnóstico ---
    _titulo(doc, "2. Diagnóstico")
    _tabela_indicadores(doc, [
        ("Renda líquida mensal", formatar_brl(diag["renda_liquida"])),
        ("Despesas totais", formatar_brl(diag["despesas_totais"])),
        ("Total de parcelas/mês", formatar_brl(diag["total_parcelas"])),
        ("Fluxo de caixa (sobra/mês)", formatar_brl(diag["fluxo_caixa"])),
        ("Saldo devedor total", formatar_brl(diag["saldo_devedor_total"])),
        ("Juros futuros embutidos", formatar_brl(diag["juros_totais_futuros"])),
        ("Comprometimento de renda", formatar_pct(diag["comprometimento_renda"])),
    ])

    # --- Ranking de dívidas ---
    _titulo(doc, "3. Suas dívidas, da mais cara para a mais barata")
    if perfil.dividas:
        tab = doc.add_table(rows=1, cols=5)
        tab.style = "Light Grid Accent 1"
        hdr = tab.rows[0].cells
        for i, txt in enumerate(["Credor", "Tipo", "Saldo", "Taxa a.m.", "Parcela"]):
            hdr[i].text = txt
            hdr[i].paragraphs[0].runs[0].bold = True
        for d in diag["ranking"]:
            c = tab.add_row().cells
            c[0].text = d.credor
            c[1].text = d.tipo
            c[2].text = formatar_brl(d.saldo_devedor)
            c[3].text = formatar_pct(d.taxa_mensal)
            c[4].text = formatar_brl(d.parcela)
    else:
        doc.add_paragraph("Nenhuma dívida cadastrada.")

    # --- Estratégia ---
    _titulo(doc, "4. Estratégia de quitação")
    doc.add_paragraph(
        f"Considerando um pagamento extra de {formatar_brl(extra_mensal)} por mês "
        "além das parcelas mínimas, comparamos os dois métodos clássicos:"
    )
    comp = comparar_estrategias(perfil, extra_mensal)

    def _descreve(nome, res, explicacao):
        p = doc.add_paragraph(style="List Bullet")
        p.add_run(f"{nome}: ").bold = True
        if res["quitavel"]:
            p.add_run(
                f"quita em {res['meses']} meses, pagando "
                f"{formatar_brl(res['juros_pagos'])} em juros. {explicacao}"
            )
        else:
            p.add_run(
                "com esse valor extra, as parcelas mínimas não conseguem quitar a "
                "dívida (os juros crescem mais rápido). É preciso aumentar o aporte "
                "ou renegociar as taxas."
            )

    _descreve("Avalanche (ataca o maior juro)", comp["avalanche"],
              "Matematicamente é o caminho mais barato.")
    _descreve("Bola de neve (ataca o menor saldo)", comp["bola_de_neve"],
              "Custa um pouco mais, mas entrega vitórias rápidas que ajudam a manter a disciplina.")

    # Transparência do modelo (SPEC REQ-F-003, auditoria F-10).
    nota = doc.add_paragraph()
    r_nota = nota.add_run(
        "Nota: a simulação usa um modelo simplificado (juros compostos sobre o "
        "saldo, parcela constante) e serve para comparar as estratégias entre "
        "si; o prazo exato pode diferir do cronograma contratual do banco."
    )
    r_nota.italic = True
    r_nota.font.size = Pt(9)
    r_nota.font.color.rgb = CINZA

    if comp["avalanche"]["quitavel"] and comp["bola_de_neve"]["quitavel"]:
        diferenca = comp["bola_de_neve"]["juros_pagos"] - comp["avalanche"]["juros_pagos"]
        if diferenca > 0:
            doc.add_paragraph(
                f"Recomendação: a avalanche economiza {formatar_brl(diferenca)} em "
                "juros. Prefira-a, a menos que você precise do impulso psicológico "
                "das quitações rápidas da bola de neve."
            )

    # --- Portabilidade ---
    ops = oportunidades_portabilidade(perfil, taxa_alvo_mensal)
    if ops:
        _titulo(doc, "5. Oportunidades de portabilidade")
        doc.add_paragraph(
            f"Migrando as dívidas caras para uma taxa de "
            f"{formatar_pct(taxa_alvo_mensal)} a.m., a economia estimada seria:"
        )
        tab = doc.add_table(rows=1, cols=3)
        tab.style = "Light Grid Accent 1"
        hdr = tab.rows[0].cells
        for i, txt in enumerate(["Credor", "Economia mensal", "Economia total"]):
            hdr[i].text = txt
            hdr[i].paragraphs[0].runs[0].bold = True
        for o in ops:
            c = tab.add_row().cells
            c[0].text = o["credor"]
            c[1].text = formatar_brl(o["economia_mensal"])
            c[2].text = formatar_brl(o["economia_total"])

    # --- Recomendações ---
    _titulo(doc, f"{6 if ops else 5}. Recomendações")
    for rec in gerar_recomendacoes(perfil, diag):
        doc.add_paragraph(rec, style="List Bullet")

    # --- Próximos passos ---
    _titulo(doc, f"{7 if ops else 6}. Próximos passos")
    for passo in [
        "Solicite a cada credor o saldo devedor atualizado, por escrito.",
        "Simule a portabilidade nos concorrentes e use as propostas como alavanca.",
        "Negocie primeiro as dívidas mais caras (maior taxa/CET).",
        "Registre todo acordo por escrito (protocolo ou Consumidor.gov.br).",
    ]:
        doc.add_paragraph(passo, style="List Number")

    # --- Aviso ---
    doc.add_paragraph()
    aviso = doc.add_paragraph()
    r = aviso.add_run(
        "Aviso: este relatório é uma ferramenta de apoio à decisão baseada nos "
        "dados informados. Não constitui aconselhamento financeiro ou de "
        "investimento personalizado. As taxas de mercado e as regras de programas "
        "de renegociação mudam; confirme os números vigentes antes de decidir."
    )
    r.italic = True
    r.font.size = Pt(9)
    r.font.color.rgb = CINZA

    doc.save(caminho_saida)
    return caminho_saida
