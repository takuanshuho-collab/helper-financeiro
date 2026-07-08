"""
Motor de OCR local para documentos escaneados/imagem (ADR-0015, REQ-F-024/NF-006).

Envolve o RapidOCR (os modelos PaddleOCR PP-OCRv6 em ONNX Runtime), rodando
**100% na máquina**: a imagem/PDF com PII nunca sai do computador (H2/H7) e os
modelos são **empacotados** (sem download em execução — REQ-NF-006). PDF
escaneado é rasterizado com o **PyMuPDF já presente**. A saída é texto ordenado
pela leitura do layout, que alimenta a extração (ADR-0010) e a importação
(ADR-0014).

O OCR NÃO interpreta: reconhece texto + caixas + confiança. Quem diz qual número
é a prestação é a LLM + o verificador (ADR-0007/0010). O texto de OCR é
**entrada não-confiável** (P5). Sem o motor disponível, o chamador degrada (P8).
"""
from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from core.documento import FonteDocumento, fonte_por_extensao

log = logging.getLogger(__name__)

# Modelos ONNX que a nossa configuração (`_params_medium` + o classificador
# padrão do rapidocr) exige em runtime. São a fonte única para o passo de build
# (`scripts/preparar_ocr.py`) e para a trave do `SidecarHF.spec`: o binário
# congelado precisa trazer estes três arquivos ou o OCR não roda (REQ-NF-006).
#   det/rec: PP-OCRv6 medium (o que `_params_medium` seleciona; lang latino/pt)
#   cls:     PP-OCRv4 mobile (orientação de linha; default do rapidocr, não trocado)
MODELOS_OCR_NECESSARIOS = (
    "PP-OCRv6_det_medium.onnx",
    "PP-OCRv6_rec_medium.onnx",
    "ch_ppocr_mobile_v2.0_cls_mobile.onnx",
)


def diretorio_modelos_ocr() -> Path:
    """Diretório onde o `rapidocr` guarda/resolve os `.onnx` (dentro do pacote).

    É o `model_root_dir` padrão do rapidocr (`<pacote>/models`); o
    `OrtInferSession` monta `model_root_dir / <nome>.onnx` e só baixa se faltar.
    """
    import rapidocr

    return Path(rapidocr.__file__).resolve().parent / "models"


# Rasterização: DPI que dá sinal ao OCR sem estourar memória em documento longo.
DPI_OCR = 200
# Confiança mínima por linha; abaixo disso a linha é ruído e vira descarte.
SCORE_MINIMO = 0.5
# Tolerância vertical (fração da altura da caixa) p/ agrupar caixas na MESMA
# linha ao reconstruir a ordem de leitura.
TOLERANCIA_LINHA = 0.6

def _params_medium() -> dict[str, Any]:
    """Config alvo: PaddleOCR PP-OCRv6 calibre **medium** (o "server"), detecção
    multilíngue e reconhecimento **latino** (o português cai no modelo latino) —
    supera o PP-OCRv5_server em scan degradado.

    O PP-OCRv6 medium é um único modelo multilíngue (`multi_PP-OCRv6_*_medium`);
    `lang_type='pt'` é validado como suportado e é o correto para documento
    brasileiro. Import preguiçoso: o rapidocr exige que `ocr_version`/`model_type`
    sejam **instâncias de Enum** (não strings), e carregá-lo puxa onnxruntime/cv2
    — por isso não fica no topo do módulo.
    """
    from rapidocr import ModelType, OCRVersion

    return {
        "Global.text_score": SCORE_MINIMO,
        "Det.ocr_version": OCRVersion.PPOCRV6,
        "Det.model_type": ModelType.MEDIUM,
        "Det.lang_type": "pt",
        "Rec.ocr_version": OCRVersion.PPOCRV6,
        "Rec.model_type": ModelType.MEDIUM,
        "Rec.lang_type": "pt",
    }


class OCRIndisponivel(RuntimeError):
    """Motor de OCR ausente ou falho — o chamador degrada (P8)."""


@dataclass(frozen=True)
class LinhaOCR:
    """Uma caixa de texto reconhecida, com o mínimo para ordenar a leitura."""

    texto: str
    topo: float
    esquerda: float
    altura: float
    score: float


@dataclass(frozen=True)
class ResultadoOCR:
    texto: str
    linhas: tuple[LinhaOCR, ...] = ()
    paginas: int = 0
    confianca_media: float = 0.0


class Motor(Protocol):
    def reconhecer(self, imagem: bytes) -> list[LinhaOCR]: ...


