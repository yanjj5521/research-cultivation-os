# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path


root = Path(SPECPATH).resolve().parent
datas = [
    (str(root / "hub_templates"), "hub_templates"),
    (str(root / "hub_static"), "hub_static"),
    (str(root / "VERSION"), "."),
]

a = Analysis(
    [str(root / "run_hub.py")],
    pathex=[str(root)],
    binaries=[],
    datas=datas,
    hiddenimports=["hub_app", "hub_db"],
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
    name="ResearchHub",
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
