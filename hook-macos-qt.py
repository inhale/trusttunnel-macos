"""
PyInstaller runtime hook for macOS PyQt6.
Sets Qt plugin path before Qt initializes, preventing CFBundle crashes.
"""
import os
import sys

if getattr(sys, 'frozen', False) and sys.platform == 'darwin':
    meipass = getattr(sys, '_MEIPASS', '')
    candidates = [
        os.path.join(meipass, 'PyQt6', 'Qt6', 'plugins'),
        os.path.join(meipass, 'PyQt6', 'plugins'),
        os.path.join(meipass, 'plugins'),
    ]
    for p in candidates:
        if os.path.isdir(p):
            os.environ['QT_QPA_PLATFORM_PLUGIN_PATH'] = p
            break