# ------------------------------------------------------------ ordem de leitura
def reconstruir_texto(linhas: Sequence[LinhaOCR]) -> str:
    """Ordena as caixas pela leitura (cima→baixo, esquerda→direita) e junta.

    Pura e testável (sem OCR): caixas com topo próximo — dentro de
    `TOLERANCIA_LINHA` da altura da caixa de referência — formam a mesma linha,
    unidas por espaço; linhas distintas são separadas por `\\n`.
    """
    validas = [ln for ln in linhas if ln.texto.strip()]
    if not validas:
        return ""

    ordenadas = sorted(validas, key=lambda ln: (ln.topo, ln.esquerda))
    grupos: list[list[LinhaOCR]] = [[ordenadas[0]]]
    for ln in ordenadas[1:]:
        ref = grupos[-1][-1]
        if abs(ln.topo - ref.topo) <= TOLERANCIA_LINHA * max(ref.altura, 1.0):
            grupos[-1].append(ln)
        else:
            grupos.append([ln])

    return "\n".join(
        " ".join(x.texto.strip() for x in sorted(g, key=lambda ln: ln.esquerda))
        for g in grupos
    )


def _linhas_do_resultado(resultado: Any) -> list[LinhaOCR]:
    """Normaliza a saída do RapidOCR (objeto novo `.boxes/.txts/.scores` ou o
    formato clássico iterável de `[box, texto, score]`) em `LinhaOCR`."""
    if resultado is None:
        return []

    boxes = getattr(resultado, "boxes", None)
    txts = getattr(resultado, "txts", None)
    if boxes is not None and txts is not None:
        scores = getattr(resultado, "scores", None) or [1.0] * len(txts)
        trios: Any = zip(boxes, txts, scores, strict=False)
    else:
        trios = resultado  # iterável de (box, texto, score)

    linhas: list[LinhaOCR] = []
    for box, texto, score in trios:
        if float(score) < SCORE_MINIMO:
            continue
        ys = [float(p[1]) for p in box]
        xs = [float(p[0]) for p in box]
        linhas.append(
            LinhaOCR(
                texto=str(texto),
                topo=min(ys),
                esquerda=min(xs),
                altura=max(ys) - min(ys),
                score=float(score),
            )
        )
    return linhas


# ------------------------------------------------------------------ motor real
class RapidOCRMotor:
    """Motor real: RapidOCR + PP-OCRv6 medium em ONNX Runtime, local (H2/H7)."""

    def __init__(self, params: dict[str, Any] | None = None) -> None:
        from rapidocr import RapidOCR  # import local: só carrega quando usado

        self._engine = RapidOCR(params=params if params is not None else _params_medium())

    def reconhecer(self, imagem: bytes) -> list[LinhaOCR]:
        return _linhas_do_resultado(self._engine(imagem))


def obter_motor(params: dict[str, Any] | None = None) -> Motor:
    """Fábrica: devolve o motor real ou levanta `OCRIndisponivel` (o chamador
    degrada para preenchimento manual, P8)."""
    try:
        return RapidOCRMotor(params=params)
    except ImportError as e:
        raise OCRIndisponivel(f"RAPIDOCR_AUSENTE:{e}") from e
    except Exception as e:  # noqa: BLE001 — qualquer falha de init vira P8
        log.warning("Motor de OCR indisponível: %s", e)
        raise OCRIndisponivel(f"OCR_FALHOU:{type(e).__name__}") from e


# ----------------------------------------------------------------- rasterização
def _imagens_do_documento(dados: bytes, nome: str) -> list[bytes]:
    """PDF → uma imagem PNG por página (rasterizada via PyMuPDF); arquivo de
    imagem → os próprios bytes. Tudo em memória (H2)."""
    if fonte_por_extensao(nome) is FonteDocumento.IMAGEM:
        return [dados]

    import pymupdf

    imagens: list[bytes] = []
    with pymupdf.open(stream=dados, filetype="pdf") as doc:
        for pagina in doc:
            imagens.append(pagina.get_pixmap(dpi=DPI_OCR).tobytes("png"))
    return imagens


def ocr_documento(dados: bytes, nome: str, motor: Motor | None = None) -> ResultadoOCR:
    """Entrada principal: OCRiza um documento escaneado/imagem e devolve o texto
    reconstruído pela leitura do layout.

    `motor=None` usa o RapidOCR real (`obter_motor`); os testes injetam um motor
    falso. Levanta `OCRIndisponivel` se o motor real faltar (P8 no chamador).
    """
    motor = motor or obter_motor()
    imagens = _imagens_do_documento(dados, nome)

    todas: list[LinhaOCR] = []
    partes: list[str] = []
    for imagem in imagens:
        linhas = motor.reconhecer(imagem)
        todas.extend(linhas)
        partes.append(reconstruir_texto(linhas))

    conf = sum(ln.score for ln in todas) / len(todas) if todas else 0.0
    return ResultadoOCR(
        texto="\n\n".join(p for p in partes if p),
        linhas=tuple(todas),
        paginas=len(imagens),
        confianca_media=round(conf, 4),
    )
