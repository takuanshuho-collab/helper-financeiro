"""Prepara os modelos de OCR para o empacotamento (T-1404, ADR-0015).

O wheel do `rapidocr` só embarca os modelos PP-OCRv6 *tiny/small* + o classificador;
os modelos **medium** que usamos (`agent.ocr._params_medium`) são baixados na 1ª
execução. Este script os materializa no diretório de modelos do `rapidocr`
DENTRO da venv, para que o `SidecarHF.spec` os colete como *data files* e o
binário congelado rode **100% offline** (REQ-NF-006): nenhum download no
computador do usuário.

Rede é usada **só aqui, no build** (a máquina de build tem internet); é
idempotente — se o `.onnx` já existe com o SHA certo, o `rapidocr` pula o
download. Rode antes do PyInstaller:

    uv run python scripts/preparar_ocr.py
    uv run --group build pyinstaller SidecarHF.spec --noconfirm
"""
from __future__ import annotations

import sys
from pathlib import Path

# Rodar o script direto põe scripts/ no sys.path, não a raiz — corrige aqui.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.ocr import (  # noqa: E402
    MODELOS_OCR_NECESSARIOS,
    diretorio_modelos_ocr,
    obter_motor,
)


def main() -> int:
    destino = diretorio_modelos_ocr()
    print(f"Diretório de modelos do RapidOCR: {destino}")

    # Instanciar o motor medium dispara o resolvedor do RapidOCR: para cada
    # sub-modelo (det/rec/cls) ele confere o arquivo local e baixa só o que
    # faltar. Uma vez criado, os três .onnx estão no lugar.
    print("Garantindo os modelos PP-OCRv6 medium (pode baixar na 1ª vez)…")
    obter_motor()

    faltando = [n for n in MODELOS_OCR_NECESSARIOS if not (destino / n).is_file()]
    if faltando:
        print(f"ERRO: modelos ausentes após a preparação: {', '.join(faltando)}", file=sys.stderr)
        return 1

    for nome in MODELOS_OCR_NECESSARIOS:
        tamanho = (destino / nome).stat().st_size / 1024 / 1024
        print(f"  [ok] {nome} ({tamanho:.1f} MB)")
    print("Modelos de OCR prontos para o empacotamento.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
