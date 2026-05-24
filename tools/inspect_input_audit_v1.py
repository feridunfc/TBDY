from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import List

PROJECT_ROOT = Path(__file__).resolve().parents[1]
AUDIT_DIR = PROJECT_ROOT / "reports_out" / "input_audit"
DEFAULT_AUDIT = AUDIT_DIR / "input_audit_full.json"

def main(argv: List[str] | None = None) -> int:
    argv = argv or sys.argv[1:]
    path = Path(argv[0]) if argv else DEFAULT_AUDIT
    path = path if path.is_absolute() else PROJECT_ROOT / path
    if not path.exists():
        print(f"ERROR: audit file not found: {path}")
        print("Run first: python tools\\run_input_audit_v1.py")
        return 2

    audit = json.loads(path.read_text(encoding="utf-8"))
    mi = audit["model_input_audit"]
    combo = audit["combo_contract_audit"]
    unit = audit["unit_audit"]
    ds = audit["design_source_audit"]

    print("INPUT_AUDIT_INSPECT_V1")
    print("path:", path)
    print("metadata:", audit.get("metadata"))

    print("\nmodel_input:")
    print("  total_check_rows:", mi["total_check_rows"])
    print("  has_scwb_projection_rows:", mi["has_scwb_projection_rows"])
    print("  has_column_confinement_policy:", mi["has_column_confinement_policy"])
    print("  check_coverage:")
    for k, v in mi["check_coverage"].items():
        print(f"    {k}: {v}")

    print("\ncombo_contract:")
    print("  contract_families:", combo["contract_families"])
    print("  raw_combo_values_found:", len(combo["raw_combo_values_found_in_report"]))
    print("  mapped_combos:", len(combo["mapped_combos"]))
    print("  unmapped_combos:", len(combo["unmapped_combos"]))
    print("  missing_required_families:", len(combo["missing_required_families"]))
    if not combo["raw_combo_values_found_in_report"]:
        print("  WARNING: raw combo/governing_combo provenance not present yet.")

    print("\nunit_audit:")
    print("  unit_policy:", unit["unit_policy"])
    print("  raw_units_seen:", unit["raw_units_seen"])
    print("  canonical_units_seen:", unit["canonical_units_seen"])
    print("  display_units_seen:", unit["display_units_seen"])
    print("  suspicious_unit_values:", len(unit["suspicious_unit_values"]))

    print("\ndesign_source:")
    print("  has_column_design_rows:", ds["has_column_design_rows"])
    print("  has_beam_design_rows:", ds["has_beam_design_rows"])
    print("  design_summary_like_sources:", ds["design_summary_like_sources"])
    print("  governing_combo_count:", ds["governing_combo_count"])
    if ds["governing_combo_count"] == 0:
        print("  WARNING: design summary governing combos are not exposed in final report rows.")

    summary_path = AUDIT_DIR / "input_audit_summary.txt"
    if summary_path.exists():
        print("\nsummary_text:")
        print(summary_path.read_text(encoding="utf-8"))

    return 0

if __name__ == "__main__":
    raise SystemExit(main())
