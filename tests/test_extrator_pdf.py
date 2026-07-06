"""Leitura de PDF em memória: texto plano (pdfplumber) e Markdown (pymupdf4llm).

Gera o PDF com o próprio pymupdf (sem tocar o disco) e confere os dois leitores
do `core.extrator_pdf` — o Markdown do pymupdf4llm dá mais sinal à LLM (ADR-0010).
"""
import pymupdf

from core.extrator_pdf import (
    extrair_markdown_pdf_bytes,
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


def test_regex_classico_no_texto_plano():
    campos = parsear_campos(extrair_texto_pdf_bytes(_pdf_contrato()))
    assert campos["tipo"] == "Consignado"
    assert abs(campos["taxa_mensal"] - 0.0142) < 1e-9
    assert campos["num_parcelas"] == 48
