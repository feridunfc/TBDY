
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
        if "K_E" in s or "CAPACITY" in s or "KAPASITE" in s:
            fam = "K_E"
        elif any(x in s for x in ["EX", "EY", "EQ", "RS", "SPEC", "DEPREM"]):
            fam = "S_E"
        return {"resolved_family": fam, "resolved_by": "fallback", "confidence": 0.5 if fam else 0.0}

REPORTS_OUT = PROJECT_ROOT / "reports_out"
OUT_DIR = REPORTS_OUT / "actual_combo_source_injection"
DEFAULT_REPORT = REPORTS_OUT / "final_engine_report_combo_resolved.json"
DEFAULT_INJECTED = OUT_DIR / "final_engine_report_injected_combo.json"

COMBO_KEY_EXACT = {
    "combo", "load_combo", "load_combination", "loadcombination",
    "design_combo", "designcombination", "design_combo_name",
    "output_case", "outputcase", "load_case", "loadcase",
    "case_name", "case", "combo_name", "governing_combo",
    "designcomb", "loadcomb",
}
EXCLUDE_KEYS = {
    "combo_family", "combo_required_family", "combo_resolved_family",
    "combo_resolved_by", "combo_resolved_by_v1", "combo_matches_required_family",
    "combo_resolution_confidence", "combo_alias_summary", "combo_provenance_level",
    "raw_combo", "actual_combo_candidate", "actual_combo_family_candidate",
}
SOURCE_HINTS = (
    "design_summary", "beam_design_summary", "column_design_summary",
    "etabs", "frame_force", "frame_forces", "force_table", "forces",
    "design_metadata", "envelope", "envelopes", "tables", "database",
)
VALUE_RE = re.compile(
    r"(?:\b(?:EX|EY|EQ|EQX|EQY|RS|RSX|RSY|SPEC|SPECX|SPECY|DEPREM|DRIFT|CAPACITY|KAPASITE)\b|K[_\-\s]?E(?:[_\-\s]?[XY])?|[GD]\s*[+]\s*(?:0\.3\s*)?[QL]\s*[+\-]\s*E[XY]|[+\-*/]|\d\.\d)",
    re.I,
)

def normalize_key(key: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(key or "").strip().lower()).strip("_")

def flatten(obj: Any, prefix: str = "") -> Iterable[Tuple[str, Any]]:
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = f"{prefix}.{k}" if prefix else str(k)
            yield from flatten(v, p)
    elif isinstance(obj, list):
        for i, v in enumerate(obj[:100000]):
            p = f"{prefix}[{i}]"
            yield from flatten(v, p)
    else:
        yield prefix, obj

def is_combo_key(key: str) -> bool:
    nk = normalize_key(key)
    if nk in EXCLUDE_KEYS:
        return False
    return nk in COMBO_KEY_EXACT

def is_combo_value(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    v = value.strip()
    if not v or len(v) > 160:
        return False
    if v.startswith("UNEXPOSED_ETABS_COMBO::"):
        return False
    if v.upper() in {"OK", "FAIL", "WARNING", "NO_DATA", "SCREENING", "DESIGN_LEVEL", "K_E", "S_E", "G", "DRIFT", "SOIL"}:
        return False
    return bool(VALUE_RE.search(v))

def path_has_source_hint(path: str) -> bool:
    p = str(path or "").lower()
    return any(h in p for h in SOURCE_HINTS)

def extract_candidates_from_obj(obj: Any, source: str) -> List[Dict[str, Any]]:
    out = []
    for path, value in flatten(obj):
        key = path.split(".")[-1].split("[")[0]
        if not is_combo_key(key) or not is_combo_value(value):
            continue
        if "final_engine_report" in source.lower() and not path_has_source_hint(path):
            continue
        raw = str(value).strip()
        res = resolve_combo_family(raw)
        out.append({
            "candidate": raw,
            "field": key,
            "path": path,
            "source": source,
            "family": res.get("resolved_family") or "",
            "resolved_by": res.get("resolved_by") or "",
            "confidence": res.get("confidence", ""),
        })
    return out

def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))

