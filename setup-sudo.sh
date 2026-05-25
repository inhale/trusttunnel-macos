#!/bin/bash
# Configure passwordless sudo for TrustTunnel VPN client
# Run once after installing TrustTunnel.app to /Applications
# Safe to run via: curl -fsSL ... | bash

set -euo pipefail

APP_CLI="/Applications/TrustTunnel.app/Contents/Resources/bin/trusttunnel_client"
BREW_CLI="/usr/local/bin/trusttunnel_client"
OPT_CLI="/opt/trusttunnel_client/trusttunnel_client"
SUDOERS_FILE="/etc/sudoers.d/trusttunnel"

echo "=== TrustTunnel Sudo Setup ==="
echo ""
echo "TrustTunnel needs root to create a virtual network interface (utun)."
echo "This script adds passwordless sudo for the trusttunnel_client binary."
echo ""

# Find the binary
CLI_PATH=""
if [ -f "$APP_CLI" ]; then
    CLI_PATH="$APP_CLI"
elif [ -f "$BREW_CLI" ]; then
    CLI_PATH="$BREW_CLI"
elif [ -f "$OPT_CLI" ]; then
    CLI_PATH="$OPT_CLI"
fi

if [ -z "$CLI_PATH" ]; then
    echo "ERROR: trusttunnel_client not found."
    echo "Searched: $APP_CLI, $BREW_CLI, $OPT_CLI"
    exit 1
fi

echo "Found: $CLI_PATH"
echo ""

# Determine the real user (works when already root or called via sudo)
REAL_USER="${SUDO_USER:-${USER:-$(id -un)}}"
echo "Configuring sudo for user: $REAL_USER"
echo ""

# Write sudoers file via tee (avoids any shell quoting/newline issues)
SUDOERS_LINE="$REAL_USER ALL=(ALL) NOPASSWD: $CLI_PATH"

echo "Need sudo to write $SUDOERS_FILE (you will be prompted for your password):"
printf '# TrustTunnel VPN — passwordless sudo for the client binary\n%s\n' "$SUDOERS_LINE" \
    | sudo tee "$SUDOERS_FILE" > /dev/null
sudo chmod 440 "$SUDOERS_FILE"

# Verify syntax
if sudo visudo -c -f "$SUDOERS_FILE" >/dev/null 2>&1; then
    echo "✓ Done! $REAL_USER can now run $CLI_PATH without a password."
    echo ""
    echo "To verify:"
    echo "  sudo -n $CLI_PATH --version"
else
    echo "ERROR: sudoers syntax error. Removing file."
    sudo rm -f "$SUDOERS_FILE"
    exit 1
fi
