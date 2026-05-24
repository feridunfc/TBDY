from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORTS_OUT = PROJECT_ROOT / "reports_out"
DEFAULT_REPORT = REPORTS_OUT / "final_engine_report_combo_resolved.json"
DEFAULT_AUDIT = REPORTS_OUT / "combo_alias_audit" / "combo_alias_audit.json"

def main(argv=None) -> int:
    argv = argv or sys.argv[1:]
    report_path = Path(argv[0]) if argv else DEFAULT_REPORT
    report_path = report_path if report_path.is_absolute() else PROJECT_ROOT / report_path
    if not report_path.exists():
        print(f"ERROR: report not found: {report_path}")
        return 2

    report = json.loads(report_path.read_text(encoding="utf-8"))
    audit = json.loads(DEFAULT_AUDIT.read_text(encoding="utf-8")) if DEFAULT_AUDIT.exists() else {}

    print("COMBO_ALIAS_RESOLVER_INSPECT_V1")
    print("report:", report_path)
    print("metadata:", report.get("report_metadata"))
    print("combo_alias_summary:", report.get("combo_alias_summary"))
    print("unique_raw_combo_audit:", {k: v for k, v in audit.items() if k != "items"})

    print("\nunique_raw_combos:")
    for item in audit.get("items", [])[:50]:
        print(
            f"  {item.get('raw_combo')} | required={item.get('required_families_seen')} | "
            f"family={item.get('resolved_family')} | by={item.get('resolved_by')} | "
            f"conf={item.get('confidence')} | fallback={item.get('is_fallback_marker')} | rows={item.get('row_count')}"
        )

    mismatches = (report.get("combo_alias_summary") or {}).get("mismatches") or []
    if mismatches:
        print("\nfirst_mismatches:")
        for item in mismatches[:20]:
            print(" ", item)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
