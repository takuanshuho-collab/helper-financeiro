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
