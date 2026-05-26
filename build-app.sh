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
PYTHON_OK=""

# Check a single candidate: prints version info if suitable, fails otherwise
_check_py() {
    local py="$1"
    [ -x "$py" ] || return 1
    "$py" -c "
import sys
assert sys.version_info >= (3, 11), f'need 3.11+, got {sys.version_info.major}.{sys.version_info.minor}'
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt, PYQT_VERSION_STR
print(f'{sys.version_info.major}.{sys.version_info.minor}  PyQt6={PYQT_VERSION_STR}')
" 2>/dev/null
}

# Build deduplicated candidate list in priority order
declare -A _seen_candidates
_candidates=""

_add_candidate() {
    local p="$1"
    [ -z "$p" ] && return
    [ "${_seen_candidates[$p]+exists}" ] && return
    _seen_candidates["$p"]=1
    _candidates="$_candidates $p"
}

# Homebrew arm64 (Apple Silicon)
for v in 3.13 3.12 3.11; do
    _add_candidate "/opt/homebrew/bin/python${v}"
    _add_candidate "/opt/homebrew/opt/python@${v}/bin/python${v}"
done
_add_candidate "/opt/homebrew/bin/python3"
# Homebrew x86_64 (Intel)
for v in 3.13 3.12 3.11; do
    _add_candidate "/usr/local/bin/python${v}"
    _add_candidate "/usr/local/opt/python@${v}/bin/python${v}"
done
_add_candidate "/usr/local/bin/python3"
# MacPorts
for v in 3.13 3.12 3.11; do
    _add_candidate "/opt/local/bin/python${v}"
done
_add_candidate "/opt/local/bin/python3"
# pyenv
_add_candidate "$HOME/.pyenv/shims/python3"
_add_candidate "$HOME/.pyenv/shims/python3.13"
_add_candidate "$HOME/.pyenv/shims/python3.12"
_add_candidate "$HOME/.pyenv/shims/python3.11"
# System
_add_candidate "/usr/bin/python3"
# PATH (last, to avoid shadowing explicit paths)
for v in python3.13 python3.12 python3.11 python3; do
    _path_resolved="$(command -v "$v" 2>/dev/null || true)"
    [ -n "$_path_resolved" ] && _add_candidate "$_path_resolved"
done

# Search all candidates
_DEBUG_LOG=""
for candidate in $_candidates; do
    [ -n "$candidate" ] || continue
    _result=$(_check_py "$candidate" 2>/dev/null) || true
    _DEBUG_LOG="${_DEBUG_LOG}  ${candidate} -> '${_result}'\n"
    if [ -n "$_result" ]; then
        PYTHON="$candidate"
        PYTHON_OK="$_result"
        break
    fi
done

# If no suitable Python — give clear fix instructions
if [ -z "$PYTHON" ]; then
    echo ""
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║  ⚠  No Python 3.11+ with PyQt6 found.                     ║"
    echo "╠══════════════════════════════════════════════════════════════╣"
    echo "║                                                              ║"
    echo "║  Install steps:                                              ║"
    echo "║                                                              ║"
    echo "║  1. Install Homebrew Python:                                 ║"
    echo "║     brew install python@3.12                                 ║"
    echo "║                                                              ║"
    echo "║  2. Install PyQt6 + PyInstaller:                             ║"
    echo "║     pip3 install PyQt6 PyInstaller                           ║"
    echo "║                                                              ║"
    echo "║  3. Re-run: ./build-app.sh                                   ║"
    echo "║                                                              ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo ""
    echo "Debug — candidates checked:"
    printf "$_DEBUG_LOG"
    exit 1
fi

echo "Python: $PYTHON  ($PYTHON_OK)"

# 2. Install build deps (if not already)
echo ""
echo "=== Checking build dependencies ==="

if ! "$PYTHON" -c "import PyInstaller" 2>/dev/null; then
    echo "  → Installing PyInstaller..."
    "$PYTHON" -m pip install --quiet PyInstaller 2>&1 || {
        echo "  ✗ Failed to install PyInstaller"
        exit 1
    }
fi
echo "  PyInstaller: $($PYTHON -c "import PyInstaller; print(PyInstaller.__version__)" 2>/dev/null || echo 'ok')"

if ! "$PYTHON" -c "import PIL" 2>/dev/null; then
    echo "  → Installing Pillow..."
    "$PYTHON" -m pip install --quiet Pillow 2>&1 || true
fi
echo "  Pillow: $($PYTHON -c "from PIL import __version__; print(__version__)" 2>/dev/null || echo 'ok')"

# 3. Download TrustTunnel client binary (bundled in .app)
echo ""
if [ ! -f "bin/trusttunnel_client" ]; then
    echo "=== Downloading TrustTunnel CLI client ==="
    mkdir -p bin
    TT_VERSION="v1.0.49"
    TT_URL="https://github.com/TrustTunnel/TrustTunnelClient/releases/download/${TT_VERSION}/trusttunnel_client-${TT_VERSION}-macos-universal.tar.gz"
    curl -fsSL "$TT_URL" | tar xz --strip-components=1 -C bin/ trusttunnel_client-${TT_VERSION}-macos-universal/trusttunnel_client
    chmod +x bin/trusttunnel_client
    rm -f bin/LICENSE bin/*.sig
    echo "  bin/trusttunnel_client ($(du -sh bin/trusttunnel_client | cut -f1))"
else
    echo "=== TrustTunnel CLI client already bundled ==="
    echo "  bin/trusttunnel_client ($(du -sh bin/trusttunnel_client | cut -f1))"
fi

# 4. Generate icon (if no icon.icns exists)
if [ ! -f "icon.icns" ]; then
    echo ""
    echo "=== Generating icon ==="

    "$PYTHON" -c "
import struct, zlib
SZ = 512
raw = b''
for y in range(SZ):
    raw += b'\x00'
    for x in range(SZ):
        r, g, b, a = 37, 99, 235, 255
        raw += struct.pack('BBBB', r, g, b, a)

sig = b'\x89PNG\r\n\x1a\n'
ihdr = struct.pack('>IIBBBBB', SZ, SZ, 8, 6, 0, 0, 0)
def chunk(t, d):
    return struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d) & 0xffffffff)
z = zlib.compress(raw)
png = sig + chunk(b'IHDR', ihdr) + chunk(b'IDAT', z) + chunk(b'IEND', b'')
with open('icon.png', 'wb') as f: f.write(png)
"
    echo "icon.png created"

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

# 5. Build
echo ""
echo "=== Building .app ==="
"$PYTHON" -m PyInstaller trusttunnel.spec --clean --noconfirm 2>&1

# 6. Ad-hoc codesign
echo ""
echo "=== Signing .app (ad-hoc) ==="
APP="dist/TrustTunnel.app"
if codesign --force --deep --sign - "$APP" 2>&1; then
    echo "  Signed (ad-hoc): $APP"
    xattr -cr "$APP" 2>/dev/null || true
else
    echo "  WARNING: codesign failed — app will show Gatekeeper warning on first launch."
    echo "  Users can bypass: System Settings → Privacy & Security → Open Anyway"
    echo "  Or: xattr -cr /Applications/TrustTunnel.app"
fi

# 7. Result + install
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

    echo ""
    echo "  Configuring passwordless sudo for VPN client..."
    "$SCRIPT_DIR/setup-sudo.sh"

    echo ""
    echo "To share: zip -r TrustTunnel-macOS.zip \"$APP\""
else
    echo "ERROR: Build failed. Check output above."
    exit 1
fi
