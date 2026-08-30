"""Two-stage real-ETABS acceptance discovery for ETABS-OAPI-LAYER-1.

This is live-test infrastructure, not production acquisition authority. It must
be executed only from the exact final candidate checkout against the supervisor
target ETABS instance. Model-dependent test data is discovered; acceptance
invariants remain fixed.

Stage 1 writes ``live_model_inventory.json`` using only supported candidate
boundaries. Stage 2 rows are derived from those exact discovered facts. No
engineering meaning is inferred from names and deterministic sampling is
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

from etabs_gateway.errors import ETABSGatewayError

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
    EtabsSafetyError,
    EtabsVerifiedSession,
    attach_verified_to_running_etabs,
    read_verified_database_tables_selection,
    read_verified_results_setup_selection,
    read_verified_unit_snapshot,
    reread_verified_session_identity,
)
from tbdy_engine.integration.live_etabs_acquisition_context import (
    LiveAcquisitionContextError,
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
INVENTORY_CONTRACT = "ETABS_OAPI_LAYER1_LIVE_MODEL_INVENTORY_V2"
PLAN_CONTRACT = "ETABS_OAPI_LAYER1_MODEL_ADAPTIVE_STAGE2_PLAN_V2"
SAMPLING_RULE = "LEXICOGRAPHICALLY_SMALLEST_UP_TO_3_VALID_IDENTITIES_TEST_ONLY"
REVIEWED_LENGTH_UNIT_SOURCE = "EXPLICIT_LIVE_RUNNER_ARGUMENT"

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


class LiveAcceptanceStateIntegrityError(RuntimeError):
    """Hard live-gate failure; ETABS must not be used further after this error."""


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


def _raise_if_hard_live_failure(exc: Exception) -> None:
    """Never downgrade safety/session/provenance failure to factual unavailability."""
    if isinstance(exc, (EtabsSafetyError, ETABSGatewayError, LiveAcquisitionContextError)):
        raise exc


def _factual_failure_payload(exc: Exception) -> dict[str, Any]:
    _raise_if_hard_live_failure(exc)
    message = str(exc)
    lower = message.lower()
    if isinstance(exc, EtabsOAPIError):
        if "nonzero" in lower or "non-zero" in lower or "returned code" in lower:
            status = "NONZERO_CSI_RETURN"
        elif (
            "shape" in lower
            or "tuple" in lower
            or "array" in lower
            or "count mismatch" in lower
            or "length" in lower
        ):
            status = "MALFORMED_TUPLE_OR_SHAPE"
        else:
            status = "FACTUAL_OAPI_FAILURE"
    else:
        status = "FACTUAL_AVAILABILITY_FAILURE"
    return {
        "availability_status": status,
        "error_type": type(exc).__name__,
        "error": message,
    }


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


def _discover_topology_and_design(
    session: EtabsVerifiedSession,
    *,
    reviewed_length_unit: str,
) -> dict[str, Any]:
    if reviewed_length_unit not in {"m", "mm"}:
        raise ValueError("reviewed_length_unit must be explicitly 'm' or 'mm'")

    topology_evidence = capture_etabs_strict_column_topology_from_session(
        session,
        reviewed_length_unit=reviewed_length_unit,
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
    section_api_call_count = 0
    result_api_call_count = 0
    for column in columns:
        section_api_call_count += 1
        try:
            section = read_design_section_from_session(session, column.unique_name)
            section_candidates.append(
                {
                    "component_id": column.component_id,
                    "unique_name": column.unique_name,
                    "available": True,
                    "availability_status": "API_SUCCESS",
                    "design_section": section.design_section,
                }
            )
        except Exception as exc:
            section_candidates.append(
                {
                    "component_id": column.component_id,
                    "unique_name": column.unique_name,
                    "available": False,
                    **_factual_failure_payload(exc),
                }
            )

        result_api_call_count += 1
        try:
            summary = read_summary_results_column_from_session(session, column.unique_name)
            has_rows = summary.reported_row_count > 0
            result_candidates.append(
                {
                    "component_id": column.component_id,
                    "unique_name": column.unique_name,
                    "api_success": True,
                    "availability_status": (
                        "API_SUCCESS_ROWS_PRESENT" if has_rows else "API_SUCCESS_ZERO_ROWS"
                    ),
                    "reported_row_count": summary.reported_row_count,
                    "has_rows": has_rows,
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
                    **_factual_failure_payload(exc),
                }
            )

    return {
        "reviewed_length_unit": reviewed_length_unit,
        "reviewed_length_unit_source": REVIEWED_LENGTH_UNIT_SOURCE,
        "strict_column_topology_table_row_counts": dict(topology_evidence.table_row_counts),
        "concrete_column_candidates": candidates,
        "design_section_candidates": section_candidates,
        "concrete_design_result_candidates": result_candidates,
        "concrete_design_availability_scan": {
            "candidate_count": len(columns),
            "design_section_api_call_count": section_api_call_count,
            "design_result_api_call_count": result_api_call_count,
            "purpose": "FACTUAL_AVAILABILITY_DISCOVERY_ONLY",
        },
    }


def _discover_relevant_tables(session: EtabsVerifiedSession) -> dict[str, Any]:
    planned_keys = tuple(
        dict.fromkeys((*REQUIRED_TABLES, TABLE_CONCRETE_FRAME_DESIGN_LOAD_COMBINATION_DATA))
    )
    rows: list[dict[str, Any]] = []
    available: list[str] = []
    for table in planned_keys:
        before = _selection_payload(read_verified_database_tables_selection(session))
        try:
            fetched = fetch_display_table_from_session(session, table, max_rows=None)
        except Exception as exc:
            _raise_if_hard_live_failure(exc)
            after = _selection_payload(read_verified_database_tables_selection(session))
            if before != after:
                raise LiveAcceptanceStateIntegrityError(
                    f"DatabaseTables selection changed after failed discovery read for {table!r}"
                )
            rows.append(
                {
                    "requested_table_key": table,
                    "api_success": False,
                    "selection_state_before": before,
                    "selection_state_after": after,
                    "selection_state_restored_exact": True,
                    **_factual_failure_payload(exc),
                }
            )
            continue

        after = _selection_payload(read_verified_database_tables_selection(session))
        if before != after:
            raise LiveAcceptanceStateIntegrityError(
                f"DatabaseTables selection changed during discovery read for {table!r}"
            )
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
                "selection_state_before": before,
                "selection_state_after": after,
                "selection_state_restored_exact": True,
            }
        )
    return {
        "table_discovery_scope": "SPRINT_RELEVANT_KEYS_ONLY_NOT_GLOBAL_GOD_INVENTORY",
        "available_table_keys_relevant_to_sprint": available,
        "table_probe_results": rows,
    }


def _matrix_row(
    *,
    test_id: str,
    layer: str,
    csi_api: str,
    real_identity: Any,
    selection_reason: str,
    expected_invariant: str,
    restoration_required: bool = False,
    **extra: Any,
) -> dict[str, Any]:
    return {
        "test_id": test_id,
        "layer": layer,
        "csi_api": csi_api,
        "real_identity": real_identity,
        "selection_reason": selection_reason,
        "expected_invariant": expected_invariant,
        "actual": None,
        "ret_code": None,
        "provenance_result": None,
        "restoration_required": restoration_required,
        "restoration_result": "NOT_RUN" if restoration_required else "NOT_REQUIRED",
        "status": "NOT_RUN",
        **extra,
    }


def build_stage2_matrix(inventory: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Generate model-adaptive rows while keeping the acceptance standard fixed."""
    matrix: list[dict[str, Any]] = [
        _matrix_row(
            test_id="LIVE-GATEWAY-ATTACH-01",
            layer="GATEWAY",
            csi_api="Helper.GetObjectProcess",
            real_identity=inventory["requested_pid"],
            selection_reason="EXACT_REQUESTED_PID",
            expected_invariant="exact PID attach and exact model identity",
        ),
        _matrix_row(
            test_id="LIVE-GATEWAY-STA-01",
            layer="GATEWAY",
            csi_api="bounded STA execution",
            real_identity=inventory["requested_pid"],
            selection_reason="FROZEN_REQUIRED_FAMILY",
            expected_invariant="all CSI work executes on gateway-owned STA",
        ),
        _matrix_row(
            test_id="LIVE-GATEWAY-REATTACH-01",
            layer="GATEWAY",
            csi_api="detach + exact-PID reattach",
            real_identity=inventory["requested_pid"],
            selection_reason="FROZEN_REQUIRED_FAMILY",
            expected_invariant="detach/reattach preserves exact target identity",
        ),
        _matrix_row(
            test_id="LIVE-GATEWAY-CLOSED-01",
            layer="GATEWAY",
            csi_api="closed-session bounded read rejection",
            real_identity=inventory["requested_pid"],
            selection_reason="FROZEN_REQUIRED_FAMILY",
            expected_invariant="closed session rejects further CSI access",
        ),
        _matrix_row(
            test_id="LIVE-SAFETY-IDENTITY-01",
            layer="SAFETY",
            csi_api="session identity reread",
            real_identity=inventory["model_path"],
            selection_reason="VERIFIED_TARGET_MODEL",
            expected_invariant="PID/model/path/lock identity preserved",
        ),
        _matrix_row(
            test_id="LIVE-SAFETY-UNITS-01",
            layer="SAFETY",
            csi_api="GetPresentUnits_2 + GetDatabaseUnits_2",
            real_identity=inventory["model_path"],
            selection_reason="FROZEN_REQUIRED_FAMILY",
            expected_invariant="unit facts are immutable",
        ),
        _matrix_row(
            test_id="LIVE-RESULTS-SETUP-01",
            layer="SAFETY",
            csi_api="Results.Setup snapshot/select/restore",
            real_identity=(
                inventory.get("static_linear_cases", [{}])[0].get("name")
                if inventory.get("static_linear_cases")
                else None
            ),
            selection_reason="DISCOVERED_STATIC_CASE_IF_PRESENT",
            expected_invariant="temporary Results.Setup selection restores exactly",
            restoration_required=True,
        ),
        _matrix_row(
            test_id="LIVE-CONTEXT-PROVENANCE-01",
            layer="INTEGRATION",
            csi_api="TrustedLiveAcquisitionContext",
            real_identity=inventory["acquisition_context_ref"],
            selection_reason="FACTORY_CREATED_CONTEXT",
            expected_invariant="EvidenceEpoch/session provenance remains internally owned",
        ),
        _matrix_row(
            test_id="LIVE-FINAL-STATE-01",
            layer="SAFETY",
            csi_api="preflight/postflight comparison",
            real_identity=inventory["model_path"],
            selection_reason="FROZEN_REQUIRED_FINAL_GATE",
            expected_invariant="PRE-FLIGHT STATE == POST-FLIGHT STATE",
            restoration_required=True,
        ),
    ]

    representatives = inventory["representative_object_model_identities"]
    for index, point in enumerate(representatives.get("points", ()), start=1):
        matrix.append(_matrix_row(
            test_id=f"LIVE-OBJ-POINT-{index:02d}",
            layer="OAPI_OBJECT_MODEL",
            csi_api="PointObj.GetRestraint",
            real_identity=point,
            selection_reason=SAMPLING_RULE,
            expected_invariant="typed six-DOF factual restraint with exact identity",
        ))
    for index, area in enumerate(representatives.get("areas", ()), start=1):
        matrix.append(_matrix_row(
            test_id=f"LIVE-OBJ-AREA-{index:02d}",
            layer="OAPI_OBJECT_MODEL",
            csi_api="AreaObj.GetProperty",
            real_identity=area,
            selection_reason=SAMPLING_RULE,
            expected_invariant="typed factual area-property assignment with exact identity",
        ))

    for index, pattern in enumerate(inventory.get("load_patterns", ()), start=1):
        matrix.append(_matrix_row(
            test_id=f"LIVE-LOAD-{index:03d}",
            layer="OAPI_LOAD_DEFINITIONS",
            csi_api="LoadPatterns.GetLoadType",
            real_identity=pattern["name"],
            selection_reason="ALL_DISCOVERED_LOAD_PATTERNS",
            expected_invariant="exact pattern identity and factual type code",
            discovered_type_code=pattern["type_code"],
        ))

    for index, case in enumerate(inventory.get("load_cases", ()), start=1):
        matrix.append(_matrix_row(
            test_id=f"LIVE-CASE-META-{index:03d}",
            layer="OAPI_LOAD_DEFINITIONS",
            csi_api="LoadCases.GetTypeOAPI_1",
            real_identity=case["name"],
            selection_reason="ALL_DISCOVERED_LOAD_CASES",
            expected_invariant="exact factual case metadata preserved",
        ))

    for index, case in enumerate(inventory.get("static_linear_cases", ()), start=1):
        matrix.append(_matrix_row(
            test_id=f"LIVE-CASE-STATIC-{index:03d}",
            layer="PROVIDER_STATIC_LINEAR",
            csi_api="LoadCases.StaticLinear.GetLoads",
            real_identity=case["name"],
            selection_reason="ALL_FACTUALLY_CLASSIFIED_LINEAR_STATIC_CASES",
            expected_invariant="typed load terms/counts/scale factors preserve exact case identity",
        ))

    for index, combo in enumerate(inventory.get("response_combinations", ()), start=1):
        matrix.append(_matrix_row(
            test_id=f"LIVE-COMBO-{index:03d}",
            layer="PROVIDER_RESPONSE_COMBO",
            csi_api="RespCombo.GetTypeCombo + RespCombo.GetCaseList",
            real_identity=combo["name"],
            selection_reason="ALL_DISCOVERED_RESPONSE_COMBINATIONS",
            expected_invariant="typed combo type/constituents/nesting preserve exact identity",
        ))

    for index, table in enumerate(inventory.get("available_table_keys_relevant_to_sprint", ()), start=1):
        matrix.append(_matrix_row(
            test_id=f"LIVE-DB-{index:03d}",
            layer="OAPI_DATABASE_TABLES",
            csi_api="DatabaseTables.GetTableForDisplayArray",
            real_identity=table,
            selection_reason="ALL_AVAILABLE_SPRINT_RELEVANT_TABLES",
            expected_invariant="return/count/shape valid and selection state unchanged/restored",
            restoration_required=True,
        ))

    sections = [row for row in inventory.get("design_section_candidates", ()) if row.get("available")]
    section_names = _sample([str(row["unique_name"]) for row in sections])
    section_by_name = {str(row["unique_name"]): row for row in sections}
    for index, name in enumerate(section_names, start=1):
        row = section_by_name[name]
        matrix.append(_matrix_row(
            test_id=f"LIVE-DESIGN-SECTION-{index:02d}",
            layer="OAPI_CONCRETE_DESIGN",
            csi_api="DesignConcrete.GetDesignSection",
            real_identity=name,
            selection_reason=SAMPLING_RULE,
            expected_invariant="exact frame/design-section identity preserved",
            component_id=row["component_id"],
        ))

    results = [
        row
        for row in inventory.get("concrete_design_result_candidates", ())
        if row.get("api_success") and row.get("has_rows")
    ]
    result_names = _sample([str(row["unique_name"]) for row in results])
    result_by_name = {str(row["unique_name"]): row for row in results}
    for index, name in enumerate(result_names, start=1):
        row = result_by_name[name]
        matrix.append(_matrix_row(
            test_id=f"LIVE-DESIGN-RESULT-{index:02d}",
            layer="OAPI_CONCRETE_DESIGN",
            csi_api="DesignConcrete.GetSummaryResultsColumn",
            real_identity=name,
            selection_reason=SAMPLING_RULE,
            expected_invariant="typed result rows/counts/provenance and units are stable",
            component_id=row["component_id"],
            discovered_row_count=row["reported_row_count"],
        ))

    zero_results = [
        row
        for row in inventory.get("concrete_design_result_candidates", ())
        if row.get("api_success") and not row.get("has_rows")
    ]
    if zero_results:
        row = sorted(zero_results, key=lambda item: str(item["unique_name"]))[0]
        matrix.append(_matrix_row(
            test_id="LIVE-DESIGN-NODATA-01",
            layer="OAPI_CONCRETE_DESIGN",
            csi_api="DesignConcrete.GetSummaryResultsColumn",
            real_identity=row["unique_name"],
            selection_reason="LEXICOGRAPHICALLY_SMALLEST_DISCOVERED_ZERO_ROW_IDENTITY_TEST_ONLY",
            expected_invariant="successful zero-row factual result remains zero-row NO_DATA",
        ))

    return matrix


