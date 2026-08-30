"""Two-stage real-ETABS acceptance discovery for ETABS-OAPI-LAYER-1.

This is live-test infrastructure, not production acquisition authority. It must
be executed only from the exact candidate checkout against the supervisor target
ETABS instance. Model-dependent test data is discovered; acceptance invariants
remain fixed.

Stage 1 writes ``live_model_inventory.json`` using only supported candidate
boundaries. Stage 2 matrix rows are derived from those exact discovered facts.
No engineering meaning is inferred from names and deterministic sampling is
explicitly test-only.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, is_dataclass
from enum import Enum
import json
from pathlib import Path
import subprocess
from typing import Any, Mapping, Sequence

from tbdy_engine.etabs.oapi import fetch_display_table_from_session
from tbdy_engine.etabs.oapi.concrete_design import (
    read_design_section_from_session,
    read_summary_results_column_from_session,
)
from tbdy_engine.etabs.oapi.contracts import EtabsOAPIError
from tbdy_engine.etabs.oapi.load_definitions import (
    LINEAR_STATIC_CASE_TYPE_CODE,
    read_load_case_names_from_session,
    read_load_case_type_from_session,
    read_load_pattern_names_from_session,
    read_load_pattern_type_from_session,
)
from tbdy_engine.etabs.oapi.object_model import (
    read_area_names_from_session,
    read_frame_names_from_session,
    read_point_names_from_session,
)
from tbdy_engine.etabs.oapi.response_combinations import (
    read_response_combo_names_from_session,
)
from tbdy_engine.etabs.safety import (
    EtabsVerifiedSession,
    attach_verified_to_running_etabs,
    read_verified_database_tables_selection,
    read_verified_results_setup_selection,
    read_verified_unit_snapshot,
    reread_verified_session_identity,
)
from tbdy_engine.integration.live_etabs_acquisition_context import (
    create_trusted_live_acquisition_context,
)
from tbdy_engine.providers.etabs_combo_definition_provider import (
    capture_etabs_combo_definitions_from_session,
)
from tbdy_engine.providers.etabs_concrete_design_combo_selection_probe import (
    TABLE_CONCRETE_FRAME_DESIGN_LOAD_COMBINATION_DATA,
)
from tbdy_engine.providers.etabs_static_linear_case_provider import (
    capture_etabs_static_linear_cases_from_session,
)
from tbdy_engine.providers.etabs_strict_column_topology_provider import (
    REQUIRED_TABLES,
    capture_etabs_strict_column_topology_from_session,
)

DEFAULT_MODEL = r"C:\tmp\B-BLOK_Revised.EDB"
INVENTORY_CONTRACT = "ETABS_OAPI_LAYER1_LIVE_MODEL_INVENTORY_V1"
PLAN_CONTRACT = "ETABS_OAPI_LAYER1_MODEL_ADAPTIVE_STAGE2_PLAN_V1"
SAMPLING_RULE = "LEXICOGRAPHICALLY_SMALLEST_UP_TO_3_VALID_IDENTITIES_TEST_ONLY"

PLANNED_BEFORE_MODEL_DISCOVERY = (
    "gateway exact-PID attach/session/STA/raw-non-escape",
    "safety identity/unit/capability/analysis-readiness",
    "DatabaseTables parse/count/restoration",
    "Results.Setup snapshot/temporary-selection/restoration",
    "object-model identity reads",
    "load-pattern and static-linear definition reads",
    "TS500 promotion boundary",
    "response-combination exact definitions",
    "concrete design-section and column-summary reads",
    "semantic-provider end-to-end provenance",
    "cross-read identity consistency",
    "repeatability/determinism",
    "final state restoration and zero model mutation",
)

FIXED_ACCEPTANCE_INVARIANTS = (
    "gateway_is_sole_attach_session_sta_owner",
    "requested_pid_equals_verified_pid",
    "raw_application_not_public",
    "raw_sapmodel_not_public",
    "return_codes_validated",
    "tuple_count_shape_validated",
    "exact_object_case_combo_identity_preserved",
    "EvidenceEpoch_and_session_provenance_preserved",
    "DatabaseTables_state_restored_exactly",
    "Results.Setup_state_restored_exactly",
    "present_and_database_units_unchanged",
    "model_path_and_lock_state_unchanged",
    "RunAnalysis_count_zero",
    "StartDesign_count_zero",
    "Save_SaveAs_count_zero",
    "SetPresentUnits_count_zero",
    "TS500_semantic_mapping_outside_OAPI",
    "same_state_same_normalized_factual_output",
)


def _plain(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Enum):
        return _plain(value.value)
    if is_dataclass(value):
        return _plain(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (tuple, list, set, frozenset)):
        return [_plain(item) for item in value]
    as_dict = getattr(value, "as_dict", None)
    if callable(as_dict):
        return _plain(as_dict())
    return repr(value)


def _git_head() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        text=True,
    ).strip()


def _sample(values: Sequence[str], limit: int = 3) -> list[str]:
    return sorted(dict.fromkeys(values))[:limit]


def _selection_payload(snapshot: Any) -> dict[str, Any]:
    return _plain(snapshot)


def _state_snapshot(session: EtabsVerifiedSession) -> dict[str, Any]:
    identity = reread_verified_session_identity(session)
    return {
        "identity": identity.as_dict(),
        "units": _plain(read_verified_unit_snapshot(session)),
        "database_tables_selection": _selection_payload(
            read_verified_database_tables_selection(session)
        ),
        "results_setup_selection": _selection_payload(
            read_verified_results_setup_selection(session)
        ),
    }


def _discover_loads(session: EtabsVerifiedSession) -> dict[str, Any]:
    pattern_names, _ = read_load_pattern_names_from_session(session)
    patterns = []
    for name in pattern_names:
        fact = read_load_pattern_type_from_session(session, name)
        patterns.append({"name": fact.name, "type_code": fact.type_code})

    case_names, _ = read_load_case_names_from_session(session)
    case_types = []
    static_names: list[str] = []
    for name in case_names:
        fact = read_load_case_type_from_session(session, name)
        row = {
            "name": fact.name,
            "case_type_code": fact.case_type_code,
            "subtype_code": fact.subtype_code,
            "design_type_code": fact.design_type_code,
            "design_type_option": fact.design_type_option,
            "auto_flag": fact.auto_flag,
        }
        case_types.append(row)
        if fact.case_type_code == LINEAR_STATIC_CASE_TYPE_CODE:
            static_names.append(name)

    static_cases = (
        capture_etabs_static_linear_cases_from_session(session, static_names)
        if static_names
        else ()
    )
    return {
        "load_patterns": patterns,
        "load_cases": case_types,
        "static_linear_cases": [_plain(item) for item in static_cases],
    }


def _discover_combos(session: EtabsVerifiedSession) -> dict[str, Any]:
    names, _ = read_response_combo_names_from_session(session)
    definitions = capture_etabs_combo_definitions_from_session(session, names) if names else ()
    return {
        "response_combination_names": list(names),
        "response_combinations": [_plain(item) for item in definitions],
    }


def _discover_objects(session: EtabsVerifiedSession) -> dict[str, Any]:
    points, _ = read_point_names_from_session(session)
    frames, _ = read_frame_names_from_session(session)
    areas, _ = read_area_names_from_session(session)
    return {
        "point_identities": list(points),
        "frame_identities": list(frames),
        "area_identities": list(areas),
        "representative_object_model_identities": {
            "sampling_rule": SAMPLING_RULE,
            "points": _sample(points),
            "frames": _sample(frames),
            "areas": _sample(areas),
        },
    }


def _discover_topology_and_design(session: EtabsVerifiedSession) -> dict[str, Any]:
    topology_evidence = capture_etabs_strict_column_topology_from_session(
        session,
        reviewed_length_unit="m",
    )
    columns = tuple(
        sorted(
            topology_evidence.topology.columns,
            key=lambda item: (item.component_id, item.unique_name),
        )
    )
    candidates = [
        {
            "component_id": column.component_id,
            "unique_name": column.unique_name,
            "story": column.story,
            "label": column.column_label,
            "assigned_section": column.section,
            "joint_bottom": column.joint_bottom,
            "joint_top": column.joint_top,
        }
        for column in columns
    ]

    section_candidates: list[dict[str, Any]] = []
    result_candidates: list[dict[str, Any]] = []
    for column in columns:
        try:
            section = read_design_section_from_session(session, column.unique_name)
            section_candidates.append(
                {
                    "component_id": column.component_id,
                    "unique_name": column.unique_name,
                    "available": True,
                    "design_section": section.design_section,
                }
            )
        except Exception as exc:
            section_candidates.append(
                {
                    "component_id": column.component_id,
                    "unique_name": column.unique_name,
                    "available": False,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
            )

        try:
            summary = read_summary_results_column_from_session(session, column.unique_name)
            result_candidates.append(
                {
                    "component_id": column.component_id,
                    "unique_name": column.unique_name,
                    "api_success": True,
                    "reported_row_count": summary.reported_row_count,
                    "has_rows": summary.reported_row_count > 0,
                    "combo_identities": sorted(
                        {
                            str(row.pmm_combo)
                            for row in summary.rows
                            if isinstance(row.pmm_combo, str) and row.pmm_combo.strip()
                        }
                    ),
                }
            )
        except Exception as exc:
            result_candidates.append(
                {
                    "component_id": column.component_id,
                    "unique_name": column.unique_name,
                    "api_success": False,
                    "reported_row_count": None,
                    "has_rows": False,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
            )

    return {
        "strict_column_topology_table_row_counts": dict(topology_evidence.table_row_counts),
        "concrete_column_candidates": candidates,
        "design_section_candidates": section_candidates,
        "concrete_design_result_candidates": result_candidates,
    }


def _discover_relevant_tables(session: EtabsVerifiedSession) -> dict[str, Any]:
    planned_keys = tuple(dict.fromkeys((*REQUIRED_TABLES, TABLE_CONCRETE_FRAME_DESIGN_LOAD_COMBINATION_DATA)))
    rows: list[dict[str, Any]] = []
    available: list[str] = []
    for table in planned_keys:
        try:
            fetched = fetch_display_table_from_session(session, table, max_rows=None)
            api_success = fetched.parsed.return_code == 0
            if api_success:
                available.append(table)
            rows.append(
                {
                    "requested_table_key": table,
                    "resolved_table_key": fetched.parsed.actual_table_name,
                    "api_success": api_success,
                    "return_code": fetched.parsed.return_code,
                    "capture_status": fetched.capture_status.value,
                    "field_keys": list(fetched.parsed.field_keys),
                    "row_count_reported": fetched.parsed.row_count_reported,
                    "row_count_captured": len(fetched.parsed.rows),
                    "selected_signature": dict(fetched.selected_signature),
                }
            )
        except Exception as exc:
            rows.append(
                {
                    "requested_table_key": table,
                    "api_success": False,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
            )
    return {
        "table_discovery_scope": "SPRINT_RELEVANT_KEYS_ONLY_NOT_GLOBAL_GOD_INVENTORY",
        "available_table_keys_relevant_to_sprint": available,
        "table_probe_results": rows,
    }


def build_stage2_matrix(inventory: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Generate model-adaptive test rows; acceptance requirements are not weakened."""
    matrix: list[dict[str, Any]] = []

    representatives = inventory["representative_object_model_identities"]
    for index, point in enumerate(representatives.get("points", ()), start=1):
        matrix.append({
            "test_id": f"LIVE-OBJ-POINT-{index:02d}",
            "layer": "OAPI_OBJECT_MODEL",
            "csi_api": "PointObj.GetRestraint",
            "real_identity": point,
            "selection_reason": SAMPLING_RULE,
        })

    for index, pattern in enumerate(inventory.get("load_patterns", ()), start=1):
        matrix.append({
            "test_id": f"LIVE-LOAD-{index:03d}",
            "layer": "OAPI_LOAD_DEFINITIONS",
            "csi_api": "LoadPatterns.GetLoadType",
            "real_identity": pattern["name"],
            "discovered_type_code": pattern["type_code"],
        })

    for index, case in enumerate(inventory.get("static_linear_cases", ()), start=1):
        matrix.append({
            "test_id": f"LIVE-CASE-{index:03d}",
            "layer": "PROVIDER_STATIC_LINEAR",
            "csi_api": "LoadCases.StaticLinear.GetLoads",
            "real_identity": case["name"],
        })

    for index, combo in enumerate(inventory.get("response_combinations", ()), start=1):
        matrix.append({
            "test_id": f"LIVE-COMBO-{index:03d}",
            "layer": "PROVIDER_RESPONSE_COMBO",
            "csi_api": "RespCombo.GetTypeCombo + RespCombo.GetCaseList",
            "real_identity": combo["name"],
        })

    for index, table in enumerate(inventory.get("available_table_keys_relevant_to_sprint", ()), start=1):
        matrix.append({
            "test_id": f"LIVE-DB-{index:03d}",
            "layer": "OAPI_DATABASE_TABLES",
            "csi_api": "DatabaseTables.GetTableForDisplayArray",
            "real_identity": table,
        })

    sections = [row for row in inventory.get("design_section_candidates", ()) if row.get("available")]
    for index, row in enumerate(sections, start=1):
        matrix.append({
            "test_id": f"LIVE-DESIGN-SECTION-{index:03d}",
            "layer": "OAPI_CONCRETE_DESIGN",
            "csi_api": "DesignConcrete.GetDesignSection",
            "real_identity": row["unique_name"],
            "component_id": row["component_id"],
        })

    results = [
        row
        for row in inventory.get("concrete_design_result_candidates", ())
        if row.get("api_success") and row.get("has_rows")
    ]
    for index, row in enumerate(results, start=1):
        matrix.append({
            "test_id": f"LIVE-DESIGN-RESULT-{index:03d}",
            "layer": "OAPI_CONCRETE_DESIGN",
            "csi_api": "DesignConcrete.GetSummaryResultsColumn",
            "real_identity": row["unique_name"],
            "component_id": row["component_id"],
            "discovered_row_count": row["reported_row_count"],
        })

    return matrix


