from __future__ import annotations

from pathlib import Path
import argparse
import sys

from tbdy_engine.product.live_beam_column_minimum_compliance import (
    run_live_beam_column_minimum_compliance,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the C14.1-P1 live beam/column minimum compliance product")
    parser.add_argument("--live-etabs", action="store_true", help="Required explicit opt-in to attach to the running ETABS instance")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--element-type", choices=("beam", "column"))
    parser.add_argument("--story")
    parser.add_argument("--section")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if not args.live_etabs:
        print("ERROR: --live-etabs is required; no output was created.", file=sys.stderr)
        return 2
    result = run_live_beam_column_minimum_compliance(
        output_dir=args.out,
        element_type=args.element_type,
        story=args.story,
        section=args.section,
    )
    print(f"product_status={result.get('product_status')}")
    print(f"output_dir={args.out}")
    return 1 if result.get("product_status") == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