def run_stage1(
    *,
    pid: int,
    model_path: str,
    reviewed_length_unit: str,
    output_path: Path,
) -> dict[str, Any]:
    if reviewed_length_unit not in {"m", "mm"}:
        raise ValueError("reviewed_length_unit must be explicitly 'm' or 'mm'")
    candidate_sha = _git_head()
    session = attach_verified_to_running_etabs(model_path, pid=pid, allow_pid_fallback=False)
    try:
        if session.identity.process_id != pid:
            raise LiveAcceptanceStateIntegrityError(
                f"exact PID verification failed: requested={pid} observed={session.identity.process_id}"
            )
        context = create_trusted_live_acquisition_context(session)
        preflight = _state_snapshot(session)
        loads = _discover_loads(session)
        combos = _discover_combos(session)
        objects = _discover_objects(session)
        topology_design = _discover_topology_and_design(
            session,
            reviewed_length_unit=reviewed_length_unit,
        )
        tables = _discover_relevant_tables(session)
        postflight = _state_snapshot(session)

        state_equal = preflight == postflight
        if not state_equal:
            raise LiveAcceptanceStateIntegrityError(
                "LIVE ACCEPTANCE FAIL: Stage-1 discovery changed a protected pre/post state dimension"
            )

        inventory: dict[str, Any] = {
            "contract": INVENTORY_CONTRACT,
            "stage2_plan_contract": PLAN_CONTRACT,
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
            "reviewed_length_unit": reviewed_length_unit,
            "reviewed_length_unit_source": REVIEWED_LENGTH_UNIT_SOURCE,
            "etabs_present_units": preflight["units"].get("present_units"),
            "etabs_database_units": preflight["units"].get("database_units"),
            "etabs_unit_facts": preflight["units"],
            "preflight_state": preflight,
            **loads,
            **combos,
            **objects,
            **topology_design,
            **tables,
            "postflight_state": postflight,
            "state_restoration_verified_exact": True,
        }
        inventory["actual_test_matrix_after_model_discovery"] = build_stage2_matrix(inventory)
        output_path.write_text(
            json.dumps(_plain(inventory), indent=2, sort_keys=True, ensure_ascii=True) + "\n",
            encoding="utf-8",
        )
        return inventory
    finally:
        session.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--reviewed-length-unit", choices=("m", "mm"), required=True)
    parser.add_argument("--output", default="live_model_inventory.json")
    args = parser.parse_args()
    run_stage1(
        pid=args.pid,
        model_path=args.model,
        reviewed_length_unit=args.reviewed_length_unit,
        output_path=Path(args.output),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
