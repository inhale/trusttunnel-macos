#!/bin/bash
# TrustTunnel macOS launcher
# Sets up proper bundle environment before launching the Python app

# Get the directory where this script lives
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CONTENTS_DIR="$(dirname "$SCRIPT_DIR")"
RESOURCES_DIR="$CONTENTS_DIR/Resources"

# Set up bundle environment so CFBundleGetMainBundle() works
export CF_BUNDLE_PATH="$CONTENTS_DIR"
export CF_BUNDLE_EXECUTABLE="TrustTunnel"

# Launch the actual Python binary
exec "$SCRIPT_DIR/TrustTunnel_bin" "$@"
