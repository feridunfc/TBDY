
from __future__ import annotations
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
AUDIT = PROJECT_ROOT / "reports_out" / "etabs_combo_column_discovery" / "combo_column_discovery.json"

def main() -> int:
    if not AUDIT.exists():
        print(f"ERROR: discovery audit not found: {AUDIT}")
        print("Run first: python tools\\discover_etabs_combo_columns_v1.py")
        return 2
    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    print("ETABS_COMBO_COLUMN_DISCOVERY_INSPECT_V1")
    print("audit:", AUDIT)
    print("metadata:", audit.get("metadata"))
    print("summary:", audit.get("summary"))
    print("diagnostic:", audit.get("diagnostic"))
    print("policy:", audit.get("policy"))
    print("\nfirst_candidate_tables:")
    for item in audit.get("table_hits", [])[:30]:
        print(" ", item)
    print("\nfirst_candidate_columns:")
    for item in audit.get("column_hits", [])[:30]:
        print(" ", item)
    print("\nfirst_candidate_values:")
    for item in audit.get("value_hits", [])[:30]:
        print(" ", item)
    print("\nunique_values_first_50:")
    for val in audit.get("unique_values", [])[:50]:
        print(" ", val)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
