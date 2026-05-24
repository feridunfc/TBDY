from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from typing import List

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT = PROJECT_ROOT / "reports_out" / "final_engine_report.json"

def c(rows, key):
    return Counter(str(r.get(key) or "<empty>") for r in rows if isinstance(r, dict))

def print_counter(title, counter, limit=25):
    print(f"\n{title}:")
    for k, v in counter.most_common(limit):
        print(f"  {k}: {v}")

def main(argv: List[str] | None = None) -> int:
    argv = argv or sys.argv[1:]
    path = Path(argv[0]) if argv else DEFAULT_REPORT
    path = path if path.is_absolute() else PROJECT_ROOT / path
    if not path.exists():
        print(f"ERROR: final report not found: {path}")
        return 2

    d = json.loads(path.read_text(encoding="utf-8"))
    rows = [r for r in d.get("checks", []) if isinstance(r, dict)]
    conf = [r for r in rows if r.get("check_id") == "column_confinement"]

    print("FINAL_ENGINE_REPORT_INSPECT_V1")
    print("path:", path)
    print("metadata:", d.get("report_metadata"))
    print("summary:", d.get("summary"))
    print("final_summary:", d.get("final_summary"))
    print("confinement_policy_summary:", d.get("confinement_policy_summary"))

    print_counter("by_status", c(rows, "status"))
    print_counter("by_check_id", c(rows, "check_id"))
    print_counter("by_evaluation_level", c(rows, "evaluation_level"))
    print_counter("by_source", c(rows, "source"))
    print_counter("by_reason_code", c(rows, "reason_code"))

    print("\ncolumn_confinement first_10:")
    for r in conf[:10]:
        print(
            f"  {r.get('status')} | {r.get('element_label')} | level={r.get('evaluation_level')} | "
            f"source={r.get('source')} | reason={r.get('reason_code')} | "
            f"Ash={r.get('Ash_provided')}/{r.get('Ash_required')} | "
            f"spacing={r.get('spacing_mm')} | legs={r.get('legs_x')}/{r.get('legs_y')}"
        )
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
