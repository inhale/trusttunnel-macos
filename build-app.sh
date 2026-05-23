#!/bin/bash
# Build TrustTunnel.app for macOS distribution
# Run this on your Mac (not on VPS — PyInstaller needs target OS)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== TrustTunnel macOS App Builder ==="
echo ""

# 1. Ensure MacPorts Python 3.11+ with Tk 8.6+
echo "=== Checking Python + Tkinter ==="
PYTHON=""

# Preferred: MacPorts Python 3.11
for candidate in /opt/local/bin/python3.11 /opt/local/bin/python3; do
    if [ -x "$candidate" ]; then
        ver=$("$candidate" -c "import tkinter; print(tkinter.TkVersion)" 2>/dev/null || echo "0")
        if [ "${ver%%.*}" -ge 8 ] && [ "${ver#*.}" -ge 6 ]; then
            PYTHON="$candidate"
            break
        fi
    fi
done

# If no suitable Python — give clear fix instructions
if [ -z "$PYTHON" ]; then
    echo ""
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║  ⚠ No suitable Python found.                                ║"
    echo "║  TrustTunnel needs MacPorts Python 3.11 with Tk 8.6.        ║"
    echo "╠══════════════════════════════════════════════════════════════╣"
    echo "║  Copy-paste to fix (one-time, ~10 min):                      ║"
    echo "║                                                            ║"
    echo "║  # 1. Install MacPorts (if not installed)                    ║"
    echo "║  #    Download from https://www.macports.org/install.php      ║"
    echo "║                                                            ║"
    echo "║  # 2. Install Python 3.11 with Tkinter                       ║"
    echo "║  sudo port install python311 py-tkinter                      ║"
    echo "║                                                            ║"
    echo "║  # 3. Re-run build                                         ║"
    echo "║  ./build-app.sh                                             ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo ""
    exit 1
fi

echo "Python: $PYTHON (Tk $("$PYTHON" -c "import tkinter; print(tkinter.TkVersion)"))"

# 2. Install build deps
echo ""
echo "=== Installing build dependencies ==="

# MacPorts Python's bin/ should be on PATH via /opt/local/bin
# Install pyinstaller via pip
_install_deps() {
    if "$PYTHON" -m pip install --quiet pyinstaller 2>/dev/null; then
        return 0
    fi
    # MacPorts Python may need ensurepip
    echo "  → pip not found, installing via get-pip.py..."
    curl -fsSL https://bootstrap.pypa.io/get-pip.py -o /tmp/get-pip.py
    "$PYTHON" /tmp/get-pip.py --quiet 2>&1 || true
    rm -f /tmp/get-pip.py
    if "$PYTHON" -m pip install --quiet pyinstaller 2>/dev/null; then
        return 0
    fi
    # Last resort: find any working pip3
    PIP3=$(find /opt/local/Library/Frameworks/Python.framework -name pip3 -maxdepth 4 2>/dev/null | head -1)
    if [ -n "$PIP3" ] && "$PIP3" --version >/dev/null 2>&1; then
        "$PIP3" install --quiet pyinstaller 2>&1
        return $?
    fi
    return 1
}
_install_deps || {
    echo "  ✗ Failed to install build deps."
    exit 1
}

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

# 5. Result + install
echo ""
echo "=== Done ==="
APP="dist/TrustTunnel.app"
if [ -d "$APP" ]; then
    SIZE=$(du -sh "$APP" | cut -f1)
    echo "App:  $SCRIPT_DIR/$APP  ($SIZE)"
    echo ""
    echo "Copy to /Applications?"
    read -p "  [Y/n]: " answer
    if [ "${answer:-y}" = "y" ] || [ "${answer:-y}" = "Y" ] || [ -z "$answer" ]; then
        rm -rf /Applications/TrustTunnel.app
        cp -R "$APP" /Applications/
        echo "  → Copied to /Applications/TrustTunnel.app"

        # Auto-configure sudo if not already done
        SUDOERS="/etc/sudoers.d/trusttunnel"
        if [ -f "$SUDOERS" ] && grep -q "trusttunnel_client" "$SUDOERS" 2>/dev/null; then
            echo "  → Sudo already configured."
        else
            echo ""
            echo "  TrustTunnel needs root to create a virtual network interface."
            echo "  Configure passwordless sudo for the VPN client?"
            read -p "  [Y/n]: " sudo_ans
            if [ "${sudo_ans:-y}" = "y" ] || [ "${sudo_ans:-y}" = "Y" ] || [ -z "$sudo_ans" ]; then
                "$SCRIPT_DIR/setup-sudo.sh"
            else
                echo "  (Skipped. Run ./setup-sudo.sh later.)"
            fi
        fi
    else
        echo "  To install later: cp -r \"$APP\" /Applications/"
    fi
    echo ""
    echo "To share: zip -r TrustTunnel-macOS.zip \"$APP\""
else
    echo "ERROR: Build failed. Check output above."
    exit 1
fi
