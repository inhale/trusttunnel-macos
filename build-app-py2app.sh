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

# On Apple Silicon, build universal2
if [ "$(uname -s)" = "Darwin" ] && [ "$(uname -m)" = "arm64" ]; then
    # Find x86_64 Python and libpython
    X86_PYTHON=""
    for _py in /usr/local/bin/python3.12 /usr/local/bin/python3.13 /usr/local/bin/python3.11; do
        if [ -x "$_py" ] && file "$_py" 2>/dev/null | grep -q "x86_64"; then
            X86_PYTHON="$_py"
            break
        fi
    done

    X86_LIBPYTHON=""
    for _d in \
        /usr/local/Cellar/python@3.12/*/Frameworks/Python.framework/Versions/3.12/lib \
        /usr/local/Cellar/python@3.13/*/Frameworks/Python.framework/Versions/3.13/lib \
        /usr/local/lib \
        /usr/local/Frameworks/Python.framework/Versions/Current/lib; do
        if [ -f "$_d/libpython3.12.dylib" ] && file "$_d/libpython3.12.dylib" 2>/dev/null | grep -q "x86_64"; then
            X86_LIBPYTHON="$_d/libpython3.12.dylib"
            break
        fi
        if [ -f "$_d/libpython3.13.dylib" ] && file "$_d/libpython3.13.dylib" 2>/dev/null | grep -q "x86_64"; then
            X86_LIBPYTHON="$_d/libpython3.13.dylib"
            break
        fi
    done

    HAVE_X86=0
    if [ -n "$X86_PYTHON" ] && [ -n "$X86_LIBPYTHON" ]; then
        echo "  x86_64 Python found: $X86_PYTHON"
        HAVE_X86=1
    else
        echo "  ⚠ No x86_64 Python — will build arm64 only"
    fi
fi

# --- arm64 build ---
echo "  [1/3] Building arm64..."
rm -rf build dist dist_arm64
mkdir -p dist_arm64
ARCHFLAGS="-arch arm64" "$PYTHON" setup.py py2app 2>&1 | tee /tmp/py2app_arm64.log
if [ ! -d "dist/TrustTunnel.app" ]; then
    echo "  ✗ ARM64 BUILD FAILED"
    tail -20 /tmp/py2app_arm64.log
    exit 1
fi
mv dist/TrustTunnel.app dist_arm64/TrustTunnel.app
echo "        -> $(file dist_arm64/TrustTunnel.app/Contents/MacOS/TrustTunnel | grep -o 'arm64\|x86_64' | head -1)"

# --- x86_64 build ---
X86_APP=""
if [ "$HAVE_X86" = "1" ]; then
    echo "  [2/3] Building x86_64..."
    "$X86_PYTHON" -c "import py2app" 2>/dev/null || "$X86_PYTHON" -m pip install --quiet --break-system-packages py2app modulegraph 2>&1
    "$X86_PYTHON" -c "import PIL" 2>/dev/null || "$X86_PYTHON" -m pip install --quiet --break-system-packages Pillow 2>&1
    rm -rf build .eggs
    [ -d "$HOME/.py2app" ] && rm -rf "$HOME/.py2app"
    mkdir -p dist_x86_64
    ARCHFLAGS="-arch x86_64" arch -x86_64 "$X86_PYTHON" setup.py py2app 2>&1 | tee /tmp/py2app_x86_64.log
    if [ -d "dist/TrustTunnel.app" ]; then
        mv dist/TrustTunnel.app dist_x86_64/TrustTunnel.app
        X86_APP="dist_x86_64/TrustTunnel.app"
        echo "        -> $(file $X86_APP/Contents/MacOS/TrustTunnel | grep -o 'arm64\|x86_64' | head -1)"
    else
        echo "        -> FAILED (non-fatal, will use arm64 main binary)"
        tail -5 /tmp/py2app_x86_64.log
    fi
fi

# --- merge ---
echo "  [3/3] Merging universal2..."
rm -rf dist/TrustTunnel.app
cp -R dist_arm64/TrustTunnel.app dist/TrustTunnel.app

