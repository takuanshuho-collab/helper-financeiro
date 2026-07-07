"""
Ponto de entrada do Helper Financeiro.

Desde o ciclo v2.3 (ADR-0009 / T-1004), a interface OFICIAL é a GUI web
(Electron + React falando com o núcleo Python via sidecar). A janela tkinter
clássica segue disponível como fallback até ser aposentada.

    python main.py            → GUI web (npm start em gui_web/)
    python main.py --tkinter  → GUI clássica (fallback)

Usuário final: use o instalador gerado pelo `npm run dist` (T-1001) — o exe
"Helper Financeiro" já embute o sidecar congelado, sem precisar de Python.
"""
import os
import shutil
import subprocess
import sys

# Garante que a raiz do projeto está no path (importante quando vira .exe).
RAIZ = os.path.dirname(os.path.abspath(__file__))
if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)


def _abrir_gui_web() -> int | None:
    """Sobe a GUI web (`npm start` em gui_web/). Devolve None se indisponível.

    Indisponível = sem `npm` no PATH ou sem `node_modules` instalado. O exe
    congelado (PyInstaller) também não tenta: ele é a GUI clássica empacotada.
    """
    if getattr(sys, "frozen", False):
        return None
    npm = shutil.which("npm")
    gui = os.path.join(RAIZ, "gui_web")
    if not npm or not os.path.isdir(os.path.join(gui, "node_modules")):
        return None
    return subprocess.call([npm, "start"], cwd=gui)


def _abrir_tkinter() -> None:
    from gui.app import main as main_tkinter
    main_tkinter()


def main() -> None:
    if "--tkinter" in sys.argv:
        _abrir_tkinter()
        return
    if _abrir_gui_web() is None:
        print("GUI web indisponível (npm/node_modules não encontrados em gui_web/).")
        print("Para instalá-la: cd gui_web && npm install")
        print("Abrindo a GUI clássica (tkinter) como fallback...")
        _abrir_tkinter()


if __name__ == "__main__":
    main()
