from __future__ import annotations

import csv
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from tools.combo_alias_resolver_v1 import resolve_combo_family
except Exception:
    def resolve_combo_family(raw_name: str, required_family: str = "", families=None) -> Dict[str, Any]:
        s = str(raw_name or "").upper()
        fam = ""
        by = "fallback_simple"
        if raw_name.startswith("UNEXPOSED_ETABS_COMBO::"):
            fam = raw_name.split("::", 1)[1]
            by = "fallback_family_marker"
        elif any(tok in s for tok in ["EX", "EY", "EQ", "SPEC", "RS", "DEPREM"]):
            fam = "S_E"
        elif any(tok in s for tok in ["K_E", "CAPACITY", "KAPASITE", "SHEAR", "KESME"]):
            fam = "K_E"
        elif "DRIFT" in s:
            fam = "DRIFT"
        elif any(tok in s for tok in ["G", "D", "Q", "L"]):
            fam = "G"
        return {
            "raw_combo": raw_name,
            "resolved_family": fam,
            "resolved_by": by,
            "confidence": 0.5 if fam else 0.0,
            "required_family": required_family,
            "matches_required_family": (not required_family or fam == required_family),
            "is_fallback_marker": raw_name.startswith("UNEXPOSED_ETABS_COMBO::"),
        }

REPORTS_OUT = PROJECT_ROOT / "reports_out"
AUDIT_DIR = REPORTS_OUT / "actual_combo_audit"
DEFAULT_INPUT = REPORTS_OUT / "final_engine_report_combo_resolved.json"
DEFAULT_OUTPUT = AUDIT_DIR / "final_engine_report_actual_combo.json"

CANDIDATE_FIELD_NAMES = {
    "governing_combo", "design_combo", "load_combo", "output_case", "load_case",
    "combo_name", "combo", "case", "case_name", "loadcomb", "designcomb",
    "Combo", "Load Combo", "OutputCase", "LoadCase", "DesignCombo",
    "Load Combination", "LoadCombination", "Output Case", "Case", "Case Name",
}

# lowercase normalized tokens used for fuzzy key matching
CANDIDATE_KEY_TOKENS = {
    "governing_combo", "design_combo", "load_combo", "output_case", "load_case",
    "combo_name", "combo", "case_name", "loadcomb", "designcomb",
    "loadcombination", "load_combination", "outputcase", "output_case", "loadcase",
    "designcombo",
}

SKIP_VALUES_PREFIXES = ("UNEXPOSED_ETABS_COMBO::",)

# === ACTUAL_COMBO_V1_1_METADATA_FILTER_START ===
METADATA_COMBO_KEYS_EXCLUDE = {
    "combo_family",
    "combo_required_family",
    "combo_resolved_family",
    "combo_alias_summary",
    "combo_provenance_level",
    "combo_resolved_by",
    "combo_resolved_by_v1",
    "combo_resolution_confidence",
    "combo_matches_required_family",
    "combo_audit_source",
    "combo_alias_resolver",
    "combo_alias_resolver_applied_at",
    "available_families_from_raw_combos",
    "raw_combo_values_found_in_report",
    "mapped_combos",
    "unmapped_combos",
    "resolved_family",
    "resolved_by",
    "required_family",
}
PIPELINE_FALLBACK_FIELD_NAMES = {"raw_combo", "governing_combo"}
ACTUAL_COMBO_SOURCE_HINTS = (
    "design_summary",
    "beam_design_summary",
    "column_design_summary",
    "force_table",
    "frame_force",
    "frame_forces",
    "etabs_table",
    "ctx.tables",
    "ctx_tables",
    "database_tables",
    "table.",
    "tables.",
)
# === ACTUAL_COMBO_V1_1_METADATA_FILTER_END ===

COMBO_HINT_RE = re.compile(
    r"(?:\b(?:G|D|Q|L|E|EX|EY|EQ|RS|SPEC|KE|DRIFT|DEPREM|CAPACITY|KAPASITE)\b|K[_\-\s]?E(?:[_\-\s]?[XY])?|[+\-*/]|\d\.\d)",
    re.I,
)

SCAN_REPORT_NAMES = [
    "final_engine_report_combo_resolved.json",
    "final_engine_report_provenance.json",
    "final_engine_report.json",
    "engine_report_confinement_policy.json",
    "engine_report_enriched.json",
    "engine_report.json",
]

SCAN_EXTENSIONS = {".json", ".csv", ".txt"}

def normalize_key(key: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(key or "").strip().lower()).strip("_")

