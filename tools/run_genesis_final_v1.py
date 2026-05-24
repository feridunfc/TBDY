from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

REPORTS_OUT = PROJECT_ROOT / "reports_out"
SUMMARY_PATH = REPORTS_OUT / "genesis_final_summary.txt"
SUMMARY_JSON_PATH = REPORTS_OUT / "genesis_final_summary.json"

def _run_py(script: str, *args: str) -> Dict[str, Any]:
    cmd = [sys.executable, str(PROJECT_ROOT / script), *args]
    proc = subprocess.run(
        cmd,
        cwd=str(PROJECT_ROOT),
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
    )
    return {
        "script": script,
        "args": list(args),
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "ok": proc.returncode == 0,
    }

def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))

def _need(path: Path, label: str) -> None:
    if not path.exists():
        raise FileNotFoundError(f"{label} not found: {path}")

def run_pipeline(run_engine: bool = False) -> Dict[str, Any]:
    """
    Consolidated final report runner.

    Default does not run ETABS/context engine; it consumes reports_out/engine_report.json.
    Use --run-engine to call tools/run_engine_v2_smoke.py first.
    """
    REPORTS_OUT.mkdir(parents=True, exist_ok=True)

    steps: List[Dict[str, Any]] = []
    if run_engine:
        steps.append(_run_py("tools/run_engine_v2_smoke.py"))
        if not steps[-1]["ok"]:
            return build_summary(steps)

    steps.append(_run_py("tools/run_final_engine_report_v1.py"))
    if not steps[-1]["ok"]:
        return build_summary(steps)

    steps.append(_run_py("tools/apply_provenance_fields_v1.py"))
    if not steps[-1]["ok"]:
        return build_summary(steps)

    steps.append(_run_py("tools/apply_combo_alias_resolver_v1.py"))
    if not steps[-1]["ok"]:
        return build_summary(steps)

    steps.append(_run_py("tools/run_input_audit_v1_1.py", "reports_out/final_engine_report_combo_resolved.json"))
    return build_summary(steps)

def build_summary(steps: List[Dict[str, Any]]) -> Dict[str, Any]:
    final_report = _read_json(REPORTS_OUT / "final_engine_report.json")
    provenance_report = _read_json(REPORTS_OUT / "final_engine_report_provenance.json")
    combo_report = _read_json(REPORTS_OUT / "final_engine_report_combo_resolved.json")
    audit = _read_json(REPORTS_OUT / "input_audit" / "input_audit_v1_1_full.json")

    final_summary = final_report.get("final_summary") or {}
    conf_summary = final_report.get("confinement_policy_summary") or {}
    prov_summary = provenance_report.get("provenance_summary") or {}
    combo_summary = combo_report.get("combo_alias_summary") or {}
    combo_audit = (audit.get("combo_contract_audit") or {})
    unit_audit = (audit.get("unit_audit") or {})
    design_audit = (audit.get("design_source_audit") or {})

    summary = {
        "metadata": {
            "tool": "Genesis Consolidated Final Runner v1",
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "project_root": str(PROJECT_ROOT),
        },
        "steps": [
            {
                "script": s["script"],
                "args": s["args"],
                "returncode": s["returncode"],
                "ok": s["ok"],
            }
            for s in steps
        ],
        "ok": all(s["ok"] for s in steps),
        "outputs": {
            "final_engine_report": str(REPORTS_OUT / "final_engine_report.json"),
            "final_engine_report_provenance": str(REPORTS_OUT / "final_engine_report_provenance.json"),
            "final_engine_report_combo_resolved": str(REPORTS_OUT / "final_engine_report_combo_resolved.json"),
            "input_audit_v1_1": str(REPORTS_OUT / "input_audit" / "input_audit_v1_1_full.json"),
            "summary_txt": str(SUMMARY_PATH),
            "summary_json": str(SUMMARY_JSON_PATH),
        },
        "final_report": {
            "total_checks": final_summary.get("total_checks"),
            "column_confinement_FAIL": final_summary.get("column_confinement_FAIL"),
            "column_confinement_WARNING": final_summary.get("column_confinement_WARNING"),
            "scwb_resolver_rows": final_summary.get("scwb_resolver_rows"),
            "source_empty": final_summary.get("source_empty"),
            "not_evaluated": final_summary.get("not_evaluated"),
            "confinement_policy_summary": conf_summary,
        },
        "provenance": {
            "source_table_count": prov_summary.get("source_table_count"),
            "source_field_count": prov_summary.get("source_field_count"),
            "raw_combo_count": prov_summary.get("raw_combo_count"),
            "governing_combo_count": prov_summary.get("governing_combo_count"),
            "raw_unit_count": prov_summary.get("raw_unit_count"),
            "canonical_unit_count": prov_summary.get("canonical_unit_count"),
            "display_unit_count": prov_summary.get("display_unit_count"),
            "combo_provenance_level": prov_summary.get("combo_provenance_level"),
        },
        "combo_alias": {
            "rows_resolved": combo_summary.get("rows_resolved"),
            "rows_fallback_marker": combo_summary.get("rows_fallback_marker"),
            "rows_mismatch": combo_summary.get("rows_mismatch"),
            "resolved_by": combo_summary.get("resolved_by"),
            "resolved_family": combo_summary.get("resolved_family"),
        },
        "input_audit_v1_1": {
            "combo_audit_source": combo_audit.get("combo_audit_source"),
            "unique_raw_combo_count": combo_audit.get("unique_raw_combo_count"),
            "mapped_unique": combo_audit.get("mapped_unique"),
            "unmapped_unique": combo_audit.get("unmapped_unique"),
            "fallback_unique": combo_audit.get("fallback_unique"),
            "actual_unique": combo_audit.get("actual_unique"),
            "rows_resolved": combo_audit.get("rows_resolved"),
            "rows_fallback_marker": combo_audit.get("rows_fallback_marker"),
            "rows_mismatch": combo_audit.get("rows_mismatch"),
            "raw_units_seen": unit_audit.get("raw_units_seen"),
            "canonical_units_seen": unit_audit.get("canonical_units_seen"),
            "display_units_seen": unit_audit.get("display_units_seen"),
            "governing_combo_count": design_audit.get("governing_combo_count"),
        },
    }

    SUMMARY_JSON_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    SUMMARY_PATH.write_text(format_summary(summary, steps), encoding="utf-8")
    return summary

