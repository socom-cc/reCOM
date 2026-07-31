#!/usr/bin/env python3
"""Entrypoint for every soCOM reconstruction workflow."""

from __future__ import annotations

import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools._socom.cli import main


if __name__ == "__main__":
    raise SystemExit(main())

