#!/usr/bin/env python
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tbdy_engine.product.geometry_product_smoke import run_geometry_product_smoke


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the C13.4-P6 geometry product smoke command")
    parser.add_argument("--feature-snapshot", required=True, help="Path to FeatureSnapshot JSON input")
    parser.add_argument("--out", required=True, help="Output directory for product smoke bundle")
    parser.add_argument("--catalog-dir", default=None, help="Optional catalog directory containing check_catalog.yaml")
    args = parser.parse_args(argv)

    try:
        result = run_geometry_product_smoke(
            feature_snapshot_path=Path(args.feature_snapshot),
            output_dir=Path(args.out),
            catalog_dir=Path(args.catalog_dir) if args.catalog_dir is not None else None,
        )
    except Exception as exc:  # pragma: no cover - CLI boundary returns stable nonzero status.
        print("Geometry product smoke: ERROR", file=sys.stderr)
        print(str(exc), file=sys.stderr)
        return 1

    print("Geometry product smoke: OK")
    print(f"Artifacts: {result.artifact_dir}")
    print(f"Report: {result.report_path}")
    print(f"CheckResults: {result.p4_check_result_count}")
    print(f"Adapter diagnostics: {result.p4_adapter_diagnostic_count}")
    print(f"Sections: {result.p5_section_count}")
    print(f"Tables: {result.p5_table_count}")
    print(f"Summary: {result.product_smoke_summary_path}")
    print(f"Manifest: {result.product_smoke_manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
