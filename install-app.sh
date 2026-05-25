#!/bin/bash
# TrustTunnel macOS one-liner installer
# Usage: curl -fsSL https://raw.githubusercontent.com/inhale/trusttunnel-macos/main/install-app.sh | bash
#
# What it does:
#   1. Downloads the latest TrustTunnel.app release zip from GitHub
#   2. Unzips and moves the app to /Applications
#   3. Strips the quarantine flag (prevents Gatekeeper "malware" dialog)
#   4. Runs setup-sudo.sh to configure passwordless sudo for VPN
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
