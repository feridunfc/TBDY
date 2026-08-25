#!/usr/bin/env python
"""Read-only ETABS source discovery for TS500 column slenderness promotion.

This probe is intentionally factual. It does not promote ETABS clear-length
candidates to TS500 ``ln``, classify sway, calculate effective length, magnify
moments, select reinforcement, or emit a compliance verdict.

It inspects the selected column's strict-topology evidence, endpoint restraint
API response, and a bounded set of ETABS display-table candidates that may
support later source-bound promotion of:

* TS500 7.6.2.2 free length between lateral supports; and
* TS500 7.6.2.1 sway-prevented classification.

For sway-source discovery, FULL table capture is preserved only as a bounded
projection: rows matching the selected column story are emitted for story
result tables, and the small Load Case Definitions - Summary table is emitted
in full. No ETABS quantity is interpreted as Delta_i, V_fi or sum(N_di) here.

Safety boundary: no analysis/design run, no model save, no property mutation,
no present-unit mutation. Result-table selection is not changed by this probe.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tbdy_engine.etabs.safety import read_session_identity
from tbdy_engine.features.etabs_com_attach import ATTACH_STATUS_ATTACHED, attach_to_running_etabs
from tbdy_engine.integration.live_beam_geometry_f0 import model_fingerprint_from_path
from tbdy_engine.json_safe import to_jsonable
from tbdy_engine.providers.etabs_display_table_fetcher import fetch_display_table
from tbdy_engine.providers.etabs_strict_column_topology_provider import (
    capture_etabs_strict_column_topology,
)


SUPPORT_SOURCE_TABLE_CANDIDATES: tuple[str, ...] = (
    "Joint Assignments - Restraints",
    "Point Assignments - Restraints",
    "Floor Object Connectivity",
    "Area Object Connectivity",
    "Area Assignments - Diaphragms",
)

SWAY_SOURCE_TABLE_CANDIDATES: tuple[str, ...] = (
    "Story Definitions",
    "Story Drifts",
    "Story Forces",
    "Story Stiffness",
    "Story Max Over Avg Drifts",
    "Load Case Definitions - Summary",
)

SOURCE_TABLE_CANDIDATES = tuple(dict.fromkeys((*SUPPORT_SOURCE_TABLE_CANDIDATES, *SWAY_SOURCE_TABLE_CANDIDATES)))

SAFETY = {
    "analysis_run": False,
    "design_run": False,
    "model_save": False,
    "model_or_property_mutation": False,
    "present_units_set": False,
    "result_output_selection_changed": False,
}


def _sample_rows(rows: Sequence[Mapping[str, Any]], *, limit: int = 12) -> list[dict[str, Any]]:
    return [dict(row) for row in rows[:limit]]


def _selected_story_rows(rows: Sequence[Mapping[str, Any]], story: str) -> list[dict[str, Any]]:
    return [dict(row) for row in rows if str(row.get("Story", "")) == story]


def _snapshot(database_tables: Any, table_name: str, *, selected_story: str) -> dict[str, Any]:
    try:
        fetched = fetch_display_table(database_tables, table_name, max_rows=None)
    except Exception as exc:  # pragma: no cover - live COM only
        return {
            "table": table_name,
            "status": "FETCH_EXCEPTION",
            "exception_type": type(exc).__name__,
            "exception": str(exc),
        }

    rows = tuple(dict(row) for row in fetched.parsed.rows)
    payload: dict[str, Any] = {
        "table": table_name,
        "status": "FETCHED",
        "capture_status": fetched.capture_status.value,
        "return_code": fetched.parsed.return_code,
        "field_keys": list(fetched.parsed.field_keys),
        "row_count_reported": fetched.parsed.row_count_reported,
        "row_count_captured": len(rows),
        "sample_rows": _sample_rows(rows),
        "selected_signature": dict(fetched.selected_signature),
    }
    if "Story" in fetched.parsed.field_keys:
        payload["selected_story"] = selected_story
        payload["selected_story_rows"] = _selected_story_rows(rows, selected_story)
    if table_name == "Load Case Definitions - Summary":
        payload["all_rows"] = [dict(row) for row in rows]
    return payload


def _jsonable_raw(value: Any) -> Any:
    if isinstance(value, tuple):
        return [_jsonable_raw(item) for item in value]
    if isinstance(value, list):
        return [_jsonable_raw(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonable_raw(item) for key, item in value.items()}
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    try:
        return list(value)
    except Exception:
        return repr(value)


def _point_restraint_probe(point_obj: Any, point_name: str) -> dict[str, Any]:
    """Capture raw GetRestraint response without assigning regulatory meaning."""
    try:
        raw = point_obj.GetRestraint(str(point_name))
    except Exception as exc:  # pragma: no cover - live COM only
        return {
            "point": str(point_name),
            "status": "GET_RESTRAINT_EXCEPTION",
            "exception_type": type(exc).__name__,
            "exception": str(exc),
        }
    return {
        "point": str(point_name),
        "status": "RAW_CAPTURED",
        "raw_get_restraint": _jsonable_raw(raw),
        "regulatory_lateral_support_promoted": False,
    }


def _write(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(to_jsonable(payload), ensure_ascii=False, allow_nan=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--expected-model-fingerprint", required=True)
    parser.add_argument("--reviewed-length-unit", choices=("m", "mm"), required=True)
    parser.add_argument("--column-name", default="236")
    args = parser.parse_args(argv)

    attach = attach_to_running_etabs()
    if attach.status != ATTACH_STATUS_ATTACHED:
        payload = {
            "status": "BLOCKED_ATTACH",
            "safety": SAFETY,
            "attempts": [item.as_dict() for item in attach.attempts],
        }
        _write(args.out, payload)
        print(json.dumps(to_jsonable(payload), ensure_ascii=False, sort_keys=True))
        return 3

    sap = attach.sap_model
    identity = read_session_identity(attach.etabs_object, sap, attach_strategy=attach.strategy)
    fingerprint = model_fingerprint_from_path(identity.model_full_path)
    if fingerprint != args.expected_model_fingerprint:
        payload = {
            "status": "BLOCKED_MODEL_IDENTITY_MISMATCH",
            "expected_model_fingerprint": args.expected_model_fingerprint,
            "observed_model_fingerprint": fingerprint,
            "model_path": identity.model_full_path,
            "safety": SAFETY,
        }
        _write(args.out, payload)
        print(json.dumps(to_jsonable(payload), ensure_ascii=False, sort_keys=True))
        return 4

    try:
        topology_capture = capture_etabs_strict_column_topology(
            sap.DatabaseTables,
            reviewed_length_unit=args.reviewed_length_unit,
        )
        column = topology_capture.topology.column(args.column_name)
        column_projection = column.as_dict()
        table_snapshots = {
            name: _snapshot(sap.DatabaseTables, name, selected_story=column.story)
            for name in SOURCE_TABLE_CANDIDATES
        }
        endpoint_restraints = {
            "bottom": _point_restraint_probe(sap.PointObj, column.joint_bottom),
            "top": _point_restraint_probe(sap.PointObj, column.joint_top),
        }
    except Exception as exc:
        payload = {
            "status": "BLOCKED_FACTUAL_SOURCE_DISCOVERY",
            "exception_type": type(exc).__name__,
            "message": str(exc),
            "model": {"path": identity.model_full_path, "fingerprint": fingerprint},
            "safety": SAFETY,
        }
        _write(args.out, payload)
        print(json.dumps(to_jsonable(payload), ensure_ascii=False, sort_keys=True))
        return 5

    payload = {
        "status": "COMPLETE_FACTUAL_SOURCE_DISCOVERY",
        "model": {
            "path": identity.model_full_path,
            "fingerprint": fingerprint,
            "program_name": identity.program_name,
            "program_version": identity.program_version,
            "database_units": identity.units.database_units,
            "present_units": identity.units.present_units,
        },
        "safety": SAFETY,
        "selected_column": {
            "component_id": column.component_id,
            "UniqueName": column.unique_name,
            "Story": column.story,
            "Column": column.column_label,
            "Section": column.section,
            "joint_bottom": column.joint_bottom,
            "joint_top": column.joint_top,
            "object_length_m": column.object_length_m,
            "offset_bottom_m": column.offset_bottom_m,
            "offset_top_m": column.offset_top_m,
            "analysis_clear_length_candidate_m": column.analysis_clear_length_candidate_m,
            "regulatory_ln_status": column_projection["regulatory_ln_status"],
            "beams_at_bottom": [item.as_dict() for item in column.beams_at_bottom],
            "beams_at_top": [item.as_dict() for item in column.beams_at_top],
        },
        "endpoint_restraint_api": endpoint_restraints,
        "candidate_tables": table_snapshots,
        "promotion_boundary": {
            "regulatory_ln_promoted": False,
            "sway_classification_promoted": False,
            "effective_length_factor_promoted": False,
            "moment_ratio_promoted": False,
            "engineering_calculation_performed": False,
            "compliance_verdict_emitted": False,
        },
        "next_evidence_questions": (
            "Which ETABS field is source-authoritative for TS500 Delta_i displacement rather than a drift ratio?",
            "Which ETABS field is source-authoritative for TS500 V_fi storey shear?",
            "Can sum(N_di) be proven from a storey-level force result or must exact column axial forces be summed?",
            "Do existing result cases match both TS500 Eq.6.7 G+Q+E and Eq.6.5 G+1.3Q+1.3W bases?",
            "Do those results come from the TS500-required uncracked-section stability basis?",
        ),
    }
    _write(args.out, payload)
    print(json.dumps(to_jsonable({
        "status": payload["status"],
        "column": payload["selected_column"],
        "endpoint_restraint_api": endpoint_restraints,
        "table_statuses": {
            name: snapshot.get("status")
            for name, snapshot in table_snapshots.items()
        },
        "safety": SAFETY,
    }), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
