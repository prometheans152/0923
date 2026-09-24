"""Convenience verification script for Gate 2 SQLite queries.

Safely displays database count and sample query rows without exposing secrets.
"""
from __future__ import annotations

from pathlib import Path
import sys

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from database import main_cli

if __name__ == "__main__":
    main_cli()
