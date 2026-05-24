from pathlib import Path

root = Path.cwd()
(root / "tools").mkdir(exist_ok=True)
(root / "tests").mkdir(exist_ok=True)

(root / "tools" / "enrich_engine_report_v1_2.py").write_text(r'''
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT = PROJECT_ROOT / "reports_out" / "engine_report.json"

SOURCE_RE = re.compile(r"(?:^|\s|\|)\s*source\s*=\s*([A-Za-z0-9_.:-]+)")
REASON_RE = re.compile(r"(?:^|\s|\|)\s*reason_code\s*=\s*([A-Za-z0-9_.:-]+)")

KNOWN_SOURCE_BY_CHECK = {
    "beam_flexure": "etabs_or_design",
    "beam_shear": "etabs_or_design",
    "beam_ductility": "etabs",
    "beam_geometry": "geometry_context",
    "column_geometry": "geometry_context",
    "column_axial": "force_envelope",
    "column_pmm": "pmm_module",
    "column_shear": "force_envelope",
    "column_confinement": "column_rebar",
    "column_rebar_minimum": "column_rebar",
    "column_design_full": "column_module_summary",
    "beam_design_full": "beam_module_summary",
    "column_capacity_hierarchy": "scwb_resolver",
    "beam_capacity_hierarchy": "scwb_resolver",
}

CATEGORY_FALLBACK_SOURCE = {
    "GEOMETRY": "geometry_context",
    "DESIGN_BEAM": "beam_module",
    "DESIGN_COLUMN": "column_module",
    "DESIGN_SCWB": "scwb_resolver",
    "HIERARCHY": "scwb_resolver",
    "SUMMARY": "module_summary",
    "DETAILING": "detailing_module",
}

def _norm_status(value: Any) -> str:
    return str(value or "").upper().strip() or "NOT_EVALUATED"

def _msg(row: Dict[str, Any]) -> str:
    return str(row.get("message") or row.get("description") or "")

def infer_source(row: Dict[str, Any]) -> Tuple[str, str]:
    existing = str(row.get("source") or "").strip()
    if existing and existing != "<empty>":
        return existing, "existing"

    m = SOURCE_RE.search(_msg(row))
    if m:
        return m.group(1), "message"

    cid = str(row.get("check_id") or "")
    if cid in KNOWN_SOURCE_BY_CHECK:
        return KNOWN_SOURCE_BY_CHECK[cid], "check_id"

    cat = str(row.get("category") or "")
    if cat in CATEGORY_FALLBACK_SOURCE:
        return CATEGORY_FALLBACK_SOURCE[cat], "category"

    ev = str(row.get("evaluation") or "")
    if ev:
        return ev.lower(), "evaluation"

    return "", "unknown"

def infer_reason_code(row: Dict[str, Any]) -> str:
    existing = str(row.get("reason_code") or "").strip()
    if existing:
        return existing

    msg = _msg(row)
    msg_l = msg.lower()

    m = REASON_RE.search(msg)
    if m:
        return m.group(1)

    status = _norm_status(row.get("status"))
    source = str(row.get("source") or "")
    level = str(row.get("evaluation_level") or "")
    cid = str(row.get("check_id") or "")

    if status == "NO_DATA":
        if "kuvvet verisi yok" in msg_l or "force" in msg_l:
            return "missing_forces"
        if "topoloji" in msg_l or "topology" in msg_l:
            return "missing_topology"
        return "missing_data"

    if source == "scwb_resolver":
        if level == "APPROXIMATE":
            return "approximate_capacity"
        if level == "NO_DATA":
            return "missing_scwb_data"

    if cid.endswith("_design_full"):
        return "package_summary"

    if "requires final provided" in msg_l:
        return "requires_final_rebar_schedule"

    if "downgraded to warning" in msg_l:
        return "approximate_downgraded"

    return ""

def infer_evaluation_level(row: Dict[str, Any]) -> Tuple[str, str]:
    existing = str(row.get("evaluation_level") or "").upper().strip()
    if existing and existing != "NOT_EVALUATED":
        return existing, "existing"

    status = _norm_status(row.get("status"))
    source = str(row.get("source") or "")
    msg_l = _msg(row).lower()
    cid = str(row.get("check_id") or "")

    if status == "ERROR":
        return "ERROR", "status"
    if status == "NO_DATA":
        return "NO_DATA", "status"
    if source == "scwb_resolver":
        return "APPROXIMATE", "source"
    if "screening" in msg_l or "requires final" in msg_l:
        return "SCREENING", "message"
    if "approx" in msg_l or "basitlestirilmis" in msg_l or source == "simplified":
        return "APPROXIMATE", "message"
    if source.startswith("etabs") or source in {"etabs", "etabs_or_design"}:
        return "ETABS_DESIGN_RESULT", "source"
    if cid in {"beam_geometry", "column_geometry"}:
        return "DESIGN_LEVEL", "check_id"
    if source:
        return "DESIGN_LEVEL", "source"

    return "NOT_EVALUATED", "unknown"

def enrich_report(report: Dict[str, Any]) -> Dict[str, Any]:
    checks = list(report.get("checks") or [])
    source_filled = 0
    level_filled = 0
    reason_filled = 0
    enriched_count = 0

    for row in checks:
        if not isinstance(row, dict):
            continue

        old_source = str(row.get("source") or "").strip()
        source, source_conf = infer_source(row)
        if source and not old_source:
            row["source"] = source
            row["source_inference"] = source_conf
            source_filled += 1

        old_reason = str(row.get("reason_code") or "").strip()
        reason = infer_reason_code(row)
        if reason and not old_reason:
            row["reason_code"] = reason
            reason_filled += 1

        old_level = str(row.get("evaluation_level") or "").upper().strip()
        level, level_conf = infer_evaluation_level(row)
        if level and (not old_level or old_level == "NOT_EVALUATED"):
            row["evaluation_level"] = level
            row["evaluation_level_inference"] = level_conf
            if level != "NOT_EVALUATED":
                level_filled += 1

        if row.get("source_inference") or row.get("evaluation_level_inference") or row.get("reason_code"):
            enriched_count += 1

    distributions = {
        "by_status": dict(Counter(_norm_status(r.get("status")) for r in checks if isinstance(r, dict))),
        "by_check_id": dict(Counter(str(r.get("check_id") or "<empty>") for r in checks if isinstance(r, dict))),
        "by_evaluation_level": dict(Counter(str(r.get("evaluation_level") or "<empty>") for r in checks if isinstance(r, dict))),
        "by_source": dict(Counter(str(r.get("source") or "<empty>") for r in checks if isinstance(r, dict))),
        "by_category": dict(Counter(str(r.get("category") or "<empty>") for r in checks if isinstance(r, dict))),
        "by_reason_code": dict(Counter(str(r.get("reason_code") or "<empty>") for r in checks if isinstance(r, dict))),
    }

    report["checks"] = checks
    report["distributions"] = distributions

    metadata = dict(report.get("report_metadata") or {})
    metadata["schema"] = "engine_report.v1.2"
    metadata["enriched_by"] = "Genesis Report Enrichment v1.2"
    metadata["enriched_at"] = datetime.now().isoformat(timespec="seconds")
    report["report_metadata"] = metadata

    report["enrichment_summary"] = {
        "checks": len(checks),
        "enriched_rows": enriched_count,
        "source_filled": source_filled,
        "evaluation_level_filled": level_filled,
        "reason_code_filled": reason_filled,
        "source_empty_after": distributions["by_source"].get("<empty>", 0),
        "not_evaluated_after": distributions["by_evaluation_level"].get("NOT_EVALUATED", 0),
    }

    return report

def main(argv: List[str] | None = None) -> int:
    argv = argv or sys.argv[1:]
    report_path = Path(argv[0]) if argv else DEFAULT_REPORT
    report_path = report_path if report_path.is_absolute() else PROJECT_ROOT / report_path

    if not report_path.exists():
        print(f"ERROR: report not found: {report_path}")
        return 2

    report = json.loads(report_path.read_text(encoding="utf-8"))
    enriched = enrich_report(report)

    out_dir = report_path.parent
    out_path = out_dir / "engine_report_enriched.json"
    out_path.write_text(json.dumps(enriched, ensure_ascii=False, indent=2), encoding="utf-8")

    hist_dir = out_dir / "history"
    hist_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    hist_path = hist_dir / f"{stamp}_engine_report_enriched.json"
    hist_path.write_text(json.dumps(enriched, ensure_ascii=False, indent=2), encoding="utf-8")

    print("GENESIS_REPORT_ENRICHMENT_V1_2")
    print("input:", report_path)
    print("output:", out_path)
    print("snapshot:", hist_path)
    for k, v in enriched.get("enrichment_summary", {}).items():
        print(f"{k}: {v}")

    return 0

if __name__ == "__main__":
    raise SystemExit(main())
''', encoding="utf-8")

