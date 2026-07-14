"""Motor de OCR local (ADR-0015, T-1402).

Gate offline: helpers puros (ordem de leitura, parsing da saída) + um motor
FALSO injetado. O motor real (RapidOCR + modelos) baixa/carrega pesos e só roda
sob `HF_OCR_REAL=1` — nunca no gate nem no pre-commit.
"""
from __future__ import annotations

import os

import pytest

from agent.ocr import (
    LinhaOCR,
    Motor,
    OCRIndisponivel,
    RapidOCRMotor,
    ResultadoOCR,
    _imagens_do_documento,
    _linhas_do_resultado,
    obter_motor,
    ocr_documento,
    reconstruir_texto,
)


def _linha(texto, topo, esquerda, altura=20.0, score=0.99):
    return LinhaOCR(texto=texto, topo=topo, esquerda=esquerda, altura=altura, score=score)


class MotorFalso:
    """Devolve linhas fixas, ignorando os bytes — testa o pipeline sem modelos."""

    def __init__(self, linhas: list[LinhaOCR]):
        self.linhas = linhas
        self.chamadas = 0

    def reconhecer(self, imagem: bytes) -> list[LinhaOCR]:
        self.chamadas += 1
        return list(self.linhas)


# ------------------------------------------------------------ ordem de leitura
def test_reconstruir_uma_linha_ordena_por_esquerda():
    linhas = [_linha("mundo", topo=10, esquerda=80), _linha("Olá", topo=12, esquerda=10)]
    assert reconstruir_texto(linhas) == "Olá mundo"


def test_reconstruir_linhas_distintas_por_topo():
    linhas = [
        _linha("segunda", topo=60, esquerda=10),
        _linha("primeira", topo=10, esquerda=10),
    ]
    assert reconstruir_texto(linhas) == "primeira\nsegunda"


def test_reconstruir_agrupa_por_proximidade_vertical():
    # topo 10 e 18 (< 0,6*20=12) = mesma linha; topo 60 = outra.
    linhas = [
        _linha("A", topo=10, esquerda=10),
        _linha("B", topo=18, esquerda=40),
        _linha("C", topo=60, esquerda=10),
    ]
    assert reconstruir_texto(linhas) == "A B\nC"


def test_reconstruir_ignora_vazias_e_lista_vazia():
    assert reconstruir_texto([]) == ""
    assert reconstruir_texto([_linha("   ", topo=1, esquerda=1)]) == ""


# ------------------------------------------------------ parsing da saída do OCR
class _SaidaNova:
    def __init__(self, boxes, txts, scores):
        self.boxes, self.txts, self.scores = boxes, txts, scores


def test_linhas_do_resultado_formato_objeto_filtra_score_baixo():
    caixa = [[10, 10], [90, 10], [90, 30], [10, 30]]
    saida = _SaidaNova(
        boxes=[caixa, caixa],
        txts=["bom", "ruido"],
        scores=[0.95, 0.10],  # 0.10 < SCORE_MINIMO ⇒ descartado
    )
    linhas = _linhas_do_resultado(saida)
    assert [ln.texto for ln in linhas] == ["bom"]
    assert linhas[0].altura == 20.0


def test_linhas_do_resultado_formato_classico_e_none():
    caixa = [[0, 0], [50, 0], [50, 20], [0, 20]]
    classico = [[caixa, "texto", 0.9]]
    assert [ln.texto for ln in _linhas_do_resultado(classico)] == ["texto"]
    assert _linhas_do_resultado(None) == []


# --------------------------------------------------------- ocr_documento (fake)  # noqa: ERA001 — cabeçalho de seção, não código comentado
def test_ocr_documento_imagem_usa_bytes_direto():
    motor = MotorFalso([_linha("Recibo", topo=10, esquerda=10)])
    resultado = ocr_documento(b"\x89PNG-falso", "recibo.png", motor=motor)
    assert isinstance(resultado, ResultadoOCR)
    assert resultado.texto == "Recibo"
    assert resultado.paginas == 1
    assert motor.chamadas == 1
    assert resultado.confianca_media == pytest.approx(0.99)


def test_ocr_documento_pdf_rasteriza_paginas():
    pymupdf = pytest.importorskip("pymupdf")
    doc = pymupdf.open()
    doc.new_page()
    doc.new_page()
    dados = doc.tobytes()
    doc.close()

    motor = MotorFalso([_linha("linha", topo=10, esquerda=10)])
    resultado = ocr_documento(dados, "scan.pdf", motor=motor)
    assert resultado.paginas == 2
    assert motor.chamadas == 2  # uma chamada por página rasterizada


def test_imagens_do_documento_imagem_nao_abre_arquivo():
    # Bytes inválidos, mas imagem por extensão ⇒ devolvidos crus, sem decodificar.
    assert _imagens_do_documento(b"lixo", "foto.jpg") == [b"lixo"]


# ------------------------------------------------------------- degradação (P8)  # noqa: ERA001 — cabeçalho de seção, não código comentado
def test_obter_motor_ausente_levanta_ocr_indisponivel(monkeypatch):
    def _falha(self, params=None):
        raise ImportError("No module named 'rapidocr'")

    monkeypatch.setattr(RapidOCRMotor, "__init__", _falha)
    with pytest.raises(OCRIndisponivel, match="RAPIDOCR_AUSENTE"):
        obter_motor()


def test_motor_falso_satisfaz_protocolo():
    motor: Motor = MotorFalso([])
    assert motor.reconhecer(b"") == []


# --------------------------------------------------------- motor real (opt-in)
@pytest.mark.skipif(not os.getenv("HF_OCR_REAL"), reason="requer RapidOCR + modelos (HF_OCR_REAL=1)")
def test_motor_real_le_texto_de_imagem():
    pymupdf = pytest.importorskip("pymupdf")
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 100), "PRESTACAO R$ 600,00", fontsize=24)
    imagem = page.get_pixmap(dpi=200).tobytes("png")
    doc.close()

    resultado = ocr_documento(imagem, "prova.png")
    assert "600" in resultado.texto
    assert resultado.confianca_media > 0.5
