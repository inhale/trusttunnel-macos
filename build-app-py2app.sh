#!/bin/bash
# Build TrustTunnel.app for macOS distribution (PyQt6 + py2app)
# Run this on your Mac (not on VPS — py2app needs target OS)

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== TrustTunnel macOS App Builder (py2app) ==="
echo ""

# 1. Find Python 3.11+ with PyQt6
echo "=== Checking Python + PyQt6 ==="
echo ""

PYTHON=""
PYTHON_RAW=""
PYTHON_PYQT=""

check_candidate() {
    local py="$1"
    [ ! -e "$py" ] && return 1
    [ ! -x "$py" ] && return 1

    local raw_version
    raw_version=$("$py" -c "import sys; print(sys.version.split()[0])" 2>/dev/null)
    [ -z "$raw_version" ] && return 1

    local major minor
    major=$(echo "$raw_version" | cut -d. -f1)
    minor=$(echo "$raw_version" | cut -d. -f2)
    [ "$major" -lt 3 ] && return 1
    [ "$major" -eq 3 ] && [ "$minor" -lt 11 ] && return 1

    local pyqt_version
    pyqt_version=$("$py" -c "
try:
    import importlib.metadata; print(importlib.metadata.version('PyQt6'))
except Exception: pass
" 2>/dev/null)

    [ -z "$pyqt_version" ] && { echo "  [CHECK] $py -> Python $raw_version, PyQt6 missing"; return 1; }

    echo "  [CHECK] $py -> Python $raw_version, PyQt6 $pyqt_version ✓"
    PYTHON="$py"
    PYTHON_RAW="$raw_version"
    PYTHON_PYQT="$pyqt_version"
    return 0
}

FOUND=0
for candidate in \
    /opt/homebrew/bin/python3.13 /opt/homebrew/bin/python3.12 /opt/homebrew/bin/python3.11 \
    /opt/homebrew/bin/python3 \
    /usr/local/bin/python3.13 /usr/local/bin/python3.12 /usr/local/bin/python3.11 \
    /usr/local/bin/python3 \
    /opt/local/bin/python3.13 /opt/local/bin/python3.12 /opt/local/bin/python3.11 \
    /opt/local/bin/python3 \
    "$HOME/.pyenv/shims/python3.13" "$HOME/.pyenv/shims/python3.12" \
    "$HOME/.pyenv/shims/python3.11" "$HOME/.pyenv/shims/python3" \
    /usr/bin/python3; do
    [ -z "$candidate" ] && continue
    [ "$candidate" = "$PYTHON" ] 2>/dev/null && continue
    if check_candidate "$candidate"; then
        FOUND=1
        break
    fi
done

if [ "$FOUND" -eq 0 ]; then
    for cmd in python3.13 python3.12 python3.11 python3; do
        _resolved="$(command -v "$cmd" 2>/dev/null || true)"
        if [ -n "$_resolved" ] && [ -x "$_resolved" ] && check_candidate "$_resolved"; then
            FOUND=1; break
        fi
    done
fi

echo ""
if [ "$FOUND" -eq 0 ]; then
    echo "ERROR: No Python 3.11+ with PyQt6 found."
    echo "Install: brew install python@3.12 && pip3 install PyQt6 py2app Pillow"
    exit 1
fi

echo "Found: $PYTHON (Python $PYTHON_RAW, PyQt6 $PYTHON_PYQT)"
echo ""

# 1.4. On Apple Silicon, prefer arm64 Python
if [ "$(uname -s)" = "Darwin" ] && [ "$(uname -m)" = "arm64" ]; then
    PY_FILE=$(command -v "$PYTHON" 2>/dev/null || echo "$PYTHON")
    if file "$PY_FILE" 2>/dev/null | grep -q "x86_64"; then
        echo "  ⚠ Python is x86_64 — app will run under Rosetta."
        echo "    For native arm64: arch -arm64 brew install python@3.12"
        echo ""
    fi
fi

# 2. Install build dependencies
echo "=== Checking build dependencies ==="

if ! "$PYTHON" -c "import py2app" 2>/dev/null; then
    echo "  -> Installing py2app..."
    "$PYTHON" -m pip install --quiet --break-system-packages py2app modulegraph 2>&1 || {
        echo "  Failed to install py2app"
        exit 1
    }
fi

if ! "$PYTHON" -c "import PIL" 2>/dev/null; then
    echo "  -> Installing Pillow..."
    "$PYTHON" -m pip install --quiet --break-system-packages Pillow 2>&1 || true
fi
echo "  OK"
echo ""

# 3. Download TrustTunnel client binary
echo "=== TrustTunnel CLI client ==="
if [ ! -f "bin/trusttunnel_client" ]; then
    mkdir -p bin
    TT_VERSION="v1.0.49"
    TT_URL="https://github.com/TrustTunnel/TrustTunnelClient/releases/download/${TT_VERSION}/trusttunnel_client-${TT_VERSION}-macos-universal.tar.gz"
    curl -fsSL "$TT_URL" | tar xz --strip-components=1 -C bin/ trusttunnel_client-${TT_VERSION}-macos-universal/trusttunnel_client
    chmod +x bin/trusttunnel_client
    rm -f bin/LICENSE bin/*.sig
    echo "  bin/trusttunnel_client ($(du -sh bin/trusttunnel_client | cut -f1))"
else
    echo "  bin/trusttunnel_client (already bundled)"
fi
echo ""

# 4. Generate icon
echo "=== Generating icon ==="
if [ -f "generate-icon.py" ]; then
    rm -f icon.icns
    "$PYTHON" generate-icon.py icon.icns
    echo "  icon.icns created"
else
    echo "  generate-icon.py not found, skipping"
fi
echo ""

# 5. Build .app with py2app
echo "=== Building .app ==="

# Clean previous build
rm -rf build dist dist_arm64 dist_x86_64

# On Apple Silicon, try universal2 if x86_64 Python exists
if false && [ "$(uname -s)" = "Darwin" ] && [ "$(uname -m)" = "arm64" ]; then
    X86_PYTHON=""
    for _py in /usr/local/bin/python3.12 /usr/local/bin/python3.13 /usr/local/bin/python3.11; do
        if [ -x "$_py" ] && file "$_py" 2>/dev/null | grep -q "x86_64"; then
            X86_PYTHON="$_py"
            break
        fi
    done

    if [ -n "$X86_PYTHON" ]; then
        echo "  Building universal2 (arm64 + x86_64)..."
        echo ""

        # --- arm64 build ---
        echo "  [1/3] Building arm64..."
        rm -rf build dist dist_arm64
        mkdir -p dist_arm64
        ARCHFLAGS="-arch arm64" "$PYTHON" setup.py py2app 2>&1 | tee /tmp/py2app_arm64.log
        if [ -d "dist/TrustTunnel.app" ]; then
            mv dist/TrustTunnel.app dist_arm64/TrustTunnel.app
            ARM_APP="dist_arm64/TrustTunnel.app"
            echo "        -> $(file "$ARM_APP/Contents/MacOS/TrustTunnel" 2>/dev/null | grep -o 'arm64\|x86_64' | head -1)"
        else
            ARM_APP=""
            echo "        -> FAILED"
            tail -10 /tmp/py2app_arm64.log
            echo ""
            echo "ARM64 BUILD FAILED — cannot continue."
            exit 1
        fi
        echo ""

        # --- x86_64 build ---
        echo "  [2/3] Building x86_64..."
        "$X86_PYTHON" -c "import py2app" 2>/dev/null || "$X86_PYTHON" -m pip install --quiet --break-system-packages py2app modulegraph 2>&1
        "$X86_PYTHON" -c "import PIL" 2>/dev/null || "$X86_PYTHON" -m pip install --quiet --break-system-packages Pillow 2>&1
        # Clear all py2app caches to pick up newly installed modules
        rm -rf build .eggs
        [ -d "$HOME/.py2app" ] && rm -rf "$HOME/.py2app"
        mkdir -p dist_x86_64
        ARCHFLAGS="-arch x86_64" arch -x86_64 "$X86_PYTHON" setup.py py2app 2>&1 | tee /tmp/py2app_x86_64.log
        if [ -d "dist/TrustTunnel.app" ]; then
            mv dist/TrustTunnel.app dist_x86_64/TrustTunnel.app
            X86_APP="dist_x86_64/TrustTunnel.app"
            echo "        -> $(file "$X86_APP/Contents/MacOS/TrustTunnel" 2>/dev/null | grep -o 'arm64\|x86_64' | head -1)"
        else
            X86_APP=""
            echo "        -> FAILED"
            tail -10 /tmp/py2app_x86_64.log
            echo ""
            echo "X86_64 BUILD FAILED — falling back to arm64 only."
        fi
        echo ""

        # --- merge ---
        echo "  [3/3] Merging..."
        if [ -d "$ARM_APP" ] && [ -n "$X86_APP" ] && [ -d "$X86_APP" ]; then
            rm -rf dist/TrustTunnel.app
            cp -R "$ARM_APP" dist/TrustTunnel.app

            lipo -create "$ARM_APP/Contents/MacOS/TrustTunnel" \
                        "$X86_APP/Contents/MacOS/TrustTunnel" \
                   -output dist/TrustTunnel.app/Contents/MacOS/TrustTunnel 2>/dev/null

            for arm_file in $(find "$ARM_APP/Contents" \( -name "*.so" -o -name "*.dylib" \) 2>/dev/null); do
                rel="${arm_file#$ARM_APP/Contents/}"
                x86_file="$X86_APP/Contents/$rel"
                out_file="dist/TrustTunnel.app/Contents/$rel"
                [ ! -f "$x86_file" ] && continue
                arm_arch=$(file "$arm_file" 2>/dev/null | grep -o 'arm64\|x86_64' | head -1)
                x86_arch=$(file "$x86_file" 2>/dev/null | grep -o 'arm64\|x86_64' | head -1)
                if [ "$arm_arch" != "$x86_arch" ]; then
                    mkdir -p "$(dirname "$out_file")"
                    lipo -create "$arm_file" "$x86_file" -output "$out_file" 2>/dev/null && echo "    $rel: $arm_arch + $x86_arch -> merged"
                fi
            done
            echo "  ✓ Universal2 binary"
        elif [ -d "$ARM_APP" ]; then
            rm -rf dist/TrustTunnel.app
            cp -R "$ARM_APP" dist/TrustTunnel.app
            echo "  → arm64 only (x86_64 build failed)"
        else
            echo "  ✗ FATAL: arm64 build artifact missing"
            exit 1
        fi
    else
        echo "  No x86_64 Python — building arm64 only"
        "$PYTHON" setup.py py2app 2>&1
    fi
else
    "$PYTHON" setup.py py2app 2>&1
fi

# 6. Verify and install
APP="dist/TrustTunnel.app"
echo ""
if [ -d "$APP" ]; then
    SIZE=$(du -sh "$APP" | cut -f1)
    echo "App: $SCRIPT_DIR/$APP ($SIZE)"
    echo ""

    # Verify LSUIElement
    if grep -aq "LSUIElement" "$APP/Contents/Info.plist" 2>/dev/null; then
        echo "  ✓ LSUIElement found in Info.plist"
    else
        echo "  ✗ WARNING: LSUIElement NOT found in Info.plist"
    fi

    # DEBUG: show what's in the bundle before our fix
    echo "  [DEBUG] Frameworks/ contents:"
    ls -la "$APP/Contents/Frameworks/" 2>&1 | head -5
    echo "  [DEBUG] Looking for libpython..."
    find "$APP" -name "libpython*" -type f 2>/dev/null | head -5

    # Bundle Python shared library as a framework (for non-framework Pythons
    # like Homebrew where py2app doesn't auto-create the framework structure).
    # The C stub at MacOS/TrustTunnel does dlopen() on PyRuntimeLocations,
    # so Frameworks/Python.framework/Versions/X.Y/Python must be a dylib.
    PYTHON_VERSION=$(python3 -c "import sys; print('%d.%d' % sys.version_info[:2])")
    LIBPYTHON="libpython${PYTHON_VERSION}.dylib"
    PY_FW="$APP/Contents/Frameworks/Python.framework"
    PY_FW_VERS="$PY_FW/Versions/$PYTHON_VERSION"

    if [ ! -e "$PY_FW_VERS/Python" ]; then
        echo "  Bundling Python framework..."
        mkdir -p "$PY_FW_VERS/lib"

        # Find the dylib: try build tree, sys.prefix/lib, sysconfig LIBDIR
        FOUND_LIB=""
        for libpath in \
            "build/bdist.macosx-*/python${PYTHON_VERSION}-standalone/app/Frameworks/${LIBPYTHON}" \
            "$(python3 -c "import sysconfig; print(sysconfig.get_config_var('LIBDIR'))" 2>/dev/null)/${LIBPYTHON}" \
            "$(python3 -c "import sys; print(sys.prefix)" 2>/dev/null)/lib/${LIBPYTHON}" \
            "/opt/homebrew/lib/${LIBPYTHON}" \
            "/usr/local/lib/${LIBPYTHON}"; do
            for p in $libpath; do
                if [ -f "$p" ]; then FOUND_LIB="$p"; break 2; fi
            done
        done

        if [ -z "$FOUND_LIB" ]; then
            echo "  ✗ FATAL: Cannot find $LIBPYTHON"
            exit 1
        fi

        echo "    dylib: $FOUND_LIB"
        cp "$FOUND_LIB" "$PY_FW_VERS/lib/${LIBPYTHON}"
        # The framework 'Python' binary that dlopen() targets: symlink to the dylib
        ln -sf "lib/${LIBPYTHON}" "$PY_FW_VERS/Python"

        # Framework symlinks
        ln -sf "$PYTHON_VERSION" "$PY_FW/Versions/Current"
        ln -sf "Versions/Current/Python" "$PY_FW/Python"
        ln -sf "Versions/Current/lib" "$PY_FW/lib"

        # Minimal framework Info.plist
        cat > "$PY_FW/Resources/Info.plist" << FWPLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleName</key><string>Python</string>
<key>CFBundleIdentifier</key><string>org.python.python</string>
<key>CFBundleVersion</key><string>${PYTHON_VERSION}</string>
<key>CFBundleShortVersionString</key><string>${PYTHON_VERSION}</string>
<key>CFBundleExecutable</key><string>Python</string>
<key>CFBundlePackageType</key><string>FMFW</string>
<key>CFBundleSignature</key><string>????</string>
</dict></plist>
FWPLIST

        echo "    → $PY_FW_VERS/Python → lib/${LIBPYTHON}"
    else
        echo "  Python.framework already present: $PY_FW_VERS/Python"
    fi

    # Fix PyRuntimeLocations to match the framework we just created,
    # and remove template-only keys from the app's Info.plist.
    python3 -c "
import plistlib
p = '$APP/Contents/Info.plist'
with open(p, 'rb') as f:
    pl = plistlib.load(f)
pl['PyRuntimeLocations'] = [
    '@executable_path/../Frameworks/Python.framework/Versions/${PYTHON_VERSION}/Python'
]
for key in ('PyMainFileNames','PyResourcePackages'):
    pl.pop(key, None)
with open(p, 'wb') as f:
    plistlib.dump(pl, f)
print('  PyRuntimeLocations OK')
" 2>&1

    # Ad-hoc codesign
    echo "  Signing (ad-hoc)..."
    codesign --force --deep --sign - "$APP" 2>/dev/null && echo "  ✓ Signed" || echo "  ⚠ codesign failed"
    xattr -cr "$APP" 2>/dev/null || true

    # Install
    echo ""
    echo "=== Installing to /Applications ==="
    rm -rf /Applications/TrustTunnel.app
    cp -R "$APP" /Applications/
    echo "  -> /Applications/TrustTunnel.app"

    # Configure sudo
    echo ""
    echo "Configuring passwordless sudo..."
    "$SCRIPT_DIR/setup-sudo.sh"

    echo ""
    echo "✓ Done! Launch from /Applications or Spotlight."
else
    echo "ERROR: Build failed."
    exit 1
fi
