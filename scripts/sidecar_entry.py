"""Entrada do PyInstaller para o sidecar (T-1001).

O PyInstaller analisa um SCRIPT, não um pacote — `python -m sidecar` não é uma
entrada válida para o freeze. Este stub importa o pacote normalmente (o que
preserva os imports relativos de `sidecar/__main__.py`) e delega ao `main()`.
"""
from sidecar.__main__ import main

if __name__ == "__main__":
    main()