# lipo main binary
if [ -n "$X86_APP" ] && [ -f "$X86_APP/Contents/MacOS/TrustTunnel" ]; then
    lipo -create dist_arm64/TrustTunnel.app/Contents/MacOS/TrustTunnel \
                "$X86_APP/Contents/MacOS/TrustTunnel" \
           -output dist/TrustTunnel.app/Contents/MacOS/TrustTunnel 2>/dev/null && \
        echo "  ✓ Main binary: arm64 + x86_64"
else
    echo "  → Main binary: arm64 only (x86_64 build failed)"
fi

# lipo python interpreter
if [ -n "$X86_APP" ] && [ -f "$X86_APP/Contents/MacOS/python" ]; then
    lipo -create dist_arm64/TrustTunnel.app/Contents/MacOS/python \
                "$X86_APP/Contents/MacOS/python" \
           -output dist/TrustTunnel.app/Contents/MacOS/python 2>/dev/null && \
        echo "  ✓ Python interpreter: arm64 + x86_64"
fi

# lipo Python.framework
ARM_FW="dist_arm64/TrustTunnel.app/Contents/Frameworks/Python.framework/Versions/3.12/Python"
if [ -f "$ARM_FW" ] && [ -n "$X86_LIBPYTHON" ]; then
    FW_ARCH=$(file "$ARM_FW" | grep -o 'arm64\|x86_64' | head -1)
    X86_ARCH=$(file "$X86_LIBPYTHON" | grep -o 'arm64\|x86_64' | head -1)
    if [ "$FW_ARCH" != "$X86_ARCH" ]; then
        lipo -create "$ARM_FW" "$X86_LIBPYTHON" \
               -output dist/TrustTunnel.app/Contents/Frameworks/Python.framework/Versions/3.12/Python.tmp 2>/dev/null && \
            mv dist/TrustTunnel.app/Contents/Frameworks/Python.framework/Versions/3.12/Python.tmp \
               dist/TrustTunnel.app/Contents/Frameworks/Python.framework/Versions/3.12/Python && \
            echo "  ✓ Python.framework: $FW_ARCH + $X86_ARCH"
    fi
fi

# lipo .so and .dylib files
if [ -n "$X86_APP" ]; then
    for f in $(find dist_arm64/TrustTunnel.app/Contents -name "*.so" -o -name "*.dylib" 2>/dev/null); do
        rel="${f#dist_arm64/TrustTunnel.app/Contents/}"
        x86_f="$X86_APP/Contents/$rel"
        out="dist/TrustTunnel.app/Contents/$rel"
        [ ! -f "$x86_f" ] && continue
        a_arch=$(file "$f" | grep -o 'arm64\|x86_64' | head -1)
        x_arch=$(file "$x86_f" | grep -o 'arm64\|x86_64' | head -1)
        [ "$a_arch" = "$x_arch" ] && continue
        mkdir -p "$(dirname "$out")"
        lipo -create "$f" "$x86_f" -output "$out" 2>/dev/null && echo "    merged: $rel"
    done
fi

lipo -info dist/TrustTunnel.app/Contents/MacOS/TrustTunnel 2>/dev/null

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

    # Verify architectures — catch arm64-only Python.framework before release
    echo "  [VERIFY] Mach-O architectures:"
    MAIN_ARCH=$(file "$APP/Contents/MacOS/TrustTunnel" 2>/dev/null | grep -o 'arm64\|x86_64' | sort -u | tr '\n' '+')
    echo "    MacOS/TrustTunnel: $MAIN_ARCH"
    FW_PYTHON="$APP/Contents/Frameworks/Python.framework/Versions/3.12/Python"
    if [ -f "$FW_PYTHON" ]; then
        FW_ARCH=$(file "$FW_PYTHON" 2>/dev/null | grep -o 'arm64\|x86_64' | sort -u | tr '\n' '+')
        echo "    Python.framework:  $FW_ARCH"
        FW_COUNT=$(echo "$FW_ARCH" | tr '+' '\n' | grep -c 'arm64\|x86_64')
        if [ "$FW_COUNT" -lt 2 ]; then
            echo ""
            echo "  ✗ FATAL: Python.framework is NOT universal2 (only $FW_ARCH) — Intel Macs will crash!"
            echo "    The universal2 merge step missed the framework. Fix build-app-py2app.sh."
            exit 1
        fi
    else
        echo "    Python.framework:  NOT FOUND (will be bundled below)"
    fi

    # Bundle Python shared library as a framework (for non-framework Pythons
    # like Homebrew where py2app doesn't auto-create the framework structure).
    # The C stub at MacOS/TrustTunnel does dlopen() on PyRuntimeLocations,
    # so Frameworks/Python.framework/Versions/X.Y/Python must be a dylib.
    # Use a helper Python script to bundle the framework and fix Info.plist.
    # This runs as: python3 - "$APP" (reads the script from stdin via heredoc)
    "$PYTHON" - "$APP" << 'PYEOF'
