#!/usr/bin/env python3
"""Checkout entrypoint for the lean workflow; legacy bin/harness.py is unchanged."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from harness_core.lean import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
