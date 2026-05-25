#!/bin/bash
# Create a GitHub Release and upload the built TrustTunnel.app as a zip.
# Run this on your Mac AFTER build-app.sh has completed successfully.
#
# Usage:
#   ./release.sh           — auto-increments patch version (1.0.0 → 1.0.1)
#   ./release.sh v1.2.0    — use a specific version tag

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

APP="dist/TrustTunnel.app"

# ── Checks ──────────────────────────────────────────────────────────────────

if [ ! -d "$APP" ]; then
    echo "ERROR: $APP not found. Run ./build-app.sh first."
    exit 1
fi

if ! command -v gh &>/dev/null; then
    echo "ERROR: gh CLI not found. Install it:"
    echo "  brew install gh"
    echo "  gh auth login"
    exit 1
fi

if ! gh auth status &>/dev/null; then
    echo "ERROR: Not logged in to GitHub. Run: gh auth login"
    exit 1
fi

# ── Version ─────────────────────────────────────────────────────────────────

if [ -n "${1:-}" ]; then
    VERSION="$1"
    # Ensure it starts with v
    [[ "$VERSION" == v* ]] || VERSION="v$VERSION"
else
    # Auto-increment: get latest tag, bump patch
    LATEST=$(gh release list --limit 1 --json tagName --jq '.[0].tagName' 2>/dev/null || echo "")
    if [ -z "$LATEST" ]; then
        VERSION="v1.0.0"
    else
        # Strip leading v, split by dot
        IFS='.' read -r MAJOR MINOR PATCH <<< "${LATEST#v}"
        PATCH=$((PATCH + 1))
        VERSION="v${MAJOR}.${MINOR}.${PATCH}"
    fi
fi

echo "=== TrustTunnel macOS Release ==="
echo ""
echo "Version : $VERSION"
echo "App     : $APP ($(du -sh "$APP" | cut -f1))"
echo ""

# ── Zip ─────────────────────────────────────────────────────────────────────

ZIP="dist/TrustTunnel-macOS-${VERSION}.zip"
echo "Creating $ZIP ..."
cd dist
zip -r "TrustTunnel-macOS-${VERSION}.zip" TrustTunnel.app
cd "$SCRIPT_DIR"
echo "  $(du -sh "$ZIP" | cut -f1)"
echo ""

# ── Release notes ────────────────────────────────────────────────────────────

NOTES="## Installation

Paste this into Terminal — it downloads, installs, and configures everything automatically:

\`\`\`bash
curl -fsSL https://raw.githubusercontent.com/inhale/trusttunnel-macos/main/install-app.sh | bash
\`\`\`

The installer:
- Downloads the latest TrustTunnel.app
- Moves it to /Applications
- Removes the macOS quarantine flag (no Gatekeeper warning)
- Configures passwordless sudo for VPN — shows a standard macOS password dialog

> No Python, Homebrew, or Xcode required — the app is fully self-contained.

---

### macOS says 'app is damaged' or 'may be malware'?

macOS quarantines files downloaded through a browser. Fix it in Terminal:

\`\`\`bash
xattr -cr /Applications/TrustTunnel.app
\`\`\`

Then launch the app again."

# ── Publish ─────────────────────────────────────────────────────────────────

echo "Creating GitHub Release $VERSION ..."
gh release create "$VERSION" "$ZIP" \
    --title "TrustTunnel macOS $VERSION" \
    --notes "$NOTES"

echo ""
echo "✓ Released: https://github.com/inhale/trusttunnel-macos/releases/tag/$VERSION"
echo ""
echo "Send testers this one-liner (works for all future releases too):"
echo "  curl -fsSL https://raw.githubusercontent.com/inhale/trusttunnel-macos/main/install-app.sh | bash"
