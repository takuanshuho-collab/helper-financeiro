"""
Geração da planilha .xlsx (diagnóstico + simulações).

Filosofia: a planilha não é uma foto morta. As entradas ficam em células
editáveis e os indicadores derivados são FÓRMULAS do Excel — então o usuário
pode mudar um saldo ou uma taxa e ver tudo recalcular sozinho.
"""
from __future__ import annotations

from openpyxl import Workbook
from openpyxl.chart import BarChart, Reference
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

from core.estrategias import comparar_estrategias, oportunidades_portabilidade
from core.models import PerfilFinanceiro

# --- Paleta e estilos ---
AZUL = "1F4E79"
AZUL_CLARO = "DDEBF7"
CINZA = "F2F2F2"
FONTE = "Calibri"

MOEDA = '"R$" #,##0.00'
PCT = "0.00%"

_titulo = Font(name=FONTE, bold=True, color="FFFFFF", size=12)
_cabecalho = Font(name=FONTE, bold=True, color="FFFFFF")
_entrada = Font(name=FONTE, color="0000FF")     # azul = valor que o usuário edita
_normal = Font(name=FONTE)
_negrito = Font(name=FONTE, bold=True)
_fill_titulo = PatternFill("solid", fgColor=AZUL)
_fill_cab = PatternFill("solid", fgColor=AZUL)
_fill_entrada = PatternFill("solid", fgColor="FFF2CC")  # amarelo suave = editável
_borda = Border(*[Side(style="thin", color="BFBFBF")] * 4)


def _mesclar_titulo(ws, celula, texto, ate_coluna):
    ws[celula] = texto
    ws[celula].font = _titulo
    ws[celula].fill = _fill_titulo
    linha = celula[1:]
    ws.merge_cells(f"{celula}:{ate_coluna}{linha}")


def _aba_dividas(wb, perfil: PerfilFinanceiro):
    ws = wb.create_sheet("Dívidas")
    _mesclar_titulo(ws, "A1", "DÍVIDAS", "I")

    cabecalhos = ["Credor", "Tipo", "Saldo devedor", "Taxa a.m.", "Taxa a.a.",
                  "Parcela", "Parc. restantes", "Custo total restante", "Juros restantes"]
    ws.append([])
    ws.append(cabecalhos)
    for cell in ws[3]:
        cell.font = _cabecalho
        cell.fill = _fill_cab
        cell.alignment = Alignment(horizontal="center", wrap_text=True)

    primeira = 4
    for i, d in enumerate(perfil.dividas):
        linha = primeira + i
        ws.cell(linha, 1, d.credor).font = _normal
        ws.cell(linha, 2, d.tipo).font = _normal
        ws.cell(linha, 3, round(d.saldo_devedor, 2)).font = _entrada     # entrada
        ws.cell(linha, 4, round(d.taxa_mensal, 6)).font = _entrada       # entrada
        # Taxa anual = (1+mensal)^12 - 1  (fórmula, referencia a coluna D)
        ws.cell(linha, 5, f"=(1+D{linha})^12-1").font = _normal
        ws.cell(linha, 6, round(d.parcela, 2)).font = _entrada           # entrada
        ws.cell(linha, 7, d.parcelas_restantes).font = _entrada          # entrada
        ws.cell(linha, 8, f"=F{linha}*G{linha}").font = _normal          # custo total
        ws.cell(linha, 9, f"=MAX(H{linha}-C{linha},0)").font = _normal   # juros restantes

        for col in (3, 6, 8, 9):
            ws.cell(linha, col).number_format = MOEDA
        for col in (4, 5):
            ws.cell(linha, col).number_format = PCT

    ultima = primeira + len(perfil.dividas) - 1
    # Linha de total
    tot = ultima + 1
    ws.cell(tot, 2, "TOTAL").font = _negrito
    for col, letra in ((3, "C"), (6, "F"), (8, "H"), (9, "I")):
        c = ws.cell(tot, col, f"=SUM({letra}{primeira}:{letra}{ultima})")
        c.font = _negrito
        c.number_format = MOEDA

    larguras = [22, 30, 16, 10, 10, 14, 14, 20, 18]
    for i, w in enumerate(larguras, start=1):
        ws.column_dimensions[chr(64 + i)].width = w

    # Gráfico de barras: saldo devedor por credor
    if perfil.dividas:
        chart = BarChart()
        chart.title = "Saldo devedor por dívida"
        chart.type = "bar"
        dados = Reference(ws, min_col=3, min_row=3, max_row=ultima)
        cats = Reference(ws, min_col=1, min_row=primeira, max_row=ultima)
        chart.add_data(dados, titles_from_data=True)
        chart.set_categories(cats)
        chart.legend = None
        chart.height = 6
        chart.width = 14
        ws.add_chart(chart, f"A{tot + 3}")

    return ws, primeira, ultima


