from __future__ import annotations

import csv
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

try:
    import yaml
except Exception:
    yaml = None

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORTS_OUT = PROJECT_ROOT / "reports_out"
AUDIT_DIR = REPORTS_OUT / "input_audit"
CONTRACTS_DIR = PROJECT_ROOT / "tbdy_engine" / "contracts"

DEFAULT_FINAL_REPORT = REPORTS_OUT / "final_engine_report.json"
DEFAULT_ENGINE_REPORT = REPORTS_OUT / "engine_report.json"

DEFAULT_COMBO_USAGE = {
    "column_pmm": ["S_E", "G"],
    "column_axial": ["S_E", "G"],
    "column_shear": ["K_E", "S_E"],
    "column_capacity_hierarchy": ["S_E"],
    "column_confinement": ["S_E"],
    "beam_flexure": ["S_E", "G"],
    "beam_shear": ["K_E", "S_E"],
    "beam_capacity_hierarchy": ["S_E"],
    "beam_ductility": ["S_E"],
    "drift": ["DRIFT"],
    "modal": ["DRIFT"],
}

DEFAULT_FAMILIES = {
    "G": {
        "aliases": ["G", "DEAD", "D", "GRAVITY", "1.4G", "1.4D", "G+Q", "D+L"],
        "patterns": [r"\bG\b", r"\bD\b", r"DEAD", r"GRAVITY", r"1\.4\s*G", r"1\.4\s*D"],
        "purpose": "gravity",
    },
    "S_E": {
        "aliases": ["S_E", "SE", "EQ", "E", "EX", "EY", "DEPREM", "EARTHQUAKE", "RS", "SPEC"],
        "patterns": [r"\bE[XY]?\b", r"EQ", r"DEPREM", r"EARTH", r"RS", r"SPEC", r"X\s*[-+]?", r"Y\s*[-+]?"],
        "purpose": "seismic_strength",
    },
    "K_E": {
        "aliases": ["K_E", "KE", "CAPACITY", "KAPASITE", "SHEAR", "KESME"],
        "patterns": [r"K[_\-\s]?E", r"CAPACITY", r"KAPASITE", r"SHEAR", r"KESME"],
        "purpose": "capacity_design_shear",
    },
    "DRIFT": {
        "aliases": ["DRIFT", "DISP", "DEPLASMAN", "STORY DRIFT", "STOREY DRIFT"],
        "patterns": [r"DRIFT", r"DISP", r"DEPLAS", r"STORY\s*DRIFT", r"STOREY\s*DRIFT"],
        "purpose": "displacement_drift",
    },
    "SOIL": {
        "aliases": ["SOIL", "FOUNDATION", "UPLIFT", "BEARING", "ZEMIN"],
        "patterns": [r"SOIL", r"FOUND", r"UPLIFT", r"BEARING", r"ZEMIN"],
        "purpose": "foundation_soil",
    },
}

UNIT_POLICY = {
    "raw_etabs_units": "preserve_as_evidence_when_available",
    "engine_canonical": {
        "force": "kN",
        "moment": "kNm",
        "section_length": "mm",
        "member_length": "m",
        "stress": "MPa",
        "rebar_area": "mm2",
    },
    "report_units": {
        "force": "kN",
        "moment": "kNm",
        "length": "mm/m_by_context",
        "stress": "MPa",
        "area": "mm2",
    },
    "policy": "ETABS raw units should be captured as provenance; calculations should use canonical engine units; report layer may convert display units only.",
}

def read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))

def read_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists() or yaml is None:
        return {}
    with path.open("r", encoding="utf-8-sig") as f:
        return yaml.safe_load(f) or {}

def normalize_name(name: str) -> str:
    s = str(name or "").upper()
    s = s.replace("İ", "I")
    s = re.sub(r"[\s_]+", "", s)
    s = s.replace("LOADCOMBO", "").replace("COMBO", "")
    return s

