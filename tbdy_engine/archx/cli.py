from __future__ import annotations

import argparse
from pathlib import Path

from .demo import build_demo_snapshot
from .runner import run_archx_checks
from .serialization import write_archx_run_json


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run ARCH-X VS-1 demo checks and write deterministic JSON output.")
    parser.add_argument("--demo", action="store_true", help="Build and run the built-in deterministic ARCH-X demo snapshot.")
    parser.add_argument("--out", default="reports/archx_demo_run.json", help="Output JSON path.")
    parser.add_argument("--check-id", action="append", default=None, help="Optional check id filter. Can be repeated or comma-separated.")
    args = parser.parse_args(argv)

    if not args.demo:
        parser.error("VS-1 requires --demo because no external snapshot loader is implemented in this sprint.")

    result = run_archx_checks(build_demo_snapshot(), check_ids=args.check_id, run_id="archx-demo-run")
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
