#!/usr/bin/env python
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tbdy_engine.features.etabs_com_attach import EtabsAttachFailure
from tbdy_engine.features.live_etabs_table_discovery import (
    create_live_etabs_table_discovery_source,
    load_mapping_table_discovery_source_from_json,
    run_live_geometry_table_discovery,
    write_table_discovery_attach_failure_outputs,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Discover read-only ETABS geometry candidate tables")
    parser.add_argument("--live-etabs", action="store_true", help="Explicitly opt in to live ETABS table discovery")
    parser.add_argument("--out", required=True, help="Output directory for table discovery artifacts")
    parser.add_argument("--candidate-fetch-cap", type=int, default=5, help="Maximum candidate tables whose schemas are fetched")
    parser.add_argument("--fake-table-inventory", default=None, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    if not args.live_etabs:
        print("Live ETABS table discovery requires explicit --live-etabs opt-in; no ETABS connection was attempted.", file=sys.stderr)
        return 2

    try:
        if args.fake_table_inventory is not None:
            source = load_mapping_table_discovery_source_from_json(Path(args.fake_table_inventory))
        else:
            source = create_live_etabs_table_discovery_source()
        result = run_live_geometry_table_discovery(
            source=source,
            output_dir=Path(args.out),
            candidate_fetch_cap=args.candidate_fetch_cap,
        )
    except EtabsAttachFailure as exc:
        result = write_table_discovery_attach_failure_outputs(
            output_dir=Path(args.out),
            attach_result=exc.attach_result,
        )
        print("Live geometry table discovery: FAIL")
        print(f"Output: {Path(args.out)}")
        print("Accepted mapping: not written")
        return 1
    except Exception as exc:
        print("Live geometry table discovery: FAIL", file=sys.stderr)
        print(str(exc), file=sys.stderr)
        return 1

    print(f"Live geometry table discovery: {result.status}")
    print(f"Output: {Path(args.out)}")
    print(f"Tables: {result.table_count}")
    print(f"Candidates: {result.candidate_count}")
    print(f"Rejected: {result.rejected_count}")
    print(f"Diagnostics: {len(result.diagnostics)}")
    return 0 if result.status in {"OK", "PARTIAL"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
