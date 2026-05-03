# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_submodules


hiddenimports = (
    collect_submodules("backend")
    + collect_submodules("uvicorn")
    + collect_submodules("fastapi")
    + collect_submodules("pystray")
    + collect_submodules("PIL")
)

a = Analysis(
    ["backend/launcher.py"],
    pathex=[],
    binaries=[],
    datas=[("frontend/static", "frontend/static")],
    hiddenimports=hiddenimports,
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
    name="MineHostHelper",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
