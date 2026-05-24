from __future__ import annotations

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
AUDIT_DIR = PROJECT_ROOT / "reports_out" / "actual_combo_audit"
AUDIT = AUDIT_DIR / "actual_combo_audit.json"
REPORT = AUDIT_DIR / "final_engine_report_actual_combo.json"

def main() -> int:
    if not AUDIT.exists():
        print(f"ERROR: audit not found: {AUDIT}")
        print("Run first: python tools\\extract_actual_governing_combos_v1.py")
        return 2

    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    print("ACTUAL_ETABS_GOVERNING_COMBO_INSPECT_V1")
    print("audit:", AUDIT)
    print("report:", REPORT)
    print("metadata:", audit.get("metadata"))
    print("summary:", audit.get("summary"))
    print("policy:", audit.get("policy"))
    print("diagnostic:", audit.get("diagnostic"))
    print("family_counts:", audit.get("family_counts"))

    print("\nunique_candidates:")
    for item in audit.get("unique_candidates", [])[:30]:
        print(
            f"  {item.get('candidate')} | count={item.get('count')} | family={item.get('family')} | "
            f"by={item.get('resolved_by')} | field={item.get('field')} | source={item.get('source')}"
        )

    print("\nrow_matches:")
    for item in audit.get("row_matches", [])[:20]:
        print(" ", item)

    print("\nunmatched_rows_first_20:")
    for item in audit.get("unmatched_rows", [])[:20]:
        print(" ", item)

    return 0

if __name__ == "__main__":
    raise SystemExit(main())
