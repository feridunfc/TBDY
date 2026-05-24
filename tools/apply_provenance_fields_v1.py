from __future__ import annotations
import json, re, sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
REPORTS_OUT = PROJECT_ROOT / "reports_out"
DEFAULT_REPORT = REPORTS_OUT / "final_engine_report.json"

NUMBER = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)"
UNIT_TOKEN_RE = re.compile(r"\b(kNm|kN|mm2|mm²|mm|MPa|ratio)\b", re.I)
SCWB_RE = re.compile(rf"ΣMrc\s*=\s*({NUMBER})\s*kNm.*?ΣMrb\s*=\s*({NUMBER})\s*kNm.*?required\s*=\s*1\.2ΣMrb\s*=\s*({NUMBER})\s*kNm", re.I)
CONF_RE = re.compile(rf"Ash\s*=\s*({NUMBER})\s*mm2\s*<\s*required\s*=\s*({NUMBER})\s*mm2.*?provided\s*=\s*Phi\s*({NUMBER})\s*@\s*({NUMBER})\s*mm.*?legs\s*=\s*(\d+)\s*/\s*(\d+)", re.I)
SCWB_JOINT_RE = re.compile(r"joint\s*=\s*([A-Za-z0-9_.:-]+)", re.I)
SCWB_DIR_RE = re.compile(r"dir\s*=\s*([XY])", re.I)
SCWB_BEAMS_RE = re.compile(r"beams\s*=\s*([^;]+)", re.I)
SCWB_COLUMNS_RE = re.compile(r"columns\s*=\s*([^;]+)", re.I)

CHECK_SOURCE_TABLE = {
    "column_geometry": "Model Geometry / Frame Assignments",
    "beam_geometry": "Model Geometry / Frame Assignments",
    "column_axial": "Frame Forces / Column Envelopes",
    "column_pmm": "Concrete Frame Design Summary / PMM",
    "column_shear": "Frame Forces / Column Shear Envelope",
    "column_confinement": "Concrete Frame Design Summary / Confinement Proposal",
    "column_rebar_minimum": "Column Rebar / Design Summary",
    "column_design_full": "Column Design Package Summary",
    "beam_flexure": "Concrete Frame Design Summary / Beam Flexure",
    "beam_shear": "Concrete Frame Design Summary / Beam Shear",
    "beam_ductility": "Concrete Frame Design Summary / Beam Detailing Screen",
    "beam_design_full": "Beam Design Package Summary",
    "column_capacity_hierarchy": "SCWB Projection / Joint Capacity",
    "beam_capacity_hierarchy": "SCWB Projection / Joint Capacity",
}
CHECK_SOURCE_FIELD = {
    "column_confinement": "Ash_required/Ash_provided/spacing/legs",
    "column_capacity_hierarchy": "ΣMrc/ΣMrb/ratio",
    "beam_capacity_hierarchy": "ΣMrc/ΣMrb/ratio",
    "beam_ductility": "beam_design_summary demand values",
    "beam_flexure": "beam_design_summary flexure ratio",
    "beam_shear": "beam_design_summary shear ratio",
    "column_pmm": "column_design_summary PMM ratio",
    "column_shear": "column shear envelope",
    "column_axial": "column axial envelope",
}
CHECK_UNITS = {
    "column_confinement": ("mm2/mm", "mm2/mm", "mm2/mm"),
    "column_capacity_hierarchy": ("kNm", "kNm", "kNm"),
    "beam_capacity_hierarchy": ("kNm", "kNm", "kNm"),
    "column_pmm": ("ratio", "ratio", "ratio"),
    "column_shear": ("kN", "kN", "kN"),
    "column_axial": ("kN", "kN", "kN"),
    "beam_flexure": ("kNm", "kNm", "kNm"),
    "beam_shear": ("kN", "kN", "kN"),
    "beam_ductility": ("design_summary", "screening", "screening"),
    "column_geometry": ("mm/m", "mm/m", "mm/m"),
    "beam_geometry": ("mm/m", "mm/m", "mm/m"),
}
COMBO_FAMILY_BY_CHECK = {
    "column_pmm": "S_E", "column_axial": "S_E", "column_shear": "K_E",
    "column_capacity_hierarchy": "S_E", "column_confinement": "S_E",
    "beam_flexure": "S_E", "beam_shear": "K_E",
    "beam_capacity_hierarchy": "S_E", "beam_ductility": "S_E",
}

