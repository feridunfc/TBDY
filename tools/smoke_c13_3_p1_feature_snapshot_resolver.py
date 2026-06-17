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

from tbdy_engine.features.resolver_feature_snapshot import (  # noqa: E402
    SOURCE_FAMILIES,
    blocked_check_guardrail_report,
    build_feature_snapshot_from_source_rows,
    readiness_projection_report,
    source_family_projection_report,
    summarize_snapshot,
    unit_normalization_report,
)
from tbdy_engine.features.source_feature_snapshot_builder import INTERNAL_SOURCE_TABLE_KEY  # noqa: E402
from tbdy_engine.providers.etabs_display_table_fetcher import fetch_display_table  # noqa: E402

SPRINT = "C13.3-P1"
LIVE_TABLES = {
    "material_properties": [
        "Material Properties - Basic Mechanical Properties",
        "Material Properties - Concrete Data",
        "Material Properties - Rebar Data",
    ],
    "story_definitions": ["Story Definitions", "Tower and Base Story Definitions", "Tower and Base Story Definition"],
    "pier_section_properties": ["Pier Section Properties"],
}


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _json_safe(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return repr(value)


def _fetch_live_table(database_tables: Any, table_name: str, max_rows: int) -> tuple[list[dict[str, Any]], list[str], dict[str, Any]]:
    """Fetch one live ETABS display table through the shared display-table fetcher."""
    result = fetch_display_table(database_tables, table_name, max_rows=max_rows)
    parsed = result.parsed
    rows = [dict(row) for row in parsed.rows[:max_rows]]
    diagnostics = {
        "actual_table_name": parsed.actual_table_name,
        "parsed_fetch_status": parsed.fetch_status,
        "row_count_reported": parsed.row_count_reported,
        "return_code": parsed.return_code,
        "selected_signature": _json_safe(dict(result.selected_signature or {})),
        "selected_signature_reason": result.selected_signature_reason,
        "signature_attempts": _json_safe([dict(item) for item in result.signature_attempts]),
        "parser_debug": _json_safe(dict(parsed.debug or {})),
        "parser_diagnostics": _json_safe(list(parsed.diagnostics)),
    }
    return rows, list(parsed.field_keys), diagnostics


def _blank_debug_table(table_name: str, source_family: str) -> dict[str, Any]:
    return {
        "table_name": table_name,
        "source_family": source_family,
        "fetch_status": "NOT_FETCHED",
        "row_count": 0,
        "columns": [],
        "sample_rows": [],
        "projected_feature_count": 0,
        "projection_status": "NOT_PROJECTED",
        "projection_blocker": None,
        "selected_signature": {},
        "selected_signature_reason": None,
        "signature_attempts": [],
        "parser_debug": {},
        "parser_diagnostics": [],
    }


def _empty_projection_debug(generated_at: str) -> dict[str, Any]:
    return {
        "sprint": SPRINT,
        "generated_at": generated_at,
        "source_tables": [],
        "check_unlock_allowed": False,
        "safe_to_implement_checks_now": False,
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
        database_tables = sap_model.DatabaseTables
        try:
            model_path = sap_model.GetModelFilename()
        except Exception:
            model_path = None
        try:
            version_raw = sap_model.GetVersion()
            etabs_version = version_raw[0] if isinstance(version_raw, (list, tuple)) else version_raw
        except Exception:
            etabs_version = None
        return database_tables, {
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


def _collect_live_rows(
    target_family: str,
    max_rows_per_table: int,
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any], list[dict[str, Any]]]:
    families = SOURCE_FAMILIES if target_family == "all" else (target_family,)
    rows: dict[str, list[dict[str, Any]]] = {family: [] for family in families}
    debug_tables: list[dict[str, Any]] = []
    database_tables, connection_report = _connect_to_etabs()
    if database_tables is None:
        return rows, connection_report, debug_tables

    for family in families:
        for table_name in LIVE_TABLES.get(family, []):
            connection_report["tables_attempted"].append(table_name)
            table_debug = _blank_debug_table(table_name, family)
            try:
                fetched, columns, fetch_diagnostics = _fetch_live_table(database_tables, table_name, max_rows_per_table)
                stamped = [dict(row, **{INTERNAL_SOURCE_TABLE_KEY: table_name}) for row in fetched[:max_rows_per_table]]
                rows[family].extend(stamped)
                table_debug.update({
                    "fetch_status": "FETCHED",
                    "row_count": len(stamped),
                    "columns": columns or (list(stamped[0].keys()) if stamped else []),
                    "sample_rows": [{key: value for key, value in row.items() if key != INTERNAL_SOURCE_TABLE_KEY} for row in stamped],
                    "selected_signature": fetch_diagnostics.get("selected_signature", {}),
                    "selected_signature_reason": fetch_diagnostics.get("selected_signature_reason"),
                    "signature_attempts": fetch_diagnostics.get("signature_attempts", []),
                    "parser_debug": fetch_diagnostics.get("parser_debug", {}),
                    "parser_diagnostics": fetch_diagnostics.get("parser_diagnostics", []),
                    "fetch_diagnostics": fetch_diagnostics,
                })
            except Exception as exc:  # pragma: no cover - requires local ETABS/COM
                connection_report["table_errors"][table_name] = str(exc)
                table_debug.update({
                    "fetch_status": "FETCH_ERROR",
                    "projection_blocker": str(exc),
                    "parser_diagnostics": [{"severity": "ERROR", "message": str(exc)}],
                })
            debug_tables.append(table_debug)
    return rows, connection_report, debug_tables


def source_table_projection_debug_report(
    *,
    generated_at: str,
    debug_tables: list[dict[str, Any]],
    snapshot: dict[str, Any],
) -> dict[str, Any]:
    for table in debug_tables:
        table_name = table["table_name"]
        family = table["source_family"]
        count = sum(
            1
            for record in snapshot.get("feature_records", [])
            if record.get("source_family") == family and table_name in record.get("source_tables", [])
        )
        table["projected_feature_count"] = count
        if count > 0:
            table["projection_status"] = "PROJECTED"
            table["projection_blocker"] = None
        elif table.get("fetch_status") == "FETCHED" and table.get("row_count", 0) > 0:
            table["projection_status"] = "ZERO_PROJECTED_FROM_FETCHED_ROWS"
            table["projection_blocker"] = "source rows were fetched but no known C13.3-P1 feature aliases matched"
        elif table.get("fetch_status") == "FETCHED":
            table["projection_status"] = "NO_SOURCE_ROWS"
            table["projection_blocker"] = "no source rows after shared display table fetcher attempts"
    return {
        "sprint": SPRINT,
        "generated_at": generated_at,
        "source_tables": debug_tables,
        "check_unlock_allowed": False,
        "safe_to_implement_checks_now": False,
    }


def _write_all_reports(
    out: Path,
    *,
    connection_report: dict[str, Any],
    snapshot: dict[str, Any],
    source_debug_report: dict[str, Any],
) -> None:
    _write_json(out / "connection_report.json", connection_report)
    _write_json(out / "feature_snapshot.json", snapshot)
    _write_json(out / "feature_snapshot_summary.json", summarize_snapshot(snapshot))
    _write_json(out / "unit_normalization_report.json", unit_normalization_report(snapshot))
    _write_json(out / "readiness_projection_report.json", readiness_projection_report(snapshot))
    _write_json(out / "blocked_check_guardrail_report.json", blocked_check_guardrail_report(snapshot))
    _write_json(out / "source_family_projection_report.json", source_family_projection_report(snapshot))
    _write_json(out / "source_table_projection_debug_report.json", source_debug_report)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="C13.3-P1 FeatureSnapshot resolver integration smoke")
    parser.add_argument("--out", required=True)
    parser.add_argument("--live-etabs", action="store_true")
    parser.add_argument("--max-rows-per-table", type=int, default=25)
    parser.add_argument(
        "--target-family",
        choices=["all", "material_properties", "story_definitions", "pier_section_properties"],
        default="all",
    )
    args = parser.parse_args(argv)

    out = Path(args.out)
    generated_at = datetime.now(timezone.utc).isoformat()

    if not args.live_etabs:
        connection_report = {
            "sprint": SPRINT,
            "generated_at": generated_at,
            "live_etabs_requested": False,
            "live_etabs_connected": False,
            "connection_status": "NO_LIVE_REQUESTED",
            "feature_values_faked": False,
            "check_unlock_allowed": False,
            "safe_to_implement_checks_now": False,
            "target_family": args.target_family,
            "max_rows_per_table": args.max_rows_per_table,
        }
        snapshot = build_feature_snapshot_from_source_rows(
            {family: [] for family in SOURCE_FAMILIES},
            live_etabs_connected=False,
            target_family=args.target_family,
            generated_at=generated_at,
        )
        _write_all_reports(
            out,
            connection_report=connection_report,
            snapshot=snapshot,
            source_debug_report=_empty_projection_debug(generated_at),
        )
        return 2

    rows, connection_report, debug_tables = _collect_live_rows(args.target_family, args.max_rows_per_table)
    connection_report.update({
        "sprint": SPRINT,
        "generated_at": generated_at,
        "live_etabs_requested": True,
        "feature_values_faked": False,
        "check_unlock_allowed": False,
        "safe_to_implement_checks_now": False,
        "target_family": args.target_family,
        "max_rows_per_table": args.max_rows_per_table,
    })
    snapshot = build_feature_snapshot_from_source_rows(
        rows,
        live_etabs_connected=bool(connection_report.get("live_etabs_connected")),
        model_path=connection_report.get("model_path"),
        etabs_version=connection_report.get("etabs_version"),
        target_family=args.target_family,
        generated_at=generated_at,
    )
    source_debug_report = source_table_projection_debug_report(
        generated_at=generated_at,
        debug_tables=debug_tables,
        snapshot=snapshot,
    )
    _write_all_reports(
        out,
        connection_report=connection_report,
        snapshot=snapshot,
        source_debug_report=source_debug_report,
    )
    return 0 if connection_report.get("live_etabs_connected") else 3


if __name__ == "__main__":
    raise SystemExit(main())
