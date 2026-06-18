#!/usr/bin/env python
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tbdy_engine.checks.geometry_vertical_slice import run_geometry_vertical_slice_from_file


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the C13.4-P4 geometry vertical slice")
    parser.add_argument("--feature-snapshot", required=True, help="Path to FeatureSnapshot JSON input")
    parser.add_argument("--out", required=True, help="Output directory for P4 JSON artifacts")
    parser.add_argument("--catalog-dir", default="tbdy_engine/catalogs", help="Catalog directory containing check_catalog.yaml")
    args = parser.parse_args(argv)

    try:
        result = run_geometry_vertical_slice_from_file(
            feature_snapshot_path=Path(args.feature_snapshot),
            output_dir=Path(args.out),
            catalog_dir=Path(args.catalog_dir),
        )
    except Exception as exc:  # pragma: no cover - CLI boundary returns stable nonzero status.
        print(f"Geometry vertical slice: ERROR", file=sys.stderr)
        print(str(exc), file=sys.stderr)
        return 1

    print("Geometry vertical slice: OK")
    print(f"Snapshots: {result.run_summary['snapshot_count']}")
    print(f"Executable inputs: {result.run_summary['executable_input_count']}")
    print(f"CheckResults: {result.run_summary['check_result_count']}")
    print(f"Adapter diagnostics: {result.run_summary['adapter_diagnostic_count']}")
    print(f"Output: {Path(args.out)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
