#!/usr/bin/env python
"""Read-only local ETABS 23.2 probe for VS6-P8A-F0."""
from __future__ import annotations

import argparse
import json
from typing import Any

from tbdy_engine.etabs.safety import read_etabs_unit_snapshot
from tbdy_engine.features.etabs_com_attach import ATTACH_STATUS_ATTACHED, attach_to_running_etabs
from tbdy_engine.providers.etabs_combo_definition_provider import capture_etabs_combo_definitions
from tbdy_engine.providers.etabs_concrete_design_combo_selection_probe import (
    TABLE_CONCRETE_FRAME_DESIGN_LOAD_COMBINATION_DATA,
    probe_concrete_frame_design_combo_selection_table,
)


def _safe(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (tuple, list)):
        return [_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _safe(item) for key, item in value.items()}
    return repr(value)


def _unit_payload(snapshot: Any) -> dict[str, Any]:
    return {key: _safe(value) for key, value in snapshot.as_dict().items()}


def _call_read_only(obj: Any, method_name: str, *args: Any) -> dict[str, Any]:
    try:
        method = getattr(obj, method_name)
    except Exception as exc:
        return {"available": False, "method": method_name, "error": f"{type(exc).__name__}: {exc}"}
    if not callable(method):
        return {"available": False, "method": method_name, "error": "attribute is not callable"}
    try:
        return {"available": True, "method": method_name, "raw": _safe(method(*args))}
    except Exception as exc:
        return {"available": True, "method": method_name, "error": f"{type(exc).__name__}: {exc}"}


def _combo_related_callables(obj: Any) -> list[str]:
    try:
        names = dir(obj)
    except Exception:
        return []
    return sorted(name for name in names if "combo" in name.lower() and not name.lower().startswith(("set", "delete", "add")) and callable(getattr(obj, name, None)))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pid", type=int, default=None)
    parser.add_argument("--frame", action="append", default=[], help="Exact column FrameName/UniqueName for GetDesignSection")
    args = parser.parse_args()
    report: dict[str, Any] = {
        "probe": "VS6-P8A-F0_COLUMN_DESIGN_EVIDENCE",
        "candidate_table_key": TABLE_CONCRETE_FRAME_DESIGN_LOAD_COMBINATION_DATA,
        "mutation_audit": {
            "analysis_run": False, "design_run": False, "combo_selection_mutation": False,
            "unit_mutation": False, "model_save": False, "property_mutation": False,
        },
    }
    attach = attach_to_running_etabs(pid=args.pid, allow_pid_fallback=args.pid is None)
    report["attach"] = attach.as_diagnostic_dict()
    if attach.status != ATTACH_STATUS_ATTACHED or attach.sap_model is None:
        report["gate"] = "ACTUAL_DESIGN_COMBO_SOURCE_NOT_PROVEN"
        print(json.dumps(report, indent=2, sort_keys=True))
        return 2

    sap_model = attach.sap_model
    before = read_etabs_unit_snapshot(sap_model)
    report["present_units_before"] = _unit_payload(before)
    db = getattr(sap_model, "DatabaseTables", None)
    combo_names: tuple[str, ...] = ()
    if db is None:
        report["table_probe"] = {"available": False, "reason": "SapModel.DatabaseTables unavailable"}
    else:
        probe = probe_concrete_frame_design_combo_selection_table(db)
        combo_names = probe.combo_names
        report["table_probe"] = {
            "available": probe.return_code in (None, 0),
            "exact_table_key": probe.table_key,
            "exact_field_keys": list(probe.field_keys),
            "row_count": probe.row_count,
            "row_count_reported": probe.row_count_reported,
            "has_ComboName": probe.combo_name_field_present,
            "combo_type_or_selection_fields": list(probe.combo_type_or_selection_fields),
            "automatic_user_defined_fields": list(probe.automatic_user_defined_fields),
            "selected_signature_name": probe.selected_signature_name,
            "sample_schema_only": True,
            "source_semantics_status": probe.source_semantics_status,
        }
        if combo_names:
            try:
                definitions = capture_etabs_combo_definitions(sap_model.RespCombo, combo_names)
                report["combo_definitions"] = {
                    "available": True,
                    "count": len(definitions),
                    "names": [item.name for item in definitions],
                    "types": {item.name: item.combo_type for item in definitions},
                    "constituent_schema": {
                        item.name: [{"cname_type": term.cname_type, "name": term.name, "scale_factor": term.scale_factor} for term in item.constituents]
                        for item in definitions
                    },
                }
            except Exception as exc:
                report["combo_definitions"] = {"available": False, "error": f"{type(exc).__name__}: {exc}"}

    design_concrete = getattr(sap_model, "DesignConcrete", None)
    if design_concrete is None:
        report["design_concrete"] = {"available": False}
    else:
        report["design_concrete"] = {
            "available": True,
            "combo_related_read_candidates": _combo_related_callables(design_concrete),
            "results_available": _call_read_only(design_concrete, "GetResultsAvailable"),
            "design_sections": [{"frame_name": frame, **_call_read_only(design_concrete, "GetDesignSection", frame)} for frame in args.frame],
        }

    after = read_etabs_unit_snapshot(sap_model)
    report["present_units_after"] = _unit_payload(after)
    report["present_units_unchanged"] = report["present_units_before"] == report["present_units_after"]
    report["source_semantics_status"] = "REQUIRES_SUPERVISOR_REVIEW_OF_LIVE_SCHEMA"
    report["gate"] = "ACTUAL_DESIGN_COMBO_SOURCE_NOT_PROVEN"
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
