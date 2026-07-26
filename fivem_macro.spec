# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ["gui_macro.py"],
    pathex=[],
    binaries=[],
    datas=[("templates", "templates")],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="FiveM-Farming-Macro",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
)
