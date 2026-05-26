#!/usr/bin/env python3
"""Standalone entry point for py2app bundling.

Usage (dev):  python3 run.py
Usage (build): python3 setup.py py2app
"""
import sys
import os

# Ensure src/ is on the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.app import main

if __name__ == "__main__":
    main()
