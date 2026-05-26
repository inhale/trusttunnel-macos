#!/bin/bash
# TrustTunnel macOS installer
# Usage: curl -fsSL https://raw.githubusercontent.com/inhale/trusttunnel-macos/main/install-app.sh | bash
#
# Two modes:
#   1. Pre-built app (default) — downloads the latest release .app from GitHub
#   2. Build from source — if Python 3.11+ with PyQt6 is detected, offers to build
#
# What it does:
#   - Checks Python/PyQt6 version (if present), downgrades PyQt6 if needed
#   - Downloads the latest TrustTunnel.app release zip from GitHub
#   - Unzips and moves the app to /Applications
#   - Strips the quarantine flag (prevents Gatekeeper "malware" dialog)
#   - Runs setup-sudo.sh to configure passwordless sudo for VPN
set -euo pipefail

REPO="inhale/trusttunnel-macos"
INSTALL_DIR="/Applications"
APP_NAME="TrustTunnel.app"

echo "=== TrustTunnel macOS Installer ==="
echo ""

# ── macOS check ──────────────────────────────────────────────────────────────
if [[ "$(uname)" != "Darwin" ]]; then
    echo "ERROR: This installer is for macOS only."
    exit 1
fi

# ── PyQt6 version check (if Python is available) ─────────────────────────────
# PyQt6 >= 6.10 crashes on macOS with PyInstaller console=False.
# If Python + PyQt6 is present, ensure the version is safe.
if command -v python3 &>/dev/null; then
    PYQT_VER=$(python3 -c "
try:
    import importlib.metadata as m
    print(m.version('PyQt6'))
except Exception:
    pass
" 2>/dev/null || true)

    if [ -n "$PYQT_VER" ]; then
        PYQT_MINOR=$(echo "$PYQT_VER" | cut -d. -f2)
        if [ -n "$PYQT_MINOR" ] && [ "$PYQT_MINOR" -ge 10 ] 2>/dev/null; then
            echo "⚠ PyQt6 $PYQT_VER detected — versions >= 6.10 crash on macOS."
            echo "  Downgrading to PyQt6 6.9.1..."
            echo ""
            python3 -m pip install --quiet 'PyQt6==6.9.1' 'PyQt6-Qt6==6.9.1' 2>&1 || {
                echo "  ✗ Auto-downgrade failed. Fix manually:"
                echo "    pip3 install 'PyQt6==6.9.1' 'PyQt6-Qt6==6.9.1'"
                echo ""
                echo "  Continuing with pre-built app download..."
                echo ""
            }
            # Verify
            NEW_VER=$(python3 -c "
try:
    import importlib.metadata as m
    print(m.version('PyQt6'))
except Exception:
    pass
" 2>/dev/null || true)
            if [ -n "$NEW_VER" ]; then
                NEW_MINOR=$(echo "$NEW_VER" | cut -d. -f2)
                if [ -n "$NEW_MINOR" ] && [ "$NEW_MINOR" -lt 10 ] 2>/dev/null; then
                    echo "  ✓ PyQt6 downgraded to $NEW_VER"
                else
                    echo "  ⚠ PyQt6 still $NEW_VER — build from source may crash."
                    echo "    Fix: pip3 install --force-reinstall 'PyQt6==6.9.1' 'PyQt6-Qt6==6.9.1'"
                fi
            fi
            echo ""
        else
            echo "  PyQt6 $PYQT_VER — OK (< 6.10)"
            echo ""
        fi
    fi
fi

# ── Find latest release zip URL ──────────────────────────────────────────────
echo "Fetching latest release info..."
LATEST_JSON=$(curl -fsSL "https://api.github.com/repos/${REPO}/releases/latest")
ZIP_URL=$(echo "$LATEST_JSON" | grep '"browser_download_url"' | grep '\.zip"' | head -1 | sed 's/.*"browser_download_url": "\(.*\)"/\1/' | tr -d '"')
VERSION=$(echo "$LATEST_JSON" | grep '"tag_name"' | head -1 | sed 's/.*"tag_name": "\(.*\)".*/\1/' | tr -d '"')

if [ -z "$ZIP_URL" ]; then
    echo "ERROR: Could not find a .zip asset in the latest release."
    echo "Check: https://github.com/${REPO}/releases/latest"
    exit 1
fi

echo "Version : $VERSION"
echo "Download: $ZIP_URL"
echo ""

# ── Download ─────────────────────────────────────────────────────────────────
TMPDIR_WORK=$(mktemp -d)
trap 'rm -rf "$TMPDIR_WORK"' EXIT

ZIP_PATH="$TMPDIR_WORK/TrustTunnel.zip"
echo "Downloading..."
curl -fsSL --progress-bar "$ZIP_URL" -o "$ZIP_PATH"
echo ""

# ── Unzip ─────────────────────────────────────────────────────────────────────
echo "Unpacking..."
unzip -q "$ZIP_PATH" -d "$TMPDIR_WORK"

APP_SRC=$(find "$TMPDIR_WORK" -name "$APP_NAME" -maxdepth 2 | head -1)
if [ -z "$APP_SRC" ]; then
    echo "ERROR: $APP_NAME not found in zip."
    exit 1
fi

# ── Strip quarantine BEFORE moving (prevents Gatekeeper dialog) ───────────────
echo "Removing quarantine flag..."
xattr -cr "$APP_SRC"

# ── Install to /Applications ──────────────────────────────────────────────────
APP_DEST="$INSTALL_DIR/$APP_NAME"
if [ -d "$APP_DEST" ]; then
    echo "Replacing existing $APP_DEST ..."
    rm -rf "$APP_DEST"
fi
cp -R "$APP_SRC" "$APP_DEST"
echo "Installed: $APP_DEST"
echo ""

# ── Configure passwordless sudo for VPN ──────────────────────────────────────
echo "Configuring sudo for VPN (requires your password once)..."
SETUP_SH_URL="https://raw.githubusercontent.com/${REPO}/main/setup-sudo.sh"
curl -fsSL "$SETUP_SH_URL" | bash
echo ""

echo "=== Done! ==="
echo ""
echo "Launch TrustTunnel from /Applications or Spotlight."
