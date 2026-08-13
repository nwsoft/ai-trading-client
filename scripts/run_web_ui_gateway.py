#!/usr/bin/env python3
"""Run the v3.9.1.0 read-only Web UI gateway from the repository root."""

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from web_platform.launcher import main


if __name__ == "__main__":
    raise SystemExit(main())
