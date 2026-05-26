#!/usr/bin/env python3
"""Standalone entry point for PyInstaller bundling.

Usage (dev):  python3 run.py
Usage (build): pyinstaller trusttunnel.spec
"""
import sys
import os

# Ensure src/ is on the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# CRITICAL: Set Qt plugin path BEFORE importing PyQt6.
# On macOS with console=False, CFBundle lookups crash during Qt static
# initialization (QLoggingRegistry → QLibraryInfo → CFBundleCopyBundleURL).
# We must set QT_QPA_PLATFORM_PLUGIN_PATH before any Qt code loads.
if getattr(sys, 'frozen', False) and sys.platform == 'darwin':
    meipass = getattr(sys, '_MEIPASS', '')
    for plugin_path in [
        os.path.join(meipass, 'PyQt6', 'Qt6', 'plugins'),
        os.path.join(meipass, 'PyQt6', 'plugins'),
        os.path.join(meipass, 'plugins'),
    ]:
        if os.path.isdir(plugin_path):
            os.environ['QT_QPA_PLATFORM_PLUGIN_PATH'] = plugin_path
            break

from src.app import main

if __name__ == "__main__":
    main()
