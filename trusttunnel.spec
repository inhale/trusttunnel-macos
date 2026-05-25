# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for TrustTunnel macOS app.

Build:
    pip install pyinstaller toml
    pyinstaller trusttunnel.spec

Output: dist/TrustTunnel.app  (double-clickable, no terminal)
"""

import sys
import os
import subprocess
from pathlib import Path

# ── Collect tkinter properly ──────────────────────────────────────────────
# hiddenimports alone is NOT enough — PyInstaller needs the _tkinter C
# extension and the Tcl/Tk framework dylibs physically bundled.
# collect_all("tkinter") handles the pure-Python side; we also need to
# locate and bundle the Tcl/Tk shared libraries.

from PyInstaller.utils.hooks import collect_all as _collect_all

tk_datas, tk_binaries, tk_hiddenimports = _collect_all("tkinter")

# Find Tcl/Tk lib dir — search common Homebrew locations (arm64 + x86_64)
# and whatever Python is actually using right now.
def _find_tcltk_lib():
    # Ask the running Python where its _tkinter came from
    try:
        out = subprocess.check_output(
            [sys.executable, "-c",
             "import _tkinter; print(_tkinter.__file__)"],
            stderr=subprocess.DEVNULL,
        ).decode().strip()
        # Walk up from _tkinter.cpython-*.so to find lib/tcl8.x etc.
        p = Path(out)
        for parent in [p.parent, p.parent.parent, p.parent.parent.parent]:
            for sub in parent.glob("tcl*"):
                if sub.is_dir():
                    return str(parent)
    except Exception:
        pass
    # Fallback: common Homebrew paths
    for candidate in [
        "/opt/homebrew/opt/python-tk@3.13/lib",
        "/opt/homebrew/opt/python-tk@3.12/lib",
        "/opt/homebrew/opt/python-tk@3.11/lib",
        "/opt/homebrew/opt/tcl-tk/lib",
        "/usr/local/opt/python-tk@3.13/lib",
        "/usr/local/opt/python-tk@3.12/lib",
        "/usr/local/opt/python-tk@3.11/lib",
        "/usr/local/opt/tcl-tk/lib",
        "/opt/local/lib",  # MacPorts
    ]:
        if Path(candidate).exists():
            return candidate
    return None

_tcltk_lib = _find_tcltk_lib()
_extra_datas = []
if _tcltk_lib:
    for name in ["tcl8.5", "tcl8.6", "tcl8.7", "tk8.5", "tk8.6", "tk8.7"]:
        p = Path(_tcltk_lib) / name
        if p.exists():
            _extra_datas.append((str(p), name))

block_cipher = None

a = Analysis(
    ["run.py"],
    pathex=[],
    binaries=[
        ("bin/trusttunnel_client", "bin"),
    ] + tk_binaries,
    datas=[
        ("src", "src"),              # all source code (including _vendor/toml)
    ] + tk_datas + _extra_datas,
    hiddenimports=[
        "tkinter",
        "tkinter.ttk",
        "tkinter.messagebox",
        "_tkinter",
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
    ] + tk_hiddenimports,
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