def _msg(r): return str(r.get("message") or r.get("description") or "")
def _cid(r): return str(r.get("check_id") or "")
def _source(r): return str(r.get("source") or "")
def _level(r): return str(r.get("evaluation_level") or "").upper().strip()
def _reason(r): return str(r.get("reason_code") or "")

def infer_source_table(row: Dict[str, Any]) -> Tuple[str, str]:
    if row.get("source_table"): return str(row["source_table"]), "existing"
    cid, source, reason = _cid(row), _source(row).lower(), _reason(row).lower()
    if source == "scwb_resolver" or cid in {"column_capacity_hierarchy", "beam_capacity_hierarchy"}:
        return "SCWB Projection / Joint Capacity", "check_source"
    if source == "confinement_proposal" or reason == "non_final_confinement_proposal":
        return "Concrete Frame Design Summary / Confinement Proposal", "policy_source"
    if source in {"etabs", "etabs_or_design"} and cid.startswith("beam_"):
        return "ETABS Concrete Frame Design Summary / Beam", "source"
    if source == "force_envelope": return "Frame Forces / Envelope", "source"
    if source == "geometry_context": return "Model Geometry / Section Assignments", "source"
    return CHECK_SOURCE_TABLE.get(cid, ""), "check_id" if cid in CHECK_SOURCE_TABLE else "unknown"

def infer_source_field(row: Dict[str, Any]) -> Tuple[str, str]:
    if row.get("source_field"): return str(row["source_field"]), "existing"
    cid = _cid(row)
    if cid in CHECK_SOURCE_FIELD: return CHECK_SOURCE_FIELD[cid], "check_id"
    fields = [f for f in ["value", "limit", "ratio"] if row.get(f) is not None]
    return ",".join(fields), "available_fields" if fields else "unknown"

def infer_combo(row: Dict[str, Any]) -> Dict[str, Any]:
    cid = _cid(row)
    raw = row.get("raw_combo") or row.get("combo") or row.get("governing_combo") or row.get("design_combo") or ""
    fam = row.get("combo_family") or COMBO_FAMILY_BY_CHECK.get(cid, "")
    by = row.get("combo_resolved_by") or ("check_contract_usage" if fam and raw else "")
    if not raw and fam:
        raw = f"UNEXPOSED_ETABS_COMBO::{fam}"
        by = "required_family_fallback"
    return {
        "raw_combo": raw,
        "governing_combo": row.get("governing_combo") or raw,
        "combo_family": fam,
        "combo_resolved_by": by,
        "combo_provenance_level": "actual" if raw and not str(raw).startswith("UNEXPOSED_ETABS_COMBO::") else ("required_family_only" if fam else "missing"),
    }

def infer_units(row: Dict[str, Any]) -> Dict[str, Any]:
    cid = _cid(row)
    out = {k: row[k] for k in ["raw_unit", "canonical_unit", "display_unit"] if row.get(k)}
    if len(out) == 3: return out
    if cid in CHECK_UNITS:
        raw, can, disp = CHECK_UNITS[cid]
        out.setdefault("raw_unit", raw); out.setdefault("canonical_unit", can); out.setdefault("display_unit", disp)
    if row.get("unit"): out.setdefault("display_unit", row.get("unit"))
    units = sorted(set(m.group(1).replace("mm²", "mm2") for m in UNIT_TOKEN_RE.finditer(_msg(row))))
    if units:
        u = "/".join(units)
        out.setdefault("raw_unit", u); out.setdefault("canonical_unit", u); out.setdefault("display_unit", u)
    out.setdefault("raw_unit", ""); out.setdefault("canonical_unit", ""); out.setdefault("display_unit", row.get("unit") or "")
    return out

def infer_flags(row: Dict[str, Any]) -> Dict[str, bool]:
    source, level, reason, msg = _source(row).lower(), _level(row), _reason(row).lower(), _msg(row).lower()
    proposal = any(x in source or x in reason or x in msg for x in ["proposal", "non_final_confinement", "screening warning"])
    approx = level == "APPROXIMATE" or "approximate" in reason or "approximate" in msg
    final = level in {"DESIGN_LEVEL", "ETABS_DESIGN_RESULT"} and not proposal and not approx and "requires final" not in msg
    return {"source_is_final": bool(final), "source_is_approximate": bool(approx), "source_is_proposal": bool(proposal)}