import sys, os, shutil, plistlib

appdir = sys.argv[1]

# Get version/runtime info from THIS Python (the one that built the app)
py_ver = "%d.%d" % sys.version_info[:2]
py_prefix = sys.prefix
import sysconfig
py_libdir = sysconfig.get_config_var("LIBDIR") or ""

libpython = "libpython%s.dylib" % py_ver
fw_dir = os.path.join(appdir, "Contents", "Frameworks", "Python.framework")
fw_vers = os.path.join(fw_dir, "Versions", py_ver)

if os.path.exists(os.path.join(fw_vers, "Python")):
    print("  Python.framework already present: %s/Python" % fw_vers)
else:
    print("  Bundling Python %s framework..." % py_ver)
    os.makedirs(os.path.join(fw_vers, "lib"), exist_ok=True)
    os.makedirs(os.path.join(fw_dir, "Resources"), exist_ok=True)

    found = None
    for d in [py_libdir, os.path.join(py_prefix, "lib"),
              "/opt/homebrew/lib", "/usr/local/lib"]:
        if d and os.path.isfile(os.path.join(d, libpython)):
            found = os.path.join(d, libpython)
            break

    if not found:
        print("  FATAL: Cannot find %s" % libpython)
        sys.exit(1)

    print("    dylib: %s" % found)
    shutil.copy2(found, os.path.join(fw_vers, "lib", libpython))

    # Symlink: Versions/X.Y/Python -> lib/libpythonX.Y.dylib
    py_bin = os.path.join(fw_vers, "Python")
    if os.path.lexists(py_bin):
        os.remove(py_bin)
    os.symlink("lib/" + libpython, py_bin)

    # Framework symlinks
    for src, dst in [
        (py_ver, os.path.join(fw_dir, "Versions", "Current")),
        ("Versions/Current/Python", os.path.join(fw_dir, "Python")),
        ("Versions/Current/lib", os.path.join(fw_dir, "lib")),
    ]:
        if os.path.lexists(dst):
            os.remove(dst)
        os.symlink(src, dst)

    # Framework Info.plist
    plist = {
        "CFBundleName": "Python",
        "CFBundleIdentifier": "org.python.python",
        "CFBundleVersion": py_ver,
        "CFBundleShortVersionString": py_ver,
        "CFBundleExecutable": "Python",
        "CFBundlePackageType": "FMFW",
        "CFBundleSignature": "????",
    }
    with open(os.path.join(fw_dir, "Resources", "Info.plist"), "wb") as f:
        plistlib.dump(plist, f)
    print("    -> %s/Python -> lib/%s" % (fw_vers, libpython))

# Copy the real Python interpreter to Contents/MacOS/python.
# The C stub's getPythonInterpreter() looks for an auxiliary executable
# named "python" via CFBundleCopyAuxiliaryExecutableURL. Without it,
# CFStringGetCString crashes on the NULL return value.
python_bin = os.path.join(appdir, "Contents", "MacOS", "python")
import shutil
shutil.copy2(sys.executable, python_bin)
os.chmod(python_bin, 0o755)
print("    -> %s (interpreter)" % python_bin)

# Fix app Info.plist: PyRuntimeLocations + clean template keys
app_plist = os.path.join(appdir, "Contents", "Info.plist")
with open(app_plist, "rb") as f:
    pl = plistlib.load(f)
pl["PyRuntimeLocations"] = [
    "@executable_path/../Frameworks/Python.framework/Versions/%s/Python" % py_ver
]
for k in ("PyResourcePackages",):
    pl.pop(k, None)
with open(app_plist, "wb") as f:
    plistlib.dump(pl, f)
print("  PyRuntimeLocations OK")
PYEOF

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
