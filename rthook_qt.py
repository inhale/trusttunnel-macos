"""
PyInstaller runtime hook for macOS PyQt6.
Sets QT_QPA_PLATFORM_PLUGIN_PATH before Qt's C++ static initializers run,
preventing the CFBundleCopyBundleURL crash.
"""
import os
import sys

if sys.platform == 'darwin' and getattr(sys, 'frozen', False):
    meipass = getattr(sys, '_MEIPASS', '')
    for plugin_path in [
        os.path.join(meipass, 'PyQt6', 'Qt6', 'plugins'),
        os.path.join(meipass, 'PyQt6', 'plugins'),
        os.path.join(meipass, 'plugins'),
    ]:
        if os.path.isdir(plugin_path):
            os.environ['QT_QPA_PLATFORM_PLUGIN_PATH'] = plugin_path
            break
