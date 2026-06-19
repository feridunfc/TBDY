#!/usr/bin/env python
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tbdy_engine.product.offline_acceptance import run_offline_product_acceptance


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the C13.4 offline product acceptance gate")
    parser.add_argument("--out", required=True, help="Output directory for acceptance report and generated artifacts")
    parser.add_argument("--stop-on-failure", action="store_true", help="Stop after the first failed command")
    args = parser.parse_args(argv)

    result = run_offline_product_acceptance(
        output_dir=Path(args.out),
        stop_on_failure=args.stop_on_failure,
    )

    print(f"Offline product acceptance: {result.status}")
    print(f"Output: {result.output_dir}")
    print(f"Report: {result.report_path}")
    print(f"Commands: {result.command_count}")
    print(f"Failed: {result.failed_command_count}")
    return 0 if result.status == "OK" else 1


if __name__ == "__main__":
    raise SystemExit(main())
