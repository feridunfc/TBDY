from __future__ import annotations

import argparse
from pathlib import Path

from .demo import build_demo_snapshot
from .providers.etabs_workbook import build_snapshot_from_etabs_workbook, get_last_provider_diagnostics
from .runner import run_archx_checks
from .serialization import write_archx_run_json


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run ARCH-X checks and write deterministic JSON output.")
    parser.add_argument("--demo", action="store_true", help="Build and run the built-in deterministic ARCH-X demo snapshot.")
    parser.add_argument("--etabs-workbook", help="Path to a static ETABS-exported Excel workbook.")
    parser.add_argument("--manifest", help="Optional manifest JSON mapping ETABS table names to workbook sheet names.")
    parser.add_argument("--drift-limit", type=float, default=None, help="Optional story drift limit, for example 0.02.")
    parser.add_argument("--out", default="reports/archx_demo_run.json", help="Output JSON path.")
    parser.add_argument("--check-id", action="append", default=None, help="Optional check id filter. Can be repeated or comma-separated.")
    args = parser.parse_args(argv)

    if bool(args.demo) == bool(args.etabs_workbook):
        parser.error("Provide exactly one input source: --demo or --etabs-workbook.")

    provider_diagnostics: list[str] = []
    if args.demo:
        snapshot = build_demo_snapshot()
        run_id = "archx-demo-run"
    else:
        workbook_path = Path(args.etabs_workbook)
        if not workbook_path.exists():
            parser.error(f"ETABS workbook not found: {workbook_path}")
        try:
            snapshot = build_snapshot_from_etabs_workbook(workbook_path, manifest_path=args.manifest, drift_limit=args.drift_limit)
        except ImportError as exc:
            parser.error(f"Unable to read ETABS workbook. Optional Excel dependency may be missing: {exc}")
        except ValueError as exc:
            parser.error(str(exc))
        provider_diagnostics = get_last_provider_diagnostics()
        run_id = "archx-etabs-workbook-run"

    result = run_archx_checks(snapshot, check_ids=args.check_id, run_id=run_id)
    result.diagnostics.extend(provider_diagnostics)
    output_path = write_archx_run_json(result, Path(args.out))
    by_status = result.summary["by_status"]
    print(f"output_path={output_path}")
    print(f"total_check_results={result.summary['total_check_results']}")
    print(f"OK={by_status['OK']}")
    print(f"FAIL={by_status['FAIL']}")
    print(f"NO_DATA={by_status['NO_DATA']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
