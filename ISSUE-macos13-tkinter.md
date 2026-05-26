# Issue: macOS 13 Ventura — Python 3.11 tkinter build fails

**Status: Resolved** — app was rewritten from tkinter to PyQt6.

## Original problem

macOS 13 (Ventura) is Tier 3 for Homebrew — python@3.11 build fails with post-install errors.
MacPorts python311 doesn't include _tkinter module.

## Resolution

Rewrote the entire GUI from tkinter to PyQt6 (commit `8f84618`). PyQt6:
- Installs cleanly via `pip install PyQt6` on all macOS versions
- No tcl/tk dependency
- Native dark mode support
- Proper text rendering on Retina displays
- QSystemTrayIcon for menu bar integration

## Current requirements

- Python 3.11+ (Homebrew or MacPorts)
- PyQt6 + Pillow (installed by `build-app.sh`)

## See also

- `README.md` — updated build instructions
- `trusttunnel.spec` — PyInstaller config (no Tcl/Tk bundling)