def _aba_diagnostico(wb, perfil: PerfilFinanceiro, primeira: int, ultima: int):
    ws = wb.active
    ws.title = "Diagnóstico"
    _mesclar_titulo(ws, "A1", "DIAGNÓSTICO FINANCEIRO", "C")

    linhas = [
        ("Renda líquida mensal", round(perfil.renda_liquida, 2), True, MOEDA),
        ("Despesas fixas", round(perfil.despesas_fixas, 2), True, MOEDA),
        ("Despesas variáveis", round(perfil.despesas_variaveis, 2), True, MOEDA),
        ("Reserva de emergência", round(perfil.reserva_emergencia, 2), True, MOEDA),
        ("Saldo de FGTS", round(perfil.saldo_fgts, 2), True, MOEDA),
    ]
    r = 3
    for rotulo, valor, entrada, fmt in linhas:
        ws.cell(r, 1, rotulo).font = _negrito
        c = ws.cell(r, 2, valor)
        c.font = _entrada if entrada else _normal
        if entrada:
            c.fill = _fill_entrada
        c.number_format = fmt
        r += 1

    # Derivados (fórmulas). Total de parcelas vem da aba Dívidas.
    faixa_parcelas = f"'Dívidas'!F{primeira}:F{ultima}"
    faixa_saldos = f"'Dívidas'!C{primeira}:C{ultima}"
    derivados = [
        ("Total de parcelas/mês", f"=SUM({faixa_parcelas})", MOEDA),
        ("Despesas totais", "=B4+B5", MOEDA),
        ("Fluxo de caixa (sobra/mês)", "=B3-B9-B8", MOEDA),
        ("Saldo devedor total", f"=SUM({faixa_saldos})", MOEDA),
        ("Comprometimento de renda", "=B8/B3", PCT),
    ]
    for rotulo, formula, fmt in derivados:
        ws.cell(r, 1, rotulo).font = _negrito
        c = ws.cell(r, 2, formula)
        c.font = _normal
        c.number_format = fmt
        r += 1

    ws.column_dimensions["A"].width = 28
    ws.column_dimensions["B"].width = 18

    nota = ws.cell(r + 1, 1,
                   "Células em amarelo são entradas: altere-as e os indicadores "
                   "recalculam automaticamente ao abrir no Excel.")
    nota.font = Font(name=FONTE, italic=True, size=9, color="808080")
    return ws


def _aba_estrategias(wb, perfil: PerfilFinanceiro, extra_mensal: float,
                     taxa_alvo: float):
    ws = wb.create_sheet("Estratégias")
    _mesclar_titulo(ws, "A1", "ESTRATÉGIAS DE QUITAÇÃO", "E")

    comp = comparar_estrategias(perfil, extra_mensal)
    ws.append([])
    ws.cell(3, 1, "Pagamento extra considerado por mês:").font = _negrito
    c = ws.cell(3, 2, round(extra_mensal, 2))
    c.number_format = MOEDA
    c.font = _entrada

    ws.append([])
    ws.append(["Método", "Meses até quitar", "Total de juros pagos", "Ordem de ataque"])
    for cell in ws[5]:
        cell.font = _cabecalho
        cell.fill = _fill_cab

    def _linha_metodo(nome, res):
        meses = res["meses"] if res["quitavel"] else "não quita c/ este valor"
        ordem = " → ".join(res["ordem"])
        ws.append([nome, meses, res["juros_pagos"], ordem])
        ws.cell(ws.max_row, 3).number_format = MOEDA

    _linha_metodo("Avalanche (maior juro primeiro)", comp["avalanche"])
    _linha_metodo("Bola de neve (menor saldo primeiro)", comp["bola_de_neve"])

    # Portabilidade
    ws.append([])
    ws.append([])
    lin_port = ws.max_row + 1
    ws.cell(lin_port, 1,
            f"Portabilidade — economia se migrar para {taxa_alvo*100:.2f}% a.m.").font = _negrito
    ws.append(["Credor", "Tipo", "Parcela atual", "Parcela nova", "Economia total"])
    for cell in ws[ws.max_row]:
        cell.font = _cabecalho
        cell.fill = _fill_cab
    for o in oportunidades_portabilidade(perfil, taxa_alvo):
        ws.append([o["credor"], o["tipo"], o["parcela_atual"],
                   o["parcela_nova"], o["economia_total"]])
        for col in (3, 4, 5):
            ws.cell(ws.max_row, col).number_format = MOEDA

    for i, w in enumerate([34, 30, 16, 16, 16], start=1):
        ws.column_dimensions[chr(64 + i)].width = w
    return ws


def gerar_planilha(perfil: PerfilFinanceiro, caminho_saida: str,
                   extra_mensal: float = 0.0, taxa_alvo_mensal: float = 0.018) -> str:
    """Monta e salva a planilha completa. Retorna o caminho salvo."""
    wb = Workbook()
    _, primeira, ultima = _aba_dividas(wb, perfil)
    _aba_diagnostico(wb, perfil, primeira, ultima)
    _aba_estrategias(wb, perfil, extra_mensal, taxa_alvo_mensal)
    # Ordena as abas: Diagnóstico primeiro
    wb.move_sheet("Diagnóstico", -(wb.sheetnames.index("Diagnóstico")))
    wb.save(caminho_saida)
    return caminho_saida