def run_stage1(
    *,
    pid: int,
    model_path: str,
    output_path: Path,
) -> dict[str, Any]:
    candidate_sha = _git_head()
    session = attach_verified_to_running_etabs(model_path, pid=pid, allow_pid_fallback=False)
    try:
        context = create_trusted_live_acquisition_context(session)
        preflight = _state_snapshot(session)
        loads = _discover_loads(session)
        combos = _discover_combos(session)
        objects = _discover_objects(session)
        topology_design = _discover_topology_and_design(session)
        tables = _discover_relevant_tables(session)
        postflight = _state_snapshot(session)

        state_equal = preflight == postflight
        inventory: dict[str, Any] = {
            "contract": INVENTORY_CONTRACT,
            "candidate_sha": candidate_sha,
            "model_path": model_path,
            "requested_pid": pid,
            "verified_process_id": session.identity.process_id,
            "verified_session_identity": session.identity.as_dict(),
            "source_model_identity": _plain(context.source_model_identity),
            "EvidenceEpoch": _plain(context.evidence_epoch),
            "session_provenance_ref": context.session_provenance_ref,
            "acquisition_context_ref": context.acquisition_context_ref,
            "sampling_rule": SAMPLING_RULE,
            "planned_before_model_discovery": list(PLANNED_BEFORE_MODEL_DISCOVERY),
            "fixed_acceptance_invariants": list(FIXED_ACCEPTANCE_INVARIANTS),
            "preflight_state": preflight,
            **loads,
            **combos,
            **objects,
            **topology_design,
            **tables,
            "postflight_state": postflight,
            "state_restoration_verified_exact": state_equal,
        }
        inventory["actual_test_matrix_after_model_discovery"] = build_stage2_matrix(inventory)
        output_path.write_text(
            json.dumps(_plain(inventory), indent=2, sort_keys=True, ensure_ascii=True) + "\n",
            encoding="utf-8",
        )
        if not state_equal:
            raise RuntimeError(
                "LIVE ACCEPTANCE FAIL: Stage-1 discovery changed a protected pre/post state dimension"
            )
        return inventory
    finally:
        session.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--output", default="live_model_inventory.json")
    args = parser.parse_args()
    run_stage1(pid=args.pid, model_path=args.model, output_path=Path(args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
