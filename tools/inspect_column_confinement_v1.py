
from __future__ import annotations

import csv
import json
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENRICHED = PROJECT_ROOT / "reports_out" / "engine_report_enriched.json"
DEFAULT_RAW = PROJECT_ROOT / "reports_out" / "engine_report.json"

NUMBER = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)"
ASH_RE = re.compile(rf"(?:Ash(?:_provided)?|Ash)\s*[=:]\s*({NUMBER})", re.I)
ASH_REQ_RE = re.compile(rf"(?:Ash_required|required|req)\s*[=:]\s*({NUMBER})", re.I)
SPACING_RE = re.compile(rf"(?:spacing|s|aralık|araligi|aralığı)\s*[=:]\s*({NUMBER})", re.I)
LEGS_X_RE = re.compile(rf"(?:legs_x|kol_x|kx)\s*[=:]\s*({NUMBER})", re.I)
LEGS_Y_RE = re.compile(rf"(?:legs_y|kol_y|ky)\s*[=:]\s*({NUMBER})", re.I)
DIA_RE = re.compile(rf"(?:tie_dia|stirrup_dia|etriye|Φ|phi)\s*[=:]?\s*({NUMBER})", re.I)

def _first_float(pattern, text):
    m = pattern.search(text or "")
    if not m:
        return None
    try:
        return float(m.group(1))
    except Exception:
        return None

def _msg(row):
    return str(row.get("message") or row.get("description") or "")

def _status(row):
    return str(row.get("status") or "").upper().strip()

def _level(row):
    return str(row.get("evaluation_level") or "").upper().strip()

def _source(row):
    return str(row.get("source") or "").strip()

def classify_confinement_row(row):
    msg = _msg(row)
    status = _status(row)
    level = _level(row)
    source = _source(row)
    reason = str(row.get("reason_code") or "")

    ash = _first_float(ASH_RE, msg)
    ash_req = _first_float(ASH_REQ_RE, msg)
    spacing = _first_float(SPACING_RE, msg)
    legs_x = _first_float(LEGS_X_RE, msg)
    legs_y = _first_float(LEGS_Y_RE, msg)
    tie_dia = _first_float(DIA_RE, msg)

    source_l = source.lower()
    msg_l = msg.lower()

    has_auto_signal = any(token in source_l or token in msg_l for token in [
        "auto", "default", "fallback", "minimum", "proposal", "screening", "otomatik", "varsay",
    ])

    has_real_signal = any(token in source_l for token in [
        "user", "provided", "provided_rebar", "etabs", "column_rebar",
        "column_rebar_defs", "design_summary", "section_rebar_defs",
    ])

    has_ash_numbers = ash is not None or ash_req is not None
    has_spacing = spacing is not None

    if status == "OK":
        category = "ok"
    elif status == "WARNING":
        category = "screening_warning" if has_auto_signal or level in {"SCREENING", "APPROXIMATE"} else "borderline_warning"
    elif status == "NO_DATA":
        category = "missing_or_no_data"
    elif status == "FAIL":
        if has_auto_signal or level in {"SCREENING", "APPROXIMATE"}:
            category = "auto_or_screening_fail_candidate"
        elif has_real_signal and level in {"DESIGN_LEVEL", "ETABS_DESIGN_RESULT"}:
            category = "real_design_fail_candidate"
        elif has_real_signal and has_ash_numbers and has_spacing:
            category = "real_design_fail_candidate"
        elif not has_ash_numbers and not has_spacing:
            category = "missing_or_no_data"
        else:
            category = "unknown_fail"
    else:
        category = "unknown_status"

    if category == "auto_or_screening_fail_candidate":
        recommended_policy = "downgrade_to_WARNING_until_real_confinement_data"
    elif category == "missing_or_no_data":
        recommended_policy = "NO_DATA_or_SCREENING_WARNING_not_FAIL"
    elif category == "real_design_fail_candidate":
        recommended_policy = "keep_FAIL_and_report_Ash_spacing_evidence"
    elif category in {"borderline_warning", "screening_warning"}:
        recommended_policy = "keep_WARNING"
    else:
        recommended_policy = "keep_current"

    return {
        "check_id": row.get("check_id"),
        "element_label": row.get("element_label") or row.get("label") or "",
        "story": row.get("story") or "",
        "status": status,
        "evaluation_level": level,
        "source": source,
        "reason_code": reason,
        "category": category,
        "recommended_policy": recommended_policy,
        "ratio": row.get("ratio", 0.0),
        "ash_provided": ash,
        "ash_required": ash_req,
        "spacing_mm": spacing,
        "legs_x": legs_x,
        "legs_y": legs_y,
        "tie_dia_mm": tie_dia,
        "message": msg,
    }

