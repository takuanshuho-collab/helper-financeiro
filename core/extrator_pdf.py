"""
Extração de dados de contratos de empréstimo em PDF.

Estratégia em duas etapas (funil), no mesmo espírito do ÓCULO:
  1) `extrair_texto_pdf`  -> pega o texto do PDF (contratos digitais têm texto).
  2) `parsear_campos`     -> aplica regex para achar valor, taxa, parcelas etc.

A extração é SEMPRE "melhor esforço": o resultado é usado para PRÉ-PREENCHER
o formulário, e o usuário confere e corrige antes de usar. Nunca confie cegamente.

Observação: contratos escaneados (imagem, sem texto) não são cobertos aqui —
precisariam de OCR. A função avisa quando o PDF não tem texto extraível.
"""
from __future__ import annotations

import re

from .utils import parse_taxa, parse_valor


def _texto_das_paginas(pdf: object) -> str:
    return "\n".join(pagina.extract_text() or "" for pagina in pdf.pages)  # type: ignore[attr-defined]


def extrair_texto_pdf(caminho: str) -> str:
    """Lê todo o texto de um PDF. Retorna string vazia se não houver texto."""
    import pdfplumber  # import local: só carrega quando realmente for usar

    with pdfplumber.open(caminho) as pdf:
        return _texto_das_paginas(pdf)


def extrair_texto_pdf_bytes(dados: bytes) -> str:
    """Lê o texto de um PDF em memória — sem tocar o disco.

    A extração roda no sidecar local (H2): o documento bruto pode conter PII e
    jamais é persistido em arquivo nem enviado à nuvem.
    """
    import io

    import pdfplumber

    with pdfplumber.open(io.BytesIO(dados)) as pdf:
        return _texto_das_paginas(pdf)


def extrair_markdown_pdf_bytes(dados: bytes) -> str:
    """Converte um PDF em Markdown em memória (pymupdf4llm), preservando a
    estrutura — títulos e sobretudo TABELAS (grade de taxas, cronograma de
    parcelas). O Markdown dá muito mais sinal à LLM de extração do que o texto
    plano (ADR-0010).

    Melhor esforço: devolve "" se o pymupdf4llm não estiver disponível ou falhar
    — o chamador cai no `extrair_texto_pdf_bytes` (pdfplumber). Tudo local, sem
    tocar o disco (H2).
    """
    try:
        import pymupdf
        import pymupdf4llm
    except ImportError:
        return ""
    try:
        with pymupdf.open(stream=dados, filetype="pdf") as doc:
            return pymupdf4llm.to_markdown(doc)
    except Exception:  # noqa: BLE001 — melhor esforço; o fallback é o texto plano
        return ""


