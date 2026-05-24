
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT = PROJECT_ROOT / "reports_out" / "engine_report_confinement_policy.json"

def c(rows, key):
    return Counter(str(r.get(key) or "<empty>") for r in rows if isinstance(r, dict))

def main(argv=None):
    argv = argv or sys.argv[1:]
    path = Path(argv[0]) if argv else DEFAULT_REPORT
    path = path if path.is_absolute() else PROJECT_ROOT / path

    if not path.exists():
        print(f"ERROR: report not found: {path}")
        return 2

    d = json.loads(path.read_text(encoding="utf-8"))
    rows = [r for r in d.get("checks", []) if isinstance(r, dict)]
    conf = [r for r in rows if r.get("check_id") == "column_confinement"]
    summary = [r for r in rows if r.get("check_id") == "column_design_full"]

    print("COLUMN_CONFINEMENT_POLICY_INSPECT_V1_1")
    print("path:", path)
    print("metadata:", d.get("report_metadata"))
    print("policy_summary:", d.get("confinement_policy_summary"))

    print("\ncolumn_confinement by_status:")
    for k, v in c(conf, "status").items():
        print(f"  {k}: {v}")

    print("\ncolumn_confinement by_reason_code:")
    for k, v in c(conf, "reason_code").items():
        print(f"  {k}: {v}")

    print("\ncolumn_confinement by_source:")
    for k, v in c(conf, "source").items():
        print(f"  {k}: {v}")

    print("\ncolumn_confinement by_policy:")
    for k, v in c(conf, "confinement_policy").items():
        print(f"  {k}: {v}")

    print("\ncolumn_design_full by_status:")
    for k, v in c(summary, "status").items():
        print(f"  {k}: {v}")

    print("\nfirst_10_confinement_rows:")
    for r in conf[:10]:
        print(
            f"  {r.get('status')} | {r.get('element_label')} | level={r.get('evaluation_level')} | "
            f"source={r.get('source')} | reason={r.get('reason_code')} | "
            f"Ash={r.get('Ash_provided')}/{r.get('Ash_required')} | "
            f"spacing={r.get('spacing_mm')} | legs={r.get('legs_x')}/{r.get('legs_y')} | "
            f"msg={str(r.get('message') or '')[:140]}"
        )
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
