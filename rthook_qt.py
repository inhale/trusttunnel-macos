"""
PyInstaller runtime hook for macOS PyQt6.
Fixes the qdarwinpermissionplugin CFBundleCopyBundleURL crash by ensuring
a valid NSBundle exists before Qt's static initializers run.
"""
import os
import sys
import tempfile

if sys.platform == 'darwin' and getattr(sys, 'frozen', False):
    meipass = getattr(sys, '_MEIPASS', '')
    if meipass:
        # Create a minimal Info.plist so CFBundleGetMainBundle() returns non-NULL
        info_plist = os.path.join(meipass, '..', 'Info.plist')
        if not os.path.exists(info_plist):
            plist_content = '''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>TrustTunnel</string>
    <key>CFBundleIdentifier</key>
    <string>com.trusttunnel.gui</string>
    <key>CFBundleName</key>
    <string>TrustTunnel</string>
    <key>CFBundleVersion</key>
    <string>1.0.0</string>
    <key>CFBundleShortVersionString</key>
    <string>1.0.0</string>
    <key>LSMinimumSystemVersion</key>
    <string>10.15</string>
    <key>NSHighResolutionCapable</key>
    <true/>
</dict>
</plist>'''
            try:
                os.makedirs(os.path.dirname(info_plist), exist_ok=True)
                with open(info_plist, 'w') as f:
                    f.write(plist_content)
            except Exception:
                pass

    # Set Qt plugin path
    for plugin_path in [
        os.path.join(meipass, 'PyQt6', 'Qt6', 'plugins'),
        os.path.join(meipass, 'PyQt6', 'plugins'),
        os.path.join(meipass, 'plugins'),
    ]:
        if os.path.isdir(plugin_path):
            os.environ['QT_QPA_PLATFORM_PLUGIN_PATH'] = plugin_path
            break
