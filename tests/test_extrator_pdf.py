"""Leitura de PDF em memória: texto plano (pdfplumber) e Markdown (pymupdf4llm).

Gera o PDF com o próprio pymupdf (sem tocar o disco) e confere os dois leitores
do `core.extrator_pdf` — o Markdown do pymupdf4llm dá mais sinal à LLM (ADR-0010).
"""
import pymupdf

from core.extrator_pdf import (
    extrair_contrato,
    extrair_markdown_pdf_bytes,
    extrair_texto_pdf,
    extrair_texto_pdf_bytes,
    parsear_campos,
)


def _pdf_contrato() -> bytes:
    doc = pymupdf.open()
    pagina = doc.new_page()
    y = 72
    for linha in (
        "CONTRATO DE EMPRESTIMO CONSIGNADO No 998877",
        "Credor: Banco Beta S.A.",
        "Saldo devedor atual: R$ 12.500,00",
        "Taxa de juros: 1,42% ao mes",
        "Prazo remanescente: 48 parcelas",
        "Valor da parcela mensal: R$ 360,00",
    ):
        pagina.insert_text((72, y), linha, fontsize=11)
        y += 22
    dados: bytes = doc.tobytes()
    doc.close()
    return dados


def test_texto_plano_le_todas_as_linhas():
    texto = extrair_texto_pdf_bytes(_pdf_contrato())
    assert "R$ 12.500,00" in texto
    assert "1,42% ao mes" in texto


def test_markdown_preserva_o_conteudo():
    md = extrair_markdown_pdf_bytes(_pdf_contrato())
    assert md  # pymupdf4llm disponível como dependência (ADR-0010)
    assert "12.500,00" in md
    assert "998877" in md


def test_markdown_bytes_invalidos_degrada_para_vazio():
    # Sem PDF válido, é melhor esforço: devolve "" e o chamador usa o texto plano.
    assert extrair_markdown_pdf_bytes(b"isto nao e um pdf") == ""


def test_markdown_sem_pymupdf4llm_instalado_degrada_para_vazio(monkeypatch):
    # C-33: ambiente sem a dependência opcional (ImportError) — melhor
    # esforço, sem propagar exceção; o chamador cai no texto plano.
    monkeypatch.setitem(__import__("sys").modules, "pymupdf4llm", None)
    assert extrair_markdown_pdf_bytes(_pdf_contrato()) == ""


def test_regex_classico_no_texto_plano():
    campos = parsear_campos(extrair_texto_pdf_bytes(_pdf_contrato()))
    assert campos["tipo"] == "Consignado"
    assert abs(campos["taxa_mensal"] - 0.0142) < 1e-9
    assert campos["num_parcelas"] == 48


# Resumo de contrato com layout tabular ACHATADO pelo extrator de texto:
# o rótulo fica numa linha e o valor na SEGUINTE (caso real: resumo Itaú).
DOC_RESUMO_TABULAR = """\
Contrato de empréstimo consignado
Resumo
Valor a receber Parcelamento
R$ 45.000,00 96x de R$ 899,47
Taxa de juros Total a pagar
1,42% ao mês e 18,43% ao ano R$ 86.349,12
IOF máximo Valor da renda após a contratação
R$ 1.533,20 (3,29% do total financiado) R$ 8.472,33
Total financiado Período de pagamento
R$ 46.533,20 Agosto/2026 a Julho/2034
"""


def test_regex_nao_captura_pontuacao_como_valor():
    """Bug real: 'com base no Valor Liberado. Caso...' capturava '.' ⇒ 0.0."""
    campos = parsear_campos(
        "O IOF Efetivo será calculado com base no Valor Liberado. Caso o IOF "
        "seja financiado, esse valor muda."
    )
    assert campos["valor_liberado"] is None
    assert campos["valor_financiado"] is None


def test_regex_resumo_tabular_estilo_itau():
    campos = parsear_campos(DOC_RESUMO_TABULAR)
    assert campos["tipo"] == "Consignado"
    # Rótulo numa linha, valor na seguinte — e NÃO o "total financiado" da
    # frase do IOF (R$ 8.472,33) nem o "valor a receber" (menos específico).
    assert campos["valor_financiado"] == 46533.20
    # Notação compacta "96x de R$ 899,47".
    assert campos["num_parcelas"] == 96
    assert campos["valor_parcela"] == 899.47
    assert abs(campos["taxa_mensal"] - 0.0142) < 1e-9


def test_extrair_texto_pdf_le_do_disco(tmp_path):
    # C-33: caminho de arquivo (extrair_texto_pdf), não só o de bytes em
    # memória (extrair_texto_pdf_bytes) — usado quando o contrato já está
    # salvo em disco (fluxo diferente do upload direto do sidecar).
    caminho = tmp_path / "contrato.pdf"
    caminho.write_bytes(_pdf_contrato())
    texto = extrair_texto_pdf(str(caminho))
    assert "R$ 12.500,00" in texto


def test_extrair_contrato_pdf_escaneado_sem_texto_avisa_o_usuario(tmp_path):
    """C-33: PDF sem texto extraível (página em branco, ex.: digitalização)
    não quebra o fluxo — devolve campos vazios e o aviso para preenchimento
    manual, nunca uma exceção."""
    doc = pymupdf.open()
    doc.new_page()  # página em branco: extract_text() devolve "" (ou None)
    caminho = tmp_path / "escaneado.pdf"
    doc.save(str(caminho))
    doc.close()

    resultado = extrair_contrato(str(caminho))

    assert "aviso" in resultado
    assert "digitalização" in resultado["aviso"] or "digitaliza" in resultado["aviso"]
    assert resultado["tipo"] is None
    assert resultado["valor_financiado"] is None
    assert resultado["_texto_bruto"] == ""


def test_extrair_contrato_pdf_com_texto_preenche_campos_sem_aviso(tmp_path):
    # Contrapartida do teste acima: com texto suficiente, nada de aviso —
    # os campos batem com o que o regex já sabe extrair (ADR-0010).
    caminho = tmp_path / "contrato.pdf"
    caminho.write_bytes(_pdf_contrato())

    resultado = extrair_contrato(str(caminho))

    assert "aviso" not in resultado
    assert resultado["tipo"] == "Consignado"
    assert resultado["num_parcelas"] == 48
    assert "R$ 12.500,00" in resultado["_texto_bruto"]
