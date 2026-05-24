
from __future__ import annotations

import csv
import json
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

REPORTS_OUT = PROJECT_ROOT / "reports_out"
OUT_DIR = REPORTS_OUT / "etabs_combo_column_discovery"

COMBO_COLUMN_NAMES = {
    "combo", "load_combo", "load_combination", "loadcombination",
    "design_combo", "designcombo", "designcombination", "design_combo_name", "designcomb",
    "output_case", "outputcase", "load_case", "loadcase",
    "case", "case_name", "combo_name", "governing_combo",
    "design combination", "load combination", "output case", "load case",
    "case name", "load combo", "design combo",
}

EXCLUDED_PIPELINE_COLUMNS = {
    "combo_family", "combo_required_family", "combo_resolved_family",
    "combo_resolved_by", "combo_resolved_by_v1", "combo_resolution_confidence",
    "combo_matches_required_family", "combo_alias_summary", "combo_provenance_level",
    "raw_combo", "actual_combo_candidate", "actual_combo_family_candidate",
    "actual_combo_resolved_by", "actual_combo_confidence",
}

VALUE_RE = re.compile(
    r"(?:\b(?:EX|EY|EQ|EQX|EQY|RS|RSX|RSY|SPEC|SPECX|SPECY|DEPREM|DRIFT|CAPACITY|KAPASITE)\b|"
    r"K[_\-\s]?E(?:[_\-\s]?[XY])?|[GD]\s*[+]\s*(?:0\.3\s*)?[QL]\s*[+\-]\s*E[XY]|[+\-*/]|\d\.\d)",
    re.I,
)

def normalize_key(key: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(key or "").strip().lower()).strip("_")

def is_combo_column_name(key: str) -> bool:
    raw = str(key or "").strip().lower()
    nk = normalize_key(key)
    if nk in EXCLUDED_PIPELINE_COLUMNS:
        return False
    return raw in COMBO_COLUMN_NAMES or nk in {normalize_key(x) for x in COMBO_COLUMN_NAMES}

def is_actual_combo_like_value(value: Any) -> bool:
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

def row_like_dicts(obj: Any, path: str = "") -> Iterable[Tuple[str, Dict[str, Any]]]:
    if isinstance(obj, dict):
        scalar_count = sum(1 for v in obj.values() if not isinstance(v, (dict, list)))
        if scalar_count >= 2:
            yield path, obj
        for k, v in obj.items():
            p = f"{path}.{k}" if path else str(k)
            yield from row_like_dicts(v, p)
    elif isinstance(obj, list):
        for i, v in enumerate(obj[:100000]):
            yield from row_like_dicts(v, f"{path}[{i}]")

def scan_json_file(path: Path) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    rel = str(path.relative_to(PROJECT_ROOT))
    tables, columns, values = [], [], []
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig", errors="ignore"))
    except Exception:
        return tables, columns, values

    for row_path, row in row_like_dicts(data):
        combo_cols = [k for k in row.keys() if is_combo_column_name(k)]
        if not combo_cols:
            continue
        tables.append({"source": rel, "path": row_path, "format": "json", "combo_columns": ";".join(combo_cols), "column_count": len(row)})
        for col in combo_cols:
            val = row.get(col)
            like = is_actual_combo_like_value(val)
            columns.append({"source": rel, "path": row_path, "format": "json", "column": col, "normalized_column": normalize_key(col), "sample_value": val if isinstance(val, str) else "", "actual_value_like": like})
            if like:
                values.append({"source": rel, "path": row_path, "format": "json", "column": col, "value": str(val).strip()})
    return tables, columns, values

def scan_csv_file(path: Path) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    rel = str(path.relative_to(PROJECT_ROOT))
    tables, columns, values = [], [], []
    try:
        with path.open("r", encoding="utf-8-sig", errors="ignore", newline="") as f:
            reader = csv.DictReader(f)
            fields = reader.fieldnames or []
            combo_cols = [k for k in fields if is_combo_column_name(k)]
            if not combo_cols:
                return tables, columns, values
            tables.append({"source": rel, "path": "<csv>", "format": "csv", "combo_columns": ";".join(combo_cols), "column_count": len(fields)})
            samples = {c: "" for c in combo_cols}
            flags = {c: False for c in combo_cols}
            for i, row in enumerate(reader):
                if i > 100000:
                    break
                for col in combo_cols:
                    val = row.get(col, "")
                    if val and not samples[col]:
                        samples[col] = val
                    if is_actual_combo_like_value(val):
                        flags[col] = True
                        values.append({"source": rel, "path": f"row[{i}]", "format": "csv", "column": col, "value": str(val).strip()})
            for col in combo_cols:
                columns.append({"source": rel, "path": "<csv>", "format": "csv", "column": col, "normalized_column": normalize_key(col), "sample_value": samples[col], "actual_value_like": flags[col]})
    except Exception:
        pass
    return tables, columns, values

def scan_txt_file(path: Path) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    rel = str(path.relative_to(PROJECT_ROOT))
    tables, columns, values = [], [], []
    try:
        text = path.read_text(encoding="utf-8-sig", errors="ignore")[:5_000_000]
    except Exception:
        return tables, columns, values
    pat = re.compile(r"(Combo|Load Combo|Load Combination|DesignCombo|Design Combo|Design Combination|OutputCase|Output Case|LoadCase|Load Case|Case Name|governing_combo|design_combo|load_combo|output_case|load_case)\s*[:=]\s*['\"]?([^'\"\n;,]+)", re.I)
    for i, m in enumerate(pat.finditer(text)):
        col, val = m.group(1), m.group(2).strip()
        like = is_actual_combo_like_value(val)
        tables.append({"source": rel, "path": f"text_match[{i}]", "format": "txt", "combo_columns": col, "column_count": ""})
        columns.append({"source": rel, "path": f"text_match[{i}]", "format": "txt", "column": col, "normalized_column": normalize_key(col), "sample_value": val, "actual_value_like": like})
        if like:
            values.append({"source": rel, "path": f"text_match[{i}]", "format": "txt", "column": col, "value": val})
    return tables, columns, values