(root / "tools" / "inspect_engine_report_v1_2.py").write_text(r'''
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT = PROJECT_ROOT / "reports_out" / "engine_report_enriched.json"

def _counter(rows: List[Dict[str, Any]], key: str) -> Counter:
    return Counter(str(r.get(key) or "<empty>") for r in rows if isinstance(r, dict))

def _print_counter(title: str, c: Counter, limit: int = 30):
    print(f"\n{title}:")
    for k, v in c.most_common(limit):
        print(f"  {k}: {v}")

def main(argv: List[str] | None = None) -> int:
    argv = argv or sys.argv[1:]
    path = Path(argv[0]) if argv else DEFAULT_REPORT
    path = path if path.is_absolute() else PROJECT_ROOT / path

    if not path.exists():
        fallback = PROJECT_ROOT / "reports_out" / "engine_report.json"
        print(f"WARNING: enriched report not found, using fallback: {fallback}")
        path = fallback

    d = json.loads(path.read_text(encoding="utf-8"))
    rows = [r for r in d.get("checks", []) if isinstance(r, dict)]

    print("ENGINE_REPORT_INSPECT_V1_2")
    print("path:", path)
    print("metadata:", d.get("report_metadata"))
    print("summary:", d.get("summary"))
    print("coverage:", d.get("coverage"))
    print("enrichment_summary:", d.get("enrichment_summary"))

    _print_counter("by_status", _counter(rows, "status"))
    _print_counter("by_check_id", _counter(rows, "check_id"))
    _print_counter("by_evaluation_level", _counter(rows, "evaluation_level"))
    _print_counter("by_source", _counter(rows, "source"))
    _print_counter("by_reason_code", _counter(rows, "reason_code"))
    _print_counter("by_category", _counter(rows, "category"))

    problems = [r for r in rows if str(r.get("status", "")).upper() in {"FAIL", "WARNING", "NO_DATA", "ERROR"}]

    print("\nfirst_20_problem_rows:")
    for r in problems[:20]:
        print(
            f"  {r.get('status')} | {r.get('check_id')} | {r.get('element_label')} | "
            f"level={r.get('evaluation_level')} | source={r.get('source')} | "
            f"reason={r.get('reason_code')} | msg={str(r.get('message') or '')[:140]}"
        )

    return 0

if __name__ == "__main__":
    raise SystemExit(main())
''', encoding="utf-8")