def load_combo_contract() -> Dict[str, Any]:
    combos_doc = read_yaml(CONTRACTS_DIR / "combos.yaml")
    checks_doc = read_yaml(CONTRACTS_DIR / "checks.yaml")

    families = {}
    raw_families = combos_doc.get("combo_families") or combos_doc.get("families") or {}
    if isinstance(raw_families, list):
        for item in raw_families:
            if isinstance(item, dict):
                fid = item.get("id") or item.get("name")
                if fid:
                    families[str(fid)] = item
    elif isinstance(raw_families, dict):
        families = dict(raw_families)

    # Fill defaults without overriding existing.
    for fid, spec in DEFAULT_FAMILIES.items():
        families.setdefault(fid, spec)

    usage = {}
    raw_usage = combos_doc.get("combo_usage") or combos_doc.get("usage") or {}
    if isinstance(raw_usage, dict):
        for k, v in raw_usage.items():
            if isinstance(v, dict):
                vals = v.get("uses") or v.get("families") or []
            elif isinstance(v, list):
                vals = v
            else:
                vals = []
            usage[str(k)] = [str(x) for x in vals]

    checks = checks_doc.get("checks", [])
    if isinstance(checks, dict):
        iterable = checks.values()
    else:
        iterable = checks if isinstance(checks, list) else []

    for chk in iterable:
        if not isinstance(chk, dict):
            continue
        cid = chk.get("id")
        uses = chk.get("uses_combo") or chk.get("combo_families") or []
        if cid and uses:
            usage[str(cid)] = [str(x) for x in uses]

    for k, v in DEFAULT_COMBO_USAGE.items():
        usage.setdefault(k, v)

    return {
        "families": families,
        "usage": usage,
        "source_files": {
            "combos_yaml": str(CONTRACTS_DIR / "combos.yaml"),
            "checks_yaml": str(CONTRACTS_DIR / "checks.yaml"),
        },
    }

def family_match(raw_name: str, families: Dict[str, Any]) -> Tuple[str, str]:
    if not raw_name:
        return "", "empty"
    norm = normalize_name(raw_name)

    for fid, spec in families.items():
        if normalize_name(fid) == norm:
            return fid, "family_id_exact"

        aliases = []
        if isinstance(spec, dict):
            aliases = spec.get("aliases") or spec.get("etabs_names") or []
        if isinstance(aliases, str):
            aliases = [aliases]
        for alias in aliases:
            if normalize_name(alias) == norm:
                return fid, "alias_exact"

    # Pattern matching before loose alias_contains prevents generic aliases
    # such as "G" from stealing seismic combos like "G+0.3Q+Ex".
    for fid, spec in families.items():
        if not isinstance(spec, dict):
            continue
        for pat in spec.get("patterns") or []:
            try:
                if re.search(str(pat), str(raw_name), re.I):
                    return fid, "pattern"
            except re.error:
                pass

    for fid, spec in families.items():
        if not isinstance(spec, dict):
            continue
        aliases = spec.get("aliases") or []
        for alias in aliases:
            alias_norm = normalize_name(alias)
            if alias_norm and len(alias_norm) > 1 and alias_norm in norm:
                return fid, "alias_contains"

    return "", "unmapped"

def find_combo_like_values(rows: List[Dict[str, Any]]) -> List[str]:
    values = []
    combo_keys = [
        "combo", "load_combo", "load_combination", "combination", "case", "case_combo",
        "governing_combo", "design_combo", "output_case", "loadcase", "load_case",
    ]
    for row in rows:
        for k, v in row.items():
            kl = str(k).lower()
            if any(token in kl for token in combo_keys):
                if isinstance(v, str) and v.strip():
                    values.append(v.strip())
    return sorted(set(values))

