#!/usr/bin/env python
"""Run C11 minimal geometry/global CheckEngine dry run from C10 artifacts.

This tool is fixture/manual-artifact safe: it never calls live ETABS, providers,
or feature resolvers. It executes MinimalCheckEngine only for the three C10
RUNNABLE allowlist rows.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tbdy_engine.checks.dry_run import build_and_write_c11_outputs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run C11 minimal CheckEngine dry run from C10 readiness artifacts.")
    parser.add_argument(
        "--feature-snapshot",
        default="local_out/c10_minimal_live_readiness/feature_snapshot_with_context.json",
        help="Path to C10 feature_snapshot_with_context.json",
    )
    parser.add_argument(
        "--coverage-matrix",
        default="local_out/c10_minimal_live_readiness/coverage_matrix.json",
        help="Path to C10 coverage_matrix.json",
    )
    parser.add_argument("--out", default="local_out/c11_minimal_check_dry_run", help="Output directory")
    args = parser.parse_args(argv)
    try:
        build_and_write_c11_outputs(Path(args.feature_snapshot), Path(args.coverage_matrix), Path(args.out))
        print(f"Wrote C11 minimal check dry-run outputs to {args.out}")
        return 0
    except Exception as exc:  # pragma: no cover - CLI safety boundary
        print(f"C11 minimal check dry-run failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
