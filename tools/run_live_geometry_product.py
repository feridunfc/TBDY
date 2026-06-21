#!/usr/bin/env python
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tbdy_engine.product.live_geometry_product import run_live_geometry_product


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the C13.5-P7 live ETABS geometry product orchestration"
    )
    parser.add_argument(
        "--live-etabs",
        action="store_true",
        help="Explicitly opt in to attaching to a running ETABS instance",
    )
    parser.add_argument("--out", required=True, help="Output directory for the live product bundle")
    parser.add_argument("--target-story", default=None, help="Optional story selector")
    parser.add_argument("--target-label", default=None, help="Optional frame label selector")
    parser.add_argument("--target-component", default=None, help="Optional component id selector")
    parser.add_argument("--max-rows", type=int, default=20, help="Maximum geometry rows to process")
    args = parser.parse_args(argv)

    if not args.live_etabs:
        print(
            "Live geometry product execution requires explicit --live-etabs opt-in; "
            "no ETABS connection was attempted and no output was written.",
            file=sys.stderr,
        )
        return 2

    result = run_live_geometry_product(
        output_dir=Path(args.out),
        target_story=args.target_story,
        target_label=args.target_label,
        target_component=args.target_component,
        max_rows=args.max_rows,
    )

    print(f"Live geometry product: {result.status}")
    print(f"Output: {result.output_dir}")
    print(f"Live probe: {result.live_probe_output_dir}")
    print(f"Product: {result.product_output_dir}")
    print(f"Summary: {result.summary_path}")
    print(f"Manifest: {result.manifest_path}")
    if result.feature_snapshot_path is None:
        print("FeatureSnapshot: not written")
    else:
        print(f"FeatureSnapshot: {result.feature_snapshot_path}")
    print(f"Snapshots: {result.snapshot_count}")
    return 0 if result.status in {"OK", "PARTIAL"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