def collect_from_report(report: Dict[str, Any]) -> Dict[str, Any]:
    rows = [r for r in report.get("checks", []) if isinstance(r, dict)]
    metadata = report.get("report_metadata") or {}

    by_check = Counter(str(r.get("check_id") or "<empty>") for r in rows)
    by_source = Counter(str(r.get("source") or "<empty>") for r in rows)
    by_level = Counter(str(r.get("evaluation_level") or "<empty>") for r in rows)
    by_status = Counter(str(r.get("status") or "<empty>") for r in rows)
    by_reason = Counter(str(r.get("reason_code") or "<empty>") for r in rows)

    combo_values = find_combo_like_values(rows)

    source_tables = sorted(set(str(r.get("source_table")) for r in rows if r.get("source_table")))
    raw_units = sorted(set(str(r.get("raw_unit") or r.get("unit_input")) for r in rows if r.get("raw_unit") or r.get("unit_input")))
    canonical_units = sorted(set(str(r.get("canonical_unit") or r.get("unit_canonical")) for r in rows if r.get("canonical_unit") or r.get("unit_canonical")))
    display_units = sorted(set(str(r.get("display_unit") or r.get("unit") or r.get("unit_report")) for r in rows if r.get("display_unit") or r.get("unit") or r.get("unit_report")))

    return {
        "metadata": metadata,
        "total_rows": len(rows),
        "by_check_id": dict(by_check),
        "by_source": dict(by_source),
        "by_evaluation_level": dict(by_level),
        "by_status": dict(by_status),
        "by_reason_code": dict(by_reason),
        "combo_like_values": combo_values,
        "source_tables": source_tables,
        "raw_units_seen": raw_units,
        "canonical_units_seen": canonical_units,
        "display_units_seen": display_units,
        "has_scwb": by_source.get("scwb_resolver", 0) > 0,
        "has_column_confinement_policy": any(r.get("confinement_policy") for r in rows),
    }

def audit_combo_contract(report: Dict[str, Any], contract: Dict[str, Any]) -> Dict[str, Any]:
    families = contract["families"]
    usage = contract["usage"]
    report_info = collect_from_report(report)

    rows = [r for r in report.get("checks", []) if isinstance(r, dict)]
    combo_values = list(report_info["combo_like_values"])

    # Also infer pseudo-combo families from check metadata, because current reports may not expose raw combos yet.
    check_family_requirements = {}
    for cid, count in report_info["by_check_id"].items():
        if cid in usage:
            check_family_requirements[cid] = {
                "required_families": usage[cid],
                "row_count": count,
            }

    mapped = []
    unmapped = []
    for name in combo_values:
        family, method = family_match(name, families)
        item = {"raw_combo": name, "resolved_family": family, "resolved_by": method}
        if family:
            mapped.append(item)
        else:
            unmapped.append(item)

    available_families = sorted(set(x["resolved_family"] for x in mapped if x["resolved_family"]))

    # If raw combos are absent, use evidence from check execution as "not directly auditable yet".
    missing_required = []
    for cid, spec in check_family_requirements.items():
        for fam in spec["required_families"]:
            if combo_values and fam not in available_families:
                missing_required.append({
                    "check_id": cid,
                    "required_family": fam,
                    "reason": "no_raw_combo_mapped_to_required_family",
                })

    return {
        "contract_families": sorted(families.keys()),
        "combo_usage_by_check": check_family_requirements,
        "raw_combo_values_found_in_report": combo_values,
        "mapped_combos": mapped,
        "unmapped_combos": unmapped,
        "available_families_from_raw_combos": available_families,
        "missing_required_families": missing_required,
        "limitations": [
            "Current final report may not expose raw ETABS combo/governing_combo fields yet.",
            "If raw_combo_values_found_in_report is empty, combo-family enforcement is not yet auditable from final report alone.",
            "Next sprint should add combo/governing_combo/source_table provenance at ModelContext and CheckResult level.",
        ],
    }

