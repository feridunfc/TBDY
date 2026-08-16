#!/usr/bin/env python
"""C11.1.4 live story/base ETABS table extraction debug.

Manual/debug only. Import-safe without ETABS/comtypes. It never runs checks,
never emits CheckResult, never emits OK/FAIL, and never mutates the ETABS model.
Temporary display/output selection is transactionally restored and verified.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tbdy_engine.contracts.loader import load_contracts
from tbdy_engine.json_safe import to_jsonable
from tbdy_engine.providers.table_registry import TableRegistry
from tbdy_engine.features.resolver.live_smoke import (
    _norm_key,
    raw_com_tuple_dump_for_response,
    parser_strategy_report_for_response,
)
from tools.probe_etabs_table_headers import _table_is_available
from tbdy_engine.providers.etabs_display_table_fetcher import (
    fetch_display_table,
    fetch_display_table_for_output,
)
from tbdy_engine.providers.etabs_display_table_parser import (
    _table_data_length,
    parse_available_tables_result,
    parse_etabs_display_table_result,
)

TARGET_TABLES: Mapping[str, str] = {
    "story_drifts": "Story Drifts",
    "story_max_over_avg_drifts": "Story Max Over Avg Drifts",
    "base_reactions": "Base Reactions",
}


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(to_jsonable(payload), indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")


def _parser_status(parsed) -> str:
    debug = dict(parsed.debug or {})
    number_records = debug.get("number_records")
    table_data_length = debug.get("table_data_length")
    if parsed.rows:
        return "PARSED_ROWS"
    try:
        records = int(number_records or 0)
    except Exception:
        records = 0
    try:
        data_len = int(table_data_length or 0)
    except Exception:
        data_len = 0
    if records > 0 and data_len == 0:
        return "TABLEDATA_EMPTY_DESPITE_RECORDS"
    if parsed.field_keys and not parsed.rows:
        return "HEADER_ONLY"
    if parsed.fetch_status == "FAILED":
        return "COM_CALL_FAILED"
    if not parsed.field_keys and not parsed.rows:
        return "EMPTY_TABLE"
    return "UNKNOWN_SHAPE"


def build_table_debug(table_alias: str, actual_table_name: str, raw_response: Any, *, target_story: str | None = None, preferred_output_case: str | None = None, max_rows: int = 5, fetched: Any = None, display_selection: Mapping[str, Any] | None = None) -> dict[str, Any]:
    parsed = fetched.parsed if fetched is not None else parse_etabs_display_table_result(raw_response, actual_table_name=actual_table_name, max_rows=max_rows)
    debug = dict(parsed.debug or {})
    status = _parser_status(parsed)
    diagnostics = [dict(item) for item in parsed.diagnostics]
    if status == "TABLEDATA_EMPTY_DESPITE_RECORDS":
        diagnostics.append({
            "severity": "WARNING",
            "code": "ETABS_TABLEDATA_EMPTY_DESPITE_RECORDS",
            "message": "ETABS reported records for this display table but returned empty TableData.",
            "details": {
                "number_records": debug.get("number_records"),
                "table_data_length": debug.get("table_data_length"),
                "expected_flat_length": debug.get("expected_flat_length"),
            },
        })
    if status in {"TABLEDATA_EMPTY_DESPITE_RECORDS", "HEADER_ONLY"}:
        diagnostics.append({
            "severity": "INFO",
            "code": "DISPLAY_SELECTION_REVIEW",
            "message": "Review ETABS display selection/options if row data is unavailable; no model mutation was attempted.",
            "details": {
                "target_story": target_story,
                "preferred_output_case": preferred_output_case,
                "mutated_model": False,
            },
        })
    raw_dump = raw_com_tuple_dump_for_response(raw_response, table_name=actual_table_name)
    strategy = parser_strategy_report_for_response(raw_response, table_name=actual_table_name, max_rows=max_rows)
    signature_attempts = [dict(item) for item in getattr(fetched, "signature_attempts", ())] if fetched is not None else []
    selected_signature = dict(getattr(fetched, "selected_signature", {}) or {}) if fetched is not None else {}
    selected_signature_reason = getattr(fetched, "selected_signature_reason", None) if fetched is not None else None
    capture_status = getattr(getattr(fetched, "capture_status", None), "value", None) if fetched is not None else None
    state_diagnostics = [dict(item) for item in getattr(fetched, "state_diagnostics", ())] if fetched is not None else []
    display_selection = dict(display_selection or {})
    return {
        "actual_table_name": actual_table_name,
        "table_alias": table_alias,
        "headers": list(parsed.field_keys),
        "normalized_headers": [_norm_key(h) for h in parsed.field_keys],
        "row_count": len(parsed.rows),
        "sample_rows": [dict(row) for row in parsed.rows[:max_rows]],
        "raw_com_response_shape": raw_dump,
        "return_code": parsed.return_code,
        "number_fields": debug.get("number_fields"),
        "number_fields_detected": debug.get("number_fields_detected"),
        "number_fields_source": debug.get("number_fields_source"),
        "header_count": len(parsed.field_keys),
        "number_records": debug.get("number_records"),
        "table_data_length": debug.get("table_data_length", _table_data_length(raw_response)),
        "expected_flat_length": debug.get("expected_flat_length"),
        "parser_status": status,
        "capture_status": capture_status,
        "field_keys_included": list(parsed.field_keys),
        "table_data_sample": [],
        "parser_strategy_report": strategy | {
            "signature_attempts": signature_attempts,
            "selected_signature": selected_signature,
            "selected_signature_reason": selected_signature_reason,
        },
        "signature_attempts": signature_attempts,
        "selected_signature": selected_signature,
        "selected_signature_reason": selected_signature_reason,
        "state_diagnostics": state_diagnostics,
        "preferred_output_case": preferred_output_case,
        "preferred_output_kind_detected": display_selection.get("preferred_output_kind_detected", "unknown"),
        "attempted_case_fallback": bool(display_selection.get("attempted_case_fallback")),
        "skipped_case_selection_because_combo_succeeded": bool(display_selection.get("skipped_case_selection_because_combo_succeeded")),
        "display_selection_attempted": bool(display_selection.get("display_selection_attempted")),
        "display_selection_attempts": list(display_selection.get("display_selection_attempts") or ()),
        "display_selection_selected_method": display_selection.get("display_selection_selected_method"),
        "display_selection_success": bool(display_selection.get("display_selection_success")),
        "fetch_after_display_selection": bool(display_selection.get("fetch_after_display_selection")),
        "diagnostics": diagnostics,
    }


def _attach_live_etabs_database_tables():  # pragma: no cover - requires Windows/ETABS
    try:
        import comtypes.client  # type: ignore[import-not-found]
    except Exception as exc:
        raise RuntimeError(f"ETABS COM/comtypes unavailable: {exc}") from exc
    etabs_object = comtypes.client.GetActiveObject("CSI.ETABS.API.ETABSObject")
    return etabs_object.SapModel.DatabaseTables


def run_live_probe(out_dir: Path, *, target_story: str | None, preferred_output_case: str | None) -> dict[str, Any]:  # pragma: no cover - requires Windows/ETABS
    bundle = load_contracts()
    registry = TableRegistry.from_dict(bundle.catalog("table_registry.yaml"))
    database_tables = _attach_live_etabs_database_tables()
    available = parse_available_tables_result(database_tables.GetAvailableTables())
    reports: dict[str, Any] = {}
    diff_dir = Path("local_out/c11_1_4_old_vs_new_fetcher_diff")
    diff_dir.mkdir(parents=True, exist_ok=True)
    for alias, requested in TARGET_TABLES.items():
        actual = _table_is_available(requested, available) or requested
        if preferred_output_case:
            fetched = fetch_display_table_for_output(
                database_tables,
                actual,
                preferred_output_case=preferred_output_case,
                max_rows=None,
            )
            display_selection = dict(fetched.display_selection)
        else:
            fetched = fetch_display_table(database_tables, actual, max_rows=None)
            display_selection = {
                "display_selection_attempted": False,
                "display_selection_success": False,
                "fetch_after_display_selection": False,
                "diagnostic": "preferred_output_case_missing_no_selection_mutation",
            }
        raw = fetched.raw_response
        report = build_table_debug(alias, actual, raw, target_story=target_story, preferred_output_case=preferred_output_case, max_rows=5, fetched=fetched, display_selection=display_selection)
        reports[alias] = report
        _write_json(out_dir / f"{alias}_raw_debug.json", report)
        _write_json(diff_dir / f"new_fetcher_{alias}.json", report)
    name_map = {
        "story_drifts": "story_drifts_raw_debug.json",
        "story_max_over_avg_drifts": "story_max_over_avg_drifts_raw_debug.json",
        "base_reactions": "base_reactions_raw_debug.json",
    }
    for alias, filename in name_map.items():
        _write_json(out_dir / filename, reports[alias])
    summary = {
        "metadata": {
            "sprint": "C11_1_4_LIVE_STORY_BASE_TABLE_EXTRACTION_DEBUG_AND_SELECTOR_FIX",
            "check_engine_executed": False,
            "check_result_emitted": False,
            "ok_fail_emitted": False,
            "mutated_etabs_model": False,
            "temporary_output_selection_restored": True,
        },
        "target_story": target_story,
        "preferred_output_case": preferred_output_case,
        "tables": {alias: {"actual_table_name": r["actual_table_name"], "row_count": r["row_count"], "parser_status": r["parser_status"], "capture_status": r["capture_status"], "number_records": r["number_records"], "table_data_length": r["table_data_length"]} for alias, r in reports.items()},
    }
    _write_json(out_dir / "story_base_table_probe_summary.json", summary)
    diff_summary = {
        "tables": {},
        "note": "Run tools/probe_live_story_base_tables_legacy_oracle.py first to populate legacy_oracle_*.json, then this script to populate new_fetcher_*.json.",
    }
    for alias, report in reports.items():
        legacy_path = diff_dir / f"legacy_oracle_{alias}.json"
        legacy = {}
        if legacy_path.exists():
            try:
                legacy = json.loads(legacy_path.read_text(encoding="utf-8"))
            except Exception:
                legacy = {"read_error": str(legacy_path)}
        diff_summary["tables"][alias] = {
            "legacy_parser_status": legacy.get("parser_status"),
            "new_parser_status": report.get("parser_status"),
            "legacy_row_count": legacy.get("row_count"),
            "new_row_count": report.get("row_count"),
            "legacy_table_data_length": legacy.get("table_data_length"),
            "new_table_data_length": report.get("table_data_length"),
            "legacy_selected_signature": (legacy.get("selected_signature") or {}).get("signature_name"),
            "new_selected_signature": (report.get("selected_signature") or {}).get("signature_name"),
            "legacy_parse_strategy": ((legacy.get("selected_signature") or {}).get("parse_strategy_used") or legacy.get("selected_signature_reason")),
            "new_parse_strategy": ((report.get("selected_signature") or {}).get("parse_strategy_used") or report.get("selected_signature_reason")),
        }
    _write_json(diff_dir / "old_vs_new_fetcher_diff_summary.json", diff_summary)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="C11.1.4 live story/base display-table extraction debug. No checks; no verdicts.")
    parser.add_argument("--out", default="local_out/c11_1_4_story_base_table_debug")
    parser.add_argument("--target-story", default=None)
    parser.add_argument("--preferred-output-case", default="Crack_SeisY_UpSoil")
    args = parser.parse_args(argv)
    try:
        summary = run_live_probe(Path(args.out), target_story=args.target_story, preferred_output_case=args.preferred_output_case)
        print(f"Wrote C11.1.4 story/base table debug outputs to {args.out}")
        print(json.dumps(to_jsonable(summary["tables"]), indent=2, ensure_ascii=False))
        return 0
    except Exception as exc:
        out = Path(args.out)
        failure = {
            "metadata": {"check_engine_executed": False, "check_result_emitted": False, "ok_fail_emitted": False},
            "error_type": type(exc).__name__,
            "message": str(exc),
        }
        _write_json(out / "story_base_table_probe_summary.json", failure)
        print(f"C11.1.4 story/base table probe failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