def extract_evidence(row: Dict[str, Any]) -> Dict[str, Any]:
    msg, ev = _msg(row), {}
    m = CONF_RE.search(msg)
    if m:
        ev.update({"Ash_provided": float(m.group(1)), "Ash_required": float(m.group(2)), "tie_dia_mm": float(m.group(3)), "spacing_mm": float(m.group(4)), "legs_x": int(m.group(5)), "legs_y": int(m.group(6))})
    s = SCWB_RE.search(msg)
    if s:
        ev.update({"sum_Mrc_kNm": float(s.group(1)), "sum_Mrb_kNm": float(s.group(2)), "required_1p2_Mrb_kNm": float(s.group(3))})
    for regex, key in [(SCWB_JOINT_RE, "joint_id"), (SCWB_DIR_RE, "direction"), (SCWB_BEAMS_RE, "connected_beams"), (SCWB_COLUMNS_RE, "connected_columns")]:
        mm = regex.search(msg)
        if mm: ev[key] = mm.group(1).strip()
    return ev

def apply_provenance_to_row(row: Dict[str, Any]) -> Dict[str, Any]:
    st, st_by = infer_source_table(row); sf, sf_by = infer_source_field(row)
    row.setdefault("source_table", st); row.setdefault("source_table_inference", st_by)
    row.setdefault("source_field", sf); row.setdefault("source_field_inference", sf_by)
    for d in [infer_combo(row), infer_units(row), infer_flags(row)]:
        for k, v in d.items(): row.setdefault(k, v)
    row.setdefault("unit_context", {"raw": row.get("raw_unit", ""), "canonical": row.get("canonical_unit", ""), "display": row.get("display_unit", ""), "policy": "raw preserved when available; canonical used for checks; display used for report"})
    ev = row.get("evidence") if isinstance(row.get("evidence"), dict) else {}
    ev.update({k:v for k,v in extract_evidence(row).items() if k not in ev})
    if ev: row["evidence"] = ev
    return row

def apply_provenance(report: Dict[str, Any]) -> Dict[str, Any]:
    rows = [r for r in report.get("checks", []) if isinstance(r, dict)]
    for r in rows: apply_provenance_to_row(r)
    def count(k): return sum(1 for r in rows if r.get(k))
    def ctr(k): return dict(Counter(str(r.get(k) or "<empty>") for r in rows))
    meta = dict(report.get("report_metadata") or {})
    meta["schema"] = "final_engine_report.v1+provenance.v1"
    meta["provenance"] = "Genesis Provenance Fields v1"
    meta["provenance_applied_at"] = datetime.now().isoformat(timespec="seconds")
    report["report_metadata"] = meta
    report["checks"] = rows
    report["provenance_summary"] = {
        "total_rows": len(rows), "source_table_count": count("source_table"), "source_field_count": count("source_field"),
        "raw_combo_count": count("raw_combo"), "governing_combo_count": count("governing_combo"), "combo_family_count": count("combo_family"),
        "raw_unit_count": count("raw_unit"), "canonical_unit_count": count("canonical_unit"), "display_unit_count": count("display_unit"),
        "source_is_final_count": sum(1 for r in rows if r.get("source_is_final")),
        "source_is_approximate_count": sum(1 for r in rows if r.get("source_is_approximate")),
        "source_is_proposal_count": sum(1 for r in rows if r.get("source_is_proposal")),
        "combo_provenance_level": ctr("combo_provenance_level"), "by_source_table": ctr("source_table"), "by_combo_family": ctr("combo_family"),
        "by_raw_unit": ctr("raw_unit"), "by_canonical_unit": ctr("canonical_unit"), "by_display_unit": ctr("display_unit"),
    }
    return report

def main(argv: List[str] | None = None) -> int:
    argv = argv or sys.argv[1:]
    in_path = Path(argv[0]) if argv else DEFAULT_REPORT
    in_path = in_path if in_path.is_absolute() else PROJECT_ROOT / in_path
    if not in_path.exists():
        print(f"ERROR: final report not found: {in_path}")
        return 2
    out = apply_provenance(json.loads(in_path.read_text(encoding="utf-8")))
    out_path = REPORTS_OUT / "final_engine_report_provenance.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    hist = REPORTS_OUT / "history"; hist.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    hist_path = hist / f"{stamp}_final_engine_report_provenance.json"
    hist_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print("PROVENANCE_FIELDS_V1")
    print("input:", in_path); print("output:", out_path); print("snapshot:", hist_path)
    for k, v in out["provenance_summary"].items():
        if not isinstance(v, dict): print(f"{k}: {v}")
    print("\ncombo_provenance_level:")
    for k, v in out["provenance_summary"]["combo_provenance_level"].items(): print(f"  {k}: {v}")
    print("\nby_combo_family:")
    for k, v in out["provenance_summary"]["by_combo_family"].items(): print(f"  {k}: {v}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
