#!/usr/bin/env python
"""C8/C8.1 manual/live FeatureResolver smoke.

Manual and opt-in. Fixture mode is CI-safe and does not require ETABS. Live mode
attaches to an already open ETABS model only when --live-etabs is provided. This
script never runs checks, never emits CheckResult JSON, never emits OK/FAIL
verdicts, never modifies the ETABS model, and never starts a design run.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tbdy_engine.contracts.loader import load_contracts
from tbdy_engine.features.resolver.live_smoke import (
    C8LiveFeatureResolverSmoke,
    UnitContext,
    decode_etabs_present_units,
    direct_api_geometry_from_payload,
    table_extraction_debug_from_payload,
    tables_from_probe_report,
    unit_context_from_payload,
    write_json_payload,
    write_smoke_outputs,
)
from tbdy_engine.providers.table_registry import TableRegistry

FULL_ROW_CAPTURE_TABLES: frozenset[str] = frozenset({
    "Frame Assignments - Summary",
    "Frame Section Property Definitions - Concrete Rectangular",
    "Modal Participating Mass Ratios",
    "Story Drifts",
    "Story Max Over Avg Drifts",
    "Base Reactions",
})

OUTPUT_DEPENDENT_DISPLAY_TABLES: frozenset[str] = frozenset({
    "Story Drifts",
    "Story Max Over Avg Drifts",
    "Base Reactions",
    "Concrete Beam Design Summary",
    "Concrete Beam Design Summary - TS 500-2000(R2018)",
})


def _live_table_max_rows(actual_table_name: str, default_max_rows: int) -> int:
    """Return live smoke row-capture limit for tables that need aggregation/selection.

    Geometry/identity smoke output may stay lightweight, but modal/story/base
    tables must not be truncated to the first UI sample rows: C11.1 modal
    aggregation and C11.1.4 story/base selectors require all rows to avoid
    false FAIL/PARTIAL outcomes from intermediate rows or absent target-story
    rows.
    """
    return 100000 if actual_table_name in FULL_ROW_CAPTURE_TABLES else default_max_rows


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_unavailable(out_dir: Path, message: str) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    diagnostic = {
        "metadata": {
            "sprint": "C8_1_LIVE_IDENTITY_GEOMETRY_UNIT_FIX",
            "check_engine_executed": False,
            "check_result_emitted": False,
            "live_verdict_emitted": False,
        },
        "diagnostics": [{"severity": "WARNING", "code": "LIVE_ETABS_UNAVAILABLE", "message": message}],
    }
    empty = []
    for name in (
        "feature_snapshot.json",
        "feature_resolution_report.json",
        "evidence_report.json",
        "missing_features_report.json",
        "coverage_preview.json",
        "legacy_alias_crosswalk_report.json",
        "identity_resolution_report.json",
        "geometry_resolution_report.json",
        "unit_context_report.json",
        "unit_basis_report.json",
        "unit_normalization_report.json",
        "geometry_source_table_debug_report.json",
        "live_failure_delta_report.json",
        "c8_1_boundary_report.json",
    ):
        payload = diagnostic if name == "feature_snapshot.json" else empty
        write_json_payload(out_dir / name, payload)
    print(message)
    return 0


def _unit_context_from_live_sapmodel(sap_model: Any) -> UnitContext:
    diagnostics: list[dict[str, Any]] = []
    raw = None
    database_units = None
    try:  # pragma: no cover - requires local Windows/ETABS
        if hasattr(sap_model, "GetPresentUnits_2"):
            raw = sap_model.GetPresentUnits_2()
        elif hasattr(sap_model, "GetPresentUnits"):
            raw = sap_model.GetPresentUnits()
        if hasattr(sap_model, "GetDatabaseUnits"):
            database_units = sap_model.GetDatabaseUnits()
    except Exception as exc:  # pragma: no cover
        diagnostics.append({"severity": "WARNING", "code": "UNIT_QUERY_FAILED", "message": f"Could not query ETABS present/database units: {exc}"})
    decoded = decode_etabs_present_units(raw, source="live_etabs_present_units")
    diagnostics.extend(decoded.get("diagnostics") or [])
    return UnitContext(
        source=str(decoded.get("source") or "unknown"),
        etabs_present_units_raw=raw,
        etabs_database_units=database_units,
        force_unit=decoded.get("force_unit"),
        length_unit=decoded.get("length_unit"),
        temperature_unit=decoded.get("temperature_unit"),
        etabs_present_units_return_code=decoded.get("etabs_present_units_return_code"),
        unit_query_succeeded=bool(decoded.get("unit_query_succeeded")),
        unit_query_status=str(decoded.get("unit_query_status") or "MISSING"),
        unit_basis_confidence=str(decoded.get("unit_basis_confidence") or "unknown"),
        diagnostics=tuple(diagnostics),
    )



def _collect_direct_api_geometry(sap_model: Any, *, target_component: str | None, target_label: str | None, target_story: str | None, target_section: str | None) -> dict[str, Any]:
    """Read-only direct ETABS API geometry fallback payload.

    All calls are opt-in live/manual only. This function never mutates model state
    and never executes checks/design.
    """
    report: dict[str, Any] = {"frame": {}, "section": {}, "points": {}, "diagnostics": []}
    frame_name = target_component
    try:  # pragma: no cover - requires local ETABS
        if not frame_name and target_label and target_story and hasattr(sap_model, "FrameObj"):
            response = sap_model.FrameObj.GetNameFromLabel(target_label, target_story)
            if isinstance(response, (list, tuple)) and response:
                frame_name = str(response[0])
            elif isinstance(response, str):
                frame_name = response
        if frame_name and hasattr(sap_model, "FrameObj"):
            section_response = sap_model.FrameObj.GetSection(frame_name)
            section_name = target_section
            ret = None
            if isinstance(section_response, (list, tuple)):
                section_name = section_response[0] if section_response else section_name
                ret = section_response[-1] if section_response and isinstance(section_response[-1], int) else None
            elif isinstance(section_response, str):
                section_name = section_response
            label = target_label
            story = target_story
            if hasattr(sap_model.FrameObj, "GetLabelFromName"):
                label_response = sap_model.FrameObj.GetLabelFromName(frame_name)
                if isinstance(label_response, (list, tuple)) and len(label_response) >= 2:
                    label, story = label_response[0], label_response[1]
            points = []
            point_ret = None
            if hasattr(sap_model.FrameObj, "GetPoints"):
                point_response = sap_model.FrameObj.GetPoints(frame_name)
                if isinstance(point_response, (list, tuple)):
                    points = [str(x) for x in point_response[:2]]
                    point_ret = point_response[-1] if isinstance(point_response[-1], int) else None
            report["frame"] = {"object_name": frame_name, "label": label, "story": story, "section": section_name, "points": points, "get_section_return_code": ret, "get_points_return_code": point_ret}
            if section_name and hasattr(sap_model, "PropFrame"):
                sec_raw = None
                api_call = None
                if hasattr(sap_model.PropFrame, "GetRectangle"):
                    api_call = "PropFrame.GetRectangle"
                    sec_raw = sap_model.PropFrame.GetRectangle(section_name)
                elif hasattr(sap_model.PropFrame, "GetSectProps"):
                    api_call = "PropFrame.GetSectProps"
                    sec_raw = sap_model.PropFrame.GetSectProps(section_name)
                if isinstance(sec_raw, (list, tuple)):
                    numeric = [x for x in sec_raw if isinstance(x, (int, float))]
                    # CSI rectangle shape varies; keep best-effort t3/t2 extraction diagnostic.
                    t3 = numeric[0] if len(numeric) >= 1 else None
                    t2 = numeric[1] if len(numeric) >= 2 else None
                    report["section"] = {"api_call": api_call, "section": section_name, "return_code": sec_raw[-1] if sec_raw and isinstance(sec_raw[-1], int) else None, "t3": t3, "t2": t2, "raw_response": sec_raw}
                elif isinstance(sec_raw, dict):
                    report["section"] = {"api_call": api_call, "section": section_name, **sec_raw}
            coordinates = {}
            if points and hasattr(sap_model, "PointObj"):
                for point in points:
                    coord = sap_model.PointObj.GetCoordCartesian(point)
                    if isinstance(coord, (list, tuple)) and len(coord) >= 3:
                        coordinates[point] = {"x": coord[0], "y": coord[1], "z": coord[2], "raw_response": coord}
                report["points"] = {"return_code": 0, "point_names": points, "coordinates": coordinates}
    except Exception as exc:
        report["diagnostics"].append({"severity": "WARNING", "code": "DIRECT_API_GEOMETRY_READ_FAILED", "message": str(exc)})
    return report

def _live_probe_tables_and_units(bundle, max_rows: int, *, target_component: str | None = None, target_label: str | None = None, target_story: str | None = None, target_section: str | None = None, preferred_output_case: str | None = "Crack_SeisY_UpSoil"):
    # comtypes is imported only in this function.  COM signature probing is
    # shared with the story/base debug probe via engine provider code so smoke
    # cannot stop at a return_code=0 response with empty TableData.
    from tools.probe_etabs_table_headers import (
        DEFAULT_TABLE_WHITELIST,
        _table_is_available,
    )
    from tbdy_engine.providers.etabs_display_table_fetcher import fetch_display_table, select_output_for_display
    from tbdy_engine.providers.etabs_display_table_parser import parse_available_tables_result
    try:
        import comtypes.client  # type: ignore[import-not-found]
    except Exception as exc:  # pragma: no cover - requires local Windows/ETABS
        raise RuntimeError(f"ETABS COM/comtypes unavailable; live FeatureResolver smoke not run: {exc}") from exc
    try:  # pragma: no cover - requires local Windows/ETABS
        etabs_object = comtypes.client.GetActiveObject("CSI.ETABS.API.ETABSObject")
        sap_model = etabs_object.SapModel
        unit_context = _unit_context_from_live_sapmodel(sap_model)
        database_tables = sap_model.DatabaseTables
        available = parse_available_tables_result(database_tables.GetAvailableTables())
    except Exception as exc:  # pragma: no cover - requires local Windows/ETABS
        raise RuntimeError(f"Could not attach to an already open ETABS model: {exc}") from exc
    registry = TableRegistry.from_dict(bundle.catalog("table_registry.yaml"))
    parsed_payloads = []
    table_catalog = bundle.catalog("table_registry.yaml").get("tables", {})
    concrete_sources = table_catalog.get("concrete_beam_design_summary", {}).get("provider_sources", {}).get("etabs", [])
    concrete_aliases = list(dict.fromkeys([str(x) for x in concrete_sources] + ["Concrete Beam Design Summary - TS 500-2000(R2018)"]))
    requested_tables = list(dict.fromkeys(list(DEFAULT_TABLE_WHITELIST) + concrete_aliases))
    concrete_available_actual = next((_table_is_available(alias, available) for alias in concrete_aliases if _table_is_available(alias, available)), None)
    raw_debug_payload = {
        "raw_com_tuple_dump": {"tables": []},
        "parser_strategy_report": {"tables": []},
        "display_selection_diagnostics": {"preferred_output_case": preferred_output_case, "tables": {}},
        "concrete_beam_design_summary_availability": {
            "fetch_attempted": True,
            "aliases_attempted": concrete_aliases,
            "actual_table_name": concrete_available_actual,
            "available": bool(concrete_available_actual),
            "preferred_output_case": preferred_output_case,
            "display_selection_attempted": False,
            "display_selection_success": False,
            "display_selection_selected_method": None,
            "display_selection_attempts": [],
        },
    }
    for requested in requested_tables:  # pragma: no cover - requires local Windows/ETABS
        actual = _table_is_available(requested, available)
        if not actual:
            continue
        # C11.1 modal cumulative aggregation and C11.1.4 story/base row
        # selection must see all available rows. The old C8 smoke default of 10
        # sample rows caused modal false FAIL and live story/base false PARTIAL
        # when the target story/output case was outside the first sample rows.
        table_max_rows = _live_table_max_rows(actual, max_rows)
        display_selection = None
        if actual in OUTPUT_DEPENDENT_DISPLAY_TABLES:
            display_selection = select_output_for_display(database_tables, preferred_output_case)
            raw_debug_payload["display_selection_diagnostics"]["tables"][actual] = dict(display_selection)
            if actual in {"Concrete Beam Design Summary", "Concrete Beam Design Summary - TS 500-2000(R2018)"}:
                raw_debug_payload["concrete_beam_design_summary_availability"].update({
                    "display_selection_attempted": bool(display_selection.get("display_selection_attempted")),
                    "display_selection_success": bool(display_selection.get("display_selection_success")),
                    "display_selection_selected_method": display_selection.get("display_selection_selected_method"),
                    "display_selection_attempts": list(display_selection.get("display_selection_attempts") or ()),
                })
        fetched = fetch_display_table(database_tables, actual, max_rows=table_max_rows)
        result = fetched.raw_response
        parsed = fetched.parsed
        table_payload = fetched.header_payload(registry) | {"c11_1_modal_full_row_capture": actual == "Modal Participating Mass Ratios"}
        if display_selection is not None:
            table_payload.update(display_selection)
            raw_diag = dict(table_payload.get("raw_table_diagnostics") or {})
            raw_diag.update(display_selection)
            table_payload["raw_table_diagnostics"] = raw_diag
        if actual in {"Concrete Beam Design Summary", "Concrete Beam Design Summary - TS 500-2000(R2018)"}:
            raw_debug_payload["concrete_beam_design_summary_availability"].update({
                "actual_table_name": actual,
                "available": bool(table_payload.get("rows") or table_payload.get("parsed_rows")),
                "parser_status": (table_payload.get("raw_table_diagnostics") or {}).get("parser_status"),
                "row_count": len(table_payload.get("rows") or table_payload.get("parsed_rows") or ()),
            })
        parsed_payloads.append(table_payload)
        if actual in {"Frame Assignments - Summary", "Frame Section Property Definitions - Concrete Rectangular", "Concrete Beam Design Summary - TS 500-2000(R2018)", "Modal Participating Mass Ratios", "Story Drifts", "Story Max Over Avg Drifts", "Base Reactions"}:
            from tbdy_engine.features.resolver.live_smoke import raw_com_tuple_dump_for_response, parser_strategy_report_for_response
            raw_debug_payload["raw_com_tuple_dump"]["tables"].append(raw_com_tuple_dump_for_response(result, table_name=actual))
            raw_debug_payload["parser_strategy_report"]["tables"].append(parser_strategy_report_for_response(result, table_name=actual, max_rows=table_max_rows) | {
                "signature_attempts": [dict(item) for item in fetched.signature_attempts],
                "selected_signature": dict(fetched.selected_signature),
                "selected_signature_reason": fetched.selected_signature_reason,
                "display_selection": dict(display_selection) if display_selection is not None else None,
            })
    direct_api = _collect_direct_api_geometry(sap_model, target_component=target_component, target_label=target_label, target_story=target_story, target_section=target_section)
    return tables_from_probe_report(parsed_payloads, bundle), unit_context, direct_api, raw_debug_payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="C8.1 FeatureResolver smoke. No checks; no verdicts.")
    parser.add_argument("--out", default="local_out/c8_1_live_identity_geometry_unit_fix", help="Output directory")
    parser.add_argument("--input", default=None, help="Probe table_headers_report.json fixture/input")
    parser.add_argument("--live-etabs", action="store_true", help="Opt-in: attach to an already open local ETABS model and read display tables")
    parser.add_argument("--max-rows", type=int, default=10, help="Maximum sample rows per live table")
    parser.add_argument("--target-component", default=None, help="Optional real ETABS UniqueName/component target, e.g. 297")
    parser.add_argument("--target-label", default=None, help="Optional real ETABS Label target, e.g. B1")
    parser.add_argument("--target-story", default=None, help="Optional real ETABS Story target, e.g. +14.5")
    parser.add_argument("--target-section", default=None, help="Optional real ETABS DesignSect target, e.g. B40x70")
    parser.add_argument("--preferred-output-case", default="Crack_SeisY_UpSoil", help="Preferred ETABS output case/combination for story/base display-table reads")
    args = parser.parse_args(argv)
    out_dir = Path(args.out)
    bundle = load_contracts()
    try:
        direct_api_geometry = {}
        table_extraction_debug = {}
        if args.live_etabs:
            tables, unit_context, direct_api_geometry, table_extraction_debug = _live_probe_tables_and_units(
                bundle,
                max_rows=max(1, args.max_rows),
                target_component=args.target_component,
                target_label=args.target_label,
                target_story=args.target_story,
                target_section=args.target_section,
                preferred_output_case=args.preferred_output_case,
            )
        elif args.input:
            payload = _load_json(Path(args.input))
            tables = tables_from_probe_report(payload, bundle)
            unit_context = unit_context_from_payload(payload)
            direct_api_geometry = direct_api_geometry_from_payload(payload)
            table_extraction_debug = table_extraction_debug_from_payload(payload)
        else:
            return _write_unavailable(out_dir, "Provide --input fixture or --live-etabs. CI uses fixture mode; live ETABS is manual/local only.")
        resolver = C8LiveFeatureResolverSmoke(
            bundle,
            tables,
            unit_context=unit_context,
            target_component=args.target_component,
            target_label=args.target_label,
            target_story=args.target_story,
            target_section=args.target_section,
            preferred_output_case=args.preferred_output_case,
            direct_api_geometry=direct_api_geometry,
            table_extraction_debug=table_extraction_debug,
        )
        outputs = resolver.build_all()
        write_smoke_outputs(out_dir, outputs)
        print(f"Wrote C8.1 FeatureResolver smoke outputs to {out_dir}")
        return 0
    except Exception as exc:  # unexpected runtime only
        print(f"C8.1 FeatureResolver smoke failed unexpectedly: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
