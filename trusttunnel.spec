# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for TrustTunnel macOS app (PyQt6).

Build:
    pip install pyinstaller toml PyQt6
    pyinstaller trusttunnel.spec

Output: dist/TrustTunnel.app  (double-clickable, no terminal)
"""

import sys
import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_all as _collect_all

# Collect PyQt6
pyqt6_datas, pyqt6_binaries, pyqt6_hiddenimports = _collect_all("PyQt6")

# Collect Pillow — needed for tray icon image generation
try:
    pil_datas, pil_binaries, pil_hidden = _collect_all("PIL")
except Exception:
    pil_datas, pil_binaries, pil_hidden = [], [], []

block_cipher = None

a = Analysis(
    ["run.py"],
    pathex=[],
    binaries=pyqt6_binaries + pil_binaries,
    datas=[
        ("src", "src"),
        ("bin/trusttunnel_client", "bin"),
    ] + pyqt6_datas + pil_datas,
    hiddenimports=[
        "PyQt6",
        "PyQt6.QtCore",
        "PyQt6.QtGui",
        "PyQt6.QtWidgets",
        "base64",
        "threading",
        "json",
        "re",
        "subprocess",
        "tempfile",
        "signal",
        "datetime",
        "urllib.parse",
        "pathlib",
        "enum",
        "PIL",
        "PIL.Image",
        "PIL.ImageDraw",
    ] + pyqt6_hiddenimports + pil_hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="TrustTunnel",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,           # No terminal window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="icon.icns" if Path("icon.icns").exists() else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="TrustTunnel",
)

app = BUNDLE(
    coll,
    name="TrustTunnel.app",
    icon="icon.icns" if Path("icon.icns").exists() else None,
    bundle_identifier="com.trusttunnel.gui",
    info_plist={
        "NSHighResolutionCapable": True,
        "CFBundleShortVersionString": "1.0.0",
        "CFBundleVersion": "1.0.0",
        "CFBundleName": "TrustTunnel",
        "CFBundleDisplayName": "TrustTunnel VPN",
        "LSMinimumSystemVersion": "10.15",
        "NSRequiresAquaSystemAppearance": False,
    },
)
