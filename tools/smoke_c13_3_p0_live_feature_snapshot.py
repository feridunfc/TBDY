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

from tbdy_engine.features.source_feature_snapshot_builder import (  # noqa: E402
    SOURCE_FAMILIES,
    blocked_check_guardrail_report,
    build_c13_3_p0_feature_snapshot,
    readiness_projection_report,
    summarize_snapshot,
    unit_normalization_report,
)

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


def _parse_table_result(result: Any, max_rows: int) -> list[dict[str, Any]]:
    if not isinstance(result, tuple):
        return []
    fields = None
    table_data = None
    for item in result:
        if isinstance(item, (list, tuple)) and item and all(isinstance(value, str) for value in item):
            if fields is None or len(item) > len(fields):
                fields = list(item)
        elif isinstance(item, (list, tuple)) and item:
            table_data = list(item)
    if not fields or not table_data:
        return []
    width = len(fields)
    rows = []
    flat = list(table_data)
    for offset in range(0, min(len(flat), width * max_rows), width):
        chunk = flat[offset : offset + width]
        if len(chunk) == width:
            rows.append(dict(zip(fields, chunk)))
    return rows


def _fetch_live_table(database_tables: Any, table_name: str, max_rows: int) -> list[dict[str, Any]]:
    try:
        result = database_tables.GetTableForDisplayArray(table_name, [], "", 0, [], 0, [])
    except TypeError:
        result = database_tables.GetTableForDisplayArray(table_name, "", [])
    return _parse_table_result(result, max_rows)


def _collect_live_rows(target_family: str, max_rows_per_table: int) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    families = SOURCE_FAMILIES if target_family == "all" else (target_family,)
    rows: dict[str, list[dict[str, Any]]] = {family: [] for family in families}
    diagnostics: dict[str, Any] = {"tables_attempted": [], "table_errors": {}}
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
            etabs_version = sap_model.GetVersion()[0]
        except Exception:
            etabs_version = None
    except Exception as exc:  # pragma: no cover - requires local ETABS/COM
        return rows, {
            "live_etabs_connected": False,
            "connection_status": "LIVE_CONNECTION_ERROR",
            "diagnostic": str(exc),
            "model_path": None,
            "etabs_version": None,
            **diagnostics,
        }

    for family in families:
        for table_name in LIVE_TABLES.get(family, []):
            diagnostics["tables_attempted"].append(table_name)
            try:
                fetched = _fetch_live_table(database_tables, table_name, max_rows_per_table)
                rows[family].extend(fetched[:max_rows_per_table])
            except Exception as exc:  # pragma: no cover - requires local ETABS/COM
                diagnostics["table_errors"][table_name] = str(exc)

    return rows, {
        "live_etabs_connected": True,
        "connection_status": "LIVE_CONNECTED",
        "model_path": model_path,
        "etabs_version": etabs_version,
        **diagnostics,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="C13.3-P0 live FeatureSnapshot proof smoke")
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
            "sprint": "C13.3-P0",
            "generated_at": generated_at,
            "live_etabs_requested": False,
            "live_etabs_connected": False,
            "connection_status": "NO_LIVE_REQUESTED",
            "feature_values_faked": False,
            "check_unlock_allowed": False,
            "safe_to_implement_checks_now": False,
        }
        snapshot = build_c13_3_p0_feature_snapshot(
            {family: [] for family in SOURCE_FAMILIES},
            live_etabs_connected=False,
            target_family=args.target_family,
            generated_at=generated_at,
        )
        _write_json(out / "connection_report.json", connection_report)
        _write_json(out / "feature_snapshot.json", snapshot)
        _write_json(out / "feature_snapshot_summary.json", summarize_snapshot(snapshot))
        _write_json(out / "unit_normalization_report.json", unit_normalization_report(snapshot))
        _write_json(out / "readiness_projection_report.json", readiness_projection_report(snapshot))
        _write_json(out / "blocked_check_guardrail_report.json", blocked_check_guardrail_report(snapshot))
        return 2

    rows, connection_report = _collect_live_rows(args.target_family, args.max_rows_per_table)
    connection_report.update(
        {
            "sprint": "C13.3-P0",
            "generated_at": generated_at,
            "live_etabs_requested": True,
            "feature_values_faked": False,
            "check_unlock_allowed": False,
            "safe_to_implement_checks_now": False,
            "max_rows_per_table": args.max_rows_per_table,
            "target_family": args.target_family,
        }
    )
    snapshot = build_c13_3_p0_feature_snapshot(
        rows,
        live_etabs_connected=bool(connection_report.get("live_etabs_connected")),
        model_path=connection_report.get("model_path"),
        etabs_version=connection_report.get("etabs_version"),
        target_family=args.target_family,
        generated_at=generated_at,
    )
    _write_json(out / "connection_report.json", connection_report)
    _write_json(out / "feature_snapshot.json", snapshot)
    _write_json(out / "feature_snapshot_summary.json", summarize_snapshot(snapshot))
    _write_json(out / "unit_normalization_report.json", unit_normalization_report(snapshot))
    _write_json(out / "readiness_projection_report.json", readiness_projection_report(snapshot))
    _write_json(out / "blocked_check_guardrail_report.json", blocked_check_guardrail_report(snapshot))
    return 0 if connection_report.get("live_etabs_connected") else 3


if __name__ == "__main__":
    raise SystemExit(main())