def audit_units(report: Dict[str, Any]) -> Dict[str, Any]:
    info = collect_from_report(report)
    rows = [r for r in report.get("checks", []) if isinstance(r, dict)]

    suspicious = []
    for r in rows:
        cid = str(r.get("check_id") or "")
        val = r.get("value")
        lim = r.get("limit")
        ratio = r.get("ratio")
        unit = r.get("unit")
        label = r.get("element_label")
        if cid in {"column_confinement"}:
            ash_req = r.get("Ash_required")
            ash_prov = r.get("Ash_provided")
            spacing = r.get("spacing_mm")
            if ash_req is not None and (float(ash_req) < 20 or float(ash_req) > 5000):
                suspicious.append({"check_id": cid, "element_label": label, "field": "Ash_required", "value": ash_req, "reason": "outside_expected_mm2_range"})
            if spacing is not None and (float(spacing) < 25 or float(spacing) > 500):
                suspicious.append({"check_id": cid, "element_label": label, "field": "spacing_mm", "value": spacing, "reason": "outside_expected_spacing_mm_range"})
        if ratio is not None:
            try:
                if abs(float(ratio)) > 1000:
                    suspicious.append({"check_id": cid, "element_label": label, "field": "ratio", "value": ratio, "reason": "very_large_ratio"})
            except Exception:
                pass

    return {
        "unit_policy": UNIT_POLICY,
        "raw_units_seen": info["raw_units_seen"],
        "canonical_units_seen": info["canonical_units_seen"],
        "display_units_seen": info["display_units_seen"],
        "unit_fields_available": {
            "raw_unit_present": bool(info["raw_units_seen"]),
            "canonical_unit_present": bool(info["canonical_units_seen"]),
            "display_unit_present": bool(info["display_units_seen"]),
        },
        "suspicious_unit_values": suspicious[:200],
        "limitations": [
            "ETABS raw unit context is not guaranteed in current report rows.",
            "Audit can validate explicit unit/evidence fields in final report, but full raw→canonical provenance needs context/table-level fields.",
        ],
    }

def audit_design_sources(report: Dict[str, Any]) -> Dict[str, Any]:
    rows = [r for r in report.get("checks", []) if isinstance(r, dict)]
    by_source = Counter(str(r.get("source") or "<empty>") for r in rows)
    by_level = Counter(str(r.get("evaluation_level") or "<empty>") for r in rows)

    design_summary_sources = {k: v for k, v in by_source.items() if "design_summary" in k or "etabs" in k}
    has_column_design = any(r.get("check_id", "").startswith("column_") for r in rows)
    has_beam_design = any(r.get("check_id", "").startswith("beam_") for r in rows)

    governing_combo_rows = []
    for r in rows:
        combo = r.get("governing_combo") or r.get("combo") or r.get("load_combo") or r.get("design_combo")
        if combo:
            governing_combo_rows.append({
                "check_id": r.get("check_id"),
                "element_label": r.get("element_label"),
                "combo": combo,
                "source": r.get("source"),
                "evaluation_level": r.get("evaluation_level"),
            })

    return {
        "has_column_design_rows": has_column_design,
        "has_beam_design_rows": has_beam_design,
        "by_source": dict(by_source),
        "by_evaluation_level": dict(by_level),
        "design_summary_like_sources": design_summary_sources,
        "governing_combo_rows_found": governing_combo_rows[:500],
        "governing_combo_count": len(governing_combo_rows),
        "limitations": [
            "Current final report may not expose ETABS concrete frame selected design combo fields.",
            "Design summary combo audit becomes strict after source_table/governing_combo fields are added to CheckResult details.",
        ],
    }