def format_summary(summary: Dict[str, Any], steps: List[Dict[str, Any]]) -> str:
    lines = []
    lines.append("GENESIS CONSOLIDATED FINAL RUNNER V1")
    lines.append("=" * 72)
    lines.append(f"ok: {summary.get('ok')}")
    lines.append("")
    lines.append("steps:")
    for s in steps:
        lines.append(f"  {'PASS' if s['ok'] else 'FAIL'} {s['script']} {' '.join(s['args'])}".rstrip())
    lines.append("")

    fr = summary["final_report"]
    lines.append("final_report:")
    for k in ["total_checks", "column_confinement_FAIL", "column_confinement_WARNING", "scwb_resolver_rows", "source_empty", "not_evaluated"]:
        lines.append(f"  {k}: {fr.get(k)}")
    lines.append("")

    prov = summary["provenance"]
    lines.append("provenance:")
    for k in ["source_table_count", "source_field_count", "raw_combo_count", "governing_combo_count", "raw_unit_count", "canonical_unit_count", "display_unit_count"]:
        lines.append(f"  {k}: {prov.get(k)}")
    lines.append(f"  combo_provenance_level: {prov.get('combo_provenance_level')}")
    lines.append("")

    ca = summary["combo_alias"]
    lines.append("combo_alias:")
    for k in ["rows_resolved", "rows_fallback_marker", "rows_mismatch"]:
        lines.append(f"  {k}: {ca.get(k)}")
    lines.append(f"  resolved_by: {ca.get('resolved_by')}")
    lines.append(f"  resolved_family: {ca.get('resolved_family')}")
    lines.append("")

    ia = summary["input_audit_v1_1"]
    lines.append("input_audit_v1_1:")
    for k in ["combo_audit_source", "unique_raw_combo_count", "mapped_unique", "unmapped_unique", "fallback_unique", "actual_unique", "rows_resolved", "rows_fallback_marker", "rows_mismatch", "governing_combo_count"]:
        lines.append(f"  {k}: {ia.get(k)}")
    lines.append(f"  raw_units_seen: {ia.get('raw_units_seen')}")
    lines.append(f"  canonical_units_seen: {ia.get('canonical_units_seen')}")
    lines.append(f"  display_units_seen: {ia.get('display_units_seen')}")
    lines.append("")
    lines.append("recommended_next:")
    lines.append("  Actual ETABS Governing Combo Extraction v1")
    return "\n".join(lines) + "\n"

def print_summary(summary: Dict[str, Any]) -> None:
    print("GENESIS_FINAL_V1")
    print("ok:", summary.get("ok"))

    print("\nsteps:")
    for s in summary.get("steps", []):
        print(f"  {'PASS' if s['ok'] else 'FAIL'} {s['script']}")

    fr = summary["final_report"]
    print("\nfinal_report:")
    print("  total_checks:", fr.get("total_checks"))
    print("  column_confinement_FAIL:", fr.get("column_confinement_FAIL"))
    print("  source_empty:", fr.get("source_empty"))
    print("  not_evaluated:", fr.get("not_evaluated"))

    prov = summary["provenance"]
    print("\nprovenance:")
    print("  source_table_count:", prov.get("source_table_count"))
    print("  governing_combo_count:", prov.get("governing_combo_count"))
    print("  raw_unit_count:", prov.get("raw_unit_count"))

    ca = summary["combo_alias"]
    print("\ncombo_alias:")
    print("  rows_resolved:", ca.get("rows_resolved"))
    print("  rows_fallback_marker:", ca.get("rows_fallback_marker"))
    print("  rows_mismatch:", ca.get("rows_mismatch"))

    ia = summary["input_audit_v1_1"]
    print("\ninput_audit_v1_1:")
    print("  combo_audit_source:", ia.get("combo_audit_source"))
    print("  mapped_unique:", ia.get("mapped_unique"))
    print("  unmapped_unique:", ia.get("unmapped_unique"))
    print("  fallback_unique:", ia.get("fallback_unique"))
    print("  actual_unique:", ia.get("actual_unique"))

    print("\nsummary:", SUMMARY_PATH)
    print("summary_json:", SUMMARY_JSON_PATH)

def main(argv: List[str] | None = None) -> int:
    argv = argv or sys.argv[1:]
    run_engine = "--run-engine" in argv
    summary = run_pipeline(run_engine=run_engine)
    print_summary(summary)

    if not summary.get("ok"):
        print("\nFAILED STEP OUTPUT:")
        for step in summary.get("steps", []):
            if not step["ok"]:
                # find full step payload
                break
        return 1
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
