#!/usr/bin/env python
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tbdy_engine.product.bundle_validator import validate_geometry_product_bundle


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate a C13.4-P6 geometry product smoke bundle")
    parser.add_argument("--bundle-dir", required=True, help="Directory containing a C13.4-P6 product smoke bundle")
    parser.add_argument("--out", default=None, help="Optional validation JSON output path")
    args = parser.parse_args(argv)

    bundle_dir = Path(args.bundle_dir)
    validation_path = Path(args.out) if args.out is not None else bundle_dir / "geometry_product_bundle_validation.json"
    result = validate_geometry_product_bundle(bundle_dir=bundle_dir, validation_output_path=validation_path)

    print(f"Geometry product bundle validation: {result.status}")
    print(f"Bundle: {result.bundle_dir}")
    print(f"Required files: {result.required_file_count}")
    print(f"CheckResults: {result.check_result_count}")
    print(f"Adapter diagnostics: {result.adapter_diagnostic_count}")
    print(f"Report tables: {result.checked_table_count}")
    print(f"Errors: {result.error_count}")
    print(f"Warnings: {result.warning_count}")
    print(f"Validation: {result.validation_path}")
    return 0 if result.status == "OK" else 1


if __name__ == "__main__":
    raise SystemExit(main())
