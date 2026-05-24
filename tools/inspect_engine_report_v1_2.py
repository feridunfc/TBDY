
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT = PROJECT_ROOT / "reports_out" / "engine_report_enriched.json"

def _counter(rows: List[Dict[str, Any]], key: str) -> Counter:
    return Counter(str(r.get(key) or "<empty>") for r in rows if isinstance(r, dict))

def _print_counter(title: str, c: Counter, limit: int = 30):
    print(f"\n{title}:")
    for k, v in c.most_common(limit):
        print(f"  {k}: {v}")

def main(argv: List[str] | None = None) -> int:
    argv = argv or sys.argv[1:]
    path = Path(argv[0]) if argv else DEFAULT_REPORT
    path = path if path.is_absolute() else PROJECT_ROOT / path

    if not path.exists():
        fallback = PROJECT_ROOT / "reports_out" / "engine_report.json"
        print(f"WARNING: enriched report not found, using fallback: {fallback}")
        path = fallback

    d = json.loads(path.read_text(encoding="utf-8"))
    rows = [r for r in d.get("checks", []) if isinstance(r, dict)]

    print("ENGINE_REPORT_INSPECT_V1_2")
    print("path:", path)
    print("metadata:", d.get("report_metadata"))
    print("summary:", d.get("summary"))
    print("coverage:", d.get("coverage"))
    print("enrichment_summary:", d.get("enrichment_summary"))

    _print_counter("by_status", _counter(rows, "status"))
    _print_counter("by_check_id", _counter(rows, "check_id"))
    _print_counter("by_evaluation_level", _counter(rows, "evaluation_level"))
    _print_counter("by_source", _counter(rows, "source"))
    _print_counter("by_reason_code", _counter(rows, "reason_code"))
    _print_counter("by_category", _counter(rows, "category"))

    problems = [r for r in rows if str(r.get("status", "")).upper() in {"FAIL", "WARNING", "NO_DATA", "ERROR"}]

    print("\nfirst_20_problem_rows:")
    for r in problems[:20]:
        print(
            f"  {r.get('status')} | {r.get('check_id')} | {r.get('element_label')} | "
            f"level={r.get('evaluation_level')} | source={r.get('source')} | "
            f"reason={r.get('reason_code')} | msg={str(r.get('message') or '')[:140]}"
        )

    return 0

if __name__ == "__main__":
    raise SystemExit(main())
