#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tbdy_engine.features.semantic_source_review import (  # noqa: E402
    SPRINT,
    TARGET_FAMILIES,
    build_combo_semantic_review,
    build_design_output_semantic_review,
    build_drift_story_semantic_review,
    build_force_result_semantic_review,
    build_rebar_role_semantic_review,
    build_semantic_source_inventory_report,
    build_semantic_source_review_report,
    build_semantic_source_sample_rows,
    candidate_tables_for_target,
    classify_semantic_source_table,
    scan_semantic_outputs_for_forbidden_verdicts,
)
from tbdy_engine.providers.etabs_display_table_fetcher import fetch_display_table  # noqa: E402

OUTPUT_FILES = [
    "connection_report.json",
    "semantic_source_review_summary.json",
    "semantic_source_inventory_report.json",
    "combo_semantic_review_report.json",
    "force_result_semantic_review_report.json",
    "drift_story_semantic_review_report.json",
    "design_output_semantic_review_report.json",
    "rebar_role_semantic_review_report.json",
    "semantic_source_sample_rows.json",
    "forbidden_verdict_scan_report.json",
]


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _json_safe(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    return repr(value)


def _guardrails() -> dict[str, Any]:
    return {
        "safe_to_implement_checks_now": False,
        "check_unlock_allowed": False,
        "diagnostic_only": True,
        "check_engine_invoked": False,
        "engineering_verdicts_emitted": False,
        "check_results_emitted": False,
        "excel_production_input_used": False,
        "feature_values_faked": False,
    }


def _connect_to_etabs() -> tuple[Any | None, dict[str, Any]]:
    try:
        try:
            import comtypes.client  # type: ignore
            etabs = comtypes.client.GetActiveObject("CSI.ETABS.API.ETABSObject")
        except Exception:
            import win32com.client  # type: ignore
            etabs = win32com.client.GetActiveObject("CSI.ETABS.API.ETABSObject")
        sap_model = etabs.SapModel
        try:
            model_path = sap_model.GetModelFilename()
        except Exception:
            model_path = None
        try:
            raw_version = sap_model.GetVersion()
            etabs_version = raw_version[0] if isinstance(raw_version, (list, tuple)) else raw_version
        except Exception:
            etabs_version = None
        return sap_model.DatabaseTables, {
            "live_etabs_connected": True,
            "connection_status": "LIVE_CONNECTED",
            "model_path": model_path,
            "etabs_version": etabs_version,
            "tables_attempted": [],
            "table_errors": {},
        }
    except Exception as exc:  # pragma: no cover - requires local ETABS/COM
        return None, {
            "live_etabs_connected": False,
            "connection_status": "LIVE_CONNECTION_ERROR",
            "diagnostic": str(exc),
            "model_path": None,
            "etabs_version": None,
            "tables_attempted": [],
            "table_errors": {},
        }


def _fetch_table(database_tables: Any, table_name: str, max_rows: int) -> tuple[list[dict[str, Any]], list[str], dict[str, Any]]:
    result = fetch_display_table(database_tables, table_name, max_rows=max_rows)
    parsed = result.parsed
    rows = [dict(row) for row in parsed.rows[:max_rows]]
    diagnostics = {
        "actual_table_name": parsed.actual_table_name,
        "fetch_status": parsed.fetch_status,
        "row_count_reported": parsed.row_count_reported,
        "return_code": parsed.return_code,
        "selected_signature": _json_safe(dict(result.selected_signature or {})),
        "selected_signature_reason": result.selected_signature_reason,
        "signature_attempts": _json_safe([dict(item) for item in result.signature_attempts]),
        "parser_debug": _json_safe(dict(parsed.debug or {})),
        "parser_diagnostics": _json_safe(list(parsed.diagnostics)),
    }
    return rows, list(parsed.field_keys), diagnostics


def _review_live_sources(target_family: str, max_rows: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    database_tables, connection = _connect_to_etabs()
    classifications: list[dict[str, Any]] = []
    if database_tables is None:
        return classifications, connection
    for source_family, table_name in candidate_tables_for_target(target_family):
        connection["tables_attempted"].append(table_name)
        try:
            rows, columns, diagnostics = _fetch_table(database_tables, table_name, max_rows)
            classification = classify_semantic_source_table(
                source_family=source_family,
                table_name=table_name,
                fetch_status="FETCHED",
                rows=rows,
                columns=columns,
                notes=[f"bounded live fetch max_rows={max_rows}", f"fetch_diagnostics={json.dumps(diagnostics, sort_keys=True)}"],
            )
        except Exception as exc:  # pragma: no cover - requires local ETABS/COM
            connection["table_errors"][table_name] = str(exc)
            classification = classify_semantic_source_table(
                source_family=source_family,
                table_name=table_name,
                fetch_status="FETCH_ERROR",
                rows=[],
                columns=[],
                notes=[str(exc)],
            )
        classifications.append(classification)
    return classifications, connection


def _write_reports(out: Path, *, connection: dict[str, Any], classifications: list[dict[str, Any]], generated_at: str, target_family: str) -> None:
    summary = build_semantic_source_review_report(
        classifications=classifications,
        generated_at=generated_at,
        live_etabs_requested=bool(connection.get("live_etabs_requested")),
        live_etabs_connected=bool(connection.get("live_etabs_connected")),
        etabs_version=connection.get("etabs_version"),
        model_path=connection.get("model_path"),
        target_family=target_family,
    )
    reports = {
        "connection_report.json": connection,
        "semantic_source_review_summary.json": summary,
        "semantic_source_inventory_report.json": build_semantic_source_inventory_report(classifications),
        "combo_semantic_review_report.json": build_combo_semantic_review(classifications),
        "force_result_semantic_review_report.json": build_force_result_semantic_review(classifications),
        "drift_story_semantic_review_report.json": build_drift_story_semantic_review(classifications),
        "design_output_semantic_review_report.json": build_design_output_semantic_review(classifications),
        "rebar_role_semantic_review_report.json": build_rebar_role_semantic_review(classifications),
        "semantic_source_sample_rows.json": build_semantic_source_sample_rows(classifications),
    }
    scan_payload = scan_semantic_outputs_for_forbidden_verdicts(reports)
    reports["forbidden_verdict_scan_report.json"] = scan_payload
    for name, payload in reports.items():
        _write_json(out / name, payload)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="C13.4-P0 live semantic source review")
    parser.add_argument("--out", required=True)
    parser.add_argument("--live-etabs", action="store_true")
    parser.add_argument("--max-rows-per-table", type=int, default=25)
    parser.add_argument("--target-family", choices=["all", *TARGET_FAMILIES], default="all")
    args = parser.parse_args(argv)
    out = Path(args.out)
    generated_at = datetime.now(timezone.utc).isoformat()

    if not args.live_etabs:
        connection = {
            "sprint": SPRINT,
            "generated_at": generated_at,
            "live_etabs_requested": False,
            "live_etabs_connected": False,
            "connection_status": "NO_LIVE_REQUESTED",
            "target_family": args.target_family,
            "max_rows_per_table": args.max_rows_per_table,
            **_guardrails(),
        }
        _write_json(out / "connection_report.json", connection)
        return 2

    classifications, connection = _review_live_sources(args.target_family, args.max_rows_per_table)
    connection.update({
        "sprint": SPRINT,
        "generated_at": generated_at,
        "live_etabs_requested": True,
        "target_family": args.target_family,
        "max_rows_per_table": args.max_rows_per_table,
        **_guardrails(),
    })
    _write_reports(out, connection=connection, classifications=classifications, generated_at=generated_at, target_family=args.target_family)
    return 0 if connection.get("live_etabs_connected") else 3


if __name__ == "__main__":
    raise SystemExit(main())
