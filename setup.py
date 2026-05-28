"""py2app setup for TrustTunnel macOS app.

Usage:
    Dev mode (alias):  python3 setup.py py2app -A
    Production build:  python3 setup.py py2app

Output: dist/TrustTunnel.app
"""
from setuptools import setup

APP = ["run.py"]
DATA_FILES = [
    ("", ["generate-icon.py", "icon.icns", "PkgInfo"]),
    ("", ["bin/trusttunnel_client"]),
    ("src", ["src/config.py", "src/client.py"]),
    ("", ["rate_limiter.py"]),
]

OPTIONS = {
    "argv_emulation": False,  # Disabled: causes hang when launching from Finder
    "iconfile": "icon.icns" if __import__("os").path.exists("icon.icns") else None,
    "packages": ["PyQt6", "PIL"],
    "includes": [
        "PyQt6", "PyQt6.QtCore", "PyQt6.QtGui", "PyQt6.QtWidgets",
        "base64", "threading", "json", "re", "subprocess",
        "tempfile", "signal", "datetime", "urllib.parse",
        "pathlib", "enum",
    ],
    "plist": {
        "CFBundleIdentifier": "com.trusttunnel.gui",
        "CFBundleName": "TrustTunnel",
        "CFBundleDisplayName": "TrustTunnel VPN",
        "CFBundleShortVersionString": "1.0.0",
        "CFBundleVersion": "1.0.0",
        "LSMinimumSystemVersion": "10.15",
        "NSHighResolutionCapable": True,
        "NSRequiresAquaSystemAppearance": False,
        "PyRuntimeLocations": [
            "@executable_path/../Frameworks/Python"
        ],
        # Dock icon visible — normal app activation policy
    },
}

setup(
    app=APP,
    data_files=DATA_FILES,
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
