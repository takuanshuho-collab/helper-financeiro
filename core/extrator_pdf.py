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

from .utils import parse_valor, parse_taxa


def extrair_texto_pdf(caminho: str) -> str:
    """Lê todo o texto de um PDF. Retorna string vazia se não houver texto."""
    import pdfplumber  # import local: só carrega quando realmente for usar

    partes: list[str] = []
    with pdfplumber.open(caminho) as pdf:
        for pagina in pdf.pages:
            texto = pagina.extract_text() or ""
            partes.append(texto)
    return "\n".join(partes)


# Cada campo tem uma lista de padrões, do mais específico para o mais genérico.
# O primeiro que casar vence.
_PADROES = {
    "valor_financiado": [
        r"valor\s+(?:total\s+)?financiad[oa][:\s]*R?\$?\s*([\d\.,]+)",
        r"valor\s+do\s+cr[ée]dito[:\s]*R?\$?\s*([\d\.,]+)",
        r"valor\s+liberad[oa][:\s]*R?\$?\s*([\d\.,]+)",
        r"principal[:\s]*R?\$?\s*([\d\.,]+)",
    ],
    "valor_liberado": [
        r"valor\s+l[íi]quido\s+(?:liberad[oa]|credit[oa]d[oa])[:\s]*R?\$?\s*([\d\.,]+)",
        r"valor\s+liberad[oa][:\s]*R?\$?\s*([\d\.,]+)",
    ],
    "taxa_mensal": [
        r"taxa\s+de\s+juros?\s*(?:remunerat[óo]rios?)?[^\d%]{0,30}?([\d\.,]+)\s*%\s*a[o]?\.?\s*m",
        r"([\d\.,]+)\s*%\s*a[o]?\.?\s*m[êe]?s?",
    ],
    "taxa_anual": [
        r"taxa\s+de\s+juros?\s*(?:remunerat[óo]rios?)?[^\d%]{0,30}?([\d\.,]+)\s*%\s*a[o]?\.?\s*a",
        r"([\d\.,]+)\s*%\s*a[o]?\.?\s*an[o]?",
    ],
    "cet_anual": [
        r"cet[^\d%]{0,30}?([\d\.,]+)\s*%\s*a[o]?\.?\s*a",
        r"custo\s+efetivo\s+total[^\d%]{0,30}?([\d\.,]+)\s*%",
    ],
    "num_parcelas": [
        r"(?:em\s+)?(\d{1,3})\s*(?:parcelas|presta[çc][õo]es|vezes)",
        r"(?:quantidade|n[úu]mero)\s+de\s+parcelas[:\s]*(\d{1,3})",
    ],
    "valor_parcela": [
        r"valor\s+d[ae]\s+(?:parcela|presta[çc][ãa]o)[:\s]*R?\$?\s*([\d\.,]+)",
        r"parcelas?\s+(?:mensais\s+)?de[:\s]*R?\$?\s*([\d\.,]+)",
        r"presta[çc][õo]es\s+(?:mensais\s+)?de[:\s]*R?\$?\s*([\d\.,]+)",
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
