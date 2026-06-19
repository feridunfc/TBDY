#!/usr/bin/env python
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tbdy_engine.product.golden_regression import run_geometry_golden_regression


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the C13.4-P8 offline golden geometry product regression gate")
    parser.add_argument("--feature-snapshot", required=True, help="Path to canonical FeatureSnapshot JSON input")
    parser.add_argument("--golden", required=True, help="Path to expected golden fingerprint JSON")
    parser.add_argument("--out", required=True, help="Output directory for regression run")
    parser.add_argument("--report", default=None, help="Optional regression report JSON path")
    args = parser.parse_args(argv)

    result = run_geometry_golden_regression(
        feature_snapshot_path=Path(args.feature_snapshot),
        output_dir=Path(args.out),
        golden_fingerprint_path=Path(args.golden),
        regression_report_path=Path(args.report) if args.report is not None else None,
    )

    print(f"Geometry golden regression: {result.status}")
    print(f"Output: {result.output_dir}")
    print(f"Bundle: {result.bundle_dir}")
    print(f"Validation: {result.validation_path}")
    print(f"Golden: {result.golden_fingerprint_path}")
    print(f"Report: {result.regression_report_path}")
    print(f"Differences: {result.difference_count}")
    print(f"Errors: {result.error_count}")
    return 0 if result.status == "OK" else 1


if __name__ == "__main__":
    raise SystemExit(main())