def audit_model_inputs(report: Dict[str, Any]) -> Dict[str, Any]:
    info = collect_from_report(report)
    expected_checks = [
        "column_geometry", "column_axial", "column_pmm", "column_shear", "column_confinement",
        "column_capacity_hierarchy", "beam_geometry", "beam_flexure", "beam_shear",
        "beam_ductility", "beam_capacity_hierarchy", "scwb",
    ]
    coverage = {}
    for cid in expected_checks:
        if cid == "scwb":
            coverage[cid] = info["by_source"].get("scwb_resolver", 0)
        else:
            coverage[cid] = info["by_check_id"].get(cid, 0)

    return {
        "report_metadata": info["metadata"],
        "total_check_rows": info["total_rows"],
        "check_coverage": coverage,
        "by_status": info["by_status"],
        "by_source": info["by_source"],
        "by_evaluation_level": info["by_evaluation_level"],
        "by_reason_code": info["by_reason_code"],
        "source_tables_present": info["source_tables"],
        "has_scwb_projection_rows": info["has_scwb"],
        "has_column_confinement_policy": info["has_column_confinement_policy"],
        "limitations": [
            "This audit is report/context-output based, not a direct live ETABS table enumerator.",
            "For full ETABS intake audit, context builder should expose raw table inventory and unit context.",
        ],
    }

