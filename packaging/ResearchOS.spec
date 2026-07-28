# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path


root = Path(SPECPATH).resolve().parent
datas = [
    (str(root / "templates"), "templates"),
    (str(root / "static"), "static"),
    (str(root / "VERSION"), "."),
]

a = Analysis(
    [str(root / "run_local.py")],
    pathex=[str(root)],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=1,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="ResearchOS",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
