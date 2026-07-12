# -*- mode: python ; coding: utf-8 -*-
# Freeze do SIDECAR (T-1001): FastAPI/uvicorn embrulhando o core determinístico.
#
#   uv run --group build pyinstaller SidecarHF.spec --noconfirm
#
# Sai em dist/sidecar-hf/ (onedir: inicialização rápida — o exe sobe a cada
# abertura do app Electron, então onefile pagaria a extração a cada launch).
# console=True é OBRIGATÓRIO: o handshake {"port","token"} vai pelo stdout e o
# Electron o lê (o spawn usa windowsHide, então nenhuma janela aparece).
#
# langgraph/llama-index congelam sem collects extras (validado no T-257/T-401).
import os
import sys

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules

datas = []
binaries = []
hiddenimports = []

# python-docx carrega templates .xml em runtime.
datas += collect_data_files('docx')

# pdfplumber/pdfminer trazem dados (cmaps) e submódulos dinâmicos.
for pacote in ('pdfplumber', 'pdfminer'):
    d, b, h = collect_all(pacote)
    datas += d
    binaries += b
    hiddenimports += h

# OCR local (ADR-0015, T-1404): os modelos .onnx são *data files* (rapidocr os
# resolve em <pacote>/models) e o onnxruntime + cv2 + shapely trazem binários
# nativos que o grafo de imports não pega sozinho. `collect_all` embarca dados,
# DLLs e submódulos (o engine onnxruntime é importado dinamicamente).
for pacote in ('rapidocr', 'onnxruntime', 'cv2', 'shapely'):
    d, b, h = collect_all(pacote)
    datas += d
    binaries += b
    hiddenimports += h

# Trave de empacotamento (REQ-NF-006): sem os modelos medium embarcados o OCR
# baixaria os pesos no computador do usuário. Falha o build CEDO, com o passo de
# correção, se algum .onnx obrigatório não estiver na venv (fonte única em
# agent.ocr). Rode `uv run python scripts/preparar_ocr.py` antes do PyInstaller.
sys.path.insert(0, os.path.abspath('.'))
from agent.ocr import MODELOS_OCR_NECESSARIOS, diretorio_modelos_ocr

_dir_modelos = diretorio_modelos_ocr()
_faltando = [n for n in MODELOS_OCR_NECESSARIOS if not (_dir_modelos / n).is_file()]
if _faltando:
    raise SystemExit(
        "Modelos de OCR ausentes para o freeze: "
        + ", ".join(_faltando)
        + f"\n  (esperados em {_dir_modelos})"
        + "\n  Rode antes: uv run python scripts/preparar_ocr.py"
    )

# Cofre (ADR-0016, M16): as dependências novas trazem binário nativo e/ou são
# importadas de formas que o grafo estático do PyInstaller não pega sozinho.
#   - sqlcipher3: binding do SQLCipher com DLL nativa (sqlcipher3-wheels) — sem
#     ela o `PRAGMA key` e a migração do cofre não sobem no exe congelado.
#     `collect_all` embarca o pacote + a DLL. O nome de import é `sqlcipher3`
#     (o pacote no PyPI é `sqlcipher3-wheels`, mas importa como sqlcipher3).
#   - argon2 (argon2-cffi): KDF Argon2id da KEK; traz `_ffi`/`_argon2_cffi_bindings`
#     nativos importados dinamicamente pelo cffi.
for pacote in ('sqlcipher3', 'argon2', '_argon2_cffi_bindings'):
    d, b, h = collect_all(pacote)
    datas += d
    binaries += b
    hiddenimports += h

# TOTP + QR do onboarding (T-1604). `pyotp` é puro-Python mas importado
# tardiamente em `sidecar/auth.py`; `qrcode` usa `png` (pypng, do extra
# qrcode[png]) para o PNG do QR — SEM Pillow (o app usa PyNGImage/pypng puro,
# ver a decisão do T-1604). Declarados explícitos para não sumirem no freeze.
hiddenimports += ['pyotp', 'qrcode', 'qrcode.image.pure', 'png']

# uvicorn escolhe loop/protocolo por import dinâmico (uvicorn.loops.auto etc.).
hiddenimports += collect_submodules('uvicorn')

a = Analysis(
    ['scripts/sidecar_entry.py'],
    # O script de entrada mora em scripts/; a raiz do repo (onde vivem os
    # pacotes sidecar/core/agent/...) precisa estar no caminho de análise.
    pathex=['.'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='sidecar-hf',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='sidecar-hf',
)
