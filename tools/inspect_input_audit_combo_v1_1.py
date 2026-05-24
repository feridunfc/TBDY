from __future__ import annotations

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
AUDIT = PROJECT_ROOT / "reports_out" / "input_audit" / "input_audit_v1_1_full.json"
FALLBACK = PROJECT_ROOT / "reports_out" / "input_audit" / "input_audit_full.json"

def main() -> int:
    path = AUDIT if AUDIT.exists() else FALLBACK
    if not path.exists():
        print(f"ERROR: audit not found: {path}")
        return 2

    d = json.loads(path.read_text(encoding="utf-8"))
    combo = d.get("combo_contract_audit") or {}

    print("INPUT_AUDIT_COMBO_INTEGRATION_INSPECT_V1_1")
    print("path:", path)
    print("metadata:", d.get("metadata"))
    print("combo_audit_source:", combo.get("combo_audit_source"))
    print("unique_raw_combo_count:", combo.get("unique_raw_combo_count"))
    print("mapped_unique:", combo.get("mapped_unique"))
    print("unmapped_unique:", combo.get("unmapped_unique"))
    print("fallback_unique:", combo.get("fallback_unique"))
    print("actual_unique:", combo.get("actual_unique"))
    print("rows_resolved:", combo.get("rows_resolved"))
    print("rows_fallback_marker:", combo.get("rows_fallback_marker"))
    print("rows_mismatch:", combo.get("rows_mismatch"))
    print("resolved_by:", combo.get("resolved_by"))
    print("resolved_family:", combo.get("resolved_family"))

    print("\nunique_items:")
    for item in combo.get("unique_items", [])[:50]:
        print(
            f"  {item.get('raw_combo')} | family={item.get('resolved_family')} | "
            f"by={item.get('resolved_by')} | fallback={item.get('is_fallback_marker')} | "
            f"rows={item.get('row_count')} | matches={item.get('matches_required_family')}"
        )
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
