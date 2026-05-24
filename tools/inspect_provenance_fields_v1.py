from __future__ import annotations
import json, sys
from collections import Counter
from pathlib import Path
from typing import List
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT = PROJECT_ROOT / "reports_out" / "final_engine_report_provenance.json"
def c(rows, key): return Counter(str(r.get(key) or "<empty>") for r in rows if isinstance(r, dict))
def pc(title, counter, limit=20):
    print(f"\n{title}:")
    for k, v in counter.most_common(limit): print(f"  {k}: {v}")
def main(argv: List[str] | None = None) -> int:
    argv = argv or sys.argv[1:]
    path = Path(argv[0]) if argv else DEFAULT_REPORT
    path = path if path.is_absolute() else PROJECT_ROOT / path
    if not path.exists():
        print(f"ERROR: provenance report not found: {path}"); return 2
    d = json.loads(path.read_text(encoding="utf-8"))
    rows = [r for r in d.get("checks", []) if isinstance(r, dict)]
    print("PROVENANCE_FIELDS_INSPECT_V1")
    print("path:", path)
    print("metadata:", d.get("report_metadata"))
    print("provenance_summary:", d.get("provenance_summary"))
    for key in ["source_table", "source_field", "combo_family", "combo_provenance_level", "raw_unit", "canonical_unit", "display_unit"]:
        pc(f"by_{key}", c(rows, key))
    print("\nfirst_10_rows:")
    for r in rows[:10]:
        print(f"  {r.get('check_id')} | {r.get('element_label')} | status={r.get('status')} | source_table={r.get('source_table')} | combo={r.get('governing_combo')} | family={r.get('combo_family')} | unit={r.get('raw_unit')}->{r.get('canonical_unit')}->{r.get('display_unit')} | flags=F{int(bool(r.get('source_is_final')))} A{int(bool(r.get('source_is_approximate')))} P{int(bool(r.get('source_is_proposal')))}")
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