def write_csv(path: Path, rows: List[Dict[str, Any]], fields: List[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow(row)

def scan_reports_out() -> List[Dict[str, Any]]:
    candidates = []
    if not REPORTS_OUT.exists():
        return candidates
    for path in REPORTS_OUT.rglob("*"):
        if not path.is_file():
            continue
        if "history" in path.parts:
            continue
        if path.suffix.lower() not in {".json", ".csv", ".txt"}:
            continue
        if path.stat().st_size > 25_000_000:
            continue
        rel = str(path.relative_to(PROJECT_ROOT))
        if path.suffix.lower() == ".json":
            try:
                candidates.extend(extract_candidates_from_obj(read_json(path), rel))
            except Exception:
                pass
        elif path.suffix.lower() == ".csv":
            try:
                with path.open("r", encoding="utf-8-sig", errors="ignore", newline="") as f:
                    reader = csv.DictReader(f)
                    for i, row in enumerate(reader):
                        if i > 100000:
                            break
                        for k, v in row.items():
                            if is_combo_key(k) and is_combo_value(v) and path_has_source_hint(rel):
                                raw = str(v).strip()
                                res = resolve_combo_family(raw)
                                candidates.append({
                                    "candidate": raw,
                                    "field": k,
                                    "path": f"row[{i}].{k}",
                                    "source": rel,
                                    "family": res.get("resolved_family") or "",
                                    "resolved_by": res.get("resolved_by") or "",
                                    "confidence": res.get("confidence", ""),
                                })
            except Exception:
                pass
        else:
            try:
                text = path.read_text(encoding="utf-8-sig", errors="ignore")[:5_000_000]
                pat = re.compile(r"(Combo|Load Combo|LoadCombination|DesignCombo|OutputCase|LoadCase|Case Name|governing_combo|design_combo|load_combo|output_case|load_case|case_name)\s*[:=]\s*['\"]?([^'\"\n;,]+)", re.I)
                for i, m in enumerate(pat.finditer(text)):
                    key, val = m.group(1), m.group(2).strip()
                    if is_combo_key(key) and is_combo_value(val) and path_has_source_hint(rel):
                        res = resolve_combo_family(val)
                        candidates.append({
                            "candidate": val,
                            "field": key,
                            "path": f"text_match[{i}]",
                            "source": rel,
                            "family": res.get("resolved_family") or "",
                            "resolved_by": res.get("resolved_by") or "",
                            "confidence": res.get("confidence", ""),
                        })
            except Exception:
                pass
    return candidates

def unique_summary(candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    grouped = {}
    for c in candidates:
        key = c["candidate"]
        if key not in grouped:
            grouped[key] = dict(c)
            grouped[key]["count"] = 0
            grouped[key]["sources"] = set()
            grouped[key]["fields"] = set()
        grouped[key]["count"] += 1
        grouped[key]["sources"].add(c.get("source", ""))
        grouped[key]["fields"].add(c.get("field", ""))
    out = []
    for item in grouped.values():
        item["sources"] = "; ".join(sorted(item["sources"]))
        item["fields"] = "; ".join(sorted(item["fields"]))
        out.append(item)
    return sorted(out, key=lambda x: (-x["count"], x["candidate"]))

def load_report(path: Path = DEFAULT_REPORT) -> Dict[str, Any]:
    return read_json(path)

def check_rows(report: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [r for r in report.get("checks", []) if isinstance(r, dict)]

def candidate_index(candidates: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    by_family = defaultdict(list)
    for c in candidates:
        fam = c.get("family") or ""
        if fam:
            by_family[fam].append(c)
    return by_family

def choose_for_row(row: Dict[str, Any], by_family: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
    required = str(row.get("combo_required_family") or row.get("combo_family") or "")
    if not required:
        return {}
    options = by_family.get(required, [])
    if not options:
        return {}
    # Conservative v1: inject only if exactly one unique candidate exists for this family.
    uniq = unique_summary(options)
    if len(uniq) != 1:
        return {}
    return uniq[0]
def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    candidates = scan_reports_out()
    unique = unique_summary(candidates)
    summary = {
        "metadata": {
            "tool": "Genesis Actual Combo Source Inspector v1",
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "project_root": str(PROJECT_ROOT),
        },
        "summary": {
            "candidate_count": len(candidates),
            "unique_candidate_count": len(unique),
            "families": dict(Counter(c.get("family") or "<unmapped>" for c in candidates)),
            "fields": dict(Counter(c.get("field") or "<empty>" for c in candidates)),
            "sources": dict(Counter(c.get("source") or "<empty>" for c in candidates)),
        },
        "candidates": candidates,
        "unique_candidates": unique,
        "policy": {
            "mode": "passive_inspector",
            "changes_check_status": False,
            "changes_force_selector": False,
            "changes_legacy_runner": False,
        }
    }
    (OUT_DIR / "actual_combo_source_inspector.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(OUT_DIR / "actual_combo_source_candidates.csv", candidates, ["candidate", "field", "path", "source", "family", "resolved_by", "confidence"])
    write_csv(OUT_DIR / "actual_combo_source_unique.csv", unique, ["candidate", "count", "family", "resolved_by", "confidence", "fields", "sources"])

    s = summary["summary"]
    print("ACTUAL_COMBO_SOURCE_INSPECTOR_V1")
    print("output_dir:", OUT_DIR)
    print("candidate_count:", s["candidate_count"])
    print("unique_candidate_count:", s["unique_candidate_count"])
    print("families:", s["families"])
    print("fields:", s["fields"])
    print("sources_count:", len(s["sources"]))
    if unique:
        print("first_unique_candidates:")
        for item in unique[:20]:
            print(f"  {item['candidate']} | family={item.get('family')} | count={item.get('count')} | fields={item.get('fields')}")
    else:
        print("diagnostic: no actual ETABS combo source candidates found in current artifacts")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
