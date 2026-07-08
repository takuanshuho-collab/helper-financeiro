"""Detector determinístico de fonte + pré-marcação por tipo (ADR-0015, T-1401)."""
from __future__ import annotations

import pytest

from core.documento import (
    FonteDocumento,
    anotar_por_tipo,
    classificar_documento_bytes,
    classificar_fonte,
    fonte_por_extensao,
    precisa_ocr,
    tem_camada_de_texto,
)


# ----------------------------------------------------------- densidade de texto
def test_tem_camada_de_texto_denso_e_vazio():
    denso = "Contrato de crédito. " * 40  # ~800 chars úteis numa página
    assert tem_camada_de_texto(denso, paginas=1) is True
    assert tem_camada_de_texto("   \n  \t ", paginas=1) is False
    assert tem_camada_de_texto("", paginas=3) is False


def test_tem_camada_de_texto_media_por_pagina():
    # 300 chars úteis divididos por 5 páginas = 60/página < 100 ⇒ sem camada.
    texto = "x" * 300
    assert tem_camada_de_texto(texto, paginas=5) is False
    assert tem_camada_de_texto(texto, paginas=2) is True  # 150/página ≥ 100


# ---------------------------------------------------------------- por extensão
@pytest.mark.parametrize("nome", ["foto.jpg", "SCAN.PNG", "doc.jpeg", "x.tiff", "y.webp"])
def test_fonte_por_extensao_imagem(nome):
    assert fonte_por_extensao(nome) is FonteDocumento.IMAGEM


@pytest.mark.parametrize("nome", ["contrato.pdf", "notas.txt", "semext"])
def test_fonte_por_extensao_nao_decide(nome):
    assert fonte_por_extensao(nome) is None


# ------------------------------------------------------------- classificar_fonte
def test_classificar_fonte_imagem_ignora_texto():
    # Extensão de imagem vence mesmo que (por acaso) venha texto junto.
    assert classificar_fonte("foto.png", "qualquer coisa", 1) is FonteDocumento.IMAGEM


def test_classificar_fonte_pdf_com_e_sem_texto():
    denso = "Cláusula primeira. " * 30
    assert classificar_fonte("contrato.pdf", denso, 1) is FonteDocumento.TEXTO
    assert classificar_fonte("contrato.pdf", "", 3) is FonteDocumento.ESCANEADO


def test_precisa_ocr():
    assert precisa_ocr(FonteDocumento.ESCANEADO) is True
    assert precisa_ocr(FonteDocumento.IMAGEM) is True
    assert precisa_ocr(FonteDocumento.TEXTO) is False


# ------------------------------------------------------ integração com PDF real
def test_classificar_documento_bytes_imagem_por_extensao():
    # Não abre o arquivo: decide pela extensão (bytes irrelevantes).
    assert classificar_documento_bytes(b"\xff\xd8\xff", "recibo.jpg") is FonteDocumento.IMAGEM


def test_classificar_documento_bytes_pdf_com_texto():
    pymupdf = pytest.importorskip("pymupdf")
    doc = pymupdf.open()
    page = doc.new_page()
    for i in range(20):
        page.insert_text((72, 72 + i * 18), "Contrato de emprestimo consignado linha " + str(i))
    dados = doc.tobytes()
    doc.close()
    assert classificar_documento_bytes(dados, "contrato.pdf") is FonteDocumento.TEXTO


def test_classificar_documento_bytes_pdf_escaneado():
    pymupdf = pytest.importorskip("pymupdf")
    doc = pymupdf.open()
    doc.new_page()  # página sem camada de texto (simula digitalização)
    dados = doc.tobytes()
    doc.close()
    assert classificar_documento_bytes(dados, "scan.pdf") is FonteDocumento.ESCANEADO


def test_classificar_documento_bytes_pdf_ilegivel_vira_escaneado():
    assert classificar_documento_bytes(b"nao sou um pdf", "x.pdf") is FonteDocumento.ESCANEADO


# ---------------------------------------------------------- pré-marcação por tipo
def test_anotar_valor_monetario():
    assert anotar_por_tipo("Prestação de R$ 600,00") == "Prestação de <valor>R$ 600,00</valor>"
    assert anotar_por_tipo("Total 1.234,56 hoje") == "Total <valor>1.234,56</valor> hoje"


def test_anotar_percentual_nao_vira_valor():
    assert anotar_por_tipo("Juros de 2,50% a.m.") == "Juros de <percentual>2,50%</percentual> a.m."
    assert anotar_por_tipo("CET 12% a.a.") == "CET <percentual>12%</percentual> a.a."


def test_anotar_datas_br_e_iso():
    assert anotar_por_tipo("Vencimento 01/06/2026.") == "Vencimento <data>01/06/2026</data>."
    assert anotar_por_tipo("Ref 2026-06-01") == "Ref <data>2026-06-01</data>"
    assert anotar_por_tipo("em 10-07-26") == "em <data>10-07-26</data>"


def test_anotar_inteiro_solto_nao_vira_valor():
    # Número de parcelas não tem R$ nem casas decimais ⇒ fica cru.
    assert anotar_por_tipo("pagável em 96 vezes") == "pagável em 96 vezes"


def test_anotar_linha_mista_preserva_ordem():
    entrada = "Parcela de R$ 899,47 (2,50% a.m.) a partir de 10/07/2026"
    esperado = (
        "Parcela de <valor>R$ 899,47</valor> "
        "(<percentual>2,50%</percentual> a.m.) "
        "a partir de <data>10/07/2026</data>"
    )
    assert anotar_por_tipo(entrada) == esperado


def test_anotar_texto_sem_candidatos_inalterado():
    assert anotar_por_tipo("Cláusula sem números aqui") == "Cláusula sem números aqui"
