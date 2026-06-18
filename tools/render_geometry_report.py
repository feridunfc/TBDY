#!/usr/bin/env python
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tbdy_engine.reports.geometry_markdown_report import render_geometry_markdown_report_from_artifact_dir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render the C13.4-P5 geometry Markdown report")
    parser.add_argument("--artifact-dir", required=True, help="Directory containing C13.4-P4 JSON artifacts")
    parser.add_argument("--out", required=True, help="Output Markdown report path")
    args = parser.parse_args(argv)

    try:
        result = render_geometry_markdown_report_from_artifact_dir(
            artifact_dir=Path(args.artifact_dir),
            output_path=Path(args.out),
        )
    except Exception as exc:  # pragma: no cover - CLI boundary returns stable nonzero status.
        print("Geometry Markdown report: ERROR", file=sys.stderr)
        print(str(exc), file=sys.stderr)
        return 1

    print("Geometry Markdown report: OK")
    print(f"Sections: {result.section_count}")
    print(f"Tables: {len(result.table_names)}")
    print(f"Output: {result.report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
