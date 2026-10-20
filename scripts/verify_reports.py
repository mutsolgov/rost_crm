#!/usr/bin/env python3
"""Wrapper for docs/checks/verify_reports.py."""
import runpy
from pathlib import Path

if __name__ == "__main__":
    target = Path(__file__).resolve().parent.parent / "docs" / "checks" / "verify_reports.py"
    runpy.run_path(str(target), run_name="__main__")
