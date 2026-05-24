from __future__ import annotations

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

def _import_tools():
    from tools.enrich_engine_report_v1_2 import enrich_report
    from tools.apply_column_confinement_policy_v1_1 import apply_policy
    return enrich_report, apply_policy

def _load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))

def _write_json(path: Path, data: Dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def _counter(rows: List[Dict[str, Any]], key: str) -> Dict[str, int]:
    return dict(Counter(str(r.get(key) or "<empty>") for r in rows if isinstance(r, dict)))

def build_final_report(raw_report: Dict[str, Any]) -> Dict[str, Any]:
    enrich_report, apply_policy = _import_tools()
    enriched = enrich_report(raw_report)
    final = apply_policy(enriched)
    rows = [r for r in final.get("checks", []) if isinstance(r, dict)]

    metadata = dict(final.get("report_metadata") or {})
    metadata["schema"] = "final_engine_report.v1"
    metadata["final_pipeline"] = "Genesis Final Report Pipeline v1"
    metadata["final_pipeline_applied_at"] = datetime.now().isoformat(timespec="seconds")
    metadata["pipeline_steps"] = [
        "Genesis Runtime Bridge v1.1",
        "Genesis Report Enrichment v1.2",
        "Column Confinement Cleanup v1.1",
        "SCWB Projection Cleanup v1",
    ]
    final["report_metadata"] = metadata

    final["final_summary"] = {
        "total_checks": len(rows),
        "by_status": _counter(rows, "status"),
        "by_evaluation_level": _counter(rows, "evaluation_level"),
        "by_source": _counter(rows, "source"),
        "by_reason_code": _counter(rows, "reason_code"),
        "column_confinement_FAIL": sum(
            1 for r in rows if r.get("check_id") == "column_confinement" and str(r.get("status")).upper() == "FAIL"
        ),
        "column_confinement_WARNING": sum(
            1 for r in rows if r.get("check_id") == "column_confinement" and str(r.get("status")).upper() == "WARNING"
        ),
        "scwb_resolver_rows": sum(1 for r in rows if r.get("source") == "scwb_resolver"),
        "source_empty": sum(1 for r in rows if not r.get("source")),
        "not_evaluated": sum(1 for r in rows if str(r.get("evaluation_level") or "").upper() == "NOT_EVALUATED"),
    }
    return final

def main(argv: List[str] | None = None) -> int:
    argv = argv or sys.argv[1:]
    raw_path = Path(argv[0]) if argv else REPORTS_OUT / "engine_report.json"
    raw_path = raw_path if raw_path.is_absolute() else PROJECT_ROOT / raw_path

    if not raw_path.exists():
        print(f"ERROR: raw engine report not found: {raw_path}")
        print("Run first: python tools\\run_engine_v2_smoke.py")
        return 2

    REPORTS_OUT.mkdir(parents=True, exist_ok=True)
    raw = _load_json(raw_path)
    final = build_final_report(raw)

    final_path = REPORTS_OUT / "final_engine_report.json"
    _write_json(final_path, final)

    hist_dir = REPORTS_OUT / "history"
    hist_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    hist_path = hist_dir / f"{stamp}_final_engine_report.json"
    _write_json(hist_path, final)

    print("FINAL_ENGINE_REPORT_PIPELINE_V1")
    print("input:", raw_path)
    print("output:", final_path)
    print("snapshot:", hist_path)
    print("schema:", final.get("report_metadata", {}).get("schema"))

    fs = final.get("final_summary", {})
    print("total_checks:", fs.get("total_checks"))
    print("column_confinement_FAIL:", fs.get("column_confinement_FAIL"))
    print("column_confinement_WARNING:", fs.get("column_confinement_WARNING"))
    print("scwb_resolver_rows:", fs.get("scwb_resolver_rows"))
    print("source_empty:", fs.get("source_empty"))
    print("not_evaluated:", fs.get("not_evaluated"))

    print("\nby_status:")
    for k, v in (fs.get("by_status") or {}).items():
        print(f"  {k}: {v}")

    print("\nconfinement_policy_summary:")
    for k, v in (final.get("confinement_policy_summary") or {}).items():
        print(f"  {k}: {v}")

    return 0

if __name__ == "__main__":
    raise SystemExit(main())