(root / "tests" / "test_report_enrichment_v1_2.py").write_text(r'''
from tools.enrich_engine_report_v1_2 import enrich_report

def test_report_enrichment_v1_2_fills_source_level_and_reason():
    report = {
        "report_metadata": {"schema": "engine_report.v1.1"},
        "summary": {"error": 0},
        "checks": [
            {
                "check_id": "column_capacity_hierarchy",
                "status": "WARNING",
                "message": "SCWB approximate result; reason_code=approximate_capacity; source=scwb_resolver",
                "evaluation_level": "NOT_EVALUATED",
                "source": "",
                "category": "DESIGN_SCWB",
            },
            {
                "check_id": "beam_ductility",
                "status": "WARNING",
                "message": "Ductility/detailing requires final provided beam rebar schedule.",
                "evaluation_level": "NOT_EVALUATED",
                "source": "",
                "category": "DESIGN_BEAM",
            },
        ],
    }

    enriched = enrich_report(report)
    rows = enriched["checks"]

    assert rows[0]["source"] == "scwb_resolver"
    assert rows[0]["evaluation_level"] == "APPROXIMATE"
    assert rows[0]["reason_code"] == "approximate_capacity"

    assert rows[1]["source"] == "etabs"
    assert rows[1]["evaluation_level"] == "SCREENING"
    assert rows[1]["reason_code"] == "requires_final_rebar_schedule"

    assert enriched["report_metadata"]["schema"] == "engine_report.v1.2"
    assert enriched["enrichment_summary"]["source_empty_after"] == 0
    assert enriched["enrichment_summary"]["not_evaluated_after"] == 0
''', encoding="utf-8")

print("INSTALLED")
print(root / "tools" / "enrich_engine_report_v1_2.py")
print(root / "tools" / "inspect_engine_report_v1_2.py")
print(root / "tests" / "test_report_enrichment_v1_2.py")
