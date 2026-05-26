#!/bin/bash
# Post-build fix: remove macOS permission plugins that cause CFBundleCopyBundleURL
# crash with console=False + PyInstaller.
#
# The qdarwinpermissionplugin (and other permission plugins) have C++ static
# initializers that call CFBundleCopyBundleURL during dlopen. When PyInstaller
# extracts to a temp dir without a valid NSBundle, this crashes with SIGSEGV.
#
# Removing the plugin dylibs prevents the static initializer from running the
# permission code path. The app doesn't use location services, so this is safe.
#
# Usage: ./fix-permission-plugins.sh dist/TrustTunnel.app

set -euo pipefail

APP="${1:?Usage: $0 <path-to-.app>}"
APP_RESOURCES="$APP/Contents/Resources"
APP_FRAMEWORKS="$APP/Contents/Frameworks"

echo "=== Fixing permission plugins in $APP ==="

# Find and remove permission plugin dylibs
REMOVED=0

# PyInstaller permission plugins location
for plugin_dir in \
    "$APP_RESOURCES/PyQt6/Qt6/plugins/permissions" \
    "$APP_RESOURCES/PyQt6/Qt/plugins/permissions" \
    "$APP_RESOURCES/plugins/permissions" \
    "$APP_FRAMEWORKS/PyQt6/Qt6/plugins/permissions" \
    "$APP_FRAMEWORKS/PyQt6/Qt/plugins/permissions" \
    ; do
    if [ -d "$plugin_dir" ]; then
        echo "  Removing: $plugin_dir"
        rm -rf "$plugin_dir"
        REMOVED=$((REMOVED + 1))
    fi
done

# Also check for any qdarwin* files anywhere in the bundle
find "$APP" -name "*qdarwin*" -o -name "*permission*plugin*" 2>/dev/null | while read -r f; do
    echo "  Removing: $f"
    rm -f "$f"
    REMOVED=$((REMOVED + 1))
done

if [ "$REMOVED" -eq 0 ]; then
    echo "  No permission plugins found (already clean)"
else
    echo "  Removed $REMOVED permission plugin(s)"
fi

echo "=== Done ==="
