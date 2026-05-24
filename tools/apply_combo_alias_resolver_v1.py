from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.combo_alias_resolver_v1 import REPORTS_OUT, resolve_report, unique_raw_combo_audit, write_csv

DEFAULT_IN = REPORTS_OUT / "final_engine_report_provenance.json"
DEFAULT_OUT = REPORTS_OUT / "final_engine_report_combo_resolved.json"
AUDIT_DIR = REPORTS_OUT / "combo_alias_audit"

def main(argv=None) -> int:
    argv = argv or sys.argv[1:]
    in_path = Path(argv[0]) if argv else DEFAULT_IN
    in_path = in_path if in_path.is_absolute() else PROJECT_ROOT / in_path
    if not in_path.exists():
        print(f"ERROR: provenance report not found: {in_path}")
        print("Run first: python tools\\apply_provenance_fields_v1.py")
        return 2

    report = json.loads(in_path.read_text(encoding="utf-8"))
    out = resolve_report(report)
    audit = unique_raw_combo_audit(out)

    DEFAULT_OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    (AUDIT_DIR / "combo_alias_audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(
        AUDIT_DIR / "combo_alias_unique_raw_combos.csv",
        audit["items"],
        ["raw_combo", "required_families_seen", "resolved_family", "resolved_by", "confidence", "is_fallback_marker", "row_count"],
    )

    hist = REPORTS_OUT / "history"
    hist.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    hist_path = hist / f"{stamp}_final_engine_report_combo_resolved.json"
    hist_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    print("COMBO_ALIAS_RESOLVER_V1")
    print("input:", in_path)
    print("output:", DEFAULT_OUT)
    print("snapshot:", hist_path)
    print("unique_raw_combo_count:", audit["unique_raw_combo_count"])
    print("mapped_unique:", audit["mapped_unique"])
    print("unmapped_unique:", audit["unmapped_unique"])
    print("rows_resolved:", out["combo_alias_summary"]["rows_resolved"])
    print("rows_fallback_marker:", out["combo_alias_summary"]["rows_fallback_marker"])
    print("rows_mismatch:", out["combo_alias_summary"]["rows_mismatch"])
    print("resolved_by:")
    for k, v in out["combo_alias_summary"]["resolved_by"].items():
        print(f"  {k}: {v}")
    print("resolved_family:")
    for k, v in out["combo_alias_summary"]["resolved_family"].items():
        print(f"  {k}: {v}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
