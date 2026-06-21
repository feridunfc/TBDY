#!/usr/bin/env python
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tbdy_engine.features.etabs_com_attach import EtabsAttachFailure
from tbdy_engine.features.live_etabs_concrete_material_probe import (
    create_live_etabs_concrete_material_provider,
    probe_concrete_material_feature_snapshots,
    write_concrete_material_attach_failure_outputs,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Create material-enriched FeatureSnapshot JSON from locked live ETABS tables"
    )
    parser.add_argument(
        "--live-etabs",
        action="store_true",
        help="Explicitly opt in to attaching to a running ETABS instance",
    )
    parser.add_argument("--out", required=True, help="Output directory for probe artifacts")
    parser.add_argument("--target-story", default=None, help="Optional story selector")
    parser.add_argument("--target-label", default=None, help="Optional frame label selector")
    parser.add_argument("--target-component", default=None, help="Optional component id selector")
    parser.add_argument("--max-rows", type=int, default=20, help="Maximum accepted rows to process")
    args = parser.parse_args(argv)

    if not args.live_etabs:
        print(
            "Live concrete-material probing requires explicit --live-etabs opt-in; "
            "no ETABS connection was attempted and no output was written.",
            file=sys.stderr,
        )
        return 2

    output_dir = Path(args.out)
    try:
        provider = create_live_etabs_concrete_material_provider()
        result = probe_concrete_material_feature_snapshots(
            provider=provider,
            output_dir=output_dir,
            target_story=args.target_story,
            target_label=args.target_label,
            target_component=args.target_component,
            max_rows=args.max_rows,
        )
    except EtabsAttachFailure as exc:
        result = write_concrete_material_attach_failure_outputs(
            output_dir=output_dir,
            attach_result=exc.attach_result,
        )
    except Exception as exc:
        print("Live concrete-material probe: FAIL", file=sys.stderr)
        print(str(exc), file=sys.stderr)
        return 1

    print(f"Live concrete-material probe: {result.status}")
    print(f"Output: {result.output_dir}")
    if result.feature_snapshot_path.is_file():
        print(f"FeatureSnapshot: {result.feature_snapshot_path}")
    else:
        print("FeatureSnapshot: not written")
    print(f"Summary: {result.summary_path}")
    print(f"Diagnostics: {result.diagnostics_path}")
    print(f"Manifest: {result.manifest_path}")
    print(f"Snapshots: {result.snapshot_count}")
    print(f"Diagnostics count: {result.diagnostic_count}")
    return 0 if result.status in {"OK", "PARTIAL"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
