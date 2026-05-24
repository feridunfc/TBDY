from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("report", nargs="?", default="reports_out/engine_report.json")
    parser.add_argument("--top", type=int, default=15)
    args = parser.parse_args()

    path = Path(args.report)
    if not path.exists():
        print(f"Report not found: {path}")
        return 1

    data = json.loads(path.read_text(encoding="utf-8"))
    checks = data.get("checks", []) or []

    print("ENGINE_REPORT_INSPECT")
    print("path:", path)
    print("metadata:", data.get("report_metadata", {}))
    print("summary:", data.get("summary", {}))
    print("coverage:", data.get("coverage", {}))

    for title, key in [
        ("status", "status"),
        ("check_id", "check_id"),
        ("evaluation_level", "evaluation_level"),
        ("source", "source"),
        ("category", "category"),
    ]:
        counter = Counter((item.get(key) or "<empty>") for item in checks)
        print(f"\nby_{title}:")
        for value, count in counter.most_common(args.top):
            print(f"  {value}: {count}")

    problem_rows = [x for x in checks if x.get("status") in {"FAIL", "WARNING", "ERROR", "NO_DATA"}]
    print(f"\nfirst_{args.top}_problem_rows:")
    for item in problem_rows[: args.top]:
        print(
            f"  {item.get('status')} | {item.get('check_id')} | {item.get('element_label')} | "
            f"level={item.get('evaluation_level')} | source={item.get('source')} | "
            f"msg={str(item.get('message',''))[:180]}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
