#!/usr/bin/env python
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tbdy_engine.features.etabs_com_attach import EtabsAttachFailure
from tbdy_engine.features.live_etabs_geometry_probe import (
    create_live_etabs_geometry_provider,
    load_accepted_mapping_provider_from_json,
    load_mapping_provider_from_json,
    probe_geometry_feature_snapshots,
    write_com_attach_failure_probe_outputs,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create geometry FeatureSnapshot JSON from read-only ETABS geometry data")
    parser.add_argument("--live-etabs", action="store_true", help="Explicitly opt in to live ETABS probing")
    parser.add_argument("--out", required=True, help="Output directory for FeatureSnapshot and probe artifacts")
    parser.add_argument("--target-story", default=None, help="Optional story selector")
    parser.add_argument("--target-label", default=None, help="Optional frame label selector")
    parser.add_argument("--target-component", default=None, help="Optional component id selector")
    parser.add_argument("--max-rows", type=int, default=20, help="Maximum geometry rows to process")
    parser.add_argument("--max-candidate-tables", type=int, default=5, help="Maximum live ETABS candidate tables to inspect")
    parser.add_argument("--fake-provider-fixture", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--fake-assignment-rows-fixture", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--fake-property-definition-rows-fixture", default=None, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    if not args.live_etabs:
        print("Live ETABS geometry probing requires explicit --live-etabs opt-in; no ETABS connection was attempted.", file=sys.stderr)
        return 2

    try:
        if args.fake_provider_fixture is not None:
            provider = load_mapping_provider_from_json(Path(args.fake_provider_fixture))
        elif args.fake_assignment_rows_fixture is not None or args.fake_property_definition_rows_fixture is not None:
            if args.fake_assignment_rows_fixture is None or args.fake_property_definition_rows_fixture is None:
                raise ValueError("Both fake assignment and fake property definition fixtures are required for accepted mapping fixture mode")
            provider = load_accepted_mapping_provider_from_json(
                assignment_rows_path=Path(args.fake_assignment_rows_fixture),
                property_rows_path=Path(args.fake_property_definition_rows_fixture),
            )
        else:
            provider = create_live_etabs_geometry_provider(max_candidate_tables=args.max_candidate_tables)
        result = probe_geometry_feature_snapshots(
            provider=provider,
            output_dir=Path(args.out),
            target_story=args.target_story,
            target_label=args.target_label,
            target_component=args.target_component,
            max_rows=args.max_rows,
        )
    except EtabsAttachFailure as exc:
        result = write_com_attach_failure_probe_outputs(
            output_dir=Path(args.out),
            attach_result=exc.attach_result,
        )
        print("Live geometry probe: FAIL")
        print(f"Output: {result.output_dir}")
        print(f"Summary: {result.summary_path}")
        print(f"Diagnostics: {result.diagnostics_path}")
        print(f"Manifest: {result.manifest_path}")
        print("FeatureSnapshot: not written")
        return 1
    except Exception as exc:
        print("Live geometry probe: FAIL", file=sys.stderr)
        print(str(exc), file=sys.stderr)
        return 1

    print(f"Live geometry probe: {result.status}")
    print(f"Output: {result.output_dir}")
    print(f"FeatureSnapshot: {result.feature_snapshot_path}")
    print(f"Summary: {result.summary_path}")
    print(f"Diagnostics: {result.diagnostics_path}")
    print(f"Manifest: {result.manifest_path}")
    print(f"Snapshots: {result.snapshot_count}")
    print(f"Diagnostics count: {result.diagnostic_count}")
    return 0 if result.status in {"OK", "PARTIAL"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
