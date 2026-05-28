from __future__ import annotations

import argparse
from pathlib import Path

from .report_markdown import load_archx_run_json, write_archx_markdown_report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render an ARCH-X JSON run artifact as a Markdown report.")
    parser.add_argument("--input", required=True, help="ARCH-X_RUN_RESULT JSON artifact path.")
    parser.add_argument("--out", required=True, help="Output Markdown report path.")
    args = parser.parse_args(argv)

    payload = load_archx_run_json(Path(args.input))
    output_path = write_archx_markdown_report(payload, Path(args.out))
    summary = payload.get("summary", {})
    by_status = summary.get("by_status", {})
    print(f"output_path={output_path}")
    print(f"total_check_results={summary.get('total_check_results', 0)}")
    print(f"OK={by_status.get('OK', 0)}")
    print(f"FAIL={by_status.get('FAIL', 0)}")
    print(f"NO_DATA={by_status.get('NO_DATA', 0)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