def load_report(path=None):
    if path is None:
        path = DEFAULT_ENRICHED if DEFAULT_ENRICHED.exists() else DEFAULT_RAW
    path = path if path.is_absolute() else PROJECT_ROOT / path
    if not path.exists():
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))

def diagnose(report):
    rows = [r for r in report.get("checks", []) if isinstance(r, dict)]
    conf_rows = [r for r in rows if r.get("check_id") == "column_confinement"]
    rebar_rows = [r for r in rows if r.get("check_id") == "column_rebar_minimum"]

    details = [classify_confinement_row(r) for r in conf_rows]

    rebar_by_label = {}
    for r in rebar_rows:
        label = r.get("element_label") or r.get("label") or ""
        if label:
            rebar_by_label[label] = {
                "status": _status(r),
                "evaluation_level": _level(r),
                "source": _source(r),
                "message": _msg(r),
            }

    linked = 0
    for d in details:
        rb = rebar_by_label.get(d.get("element_label") or "")
        if rb:
            linked += 1
            d["column_rebar_minimum_status"] = rb["status"]
            d["column_rebar_minimum_source"] = rb["source"]
            d["column_rebar_minimum_level"] = rb["evaluation_level"]

    summary = {
        "total_column_confinement": len(conf_rows),
        "total_column_rebar_minimum": len(rebar_rows),
        "linked_rebar_minimum_by_label": linked,
        "by_status": dict(Counter(d["status"] for d in details)),
        "by_category": dict(Counter(d["category"] for d in details)),
        "by_recommended_policy": dict(Counter(d["recommended_policy"] for d in details)),
        "by_source": dict(Counter(d["source"] or "<empty>" for d in details)),
        "by_evaluation_level": dict(Counter(d["evaluation_level"] or "<empty>" for d in details)),
    }

    examples = {cat: [d for d in details if d["category"] == cat][:10] for cat in summary["by_category"]}

    return {
        "metadata": {
            "tool": "Genesis Column Confinement Cleanup v1 Diagnostic",
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "source_report_schema": (report.get("report_metadata") or {}).get("schema"),
        },
        "summary": summary,
        "examples": examples,
        "details": details,
    }

def write_outputs(diag):
    out_dir = PROJECT_ROOT / "reports_out"
    out_dir.mkdir(parents=True, exist_ok=True)

    json_path = out_dir / "column_confinement_diagnosis.json"
    csv_path = out_dir / "column_confinement_diagnosis.csv"

    json_path.write_text(json.dumps(diag, ensure_ascii=False, indent=2), encoding="utf-8")

    fieldnames = [
        "element_label", "story", "status", "evaluation_level", "source",
        "reason_code", "category", "recommended_policy", "ratio",
        "ash_provided", "ash_required", "spacing_mm", "legs_x", "legs_y",
        "tie_dia_mm", "column_rebar_minimum_status", "column_rebar_minimum_source",
        "column_rebar_minimum_level", "message",
    ]

    with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in diag["details"]:
            writer.writerow(row)

    hist_dir = out_dir / "history"
    hist_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    (hist_dir / f"{stamp}_column_confinement_diagnosis.json").write_text(
        json.dumps(diag, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return json_path, csv_path

def print_diag(diag, json_path, csv_path):
    s = diag["summary"]

    print("COLUMN_CONFINEMENT_DIAGNOSTIC_V1")
    print("json:", json_path)
    print("csv:", csv_path)
    print("total_column_confinement:", s["total_column_confinement"])
    print("total_column_rebar_minimum:", s["total_column_rebar_minimum"])
    print("linked_rebar_minimum_by_label:", s["linked_rebar_minimum_by_label"])

    for title, key in [
        ("by_status", "by_status"),
        ("by_category", "by_category"),
        ("by_recommended_policy", "by_recommended_policy"),
        ("by_source", "by_source"),
        ("by_evaluation_level", "by_evaluation_level"),
    ]:
        print(f"\n{title}:")
        for k, v in s[key].items():
            print(f"  {k}: {v}")

    print("\nfirst_examples:")
    for category, rows in diag["examples"].items():
        print(f"  {category}:")
        for r in rows[:3]:
            msg = (r.get("message") or "")[:140]
            print(
                f"    {r.get('status')} | {r.get('element_label')} | "
                f"level={r.get('evaluation_level')} | source={r.get('source')} | "
                f"policy={r.get('recommended_policy')} | msg={msg}"
            )

def main(argv=None):
    argv = argv or sys.argv[1:]
    report_path = Path(argv[0]) if argv else None

    try:
        report = load_report(report_path)
        diag = diagnose(report)
        json_path, csv_path = write_outputs(diag)
        print_diag(diag, json_path, csv_path)
        return 0
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}")
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
