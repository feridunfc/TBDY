from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

REPORTS_OUT = PROJECT_ROOT / "reports_out"
AUDIT_DIR = REPORTS_OUT / "input_audit"
DEFAULT_REPORT = REPORTS_OUT / "final_engine_report_combo_resolved.json"

def read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))

def rows(report: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [r for r in report.get("checks", []) if isinstance(r, dict)]

def combo_alias_audit(report: Dict[str, Any]) -> Dict[str, Any]:
    summary = report.get("combo_alias_summary") or {}
    rs = rows(report)

    unique: Dict[str, Dict[str, Any]] = {}
    for r in rs:
        raw = str(r.get("raw_combo") or r.get("governing_combo") or "")
        if not raw:
            continue
        if raw not in unique:
            unique[raw] = {
                "raw_combo": raw,
                "required_families_seen": set(),
                "resolved_family": str(r.get("combo_resolved_family") or r.get("combo_family") or ""),
                "resolved_by": str(r.get("combo_resolved_by_v1") or r.get("combo_resolved_by") or ""),
                "confidence": r.get("combo_resolution_confidence", ""),
                "is_fallback_marker": raw.startswith("UNEXPOSED_ETABS_COMBO::"),
                "row_count": 0,
                "matches_required_family": True,
            }
        item = unique[raw]
        item["row_count"] += 1
        req = str(r.get("combo_required_family") or r.get("combo_family") or "")
        if req:
            item["required_families_seen"].add(req)
        if r.get("combo_matches_required_family") is False:
            item["matches_required_family"] = False

    unique_items = []
    for item in unique.values():
        item["required_families_seen"] = sorted(item["required_families_seen"])
        unique_items.append(item)

    return {
        "combo_audit_source": "combo_alias_summary_v1" if summary else "report_fields_v1_1",
        "rows_resolved": int(summary.get("rows_resolved") or sum(1 for r in rs if r.get("combo_resolved_family"))),
        "rows_fallback_marker": int(summary.get("rows_fallback_marker") or sum(1 for r in rs if str(r.get("raw_combo") or "").startswith("UNEXPOSED_ETABS_COMBO::"))),
        "rows_mismatch": int(summary.get("rows_mismatch") or sum(1 for r in rs if r.get("combo_matches_required_family") is False)),
        "resolved_by": summary.get("resolved_by") or dict(Counter(str(r.get("combo_resolved_by_v1") or "<empty>") for r in rs)),
        "resolved_family": summary.get("resolved_family") or dict(Counter(str(r.get("combo_resolved_family") or "<empty>") for r in rs)),
        "unique_raw_combo_count": len(unique_items),
        "mapped_unique": sum(1 for x in unique_items if x.get("resolved_family")),
        "unmapped_unique": sum(1 for x in unique_items if not x.get("resolved_family")),
        "fallback_unique": sum(1 for x in unique_items if x.get("is_fallback_marker")),
        "actual_unique": sum(1 for x in unique_items if x.get("resolved_by") not in {"required_family_fallback", ""}),
        "unique_items": unique_items,
        "mismatches": summary.get("mismatches") or [],
    }

def unit_audit(report: Dict[str, Any]) -> Dict[str, Any]:
    rs = rows(report)
    return {
        "raw_units_seen": sorted(set(str(r.get("raw_unit")) for r in rs if r.get("raw_unit"))),
        "canonical_units_seen": sorted(set(str(r.get("canonical_unit")) for r in rs if r.get("canonical_unit"))),
        "display_units_seen": sorted(set(str(r.get("display_unit") or r.get("unit")) for r in rs if r.get("display_unit") or r.get("unit"))),
        "suspicious_unit_values": [],
    }

def model_audit(report: Dict[str, Any]) -> Dict[str, Any]:
    rs = rows(report)
    by_check = Counter(str(r.get("check_id") or "<empty>") for r in rs)
    by_source = Counter(str(r.get("source") or "<empty>") for r in rs)
    return {
        "total_check_rows": len(rs),
        "has_scwb_projection_rows": by_source.get("scwb_resolver", 0) > 0,
        "has_column_confinement_policy": any(r.get("confinement_policy") for r in rs),
        "check_coverage": dict(by_check),
        "by_source": dict(by_source),
        "by_status": dict(Counter(str(r.get("status") or "<empty>") for r in rs)),
        "by_evaluation_level": dict(Counter(str(r.get("evaluation_level") or "<empty>") for r in rs)),
    }

def design_source_audit(report: Dict[str, Any]) -> Dict[str, Any]:
    rs = rows(report)
    return {
        "has_column_design_rows": any(str(r.get("check_id") or "").startswith("column_") for r in rs),
        "has_beam_design_rows": any(str(r.get("check_id") or "").startswith("beam_") for r in rs),
        "governing_combo_count": sum(1 for r in rs if r.get("governing_combo")),
        "design_summary_like_sources": dict(Counter(str(r.get("source") or "") for r in rs if "etabs" in str(r.get("source") or "").lower() or "design" in str(r.get("source") or "").lower())),
    }

def write_csv(path: Path, items: List[Dict[str, Any]]) -> None:
    fields = ["raw_combo", "required_families_seen", "resolved_family", "resolved_by", "confidence", "is_fallback_marker", "row_count", "matches_required_family"]
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for item in items:
            row = dict(item)
            row["required_families_seen"] = ",".join(row.get("required_families_seen") or [])
            w.writerow(row)

def write_summary(path: Path, audit: Dict[str, Any]) -> None:
    combo = audit["combo_contract_audit"]
    unit = audit["unit_audit"]
    model = audit["model_input_audit"]
    design = audit["design_source_audit"]
    lines = [
        "GENESIS INPUT AUDIT V1.1 - COMBO RESOLVER INTEGRATION",
        "=" * 68,
        "",
        f"total_check_rows: {model['total_check_rows']}",
        f"has_scwb_projection_rows: {model['has_scwb_projection_rows']}",
        f"has_column_confinement_policy: {model['has_column_confinement_policy']}",
        "",
        "combo_contract:",
        f"  combo_audit_source: {combo['combo_audit_source']}",
        f"  unique_raw_combo_count: {combo['unique_raw_combo_count']}",
        f"  mapped_unique: {combo['mapped_unique']}",
        f"  unmapped_unique: {combo['unmapped_unique']}",
        f"  fallback_unique: {combo['fallback_unique']}",
        f"  actual_unique: {combo['actual_unique']}",
        f"  rows_resolved: {combo['rows_resolved']}",
        f"  rows_fallback_marker: {combo['rows_fallback_marker']}",
        f"  rows_mismatch: {combo['rows_mismatch']}",
        "",
        "unit_audit:",
        f"  raw_units_seen: {unit['raw_units_seen']}",
        f"  canonical_units_seen: {unit['canonical_units_seen']}",
        f"  display_units_seen: {unit['display_units_seen']}",
        f"  suspicious_unit_values: {len(unit['suspicious_unit_values'])}",
        "",
        "design_source_audit:",
        f"  has_column_design_rows: {design['has_column_design_rows']}",
        f"  has_beam_design_rows: {design['has_beam_design_rows']}",
        f"  governing_combo_count: {design['governing_combo_count']}",
        "",
        "recommended_next:",
        "  1. Actual ETABS Governing Combo Extraction v1.",
        "  2. Replace required-family fallback markers with real ETABS combo names.",
        "  3. Then start Combo-aware Force/Design Selector v1.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

def build_audit(report: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "metadata": {
            "tool": "Genesis Input Audit v1.1 Combo Resolver Integration",
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "project_root": str(PROJECT_ROOT),
        },
        "model_input_audit": model_audit(report),
        "combo_contract_audit": combo_alias_audit(report),
        "unit_audit": unit_audit(report),
        "design_source_audit": design_source_audit(report),
    }

def main(argv: List[str] | None = None) -> int:
    argv = argv or sys.argv[1:]
    report_path = Path(argv[0]) if argv else DEFAULT_REPORT
    report_path = report_path if report_path.is_absolute() else PROJECT_ROOT / report_path
    if not report_path.exists():
        print(f"ERROR: report not found: {report_path}")
        return 2

    report = read_json(report_path)
    audit = build_audit(report)

    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    out_full = AUDIT_DIR / "input_audit_v1_1_full.json"
    out_full.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    # Also overwrite canonical input_audit_full.json so existing inspector workflows see v1.1.
    (AUDIT_DIR / "input_audit_full.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(AUDIT_DIR / "combo_alias_unique_raw_combos_v1_1.csv", audit["combo_contract_audit"]["unique_items"])
    write_summary(AUDIT_DIR / "input_audit_v1_1_summary.txt", audit)
    write_summary(AUDIT_DIR / "input_audit_summary.txt", audit)

    combo = audit["combo_contract_audit"]
    unit = audit["unit_audit"]
    design = audit["design_source_audit"]

    print("GENESIS_INPUT_AUDIT_V1_1")
    print("input_report:", report_path)
    print("output:", out_full)
    print("combo_audit_source:", combo["combo_audit_source"])
    print("unique_raw_combo_count:", combo["unique_raw_combo_count"])
    print("mapped_unique:", combo["mapped_unique"])
    print("unmapped_unique:", combo["unmapped_unique"])
    print("fallback_unique:", combo["fallback_unique"])
    print("actual_unique:", combo["actual_unique"])
    print("rows_resolved:", combo["rows_resolved"])
    print("rows_fallback_marker:", combo["rows_fallback_marker"])
    print("rows_mismatch:", combo["rows_mismatch"])
    print("raw_units_seen:", unit["raw_units_seen"])
    print("canonical_units_seen:", unit["canonical_units_seen"])
    print("display_units_seen:", unit["display_units_seen"])
    print("governing_combo_count:", design["governing_combo_count"])
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
