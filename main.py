"""
Ponto de entrada do Helper Financeiro.

Execute com:  python main.py
"""
import os
import sys

# Garante que a raiz do projeto está no path (importante quando vira .exe).
RAIZ = os.path.dirname(os.path.abspath(__file__))
if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)

from gui.app import main

if __name__ == "__main__":
    main()
