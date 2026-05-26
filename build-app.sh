#!/bin/bash
# Build TrustTunnel.app for macOS distribution (PyQt6)
# Run this on your Mac (not on VPS — PyInstaller needs target OS)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== TrustTunnel macOS App Builder (PyQt6) ==="
echo ""

# 1. Find Python 3.11+ with PyQt6
echo "=== Checking Python + PyQt6 ==="
PYTHON=""

_pyqt6_ok() {
    local py="$1"
    [ -x "$py" ] || return 1
    "$py" -c "from PyQt6.QtWidgets import QApplication; from PyQt6.QtCore import Qt; print('PyQt6 ok')" 2>/dev/null
}

# Search order: Homebrew (arm64 + x86_64) → MacPorts → pyenv → system python3
_candidates() {
    # Homebrew arm64 (Apple Silicon)
    for v in 3.13 3.12 3.11; do
        echo "/opt/homebrew/opt/python@${v}/bin/python${v}"
        echo "/opt/homebrew/bin/python${v}"
    done
    echo /opt/homebrew/bin/python3
    # Homebrew x86_64
    for v in 3.13 3.12 3.11; do
        echo "/usr/local/opt/python@${v}/bin/python${v}"
        echo "/usr/local/bin/python${v}"
    done
    echo /usr/local/bin/python3
    # MacPorts
    echo /opt/local/bin/python3.11
    echo /opt/local/bin/python3.12
    echo /opt/local/bin/python3.13
    echo /opt/local/bin/python3
    # pyenv shims
    echo "$HOME/.pyenv/shims/python3"
    # System
    echo /usr/bin/python3
    # PATH fallback
    command -v python3.13 2>/dev/null
    command -v python3.12 2>/dev/null
    command -v python3.11 2>/dev/null
    command -v python3    2>/dev/null
}

for candidate in $(_candidates); do
    [ -n "$candidate" ] || continue
    if _pyqt6_ok "$candidate"; then
        PYTHON="$candidate"
        break
    fi
done

# If no suitable Python — give clear fix instructions
if [ -z "$PYTHON" ]; then
    echo ""
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║  ⚠ No Python with PyQt6 found.                             ║"
    echo "║  TrustTunnel needs Python 3.11+ with PyQt6.                ║"
    echo "╠══════════════════════════════════════════════════════════════╣"
    echo "║  Install steps:                                             ║"
    echo "║                                                              ║"
    echo "║  1. Install Homebrew Python (if not already):               ║"
    echo "║     brew install python@3.11                                ║"
    echo "║                                                              ║"
    echo "║  2. Install PyQt6 + build tools:                            ║"
    echo "║     pip3 install PyQt6 pyinstaller                          ║"
    echo "║                                                              ║"
    echo "║  3. Re-run: ./build-app.sh                                  ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo ""
    # Show what was found
    echo "Checked candidates:"
    for c in $(_candidates | head -8); do
        [ -n "$c" ] || continue
        [ -x "$c" ] || continue
        has_qt=$("$c" -c "import PyQt6" 2>/dev/null && echo "PyQt6 ✓" || echo "PyQt6 ✗")
        echo "  $c → $has_qt"
    done
    exit 1
fi

echo "Python: $PYTHON"
echo "PyQt6:  $($PYTHON -c "from PyQt6.QtCore import PYQT_VERSION_STR; print(PYQT_VERSION_STR)")"

# 2. Install build deps (if not already)
echo ""
echo "=== Checking build dependencies ==="

# Check if PyInstaller is available
if ! "$PYTHON" -c "import PyInstaller" 2>/dev/null; then
    echo "  → Installing PyInstaller..."
    "$PYTHON" -m pip install --quiet PyInstaller 2>&1 || {
        echo "  ✗ Failed to install PyInstaller"
        exit 1
    }
fi
echo "  PyInstaller: $($PYTHON -c "import PyInstaller; print(PyInstaller.__version__)" 2>/dev/null || echo 'ok')"

# Pillow (for tray icon generation)
if ! "$PYTHON" -c "import PIL" 2>/dev/null; then
    echo "  → Installing Pillow..."
    "$PYTHON" -m pip install --quiet Pillow 2>&1 || true
fi
echo "  Pillow: $( $PYTHON -c "from PIL import __version__; print(__version__)" 2>/dev/null || echo 'ok')"