def is_candidate_key(key: str) -> bool:
    nk = normalize_key(key)
    if nk in METADATA_COMBO_KEYS_EXCLUDE:
        return False
    if nk in CANDIDATE_KEY_TOKENS:
        return True
    if nk in {"case", "case_name", "output_case", "load_case"}:
        return True
    return False

def is_candidate_value(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    v = value.strip()
    if not v or len(v) > 160:
        return False
    if any(v.startswith(p) for p in SKIP_VALUES_PREFIXES):
        return False
    # Reject units or generic statuses.
    if v.upper() in {"OK", "FAIL", "WARNING", "NO_DATA", "SCREENING", "DESIGN_LEVEL", "APPROXIMATE"}:
        return False
    return bool(COMBO_HINT_RE.search(v))

def read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))

def rows(report: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [r for r in report.get("checks", []) if isinstance(r, dict)]

def flatten(obj: Any, prefix: str = "") -> Iterable[Tuple[str, Any]]:
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = f"{prefix}.{k}" if prefix else str(k)
            yield from flatten(v, p)
    elif isinstance(obj, list):
        for i, v in enumerate(obj[:20000]):
            p = f"{prefix}[{i}]"
            yield from flatten(v, p)
    else:
        yield prefix, obj

def source_path_allows_actual_combo(path: str, key: str, source: str = "") -> bool:
    nk = normalize_key(key)
    text = f"{path} {source}".lower()

    if nk in METADATA_COMBO_KEYS_EXCLUDE:
        return False

    if nk in PIPELINE_FALLBACK_FIELD_NAMES:
        return any(h in text for h in ACTUAL_COMBO_SOURCE_HINTS)

    if "final_engine_report" in text and not any(h in text for h in ACTUAL_COMBO_SOURCE_HINTS):
        return False

    return True

def candidate_from_mapping(mapping: Dict[str, Any], source_prefix: str) -> List[Dict[str, Any]]:
    out = []
    for k, v in flatten(mapping):
        key = k.split(".")[-1].split("[")[0]
        if is_candidate_key(key) and is_candidate_value(v) and source_path_allows_actual_combo(k, key, source_prefix):
            raw = str(v).strip()
            res = resolve_combo_family(raw)
            out.append({
                "candidate": raw,
                "field": key,
                "path": k,
                "source": source_prefix,
                "family": res.get("resolved_family") or "",
                "resolved_by": res.get("resolved_by") or "",
                "confidence": res.get("confidence", ""),
            })
    return out

def scan_report_rows(report: Dict[str, Any], report_name: str) -> List[Dict[str, Any]]:
    found = []
    for idx, r in enumerate(rows(report)):
        row_source = f"{report_name}.checks[{idx}]"
        cid = str(r.get("check_id") or "")
        label = str(r.get("element_label") or "")
        story = str(r.get("story") or "")
        for item in candidate_from_mapping(r, row_source):
            item.update({
                "row_index": idx,
                "check_id": cid,
                "element_label": label,
                "story": story,
                "source_type": "report_row",
            })
            found.append(item)
    return found

def scan_json_artifact(path: Path) -> List[Dict[str, Any]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig", errors="ignore"))
    except Exception:
        return []
    found = []
    for item in candidate_from_mapping(data, str(path.relative_to(PROJECT_ROOT))):
        item.update({
            "row_index": "",
            "check_id": "",
            "element_label": "",
            "story": "",
            "source_type": "json_artifact",
        })
        found.append(item)
    return found

def scan_csv_artifact(path: Path) -> List[Dict[str, Any]]:
    found = []
    try:
        with path.open("r", encoding="utf-8-sig", errors="ignore", newline="") as f:
            reader = csv.DictReader(f)
            if not reader.fieldnames:
                return found
            for i, row in enumerate(reader):
                if i > 50000:
                    break
                for k, v in row.items():
                    if is_candidate_key(k) and is_candidate_value(v) and source_path_allows_actual_combo(f"row[{i}].{k}", k, str(path.relative_to(PROJECT_ROOT))):
                        raw = str(v).strip()
                        res = resolve_combo_family(raw)
                        found.append({
                            "candidate": raw,
                            "field": k,
                            "path": f"row[{i}].{k}",
                            "source": str(path.relative_to(PROJECT_ROOT)),
                            "family": res.get("resolved_family") or "",
                            "resolved_by": res.get("resolved_by") or "",
                            "confidence": res.get("confidence", ""),
                            "row_index": i,
                            "check_id": row.get("check_id", ""),
                            "element_label": row.get("element_label", "") or row.get("label", ""),
                            "story": row.get("story", ""),
                            "source_type": "csv_artifact",
                        })
    except Exception:
        pass
    return found

def scan_txt_artifact(path: Path) -> List[Dict[str, Any]]:
    found = []
    try:
        text = path.read_text(encoding="utf-8-sig", errors="ignore")[:5_000_000]
    except Exception:
        return found
    pat = re.compile(r"(governing_combo|design_combo|load_combo|output_case|load_case|combo_name|combo|case_name|Load Combo|OutputCase|LoadCase|DesignCombo)\s*[:=]\s*['\"]?([^'\"\n;,]+)", re.I)
    for i, m in enumerate(pat.finditer(text)):
        key, raw = m.group(1), m.group(2).strip()
        if is_candidate_value(raw):
            res = resolve_combo_family(raw)
            found.append({
                "candidate": raw,
                "field": key,
                "path": f"text_match[{i}]",
                "source": str(path.relative_to(PROJECT_ROOT)),
                "family": res.get("resolved_family") or "",
                "resolved_by": res.get("resolved_by") or "",
                "confidence": res.get("confidence", ""),
                "row_index": "",
                "check_id": "",
                "element_label": "",
                "story": "",
                "source_type": "txt_artifact",
            })
    return found

def scan_artifacts() -> List[Dict[str, Any]]:
    found = []
    roots = [REPORTS_OUT]
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in SCAN_EXTENSIONS:
                continue
            if "history" in path.parts:
                continue
            if path.name in {"final_engine_report_actual_combo.json"}:
                continue
            if path.stat().st_size > 20_000_000:
                continue
            if path.suffix.lower() == ".json":
                found.extend(scan_json_artifact(path))
            elif path.suffix.lower() == ".csv":
                found.extend(scan_csv_artifact(path))
            else:
                found.extend(scan_txt_artifact(path))
    return found

def unique_candidates(cands: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    counter = Counter(c["candidate"] for c in cands)
    first = {}
    for c in cands:
        first.setdefault(c["candidate"], c)
    out = []
    for candidate, count in sorted(counter.items(), key=lambda kv: (-kv[1], kv[0])):
        item = dict(first[candidate])
        item["count"] = count
        out.append(item)
    return out

def choose_row_candidate(row: Dict[str, Any], row_candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
    required = str(row.get("combo_required_family") or row.get("combo_family") or "")
    if not row_candidates:
        return {}

    # Prefer direct family match to row requirement.
    matching = [c for c in row_candidates if required and c.get("family") == required]
    if matching:
        best = matching[0]
        best = dict(best)
        best["actual_combo_confidence"] = "HIGH"
        return best

    # If one candidate exists, use it as medium if no requirement; otherwise low mismatch candidate.
    if len(row_candidates) == 1:
        best = dict(row_candidates[0])
        best["actual_combo_confidence"] = "MEDIUM" if not required else "LOW"
        return best

    # Ambiguous: pick nothing.
    return {}

def apply_actual_combo_to_report(report: Dict[str, Any], row_field_candidates: List[Dict[str, Any]]) -> Tuple[Dict[str, Any], List[Dict[str, Any]], List[Dict[str, Any]]]:
    rs = rows(report)
    by_row = defaultdict(list)
    for c in row_field_candidates:
        if c.get("source_type") == "report_row" and c.get("row_index") != "":
            by_row[int(c["row_index"])].append(c)

    matches = []
    unmatched = []

    for idx, r in enumerate(rs):
        cand = choose_row_candidate(r, by_row.get(idx, []))
        if cand:
            r["actual_combo_candidate"] = cand.get("candidate", "")
            r["actual_combo_source"] = cand.get("source", "")
            r["actual_combo_field"] = cand.get("field", "")
            r["actual_combo_family_candidate"] = cand.get("family", "")
            r["actual_combo_resolved_by"] = cand.get("resolved_by", "actual_candidate")
            r["actual_combo_confidence"] = cand.get("actual_combo_confidence", "MEDIUM")
            r["actual_combo_path"] = cand.get("path", "")
            required = str(r.get("combo_required_family") or r.get("combo_family") or "")
            r["actual_combo_matches_required_family"] = (not required or not cand.get("family") or cand.get("family") == required)
            matches.append({
                "row_index": idx,
                "check_id": r.get("check_id", ""),
                "element_label": r.get("element_label", ""),
                "required_family": required,
                "actual_combo_candidate": r["actual_combo_candidate"],
                "actual_combo_family_candidate": r["actual_combo_family_candidate"],
                "actual_combo_source": r["actual_combo_source"],
                "actual_combo_field": r["actual_combo_field"],
                "actual_combo_confidence": r["actual_combo_confidence"],
                "matches_required_family": r["actual_combo_matches_required_family"],
            })
        else:
            r.setdefault("actual_combo_candidate", "")
            r.setdefault("actual_combo_source", "")
            r.setdefault("actual_combo_field", "")
            r.setdefault("actual_combo_family_candidate", "")
            r.setdefault("actual_combo_resolved_by", "not_found")
            r.setdefault("actual_combo_confidence", "NONE")
            r.setdefault("actual_combo_path", "")
            r.setdefault("actual_combo_matches_required_family", True)
            if r.get("raw_combo") or r.get("governing_combo") or r.get("combo_family"):
                unmatched.append({
                    "row_index": idx,
                    "check_id": r.get("check_id", ""),
                    "element_label": r.get("element_label", ""),
                    "required_family": r.get("combo_required_family") or r.get("combo_family") or "",
                    "raw_combo": r.get("raw_combo", ""),
                    "governing_combo": r.get("governing_combo", ""),
                    "reason": "no actual candidate found in row fields",
                })

    report["checks"] = rs
    return report, matches, unmatched

def build_audit(input_report: Dict[str, Any], artifact_candidates: List[Dict[str, Any]], row_candidates: List[Dict[str, Any]], matches: List[Dict[str, Any]], unmatched: List[Dict[str, Any]]) -> Dict[str, Any]:
    all_candidates = row_candidates + artifact_candidates
    unique = unique_candidates(all_candidates)
    family_counts = Counter(c.get("family") or "<unmapped>" for c in all_candidates)
    field_counts = Counter(c.get("field") or "<empty>" for c in all_candidates)
    source_counts = Counter(c.get("source") or "<empty>" for c in all_candidates)
    actual_unique_values = sorted(set(m["actual_combo_candidate"] for m in matches if m.get("actual_combo_candidate")))
    mismatch_rows = [m for m in matches if not m.get("matches_required_family")]

    return {
        "metadata": {
            "tool": "Genesis Actual ETABS Governing Combo Extraction v1.1 Metadata Filter",
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "project_root": str(PROJECT_ROOT),
        },
        "summary": {
            "total_rows": len(rows(input_report)),
            "candidate_fields_found": len(all_candidates),
            "row_candidate_fields_found": len(row_candidates),
            "artifact_candidate_fields_found": len(artifact_candidates),
            "rows_with_actual_combo_candidate": len(matches),
            "unmatched_rows": len(unmatched),
            "actual_unique": len(actual_unique_values),
            "actual_unique_values": actual_unique_values,
            "actual_combo_fields_found": dict(field_counts),
            "actual_combo_sources_found": dict(source_counts),
            "family_mapped_actual_candidates": sum(1 for c in all_candidates if c.get("family")),
            "family_unmapped_actual_candidates": sum(1 for c in all_candidates if not c.get("family")),
            "rows_mismatch": len(mismatch_rows),
        },
        "unique_candidates": unique,
        "row_matches": matches,
        "unmatched_rows": unmatched,
        "field_candidates": all_candidates,
        "family_counts": dict(family_counts),
        "policy": {
            "mode": "passive_diagnostic_plus_provenance",
            "changes_check_status": False,
            "changes_force_selector": False,
            "changes_legacy_runner": False,
        },
        "diagnostic": {
            "actual_combo_source_exposed": bool(matches),
            "message": "Actual combo candidates found and attached to rows." if matches else "No row-level actual ETABS combo fields found. Current report still exposes required-family fallback markers only.",
        },
    }

def write_csv(path: Path, items: List[Dict[str, Any]], fields: List[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for item in items:
            w.writerow(item)

def write_summary(path: Path, audit: Dict[str, Any]) -> None:
    s = audit["summary"]
    lines = [
        "GENESIS ACTUAL ETABS GOVERNING COMBO EXTRACTION V1.1",
        "=" * 72,
        "",
        f"total_rows: {s['total_rows']}",
        f"candidate_fields_found: {s['candidate_fields_found']}",
        f"row_candidate_fields_found: {s['row_candidate_fields_found']}",
        f"artifact_candidate_fields_found: {s['artifact_candidate_fields_found']}",
        f"rows_with_actual_combo_candidate: {s['rows_with_actual_combo_candidate']}",
        f"actual_unique: {s['actual_unique']}",
        f"actual_unique_values: {s['actual_unique_values']}",
        f"rows_mismatch: {s['rows_mismatch']}",
        f"unmatched_rows: {s['unmatched_rows']}",
        f"family_mapped_actual_candidates: {s['family_mapped_actual_candidates']}",
        f"family_unmapped_actual_candidates: {s['family_unmapped_actual_candidates']}",
        "",
        "policy:",
        "  passive_diagnostic_plus_provenance",
        "  changes_check_status: False",
        "  changes_force_selector: False",
        "  changes_legacy_runner: False",
        "",
        "diagnostic:",
        f"  actual_combo_source_exposed: {audit['diagnostic']['actual_combo_source_exposed']}",
        f"  message: {audit['diagnostic']['message']}",
        "",
        "recommended_next:",
        "  If actual_unique > 0: integrate actual combo candidates into consolidated runner.",
        "  If actual_unique = 0: add governing_combo extraction at ModelContext/CheckResult production point.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

def main(argv: List[str] | None = None) -> int:
    argv = argv or sys.argv[1:]
    in_path = Path(argv[0]) if argv else DEFAULT_INPUT
    in_path = in_path if in_path.is_absolute() else PROJECT_ROOT / in_path
    if not in_path.exists():
        print(f"ERROR: input report not found: {in_path}")
        print("Run first: python tools\\run_genesis_final_v1.py")
        return 2

    report = read_json(in_path)
    row_candidates = scan_report_rows(report, in_path.name)
    artifact_candidates = scan_artifacts()

    out_report, matches, unmatched = apply_actual_combo_to_report(report, row_candidates)
    audit = build_audit(out_report, artifact_candidates, row_candidates, matches, unmatched)

    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    out_report["actual_combo_audit_summary"] = audit["summary"]
    out_report["actual_combo_policy"] = audit["policy"]
    out_report["report_metadata"] = dict(out_report.get("report_metadata") or {})
    out_report["report_metadata"]["actual_combo_extraction"] = "Genesis Actual ETABS Governing Combo Extraction v1.1 Metadata Filter"
    out_report["report_metadata"]["actual_combo_extraction_applied_at"] = datetime.now().isoformat(timespec="seconds")

    DEFAULT_OUTPUT.write_text(json.dumps(out_report, ensure_ascii=False, indent=2), encoding="utf-8")
    (AUDIT_DIR / "actual_combo_audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    write_summary(AUDIT_DIR / "actual_combo_audit_summary.txt", audit)

    write_csv(AUDIT_DIR / "actual_combo_field_candidates.csv", audit["field_candidates"], [
        "candidate", "field", "path", "source", "family", "resolved_by", "confidence", "row_index", "check_id", "element_label", "story", "source_type"
    ])
    write_csv(AUDIT_DIR / "actual_combo_unique_values.csv", audit["unique_candidates"], [
        "candidate", "count", "field", "path", "source", "family", "resolved_by", "confidence", "source_type"
    ])
    write_csv(AUDIT_DIR / "actual_combo_row_matches.csv", audit["row_matches"], [
        "row_index", "check_id", "element_label", "required_family", "actual_combo_candidate", "actual_combo_family_candidate", "actual_combo_source", "actual_combo_field", "actual_combo_confidence", "matches_required_family"
    ])
    write_csv(AUDIT_DIR / "actual_combo_unmatched_rows.csv", audit["unmatched_rows"], [
        "row_index", "check_id", "element_label", "required_family", "raw_combo", "governing_combo", "reason"
    ])

    hist = AUDIT_DIR / "history"
    hist.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    (hist / f"{stamp}_actual_combo_audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")

    s = audit["summary"]
    print("ACTUAL_ETABS_GOVERNING_COMBO_EXTRACTION_V1_1")
    print("input:", in_path)
    print("output:", DEFAULT_OUTPUT)
    print("audit_dir:", AUDIT_DIR)
    print("total_rows:", s["total_rows"])
    print("candidate_fields_found:", s["candidate_fields_found"])
    print("row_candidate_fields_found:", s["row_candidate_fields_found"])
    print("artifact_candidate_fields_found:", s["artifact_candidate_fields_found"])
    print("rows_with_actual_combo_candidate:", s["rows_with_actual_combo_candidate"])
    print("actual_unique:", s["actual_unique"])
    print("rows_mismatch:", s["rows_mismatch"])
    print("unmatched_rows:", s["unmatched_rows"])
    print("family_mapped_actual_candidates:", s["family_mapped_actual_candidates"])
    print("family_unmapped_actual_candidates:", s["family_unmapped_actual_candidates"])
    print("diagnostic:", audit["diagnostic"]["message"])
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
