#!/usr/bin/env python3
"""Entrypoint for every soCOM reconstruction workflow."""

from __future__ import annotations

import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools._socom.cli import main


if __name__ == "__main__":
    # Output is canonical JSON for automation: UTF-8 whatever the console
    # code page (Windows pipes default to cp1252).
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    raise SystemExit(main())

