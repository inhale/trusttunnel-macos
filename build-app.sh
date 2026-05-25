#!/bin/bash
# Build TrustTunnel.app for macOS distribution
# Run this on your Mac (not on VPS — PyInstaller needs target OS)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== TrustTunnel macOS App Builder ==="
echo ""

# 1. Find Python 3.11+ with Tk 8.6+
echo "=== Checking Python + Tkinter ==="
PYTHON=""

_tk_ok() {
    local py="$1"
    [ -x "$py" ] || return 1
    local ver
    ver=$("$py" -c "import tkinter; print(tkinter.TkVersion)" 2>/dev/null) || return 1
    local major="${ver%%.*}"
    local minor="${ver#*.}"
    [ "$major" -ge 8 ] && [ "${minor%%.*}" -ge 6 ]
}

# Search order: MacPorts → Homebrew (arm64 + x86_64) → pyenv → system python3
_candidates() {
    # MacPorts
    echo /opt/local/bin/python3.11
    echo /opt/local/bin/python3.12
    echo /opt/local/bin/python3.13
    echo /opt/local/bin/python3
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
    if _tk_ok "$candidate"; then
        PYTHON="$candidate"
        break
    fi
done

# If no suitable Python — give clear fix instructions
if [ -z "$PYTHON" ]; then
    echo ""
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║  ⚠ No suitable Python found.                                ║"
    echo "║  TrustTunnel needs Python 3.11+ with Tk 8.6+.               ║"
    echo "╠══════════════════════════════════════════════════════════════╣"
    echo "║  Pick ONE of these options:                                  ║"
    echo "║                                                              ║"
    echo "║  Option A — Homebrew (recommended):                          ║"
    echo "║    brew install python-tk@3.11                               ║"
    echo "║                                                              ║"
    echo "║  Option B — MacPorts:                                        ║"
    echo "║    sudo port install python311 py311-tkinter                 ║"
    echo "║                                                              ║"
    echo "║  Then re-run: ./build-app.sh                                 ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo ""
    # Show what was found and why it failed (helps debug)
    echo "Checked candidates (first 6):"
    i=0
    for c in $(_candidates); do
        [ -n "$c" ] || continue
        [ -x "$c" ] || continue
        ver=$("$c" -c "import tkinter; print('Tk', tkinter.TkVersion)" 2>/dev/null || echo "no tkinter")
        echo "  $c → $ver"
        i=$((i+1)); [ $i -ge 6 ] && break
    done
    exit 1
fi

echo "Python: $PYTHON (Tk $("$PYTHON" -c "import tkinter; print(tkinter.TkVersion)"))"

# Verify _tkinter C extension is present (not just the pure-Python wrapper)
if ! "$PYTHON" -c "import _tkinter" 2>/dev/null; then
    echo ""
    echo "ERROR: _tkinter C extension missing from $PYTHON"
    echo "The .app will crash on launch with 'No module named tkinter'."
    echo ""
    echo "Fix (Homebrew):"
    echo "  brew install python-tk@3.11"
    echo "  # then re-run with the python-tk python:"
    echo "  /usr/local/opt/python-tk@3.11/bin/python3.11 build-app.sh  (Intel)"
    echo "  /opt/homebrew/opt/python-tk@3.11/bin/python3.11 build-app.sh  (Apple Silicon)"
    exit 1
fi
echo "  _tkinter C extension: ok"

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
    echo "Copy to /Applications?"
    read -p "  [Y/n]: " answer
    if [ "${answer:-y}" = "y" ] || [ "${answer:-y}" = "Y" ] || [ -z "$answer" ]; then
        rm -rf /Applications/TrustTunnel.app
        cp -R "$APP" /Applications/
        echo "  → Copied to /Applications/TrustTunnel.app"

        # Auto-configure sudo (always run to ensure correct binary path)
        echo ""
        echo "  Configuring passwordless sudo for VPN client..."
        "$SCRIPT_DIR/setup-sudo.sh"
    else
        echo "  To install later: cp -r \"$APP\" /Applications/"
    fi
    echo ""
    echo "To share: zip -r TrustTunnel-macOS.zip \"$APP\""
else
    echo "ERROR: Build failed. Check output above."
    exit 1
fi
