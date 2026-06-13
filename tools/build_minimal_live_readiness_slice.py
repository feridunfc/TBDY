#!/usr/bin/env python
"""Build C10 minimal live/fixture readiness outputs.

Manual/local smoke helper. This script is import-safe without ETABS and never
executes CheckEngine or emits engineering verdicts.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tbdy_engine.coverage.live_readiness import build_and_write_c10_outputs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build C10 minimal readiness coverage outputs from C8 FeatureSnapshot")
    parser.add_argument("--feature-snapshot", required=True, help="Path to C8 feature_snapshot.json")
    parser.add_argument("--design-context", required=True, help="Path to explicit design context JSON")
    parser.add_argument("--coverage-input", help="Optional C9 coverage matrix path; accepted for traceability but C10 rebuilds readiness")
    parser.add_argument("--manual-etabs-feedback", help="Optional manual ETABS feedback JSON, reference-only")
    parser.add_argument("--out", default="local_out/c10_minimal_live_readiness", help="Output directory")
    args = parser.parse_args(argv)
    try:
        build_and_write_c10_outputs(
            Path(args.feature_snapshot),
            Path(args.design_context),
            Path(args.out),
            coverage_input_path=Path(args.coverage_input) if args.coverage_input else None,
            manual_feedback_path=Path(args.manual_etabs_feedback) if args.manual_etabs_feedback else None,
        )
        print(f"Wrote C10 minimal readiness outputs to {args.out}")
        return 0
    except Exception as exc:  # pragma: no cover - CLI defensive boundary
        print(f"C10 minimal readiness build failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
