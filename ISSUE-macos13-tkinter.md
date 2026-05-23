# Issue: macOS 13 Ventura — Python 3.11 tkinter build fails

## Problem
macOS 13 (Ventura) is Tier 3 for Homebrew — python@3.11 build fails with post-install errors.
MacPorts python311 doesn't include _tkinter module.

## Steps to reproduce
1. Install MacPorts
2. `sudo port install python311 py-tkinter` — _tkinter missing
3. `brew install python@3.11` — build fails on Ventura (Tier 3)

## Expected
Working Python 3.11 with tkinter for PyInstaller build on macOS 13 Intel.

## Workaround attempted
- Homebrew: `brew install tcl-tk && brew reinstall python@3.11` — build takes 11+ min, post-install fails
- MacPorts: `sudo port install python311 py-tkinter` — _tkinter module missing

## Diagnostic output
```
=== Diagnostic ===
--- Python versions ---
/usr/local/bin/python3.11
/usr/bin/python3
--- MacPorts Python ---
MacPorts python3.11 not installed
--- Homebrew Python ---
Python 3.11.15
tkinter: FAIL
--- PyInstaller ---
PyInstaller not installed
=== End ===
```