# Cada campo tem uma lista de padrões, do mais específico para o mais genérico.
# O primeiro que casar vence.
_PADROES = {
    "valor_financiado": [
        r"valor\s+(?:total\s+)?financiad[oa][:\s]*R?\$?\s*(\d[\d\.,]*)",
        r"valor\s+do\s+cr[ée]dito[:\s]*R?\$?\s*(\d[\d\.,]*)",
        r"valor\s+liberad[oa][:\s]*R?\$?\s*(\d[\d\.,]*)",
        r"principal[:\s]*R?\$?\s*(\d[\d\.,]*)",
        # Resumo tabular achatado pelo extrator de texto (rótulo numa linha,
        # valor na SEGUINTE) — ex. Itaú: "Total financiado ...\nR$ 46.533,20".
        r"total\s+financiad[oa][^\n]*\n\s*R?\$?\s*(\d[\d\.,]*)",
        r"valor\s+a\s+receber[^\n]*\n\s*R?\$?\s*(\d[\d\.,]*)",
    ],
    "valor_liberado": [
        r"valor\s+l[íi]quido\s+(?:liberad[oa]|credit[oa]d[oa])[:\s]*R?\$?\s*(\d[\d\.,]*)",
        r"valor\s+liberad[oa][:\s]*R?\$?\s*(\d[\d\.,]*)",
    ],
    "taxa_mensal": [
        r"taxa\s+de\s+juros?\s*(?:remunerat[óo]rios?)?[^\d%]{0,30}?(\d[\d\.,]*)\s*%\s*a[o]?\.?\s*m",
        r"(\d[\d\.,]*)\s*%\s*a[o]?\.?\s*m[êe]?s?",
    ],
    "taxa_anual": [
        r"taxa\s+de\s+juros?\s*(?:remunerat[óo]rios?)?[^\d%]{0,30}?(\d[\d\.,]*)\s*%\s*a[o]?\.?\s*a",
        r"(\d[\d\.,]*)\s*%\s*a[o]?\.?\s*an[o]?",
    ],
    "cet_anual": [
        r"cet[^\d%]{0,30}?(\d[\d\.,]*)\s*%\s*a[o]?\.?\s*a",
        r"custo\s+efetivo\s+total[^\d%]{0,30}?(\d[\d\.,]*)\s*%",
    ],
    "num_parcelas": [
        r"(?:em\s+)?(\d{1,3})\s*(?:parcelas|presta[çc][õo]es|vezes)",
        r"(?:quantidade|n[úu]mero)\s+de\s+parcelas[:\s]*(\d{1,3})",
        # Notação compacta dos resumos de contrato: "96x de R$ 899,47".
        r"(\d{1,3})\s*x\s+de\s+R?\$",
    ],
    "valor_parcela": [
        r"valor\s+d[ae]\s+(?:parcela|presta[çc][ãa]o)[:\s]*R?\$?\s*(\d[\d\.,]*)",
        r"parcelas?\s+(?:mensais\s+)?de[:\s]*R?\$?\s*(\d[\d\.,]*)",
        r"presta[çc][õo]es\s+(?:mensais\s+)?de[:\s]*R?\$?\s*(\d[\d\.,]*)",
        r"\d{1,3}\s*x\s+de\s+R?\$?\s*(\d[\d\.,]*)",
    ],
}

_PADRAO_TIPO = [
    ("Consignado", r"consignad[oa]"),
    ("CDC (Crédito Direto ao Consumidor)", r"cr[ée]dito\s+direto\s+ao\s+consumidor|\bcdc\b|aliena[çc][ãa]o\s+fiduci[áa]ria"),
    ("Financiamento", r"financiamento"),
    ("Cartão de crédito", r"cart[ãa]o\s+de\s+cr[ée]dito"),
]


def _buscar(padroes: list[str], texto: str) -> str | None:
    for p in padroes:
        m = re.search(p, texto, re.IGNORECASE)
        if m:
            return m.group(1)
    return None


def parsear_campos(texto: str) -> dict:
    """Aplica os padrões e devolve os campos encontrados (None quando não achar).

    Valores numéricos já vêm convertidos: dinheiro em float, taxas em decimal.
    """
    baixo = texto.lower()

    tipo = None
    for rotulo, padrao in _PADRAO_TIPO:
        if re.search(padrao, baixo, re.IGNORECASE):
            tipo = rotulo
            break

    def num(campo):
        bruto = _buscar(_PADROES[campo], texto)
        return parse_valor(bruto) if bruto else None

    def taxa(campo):
        bruto = _buscar(_PADROES[campo], texto)
        return parse_taxa(bruto) if bruto else None

    parcelas_bruto = _buscar(_PADROES["num_parcelas"], texto)

    return {
        "tipo": tipo,
        "valor_financiado": num("valor_financiado"),
        "valor_liberado": num("valor_liberado"),
        "taxa_mensal": taxa("taxa_mensal"),
        "taxa_anual": taxa("taxa_anual"),
        "cet_anual": taxa("cet_anual"),
        "num_parcelas": int(parcelas_bruto) if parcelas_bruto else None,
        "valor_parcela": num("valor_parcela"),
    }


def extrair_contrato(caminho: str) -> dict:
    """Fluxo completo: lê o PDF e devolve os campos + o texto bruto.

    A chave 'aviso' traz uma mensagem quando o PDF parece não ter texto
    (provavelmente escaneado), para a interface orientar o usuário.
    """
    texto = extrair_texto_pdf(caminho)
    campos = parsear_campos(texto)
    campos["_texto_bruto"] = texto
    if len(texto.strip()) < 40:
        campos["aviso"] = (
            "O PDF parece não conter texto selecionável (provavelmente é uma "
            "imagem/digitalização). Preencha os campos manualmente."
        )
    return campos