def write_csv(path: Path, rows: List[Dict[str, Any]], fieldnames: List[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)

def write_summary(path: Path, audit: Dict[str, Any]) -> None:
    lines = []
    lines.append("GENESIS MODEL INTAKE + COMBO + UNIT AUDIT V1")
    lines.append("=" * 64)
    lines.append("")
    mi = audit["model_input_audit"]
    combo = audit["combo_contract_audit"]
    unit = audit["unit_audit"]
    ds = audit["design_source_audit"]

    lines.append(f"total_check_rows: {mi['total_check_rows']}")
    lines.append(f"has_scwb_projection_rows: {mi['has_scwb_projection_rows']}")
    lines.append(f"has_column_confinement_policy: {mi['has_column_confinement_policy']}")
    lines.append("")
    lines.append("check_coverage:")
    for k, v in mi["check_coverage"].items():
        lines.append(f"  {k}: {v}")

    lines.append("")
    lines.append("combo_contract:")
    lines.append(f"  contract_families: {', '.join(combo['contract_families'])}")
    lines.append(f"  raw_combo_values_found: {len(combo['raw_combo_values_found_in_report'])}")
    lines.append(f"  mapped_combos: {len(combo['mapped_combos'])}")
    lines.append(f"  unmapped_combos: {len(combo['unmapped_combos'])}")
    lines.append(f"  missing_required_families: {len(combo['missing_required_families'])}")

    if not combo["raw_combo_values_found_in_report"]:
        lines.append("  WARNING: final report currently exposes no raw combo/governing_combo fields; combo-family mapping cannot be strictly verified yet.")

    lines.append("")
    lines.append("unit_audit:")
    lines.append(f"  raw_units_seen: {unit['raw_units_seen']}")
    lines.append(f"  canonical_units_seen: {unit['canonical_units_seen']}")
    lines.append(f"  display_units_seen: {unit['display_units_seen']}")
    lines.append(f"  suspicious_unit_values: {len(unit['suspicious_unit_values'])}")

    lines.append("")
    lines.append("design_source_audit:")
    lines.append(f"  has_column_design_rows: {ds['has_column_design_rows']}")
    lines.append(f"  has_beam_design_rows: {ds['has_beam_design_rows']}")
    lines.append(f"  governing_combo_count: {ds['governing_combo_count']}")
    if ds["governing_combo_count"] == 0:
        lines.append("  WARNING: no governing_combo/design_combo fields found in final report rows.")

    lines.append("")
    lines.append("recommended_next:")
    lines.append("  1. Add raw_combo/governing_combo/source_table/unit_context provenance to CheckResult rows.")
    lines.append("  2. Add strict combo alias resolver using combos.yaml families/aliases/patterns.")
    lines.append("  3. Add combo-aware force/design selector after audit fields are present.")
    lines.append("  4. Move to report format only after provenance fields are populated.")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

def build_audit(report: Dict[str, Any]) -> Dict[str, Any]:
    contract = load_combo_contract()
    return {
        "metadata": {
            "tool": "Genesis Model Intake + Combo + Unit Audit v1",
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "project_root": str(PROJECT_ROOT),
        },
        "model_input_audit": audit_model_inputs(report),
        "combo_contract_audit": audit_combo_contract(report, contract),
        "unit_audit": audit_units(report),
        "design_source_audit": audit_design_sources(report),
    }

def main(argv: List[str] | None = None) -> int:
    argv = argv or sys.argv[1:]
    report_path = Path(argv[0]) if argv else DEFAULT_FINAL_REPORT
    report_path = report_path if report_path.is_absolute() else PROJECT_ROOT / report_path

    if not report_path.exists():
        fallback = DEFAULT_ENGINE_REPORT
        if fallback.exists():
            report_path = fallback
        else:
            print(f"ERROR: report not found: {report_path}")
            print("Run first: python tools\\run_engine_v2_smoke.py and python tools\\run_final_engine_report_v1.py")
            return 2

    report = read_json(report_path)
    audit = build_audit(report)

    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    (AUDIT_DIR / "model_input_audit.json").write_text(json.dumps(audit["model_input_audit"], ensure_ascii=False, indent=2), encoding="utf-8")
    (AUDIT_DIR / "combo_contract_audit.json").write_text(json.dumps(audit["combo_contract_audit"], ensure_ascii=False, indent=2), encoding="utf-8")
    (AUDIT_DIR / "unit_audit.json").write_text(json.dumps(audit["unit_audit"], ensure_ascii=False, indent=2), encoding="utf-8")
    (AUDIT_DIR / "design_source_audit.json").write_text(json.dumps(audit["design_source_audit"], ensure_ascii=False, indent=2), encoding="utf-8")
    (AUDIT_DIR / "input_audit_full.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")

    combo = audit["combo_contract_audit"]
    write_csv(
        AUDIT_DIR / "unmapped_combos.csv",
        combo["unmapped_combos"],
        ["raw_combo", "resolved_family", "resolved_by"],
    )

    usage_rows = []
    for cid, spec in combo["combo_usage_by_check"].items():
        for fam in spec["required_families"]:
            usage_rows.append({
                "check_id": cid,
                "required_family": fam,
                "row_count": spec["row_count"],
                "raw_combo_values_available": len(combo["raw_combo_values_found_in_report"]),
                "strictly_auditable": bool(combo["raw_combo_values_found_in_report"]),
            })
    write_csv(
        AUDIT_DIR / "check_combo_usage_matrix.csv",
        usage_rows,
        ["check_id", "required_family", "row_count", "raw_combo_values_available", "strictly_auditable"],
    )

    write_summary(AUDIT_DIR / "input_audit_summary.txt", audit)

    hist_dir = AUDIT_DIR / "history"
    hist_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    (hist_dir / f"{stamp}_input_audit_full.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")

    print("GENESIS_INPUT_AUDIT_V1")
    print("input_report:", report_path)
    print("output_dir:", AUDIT_DIR)
    print("summary:", AUDIT_DIR / "input_audit_summary.txt")
    print("total_check_rows:", audit["model_input_audit"]["total_check_rows"])
    print("contract_families:", ", ".join(combo["contract_families"]))
    print("raw_combo_values_found:", len(combo["raw_combo_values_found_in_report"]))
    print("mapped_combos:", len(combo["mapped_combos"]))
    print("unmapped_combos:", len(combo["unmapped_combos"]))
    print("missing_required_families:", len(combo["missing_required_families"]))
    print("raw_units_seen:", audit["unit_audit"]["raw_units_seen"])
    print("canonical_units_seen:", audit["unit_audit"]["canonical_units_seen"])
    print("display_units_seen:", audit["unit_audit"]["display_units_seen"])
    print("governing_combo_count:", audit["design_source_audit"]["governing_combo_count"])

    if not combo["raw_combo_values_found_in_report"]:
        print("WARNING: no raw combo/governing_combo fields found in final report; strict combo mapping requires provenance fields.")
    if not audit["unit_audit"]["raw_units_seen"]:
        print("WARNING: no raw unit fields found in final report; strict unit audit requires raw ETABS unit provenance.")

    return 0

if __name__ == "__main__":
    raise SystemExit(main())