def scan_reports_out() -> Dict[str, List[Dict[str, Any]]]:
    tables, columns, values = [], [], []
    if not REPORTS_OUT.exists():
        return {"table_hits": tables, "column_hits": columns, "value_hits": values}
    for path in REPORTS_OUT.rglob("*"):
        if not path.is_file() or "history" in path.parts or path.stat().st_size > 30_000_000:
            continue
        if path.suffix.lower() == ".json":
            t, c, v = scan_json_file(path)
        elif path.suffix.lower() == ".csv":
            t, c, v = scan_csv_file(path)
        elif path.suffix.lower() in {".txt", ".log"}:
            t, c, v = scan_txt_file(path)
        else:
            continue
        tables.extend(t); columns.extend(c); values.extend(v)
    return {"table_hits": tables, "column_hits": columns, "value_hits": values}

def write_csv(path: Path, rows: List[Dict[str, Any]], fields: List[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow(row)

def build_audit() -> Dict[str, Any]:
    scanned_files = []
    if REPORTS_OUT.exists():
        scanned_files = [
            str(p.relative_to(PROJECT_ROOT))
            for p in REPORTS_OUT.rglob("*")
            if p.is_file() and "history" not in p.parts and p.suffix.lower() in {".json", ".csv", ".txt", ".log"} and p.stat().st_size <= 30_000_000
        ]
    scan = scan_reports_out()
    tables, columns, values = scan["table_hits"], scan["column_hits"], scan["value_hits"]
    unique_values = sorted(set(v["value"] for v in values))
    msg = "No combo columns or values found in current reports_out artifacts."
    if columns and not values:
        msg = "Combo-like columns found, but no actual ETABS combo-like values were found."
    elif values:
        msg = "Actual combo-like values found; next step can map these table columns into CheckResult provenance."
    return {
        "metadata": {"tool": "Genesis ETABS Design Summary Combo Column Discovery v1", "generated_at": datetime.now().isoformat(timespec="seconds"), "project_root": str(PROJECT_ROOT)},
        "summary": {
            "files_scanned": len(scanned_files),
            "candidate_tables": len(tables),
            "candidate_columns": len(columns),
            "candidate_values": len(values),
            "actual_value_like_columns": sum(1 for c in columns if c.get("actual_value_like")),
            "unique_candidate_values": len(unique_values),
            "columns_by_name": dict(Counter(c["normalized_column"] for c in columns)),
            "values_by_column": dict(Counter(v["column"] for v in values)),
        },
        "scanned_files": scanned_files,
        "table_hits": tables,
        "column_hits": columns,
        "value_hits": values,
        "unique_values": unique_values,
        "diagnostic": {"combo_column_found": bool(columns), "actual_combo_value_found": bool(values), "message": msg},
        "policy": {"mode": "passive_discovery_only", "changes_check_status": False, "changes_force_selector": False, "changes_legacy_runner": False},
    }

def write_summary(path: Path, audit: Dict[str, Any]) -> None:
    s = audit["summary"]
    lines = [
        "ETABS DESIGN SUMMARY COMBO COLUMN DISCOVERY V1",
        "=" * 72,
        "",
        f"files_scanned: {s['files_scanned']}",
        f"candidate_tables: {s['candidate_tables']}",
        f"candidate_columns: {s['candidate_columns']}",
        f"candidate_values: {s['candidate_values']}",
        f"actual_value_like_columns: {s['actual_value_like_columns']}",
        f"unique_candidate_values: {s['unique_candidate_values']}",
        f"columns_by_name: {s['columns_by_name']}",
        f"values_by_column: {s['values_by_column']}",
        "",
        f"diagnostic: {audit['diagnostic']['message']}",
        "",
        "policy: passive_discovery_only; no status/selector/legacy changes",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    audit = build_audit()
    (OUT_DIR / "combo_column_discovery.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    write_summary(OUT_DIR / "combo_column_discovery_summary.txt", audit)
    write_csv(OUT_DIR / "candidate_tables.csv", audit["table_hits"], ["source", "path", "format", "column_count", "combo_columns"])
    write_csv(OUT_DIR / "candidate_columns.csv", audit["column_hits"], ["source", "path", "format", "column", "normalized_column", "sample_value", "actual_value_like"])
    write_csv(OUT_DIR / "candidate_values.csv", audit["value_hits"], ["source", "path", "format", "column", "value"])
    s = audit["summary"]
    print("ETABS_COMBO_COLUMN_DISCOVERY_V1")
    print("output_dir:", OUT_DIR)
    print("files_scanned:", s["files_scanned"])
    print("candidate_tables:", s["candidate_tables"])
    print("candidate_columns:", s["candidate_columns"])
    print("candidate_values:", s["candidate_values"])
    print("actual_value_like_columns:", s["actual_value_like_columns"])
    print("unique_candidate_values:", s["unique_candidate_values"])
    print("columns_by_name:", s["columns_by_name"])
    print("values_by_column:", s["values_by_column"])
    print("diagnostic:", audit["diagnostic"]["message"])
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
