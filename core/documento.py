"""
Detecção determinística da FONTE de um documento e pré-marcação por tipo.

Antes de gastar OCR (caro) ou LLM, o `core` decide de forma **determinística**
se um documento já traz texto selecionável ou se é uma imagem/digitalização que
precisa passar pelo motor de OCR (ADR-0015). O "agente sinalizador" que bifurca
o fluxo é código testável offline, não um modelo.

E, sobre o texto (venha do PDF ou do OCR), `anotar_por_tipo` envolve os
CANDIDATOS a valor/data/percentual em marcações por TIPO — nunca semânticas:
quem diz qual `<valor>` é a prestação é a LLM + o verificador (ADR-0007/0010),
não o código. Texto anotado é mais fácil de citar e de verificar.
"""
from __future__ import annotations

import logging
import re
from enum import Enum
from pathlib import PurePath

log = logging.getLogger("helper_financeiro.documento")


class FonteDocumento(Enum):
    """Como o texto do documento pode ser obtido."""

    TEXTO = "texto"        # PDF com camada de texto selecionável — sem OCR
    ESCANEADO = "escaneado"  # PDF sem texto (imagem embutida) — precisa de OCR
    IMAGEM = "imagem"      # arquivo de imagem (JPG/PNG/...) — precisa de OCR


# Abaixo deste número de caracteres úteis por página, a página é considerada
# imagem/digitalização (um contrato digital tem centenas a milhares de chars).
LIMIAR_CHARS_POR_PAGINA = 100

_EXTENSOES_IMAGEM = frozenset(
    {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff", ".gif"}
)


def tem_camada_de_texto(texto: str, paginas: int) -> bool:
    """Densidade de texto suficiente para dispensar OCR.

    Pura e testável: decide pela média de caracteres úteis por página, não pelo
    total (um PDF longo e escaneado com um rodapé de texto não deve enganar).
    """
    uteis = len("".join(texto.split()))
    return uteis / max(paginas, 1) >= LIMIAR_CHARS_POR_PAGINA


def fonte_por_extensao(nome: str) -> FonteDocumento | None:
    """`IMAGEM` para arquivos de imagem; `None` quando a extensão não decide
    sozinha (PDF, .txt, sem extensão) e é preciso sondar o texto."""
    if PurePath(nome).suffix.lower() in _EXTENSOES_IMAGEM:
        return FonteDocumento.IMAGEM
    return None


def classificar_fonte(nome: str, texto: str, paginas: int) -> FonteDocumento:
    """Decisão determinística da fonte a partir do nome e do texto já extraído.

    - Extensão de imagem vence (nem se sonda texto).
    - PDF/afins com densidade suficiente ⇒ TEXTO.
    - Caso contrário ⇒ ESCANEADO (precisa de OCR).
    """
    por_ext = fonte_por_extensao(nome)
    if por_ext is not None:
        return por_ext
    if tem_camada_de_texto(texto, paginas):
        return FonteDocumento.TEXTO
    return FonteDocumento.ESCANEADO


def precisa_ocr(fonte: FonteDocumento) -> bool:
    """A bifurcação: imagem e PDF escaneado passam pelo OCR; TEXTO não."""
    return fonte in (FonteDocumento.ESCANEADO, FonteDocumento.IMAGEM)


def classificar_documento_bytes(dados: bytes, nome: str) -> FonteDocumento:
    """Conveniência: sonda o PDF em memória (H2, sem tocar o disco) e classifica.

    Para imagem, decide pela extensão sem abrir o arquivo. Para PDF, extrai o
    texto e mede a densidade. Melhor esforço: PDF ilegível pelo pdfplumber é
    tratado como ESCANEADO (deixa o OCR tentar).
    """
    por_ext = fonte_por_extensao(nome)
    if por_ext is not None:
        return por_ext

    import io

    import pdfplumber

    try:
        with pdfplumber.open(io.BytesIO(dados)) as pdf:
            paginas = len(pdf.pages)
            texto = "\n".join(p.extract_text() or "" for p in pdf.pages)
    except Exception as e:  # noqa: BLE001 — melhor esforço; PDF quebrado vira candidato a OCR
        # C-31: só o tipo — `dados` é o documento do usuário (PII), nunca no log.
        log.debug("Falha ao sondar PDF (candidato a OCR): %s", type(e).__name__)
        return FonteDocumento.ESCANEADO

    return classificar_fonte(nome, texto, paginas)


# --------------------------------------------------------------- pré-marcação
# Uma única passada com alternação: a PRIMEIRA alternativa que casa vence e o
# `re.sub` consome sem sobreposição (esquerda→direita). A ordem importa —
# percentual e data ANTES de valor, para "2,50%" não virar <valor>2,50</valor>%
# e "01/06/2026" não virar três valores. O grupo que casou nomeia a tag.
_RE_ANOTAR = re.compile(
    r"(?P<percentual>\d[\d.,]*\s*%)"
    r"|(?P<data>\d{2}[/.\-]\d{2}[/.\-]\d{2,4}|\d{4}-\d{2}-\d{2})"
    r"|(?P<valor>R\$\s*\d[\d.,]*|\d{1,3}(?:\.\d{3})*,\d{2})"
)


def _tag(m: re.Match[str]) -> str:
    for nome, casado in m.groupdict().items():
        if casado is not None:
            return f"<{nome}>{casado}</{nome}>"
    return m.group(0)  # pragma: no cover — a alternação sempre nomeia um grupo


def anotar_por_tipo(texto: str) -> str:
    """Envolve candidatos a valor/data/percentual em marcações por TIPO.

    Tags de tipo, não semânticas: `<valor>`, `<data>`, `<percentual>`. Não
    inventa qual campo é qual — só sinaliza os candidatos para a LLM e o
    verificador (ADR-0015 §C). Um inteiro solto ("em 96 vezes") NÃO vira
    `<valor>`: valor exige `R$` ou casas decimais.
    """
    return _RE_ANOTAR.sub(_tag, texto)
