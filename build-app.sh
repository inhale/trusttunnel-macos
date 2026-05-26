#!/bin/bash
# Build TrustTunnel.app for macOS distribution (PyQt6)
# Run this on your Mac (not on VPS — PyInstaller needs target OS)

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== TrustTunnel macOS App Builder (PyQt6) ==="
echo ""

# 1. Find Python 3.11+ with PyQt6
echo "=== Checking Python + PyQt6 ==="
echo ""

PYTHON=""
PYTHON_OK=""

# Check candidates one by one — each step prints its own status
check_candidate() {
    local py="$1"
    echo "  [CHECK] $py"

    if [ ! -e "$py" ]; then
        echo "          -> does not exist"
        return 1
    fi
    if [ ! -x "$py" ]; then
        echo "          -> not executable"
        return 1
    fi

    local raw_version
    raw_version=$("$py" -c "import sys; print(sys.version.split()[0])" 2>/dev/null)
    if [ -z "$raw_version" ]; then
        echo "          -> cannot get version"
        return 1
    fi
    echo "          -> Python $raw_version"

    # Check version >= 3.11
    local major minor
    major=$(echo "$raw_version" | cut -d. -f1)
    minor=$(echo "$raw_version" | cut -d. -f2)
    if [ "$major" -lt 3 ] || { [ "$major" -eq 3 ] && [ "$minor" -lt 11 ]; }; then
        echo "          -> version too old (need 3.11+)"
        return 1
    fi

    # Check PyQt6 without importing Qt (avoids display hang)
    local pyqt_version
    if [ -d "/Library/Frameworks/Python.framework" ]; then
        # System Python may not have importlib.metadata
        pyqt_version=$("$py" -c "
try:
    import importlib.metadata
    print(importlib.metadata.version('PyQt6'))
except Exception:
    try:
        import PyQt6.QtCore
        print(PyQt6.QtCore.PYQT_VERSION_STR)
    except:
        pass
" 2>/dev/null)
    else
        pyqt_version=$("$py" -c "
try:
    import importlib.metadata
    print(importlib.metadata.version('PyQt6'))
except Exception:
    pass
" 2>/dev/null)
    fi

    if [ -z "$pyqt_version" ]; then
        echo "          -> PyQt6 not installed"
        return 1
    fi

    echo "          -> PyQt6 $pyqt_version  ✓"
    PYTHON="$py"
    PYTHON_OK="Python $raw_version, PyQt6 $pyqt_version"
    return 0
}

# Search in priority order
FOUND=0

for candidate in \
    /opt/homebrew/bin/python3.13 \
    /opt/homebrew/bin/python3.12 \
    /opt/homebrew/bin/python3.11 \
    /opt/homebrew/bin/python3 \
    /opt/homebrew/opt/python@3.13/bin/python3.13 \
    /opt/homebrew/opt/python@3.12/bin/python3.12 \
    /opt/homebrew/opt/python@3.11/bin/python3.11 \
    /usr/local/bin/python3.13 \
    /usr/local/bin/python3.12 \
    /usr/local/bin/python3.11 \
    /usr/local/bin/python3 \
    /usr/local/opt/python@3.13/bin/python3.13 \
    /usr/local/opt/python@3.12/bin/python3.12 \
    /usr/local/opt/python@3.11/bin/python3.11 \
    /opt/local/bin/python3.13 \
    /opt/local/bin/python3.12 \
    /opt/local/bin/python3.11 \
    /opt/local/bin/python3 \
    "$HOME/.pyenv/shims/python3.13" \
    "$HOME/.pyenv/shims/python3.12" \
    "$HOME/.pyenv/shims/python3.11" \
    "$HOME/.pyenv/shims/python3" \
    /usr/bin/python3 \
    ; do
    [ -z "$candidate" ] && continue
    # Skip duplicates (pyenv shims may resolve to same binary)
    [ "$candidate" = "$PYTHON" ] 2>/dev/null && continue
    if check_candidate "$candidate"; then
        FOUND=1
        break
    fi
done

# If not found from hardcoded list, try PATH
if [ "$FOUND" -eq 0 ]; then
    echo ""
    echo "  Not found in standard locations, trying PATH..."
    for cmd in python3.13 python3.12 python3.11 python3; do
        _resolved="$(command -v "$cmd" 2>/dev/null || true)"
        if [ -n "$_resolved" ] && [ -x "$_resolved" ]; then
            if check_candidate "$_resolved"; then
                FOUND=1
                break
            fi
        fi
    done
fi

echo ""

if [ "$FOUND" -eq 0 ]; then
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║  ⚠  No Python 3.11+ with PyQt6 found.                     ║"
    echo "╠══════════════════════════════════════════════════════════════╣"
    echo "║                                                              ║"
    echo "║  Install steps:                                              ║"
    echo "║                                                              ║"

    # Find any Python 3.11+ to suggest, even without PyQt6
    _suggest_py=""
    for _p in /usr/local/bin/python3.13 /usr/local/bin/python3.12 /usr/local/bin/python3.11 /usr/local/bin/python3 /opt/homebrew/bin/python3.13 /opt/homebrew/bin/python3.12 /opt/homebrew/bin/python3.11 /opt/homebrew/bin/python3; do
        if [ -x "$_p" ]; then
            _v=$("$_p" -c "import sys; print('%d.%d' % (sys.version_info.major, sys.version_info.minor))" 2>/dev/null)
            if [ -n "$_v" ]; then
                _major=$(echo "$_v" | cut -d. -f1)
                _minor=$(echo "$_v" | cut -d. -f2)
                if [ "$_major" -ge 3 ] && [ "$_minor" -ge 11 ] 2>/dev/null; then
                    _suggest_py="$_p"
                    break
                fi
            fi
        fi
    done

    if [ -n "$_suggest_py" ]; then
        echo "║  You have Python 3.11+ at:                                   ║"
        echo "║    $_suggest_py"
        echo "║                                                              ║"
        echo "║  Install PyQt6 + PyInstaller:                                ║"
        printf "║    %-58s║\n" "$_suggest_py -m pip install PyQt6 PyInstaller"
    else
        echo "║  1. Install Homebrew Python:                                 ║"
        echo "║     brew install python@3.12                                 ║"
        echo "║                                                              ║"
        echo "║  2. Install PyQt6 + PyInstaller:                             ║"
        echo "║     pip3 install PyQt6 PyInstaller                           ║"
    fi

    echo "║                                                              ║"
    echo "║  3. Re-run: ./build-app.sh                                   ║"
    echo "║                                                              ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    exit 1
fi

echo "Found: $PYTHON  ($PYTHON_OK)"
echo ""

# 1.4. On Apple Silicon, prefer arm64 Python to avoid Rosetta issues
if [ "$(uname -s)" = "Darwin" ] && [ "$(uname -m)" = "arm64" ]; then
    PY_FILE=$(command -v "$PYTHON" 2>/dev/null || echo "$PYTHON")
    if file "$PY_FILE" 2>/dev/null | grep -q "x86_64"; then
        echo "  ⚠ Python is x86_64 — app will run under Rosetta on M1/M2/M3 Macs."
        echo "    For native arm64 builds, install arm64 Python:"
        echo "    arch -arm64 brew install python@3.12"
        echo "    Then re-run this script."
        echo ""
    fi
fi

# 1.5. Check PyQt6 version — >= 6.10 has qdarwinpermissionplugin which crashes
#     with console=False on macOS (CFBundleCopyBundleURL in static initializer).
#     Auto-downgrade to 6.9.1 which is the latest safe version.
echo "=== Checking PyQt6 version compatibility ==="
PYQT_VER=$("$PYTHON" -c "
import importlib.metadata as m
v = m.version('PyQt6')
print(v)
" 2>/dev/null)
PYQT_MAJOR=$(echo "$PYQT_VER" | cut -d. -f1)
PYQT_MINOR=$(echo "$PYQT_VER" | cut -d. -f2)
if [ -n "$PYQT_MAJOR" ] && [ -n "$PYQT_MINOR" ]; then
    if [ "$PYQT_MAJOR" -ge 6 ] && [ "$PYQT_MINOR" -ge 10 ]; then
        echo ""
        echo "  ⚠ PyQt6 $PYQT_VER detected — versions >= 6.10 crash on macOS"
        echo "    with console=False due to qdarwinpermissionplugin static initializer."
        echo "    Auto-downgrading to PyQt6 6.9.1 (latest safe version)..."
        echo ""
        "$PYTHON" -m pip install --quiet 'PyQt6==6.9.1' 'PyQt6-Qt6==6.9.1' 'PyQt6-sip>=13.10' 2>&1
        if [ $? -eq 0 ]; then
            # Verify the downgrade actually took effect
            VERIFIED_VER=$("$PYTHON" -c "
import importlib.metadata as m
print(m.version('PyQt6'))
" 2>/dev/null)
            VERIFIED_MINOR=$(echo "$VERIFIED_VER" | cut -d. -f2)
            if [ -n "$VERIFIED_MINOR" ] && [ "$VERIFIED_MINOR" -lt 10 ] 2>/dev/null; then
                echo "  ✓ PyQt6 downgraded to $VERIFIED_VER (verified)"
            else
                echo "  ✗ Downgrade reported success but PyQt6 is still $VERIFIED_VER"
                echo "    Try: $PYTHON -m pip install --force-reinstall 'PyQt6==6.9.1' 'PyQt6-Qt6==6.9.1'"
                exit 1
            fi
        else
            echo "  ✗ Auto-downgrade failed — install manually:"
            echo "    $PYTHON -m pip install 'PyQt6==6.9.1' 'PyQt6-Qt6==6.9.1'"
            echo ""
            echo "  Or use console=True (shows a terminal window):"
            echo "    Edit trusttunnel.spec: change console=False to console=True"
            exit 1
        fi
    else
        echo "  PyQt6 $PYQT_VER — OK (< 6.10, no qdarwinpermissionplugin)"
    fi
else
    echo "  ⚠ Could not determine PyQt6 version — assuming OK"
fi
echo ""

# 2. Install build dependencies
echo "=== Checking build dependencies ==="

if ! "$PYTHON" -c "import PyInstaller" 2>/dev/null; then
    echo "  -> Installing PyInstaller..."
    "$PYTHON" -m pip install --quiet PyInstaller 2>&1 || {
        echo "  Failed to install PyInstaller"
        exit 1
    }
fi
echo "  PyInstaller: $("$PYTHON" -c "import PyInstaller; print(PyInstaller.__version__)" 2>/dev/null || echo ok)"

if ! "$PYTHON" -c "import PIL" 2>/dev/null; then
    echo "  -> Installing Pillow..."
    "$PYTHON" -m pip install --quiet Pillow 2>&1 || true
fi
echo "  Pillow: $("$PYTHON" -c "from PIL import __version__; print(__version__)" 2>/dev/null || echo ok)"

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

# 4. Generate icon
echo ""
echo "=== Generating icon ==="
if [ -f "generate-icon.py" ]; then
    rm -f icon.icns
    "$PYTHON" generate-icon.py icon.icns
    echo "  icon.icns created (shield icon via generate-icon.py)"
else
    echo "  generate-icon.py not found, skipping icon generation"
fi

# 5. Build (universal2 on Apple Silicon)
echo ""
echo "=== Building .app ==="

# On Apple Silicon, build universal2 (arm64 + x86_64) if x86_64 Python is available
if [ "$(uname -s)" = "Darwin" ] && [ "$(uname -m)" = "arm64" ]; then
    X86_PYTHON=""
    for _py in /usr/local/bin/python3.12 /usr/local/bin/python3.13 /usr/local/bin/python3.11; do
        if [ -x "$_py" ] && file "$_py" 2>/dev/null | grep -q "x86_64"; then
            X86_PYTHON="$_py"
            break
        fi
    done

    if [ -n "$X86_PYTHON" ]; then
        echo "  Building universal2 (arm64 + x86_64)..."
        ARM_PYTHON="$PYTHON"

        # Check x86_64 Python has PyInstaller
        if ! "$X86_PYTHON" -c "import PyInstaller" 2>/dev/null; then
            echo "  ✗ x86_64 Python missing PyInstaller. Install it:"
            echo "    $X86_PYTHON -m pip install pyinstaller"
            echo "  Falling back to arm64 only."
            "$ARM_PYTHON" -m PyInstaller trusttunnel.spec --clean --noconfirm 2>&1
        else
            # Build arm64 version — force arm64 arch
            echo "  [1/3] Building arm64..."
            ARCHFLAGS="-arch arm64" "$ARM_PYTHON" -m PyInstaller trusttunnel.spec --clean --noconfirm --distpath dist_arm64 2>&1

            # Verify arm64 output
            ARM_OUTPUT="dist_arm64/TrustTunnel.app/Contents/MacOS/TrustTunnel"
            if [ -f "$ARM_OUTPUT" ]; then
                ARM_ARCH=$(file "$ARM_OUTPUT" 2>/dev/null | grep -o 'arm64\|x86_64' | head -1)
                echo "        -> $ARM_ARCH"
            fi

            # Build x86_64 version — force x86_64 arch via Rosetta
            echo "  [2/3] Building x86_64..."
            ARCHFLAGS="-arch x86_64" arch -x86_64 "$X86_PYTHON" -m PyInstaller trusttunnel.spec --clean --noconfirm --distpath dist_x86_64 2>&1

            # Verify x86_64 output
            X86_OUTPUT="dist_x86_64/TrustTunnel.app/Contents/MacOS/TrustTunnel"
            if [ -f "$X86_OUTPUT" ]; then
                X86_ARCH=$(file "$X86_OUTPUT" 2>/dev/null | grep -o 'arm64\|x86_64' | head -1)
                echo "        -> $X86_ARCH"
            fi

            # Merge with lipo
            echo "  [3/3] Merging with lipo..."
            if [ -f "$ARM_OUTPUT" ] && [ -f "$X86_OUTPUT" ]; then
                mkdir -p dist/TrustTunnel.app/Contents/MacOS
                lipo -create "$ARM_OUTPUT" "$X86_OUTPUT" \
                    -output dist/TrustTunnel.app/Contents/MacOS/TrustTunnel

                # Copy Info.plist from arm64 build (contains LSUIElement, console=True settings)
                cp dist_arm64/TrustTunnel.app/Contents/Info.plist dist/TrustTunnel.app/Contents/Info.plist

                # Merge Frameworks — lipo only the key dylibs that differ by arch
                # Framework bundles (Python.framework, Qt*.framework) must stay intact
                # for codesign to work. Only merge the specific dylib inside them.
                echo "  Merging key dylibs (lipo per-dylib)..."
                rm -rf dist/TrustTunnel.app/Contents/Frameworks

                ARM_FW="dist_arm64/TrustTunnel.app/Contents/Frameworks"
                X86_FW="dist_x86_64/TrustTunnel.app/Contents/Frameworks"
                OUT_FW="dist/TrustTunnel.app/Contents/Frameworks"

                # Copy Frameworks from arm64 (preserves Python.framework bundle structure for codesign)
                # Then lipo-merge key dylibs that are arch-specific
                cp -R "$ARM_FW" "$OUT_FW"
                echo "  Copied Frameworks: $(ls "$OUT_FW" | tr '\n' ' ')"

                # Lipo-merge key dylibs
                for lib in "Python" "PyQt6/QtCore.abi3.so" "PyQt6/QtGui.abi3.so" "PyQt6/QtWidgets.abi3.so" "python3.11/Python" "python3.12/Python" "python3.13/Python"; do
                    arm_lib="$ARM_FW/$lib"
                    x86_lib="$X86_FW/$lib"
                    out_lib="$OUT_FW/$lib"
                    arm_exists=$([ -f "$arm_lib" ] && echo "Y" || echo "N")
                    x86_exists=$([ -f "$x86_lib" ] && echo "Y" || echo "N")
                    if [ "$arm_exists" = "Y" ] && [ "$x86_exists" = "Y" ]; then
                        arm_arch=$(file "$arm_lib" 2>/dev/null | grep -o 'arm64\|x86_64' | head -1)
                        x86_arch=$(file "$x86_lib" 2>/dev/null | grep -o 'arm64\|x86_64' | head -1)
                        if [ "$arm_arch" != "$x86_arch" ]; then
                            lipo -create "$arm_lib" "$x86_lib" -output "$out_lib" 2>/dev/null && echo "    $lib: $arm_arch + $x86_arch -> merged"
                        else
                            echo "    $lib: both $arm_arch -> same arch, skipped"
                        fi
                    else
                        echo "    $lib: arm=$arm_exists x86=$x86_exists -> skipped (missing)"
                    fi
                done

                # Lipo-merge ALL .so files in python3.x/lib-dynload/ (Python C extensions)
                echo "  Merging Python C extensions (lib-dynload)..."
                for pyver in 3.11 3.12 3.13; do
                    ARM_DYNLOAD="$ARM_FW/python${pyver}/lib-dynload"
                    X86_DYNLOAD="$X86_FW/python${pyver}/lib-dynload"
                    OUT_DYNLOAD="$OUT_FW/python${pyver}/lib-dynload"
                    if [ -d "$ARM_DYNLOAD" ] && [ -d "$X86_DYNLOAD" ]; then
                        find "$ARM_DYNLOAD" -name "*.so" | while read -r arm_so; do
                            rel="${arm_so#$ARM_DYNLOAD/}"
                            x86_so="$X86_DYNLOAD/$rel"
                            out_so="$OUT_DYNLOAD/$rel"
                            if [ -f "$x86_so" ]; then
                                arm_arch=$(file "$arm_so" 2>/dev/null | grep -o 'arm64\|x86_64' | head -1)
                                x86_arch=$(file "$x86_so" 2>/dev/null | grep -o 'arm64\|x86_64' | head -1)
                                if [ "$arm_arch" != "$x86_arch" ]; then
                                    lipo -create "$arm_so" "$x86_so" -output "$out_so" 2>/dev/null && echo "    python${pyver}/lib-dynload/$rel: merged"
                                fi
                            fi
                        done
                    fi
                done

                echo "  ✓ Frameworks merged (bundle structure preserved)"

                # Copy Resources from arm64, then merge arch-specific dylibs from x86_64
                ARM_RES="dist_arm64/TrustTunnel.app/Contents/Resources"
                X86_RES="dist_x86_64/TrustTunnel.app/Contents/Resources"
                OUT_RES="dist/TrustTunnel.app/Contents/Resources"
                cp -R "$ARM_RES" "$OUT_RES"

                # Lipo-merge Resources/PyQt6/*.abi3.so (these are loaded at runtime)
                for abi3so in QtCore QtCore.abi3 QtWidgets QtWidgets.abi3 QtGui QtGui.abi3; do
                    for ext in ".abi3.so" ".so"; do
                        f="PyQt6/${abi3so}${ext}"
                        arm_file="$ARM_RES/$f"
                        x86_file="$X86_RES/$f"
                        out_file="$OUT_RES/$f"
                        # Strip .abi3.so → .so matching
                        [ -f "$arm_file" ] && [ -f "$x86_file" ] || continue
                        arm_arch=$(file "$arm_file" 2>/dev/null | grep -o 'arm64\|x86_64' | head -1)
                        x86_arch=$(file "$x86_file" 2>/dev/null | grep -o 'arm64\|x86_64' | head -1)
                        if [ "$arm_arch" != "$x86_arch" ]; then
                            lipo -create "$arm_file" "$x86_file" -output "$out_file" 2>/dev/null && echo "    Resources/$f: $arm_arch + $x86_arch -> merged"
                        fi
                    done
                done

                # Also lipo-merge any other .so/.dylib in Resources that differs by arch
                find "$ARM_RES" -name "*.so" -o -name "*.dylib" | while read -r arm_file; do
                    rel="${arm_file#$ARM_RES/}"
                    x86_file="$X86_RES/$rel"
                    out_file="$OUT_RES/$rel"
                    [ -f "$x86_file" ] && [ -f "$out_file" ] || continue
                    arm_arch=$(file "$arm_file" 2>/dev/null | grep -o 'arm64\|x86_64' | head -1)
                    x86_arch=$(file "$x86_file" 2>/dev/null | grep -o 'arm64\|x86_64' | head -1)
                    if [ "$arm_arch" != "$x86_arch" ]; then
                        lipo -create "$arm_file" "$x86_file" -output "$out_file" 2>/dev/null && echo "    Resources/$rel: merged"
                    fi
                done

            else
                echo "  ✗ One of the builds failed. Using arm64 only."
                cp -R dist_arm64/TrustTunnel.app dist/TrustTunnel.app
            fi
            # Debug: show where .abi3.so files are in each build
            echo "  [DEBUG] arm64 .abi3.so files:"
            find dist_arm64/TrustTunnel.app -name "*.abi3.so" -exec echo "    {}" \; 2>/dev/null || echo "    (none)"
            echo "  [DEBUG] x86_64 .abi3.so files:"
            find dist_x86_64/TrustTunnel.app -name "*.abi3.so" -exec echo "    {}" \; 2>/dev/null || echo "    (none)"
            echo "  [DEBUG] arm64 Resources/ top-level:"
            ls dist_arm64/TrustTunnel.app/Contents/Resources/ 2>/dev/null | head -20
            echo "  [DEBUG] x86_64 Resources/ top-level:"
            ls dist_x86_64/TrustTunnel.app/Contents/Resources/ 2>/dev/null | head -20

            # Save Info.plist from each build for inspection
            echo "  [DEBUG] arm64 Info.plist LSUIElement:"
            grep -a "LSUIElement" dist_arm64/TrustTunnel.app/Contents/Info.plist 2>/dev/null || echo "    NOT FOUND"
            echo "  [DEBUG] x86_64 Info.plist LSUIElement:"
            grep -a "LSUIElement" dist_x86_64/TrustTunnel.app/Contents/Info.plist 2>/dev/null || echo "    NOT FOUND"
            echo "  [DEBUG] merged Info.plist LSUIElement:"
            grep -a "LSUIElement" dist/TrustTunnel.app/Contents/Info.plist 2>/dev/null || echo "    NOT FOUND"

            # Don't clean up — leave dirs for inspection
            # rm -rf dist_arm64 dist_x86_64
        fi
    else
        echo "  No x86_64 Python found — building arm64 only"
        "$PYTHON" -m PyInstaller trusttunnel.spec --clean --noconfirm 2>&1
    fi
else
    "$PYTHON" -m PyInstaller trusttunnel.spec --clean --noconfirm 2>&1
fi

# 5.5. Remove permission plugins that cause CFBundleCopyBundleURL crash
echo ""
echo "=== Removing macOS permission plugins ==="
if [ -f "fix-permission-plugins.sh" ]; then
    chmod +x fix-permission-plugins.sh
    ./fix-permission-plugins.sh dist/TrustTunnel.app 2>&1
else
    echo "  fix-permission-plugins.sh not found, skipping"
fi

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
    echo "  -> /Applications/TrustTunnel.app"
    # Auto-configure sudo (always run to ensure correct binary path)
    echo ""
    echo "  Configuring passwordless sudo for VPN client..."
    "$SCRIPT_DIR/setup-sudo.sh"

    echo ""
    echo "✓ Installed: /Applications/TrustTunnel.app"
    echo ""
    echo "To debug crashes, run:"
    echo "  QT_DEBUG_PLUGINS=1 /Applications/TrustTunnel.app/Contents/MacOS/TrustTunnel 2>&1 | head -50"
    echo ""
    echo "To share: zip -r TrustTunnel-macOS.zip \"$APP\""
else
    echo "ERROR: Build failed. Check output above."
    exit 1
fi
