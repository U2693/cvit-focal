#!/usr/bin/env python3
"""Compatibility wrapper for building the cvit guest OS image."""
import sys
from pathlib import Path

root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))

from cvit.build import main

if __name__ == "__main__":
    main()
