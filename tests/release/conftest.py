from __future__ import annotations

import sys
from pathlib import Path

TOOL = Path(__file__).resolve().parents[2] / "tools" / "release"
if str(TOOL) not in sys.path:
    sys.path.insert(0, str(TOOL))
HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