# 2.5. Download TrustTunnel client binary (bundled in .app)
echo ""
if [ ! -f "bin/trusttunnel_client" ]; then
    echo "=== Downloading TrustTunnel CLI client ==="
    mkdir -p bin
    TT_VERSION="v1.0.49"
    TT_URL="https://github.com/TrustTunnel/TrustTunnelClient/releases/download/${TT_VERSION}/trusttunnel_client-${TT_VERSION}-macos-universal.tar.gz"
    curl -fsSL "$TT_URL" | tar xz --strip-components=1 -C bin/ trusttunnel_client-${TT_VERSION}-macos-universal/trusttunnel_client
    chmod +x bin/trusttunnel_client
    rm -f bin/LICENSE bin/*.sig  # only need the binary
    echo "  bin/trusttunnel_client ($(du -sh bin/trusttunnel_client | cut -f1))"
else
    echo "=== TrustTunnel CLI client already bundled ==="
    echo "  bin/trusttunnel_client ($(du -sh bin/trusttunnel_client | cut -f1))"
fi

# 3. Generate icon (if no icon.icns exists)
if [ ! -f "icon.icns" ]; then
    echo ""
    echo "=== Generating icon ==="

    # Fallback: simple blue square PNG
    "$PYTHON" -c "
import struct, zlib
SZ = 512
raw = b''
for y in range(SZ):
    raw += b'\\x00'  # filter none
    for x in range(SZ):
        r, g, b, a = 37, 99, 235, 255  # blue
        raw += struct.pack('BBBB', r, g, b, a)

sig = b'\\x89PNG\\r\\n\\x1a\\n'
ihdr = struct.pack('>IIBBBBB', SZ, SZ, 8, 6, 0, 0, 0)
def chunk(t, d):
    return struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d) & 0xffffffff)
z = zlib.compress(raw)
png = sig + chunk(b'IHDR', ihdr) + chunk(b'IDAT', z) + chunk(b'IEND', b'')
with open('icon.png', 'wb') as f: f.write(png)
"
    echo "icon.png created"

    # Check if iconutil is available for .icns conversion
    if command -v iconutil >/dev/null 2>&1 && command -v sips >/dev/null 2>&1; then
        echo "  Converting to .icns..."
        mkdir -p icon.iconset
        sips -z 16 16   icon.png --out icon.iconset/icon_16x16.png 2>/dev/null
        sips -z 32 32   icon.png --out icon.iconset/icon_16x16@2x.png 2>/dev/null
        sips -z 32 32   icon.png --out icon.iconset/icon_32x32.png 2>/dev/null
        sips -z 64 64   icon.png --out icon.iconset/icon_32x32@2x.png 2>/dev/null
        sips -z 128 128 icon.png --out icon.iconset/icon_128x128.png 2>/dev/null
        sips -z 256 256 icon.png --out icon.iconset/icon_128x128@2x.png 2>/dev/null
        sips -z 256 256 icon.png --out icon.iconset/icon_256x256.png 2>/dev/null
        sips -z 512 512 icon.png --out icon.iconset/icon_256x256@2x.png 2>/dev/null
        sips -z 512 512 icon.png --out icon.iconset/icon_512x512.png 2>/dev/null
        sips -z 1024 1024 icon.png --out icon.iconset/icon_512x512@2x.png 2>/dev/null
        iconutil -c icns icon.iconset -o icon.icns 2>/dev/null
        rm -rf icon.iconset
        echo "  icon.icns created"
    else
        echo "  Note: iconutil/sips not available, using PNG icon"
    fi
fi

# 4. Build
echo ""
echo "=== Building .app ==="
"$PYTHON" -m PyInstaller trusttunnel.spec --clean --noconfirm 2>&1

# 5. Ad-hoc codesign (silences Gatekeeper "unverified developer" dialog)
echo ""
echo "=== Signing .app (ad-hoc) ==="
APP="dist/TrustTunnel.app"
if codesign --force --deep --sign - "$APP" 2>&1; then
    echo "  Signed (ad-hoc): $APP"
    # Strip quarantine flag in case it was set during build
    xattr -cr "$APP" 2>/dev/null || true
else
    echo "  WARNING: codesign failed — app will show Gatekeeper warning on first launch."
    echo "  Users can bypass: System Settings → Privacy & Security → Open Anyway"
    echo "  Or: xattr -cr /Applications/TrustTunnel.app"
fi

# 6. Result + install
echo ""
echo "=== Done ==="
if [ -d "$APP" ]; then
    SIZE=$(du -sh "$APP" | cut -f1)
    echo "App:  $SCRIPT_DIR/$APP  ($SIZE)"
    echo ""
    echo "=== Installing to /Applications ==="
    rm -rf /Applications/TrustTunnel.app
    cp -R "$APP" /Applications/
    echo "  → /Applications/TrustTunnel.app"

    # Auto-configure sudo (always run to ensure correct binary path)
    echo ""
    echo "  Configuring passwordless sudo for VPN client..."
    "$SCRIPT_DIR/setup-sudo.sh"

    echo ""
    echo "To share: zip -r TrustTunnel-macOS.zip \"$APP\""
else
    echo "ERROR: Build failed. Check output above."
    exit 1
fi

# 2.5. Download TrustTunnel client binary (bundled in .app)
echo ""
if [ ! -f "bin/trusttunnel_client" ]; then
    echo "=== Downloading TrustTunnel CLI client ==="
    mkdir -p bin
    TT_VERSION="v1.0.49"
    TT_URL="https://github.com/TrustTunnel/TrustTunnelClient/releases/download/${TT_VERSION}/trusttunnel_client-${TT_VERSION}-macos-universal.tar.gz"
    curl -fsSL "$TT_URL" | tar xz --strip-components=1 -C bin/ trusttunnel_client-${TT_VERSION}-macos-universal/trusttunnel_client
    chmod +x bin/trusttunnel_client
    rm -f bin/LICENSE bin/*.sig  # only need the binary
    echo "  bin/trusttunnel_client ($(du -sh bin/trusttunnel_client | cut -f1))"
else
    echo "=== TrustTunnel CLI client already bundled ==="
    echo "  bin/trusttunnel_client ($(du -sh bin/trusttunnel_client | cut -f1))"
fi

# 3. Generate icon (if no icon.icns exists)
if [ ! -f "icon.icns" ]; then
    echo ""
    echo "=== Generating icon ==="

    # Fallback: simple blue square PNG
    "$PYTHON" -c "
import struct, zlib
SZ = 512
raw = b''
for y in range(SZ):
    raw += b'\\x00'  # filter none
    for x in range(SZ):
        r, g, b, a = 37, 99, 235, 255  # blue
        raw += struct.pack('BBBB', r, g, b, a)

sig = b'\\x89PNG\\r\\n\\x1a\\n'
ihdr = struct.pack('>IIBBBBB', SZ, SZ, 8, 6, 0, 0, 0)
def chunk(t, d):
    return struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d) & 0xffffffff)
z = zlib.compress(raw)
png = sig + chunk(b'IHDR', ihdr) + chunk(b'IDAT', z) + chunk(b'IEND', b'')
with open('icon.png', 'wb') as f: f.write(png)
"
    echo "icon.png created"

    # Convert to .icns
    echo "To get a proper .icns: open icon.png in Preview, File > Export > Format: PNG,"
    echo "then in Terminal:"
    echo "  mkdir icon.iconset"
    echo "  sips -z 16 16   icon.png --out icon.iconset/icon_16x16.png"
    echo "  sips -z 32 32   icon.png --out icon.iconset/icon_16x16@2x.png"
    echo "  sips -z 32 32   icon.png --out icon.iconset/icon_32x32.png"
    echo "  sips -z 64 64   icon.png --out icon.iconset/icon_32x32@2x.png"
    echo "  sips -z 128 128 icon.png --out icon.iconset/icon_128x128.png"
    echo "  sips -z 256 256 icon.png --out icon.iconset/icon_128x128@2x.png"
    echo "  sips -z 256 256 icon.png --out icon.iconset/icon_256x256.png"
    echo "  sips -z 512 512 icon.png --out icon.iconset/icon_256x256@2x.png"
    echo "  sips -z 512 512 icon.png --out icon.iconset/icon_512x512.png"
    echo "  iconutil -c icns icon.iconset -o icon.icns"
    echo "  rm -rf icon.iconset"
fi

# 4. Build
echo ""
echo "=== Building .app ==="
"$PYTHON" -m PyInstaller trusttunnel.spec --clean --noconfirm 2>&1

# 5. Ad-hoc codesign (silences Gatekeeper "unverified developer" dialog)
echo ""
echo "=== Signing .app (ad-hoc) ==="
APP="dist/TrustTunnel.app"
if codesign --force --deep --sign - "$APP" 2>&1; then
    echo "  Signed (ad-hoc): $APP"
    # Strip quarantine flag in case it was set during build
    xattr -cr "$APP" 2>/dev/null || true
else
    echo "  WARNING: codesign failed — app will show Gatekeeper warning on first launch."
    echo "  Users can bypass: System Settings → Privacy & Security → Open Anyway"
    echo "  Or: xattr -cr /Applications/TrustTunnel.app"
fi

# 6. Result + install
echo ""
echo "=== Done ==="
if [ -d "$APP" ]; then
    SIZE=$(du -sh "$APP" | cut -f1)
    echo "App:  $SCRIPT_DIR/$APP  ($SIZE)"
    echo ""
    echo "=== Installing to /Applications ==="
    rm -rf /Applications/TrustTunnel.app
    cp -R "$APP" /Applications/
    echo "  → /Applications/TrustTunnel.app"

    # Auto-configure sudo (always run to ensure correct binary path)
    echo ""
    echo "  Configuring passwordless sudo for VPN client..."
    "$SCRIPT_DIR/setup-sudo.sh"

    echo ""
    echo "To share: zip -r TrustTunnel-macOS.zip \"$APP\""
else
    echo "ERROR: Build failed. Check output above."
    exit 1
fi
