#!/usr/bin/env python
"""Compatibility entrypoint for the integrated VS6 column design engine.

The former direct live rebar-selection runner consumed raw ETABS combination
rows and caller-supplied bar diameters. That path is intentionally retired.
Invoking this historical filename now delegates to the production integrated
engine adapter, which derives combination scope from factual combo topology and
uses the factual ETABS reinforcing-bar catalog.
"""
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.run_live_vs6_column_design_engine import main


if __name__ == "__main__":
    raise SystemExit(main())
