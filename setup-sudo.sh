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

SUDOERS_LINE="$REAL_USER ALL=(ALL) NOPASSWD: $CLI_PATH"
SUDOERS_CONTENT="# TrustTunnel VPN — passwordless sudo for the client binary
$SUDOERS_LINE
"

_write_sudoers() {
    # Called as root (either directly or via sudo below)
    printf '%s' "$SUDOERS_CONTENT" > "$SUDOERS_FILE"
    chmod 440 "$SUDOERS_FILE"
    if visudo -c -f "$SUDOERS_FILE" >/dev/null 2>&1; then
        echo "✓ Done! $REAL_USER can now run $CLI_PATH without a password."
        echo ""
        echo "To verify:"
        echo "  sudo -n $CLI_PATH --version"
    else
        echo "ERROR: sudoers syntax error. Removing file."
        rm -f "$SUDOERS_FILE"
        exit 1
    fi
}

if [ "$(id -u)" -eq 0 ]; then
    # Already root
    _write_sudoers
else
    # Need privilege — pass everything via environment, no file re-exec
    echo "Need sudo to write $SUDOERS_FILE (you will be prompted for your password):"
    sudo bash -c "
        SUDOERS_FILE='$SUDOERS_FILE'
        REAL_USER='$REAL_USER'
        CLI_PATH='$CLI_PATH'
        SUDOERS_CONTENT='$SUDOERS_CONTENT'
        printf '%s' \"\$SUDOERS_CONTENT\" > \"\$SUDOERS_FILE\"
        chmod 440 \"\$SUDOERS_FILE\"
        if visudo -c -f \"\$SUDOERS_FILE\" >/dev/null 2>&1; then
            echo \"✓ Done! \$REAL_USER can now run \$CLI_PATH without a password.\"
        else
            echo 'ERROR: sudoers syntax error. Removing file.'
            rm -f \"\$SUDOERS_FILE\"
            exit 1
        fi
    "
fi
