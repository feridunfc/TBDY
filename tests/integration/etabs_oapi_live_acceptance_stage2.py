"""Comprehensive model-adaptive Stage-2 live executor for ETABS-OAPI-LAYER-1.

The executor consumes ``live_model_inventory.json`` from Stage 1. It never
chooses engineering-governing objects. Representative detailed reads use only
the frozen deterministic test-only sampling bound recorded in the inventory.

This file is live-test infrastructure. It must not be imported by production
application/domain code and it never runs analysis/design, saves, changes units,
or performs persistent model mutation.
"""
from __future__ import annotations

import argparse
import csv
from dataclasses import fields, is_dataclass
from enum import Enum
import json
import ntpath
from pathlib import Path
import subprocess
from typing import Any, Callable, Mapping, Sequence

from etabs_gateway.errors import ETABSGatewayError

from tbdy_engine.etabs.oapi import (
    fetch_display_table_for_output_from_session,
    fetch_display_table_from_session,
)
from tbdy_engine.etabs.oapi.concrete_design import (
    read_design_section_from_session,
    read_summary_results_column_from_session,
)
from tbdy_engine.etabs.oapi.contracts import EtabsOAPIError
from tbdy_engine.etabs.oapi.load_definitions import (
    read_load_case_type_from_session,
    read_load_pattern_type_from_session,
)
from tbdy_engine.etabs.oapi.object_model import (
    read_area_property_assignment_from_session,
    read_point_restraint_from_session,
)
from tbdy_engine.etabs.safety import (
    EtabsSafetyError,
    EtabsVerifiedSession,
    attach_verified_to_running_etabs,
    exercise_verified_results_setup_selection,
    read_verified_database_tables_selection,
    read_verified_results_setup_selection,
    read_verified_sta_execution_fact,
    read_verified_unit_snapshot,
    reread_verified_session_identity,
)
from tbdy_engine.integration.live_etabs_acquisition_context import (
    LiveAcquisitionContextError,
    create_trusted_live_acquisition_context,
)
from tbdy_engine.providers.etabs_column_endpoint_restraint_provider import (
    capture_etabs_point_restraint_from_session,
)
from tbdy_engine.providers.etabs_column_rebar_intent_provider import (
    capture_etabs_column_rebar_intent_from_session,
)
from tbdy_engine.providers.etabs_combo_definition_provider import (
    capture_etabs_combo_definition_from_session,
)
from tbdy_engine.providers.etabs_load_pattern_catalog_provider import (
    capture_etabs_load_pattern_catalog_from_session,
)
from tbdy_engine.providers.etabs_static_linear_case_provider import (
    capture_etabs_static_linear_case_from_session,
)
from tbdy_engine.providers.etabs_strict_column_topology_provider import (
    capture_etabs_strict_column_topology_from_session,
)

MATRIX_FIELDS = (
    "TEST ID",
    "LAYER",
    "CSI API",
    "REAL IDENTITY",
    "SELECTION REASON",
    "EXPECTED INVARIANT",
    "ACTUAL",
    "RET CODE",
    "PROVENANCE RESULT",
    "RESTORATION REQUIRED",
    "RESTORATION RESULT",
    "STATUS",
)
ALLOWED_STATUSES = frozenset({"PASS", "FAIL", "NOT_APPLICABLE", "NOT_RUN"})
SAMPLING_RULE = "LEXICOGRAPHICALLY_SMALLEST_UP_TO_3_VALID_IDENTITIES_TEST_ONLY"


class LiveAcceptanceStateIntegrityError(RuntimeError):
    """Hard safety/state failure. Do not continue ETABS operations after this."""


def _plain(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Enum):
        return _plain(value.value)
    if is_dataclass(value):
        return {
            field.name: _plain(getattr(value, field.name))
            for field in fields(value)
        }
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (tuple, list, set, frozenset)):
        return [_plain(item) for item in value]
    as_dict = getattr(value, "as_dict", None)
    if callable(as_dict):
        return _plain(as_dict())
    return repr(value)


def _git_head() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()


def _normalize_path(value: str) -> str:
    return ntpath.normcase(ntpath.normpath(str(value)))


def _sample(values: Sequence[str], limit: int = 3) -> list[str]:
    return sorted(dict.fromkeys(str(item) for item in values if str(item).strip()))[:limit]


def _state_snapshot(session: EtabsVerifiedSession) -> dict[str, Any]:
    return {
        "identity": reread_verified_session_identity(session).as_dict(),
        "units": _plain(read_verified_unit_snapshot(session)),
        "database_tables_selection": _plain(read_verified_database_tables_selection(session)),
        "results_setup_selection": _plain(read_verified_results_setup_selection(session)),
    }


def _normalized_display_table(value: Any) -> dict[str, Any]:
    parsed = value.parsed
    return {
        "table_name": value.table_name,
        "actual_table_name": parsed.actual_table_name,
        "fetch_status": parsed.fetch_status,
        "field_keys": list(parsed.field_keys),
        "rows": [dict(row) for row in parsed.rows],
        "row_count_reported": parsed.row_count_reported,
        "return_code": parsed.return_code,
        "capture_status": value.capture_status.value,
        "display_selection": dict(value.display_selection),
    }


def _is_hard_failure(exc: Exception) -> bool:
    return isinstance(
        exc,
        (
            EtabsSafetyError,
            ETABSGatewayError,
            LiveAcquisitionContextError,
            LiveAcceptanceStateIntegrityError,
        ),
    )


def _row(
    *,
    test_id: str,
    layer: str,
    csi_api: str,
    real_identity: Any,
    selection_reason: str,
    expected_invariant: str,
    restoration_required: bool = False,
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
    }


def _ensure_row(rows: list[dict[str, Any]], candidate: dict[str, Any]) -> None:
    if not any(row.get("test_id") == candidate["test_id"] for row in rows):
        rows.append(candidate)


def _invalid_frame_identity(inventory: Mapping[str, Any]) -> str:
    existing = {str(item) for item in inventory.get("frame_identities", ())}
    index = 0
    while True:
        candidate = f"__TBDY_LIVE_ACCEPTANCE_INVALID_FRAME_{index}__"
        if candidate not in existing:
            return candidate
        index += 1


def _augment_matrix(inventory: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = [dict(item) for item in inventory.get("actual_test_matrix_after_model_discovery", ())]
    columns = list(inventory.get("concrete_column_candidates", ()))
    sampled_columns = sorted(columns, key=lambda item: str(item.get("unique_name", "")))[:3]
    point = None
    section = None
    if sampled_columns:
        point = sampled_columns[0].get("joint_bottom")
        section = sampled_columns[0].get("assigned_section")
    if point is None:
        points = inventory.get("representative_object_model_identities", {}).get("points", ())
        point = points[0] if points else None

    _ensure_row(rows, _row(
        test_id="LIVE-PROVIDER-LOAD-CATALOG-01",
        layer="SEMANTIC_PROVIDER",
        csi_api="LoadPatterns.GetNameList + GetLoadType",
        real_identity="DISCOVERED_LOAD_PATTERN_CATALOG" if inventory.get("load_patterns") else None,
        selection_reason="FACTUAL_DISCOVERED_CATALOG",
        expected_invariant="provider returns typed factual catalog through verified session",
    ))
    _ensure_row(rows, _row(
        test_id="LIVE-PROVIDER-POINT-01",
        layer="SEMANTIC_PROVIDER",
        csi_api="PointObj.GetRestraint",
        real_identity=point,
        selection_reason=SAMPLING_RULE if point else "CATEGORY_ABSENT",
        expected_invariant="provider preserves exact point identity and six restraint DOFs",
    ))
    _ensure_row(rows, _row(
        test_id="LIVE-PROVIDER-FRAME-PROPERTY-01",
        layer="SEMANTIC_PROVIDER",
        csi_api="PropFrame.GetRebarColumn",
        real_identity=section,
        selection_reason=SAMPLING_RULE if section else "CATEGORY_ABSENT",
        expected_invariant="provider preserves factual frame-section rebar intent without final authority",
    ))
    _ensure_row(rows, _row(
        test_id="LIVE-PROVIDER-STRICT-TOPOLOGY-01",
        layer="SEMANTIC_PROVIDER",
        csi_api="DatabaseTables strict-column factual topology",
        real_identity="DISCOVERED_STRICT_COLUMN_TOPOLOGY" if columns else None,
        selection_reason="EXISTING_FACTUAL_TOPOLOGY_AUTHORITY",
        expected_invariant="FULL factual topology capture with reviewed length-unit input",
        restoration_required=True,
    ))

    tables = list(inventory.get("available_table_keys_relevant_to_sprint", ()))
    cases = [str(item.get("name")) for item in inventory.get("load_cases", ()) if item.get("name")]
    combos = [str(item.get("name")) for item in inventory.get("response_combinations", ()) if item.get("name")]
    output_name = cases[0] if cases else combos[0] if combos else None
    _ensure_row(rows, _row(
        test_id="LIVE-DB-RESTORE-01",
        layer="OAPI_DATABASE_TABLES",
        csi_api="DatabaseTables temporary display selection + GetTableForDisplayArray",
        real_identity={"table": tables[0], "output": output_name} if tables and output_name else None,
        selection_reason="FIRST_DISCOVERED_VALID_TABLE_AND_OUTPUT_TEST_ONLY",
        expected_invariant="temporary DatabaseTables selection restores exactly",
        restoration_required=True,
    ))

    patterns = [str(item.get("name")) for item in inventory.get("load_patterns", ()) if item.get("name")]
    static_cases = [str(item.get("name")) for item in inventory.get("static_linear_cases", ()) if item.get("name")]
    section_rows = [item for item in inventory.get("design_section_candidates", ()) if item.get("available")]
    result_rows = [
        item
        for item in inventory.get("concrete_design_result_candidates", ())
        if item.get("api_success") and item.get("has_rows")
    ]
    deterministic_specs = (
        ("LIVE-DET-LOAD-01", "LoadPatterns.GetLoadType", patterns[0] if patterns else None),
        ("LIVE-DET-STATIC-01", "StaticLinear.GetLoads", static_cases[0] if static_cases else None),
        ("LIVE-DET-COMBO-01", "RespCombo definition", combos[0] if combos else None),
        ("LIVE-DET-DB-01", "DatabaseTables.GetTableForDisplayArray", tables[0] if tables else None),
        (
            "LIVE-DET-DESIGN-SECTION-01",
            "DesignConcrete.GetDesignSection",
            section_rows[0].get("unique_name") if section_rows else None,
        ),
        (
            "LIVE-DET-DESIGN-RESULT-01",
            "DesignConcrete.GetSummaryResultsColumn",
            result_rows[0].get("unique_name") if result_rows else None,
        ),
    )
    for test_id, api, identity in deterministic_specs:
        _ensure_row(rows, _row(
            test_id=test_id,
            layer="DETERMINISM",
            csi_api=api,
            real_identity=identity,
            selection_reason="DISCOVERED_REPRESENTATIVE_FOR_TYPED_REPEATABILITY",
            expected_invariant="two normalized typed factual reads are exactly equal",
        ))

    _ensure_row(rows, _row(
        test_id="LIVE-DESIGN-INVALID-01",
        layer="OAPI_CONCRETE_DESIGN",
        csi_api="DesignConcrete.GetDesignSection invalid-identity failure semantics",
        real_identity=_invalid_frame_identity(inventory),
        selection_reason="TEST_ONLY_IDENTITY_VERIFIED_ABSENT_FROM_DISCOVERED_FRAME_INVENTORY",
        expected_invariant="invalid identity fails factually without safety/state mutation",
    ))

    for row in rows:
        for key, default in (
            ("actual", None),
            ("ret_code", None),
            ("provenance_result", None),
            ("restoration_required", False),
            ("restoration_result", "NOT_REQUIRED"),
            ("status", "NOT_RUN"),
        ):
            row.setdefault(key, default)
    return rows


def _mark_pass(
    row: dict[str, Any],
    *,
    actual: Any,
    ret_code: Any = 0,
    provenance: str = "PRESERVED_OR_NOT_APPLICABLE",
    restoration: str | None = None,
) -> None:
    row["actual"] = _plain(actual)
    row["ret_code"] = ret_code
    row["provenance_result"] = provenance
    if restoration is not None:
        row["restoration_result"] = restoration
    elif row.get("restoration_required"):
        row["restoration_result"] = "PASS"
    row["status"] = "PASS"


def _mark_fail(row: dict[str, Any], exc_or_message: Any) -> None:
    if isinstance(exc_or_message, BaseException):
        actual = {
            "error_type": type(exc_or_message).__name__,
            "error": str(exc_or_message),
        }
    else:
        actual = {"error": str(exc_or_message)}
    row["actual"] = actual
    if row.get("restoration_required") and row.get("restoration_result") == "NOT_RUN":
        row["restoration_result"] = "UNKNOWN_OR_FAILED"
    row["status"] = "FAIL"


def _mark_na(row: dict[str, Any], reason: str) -> None:
    row["actual"] = {"reason": reason}
    row["ret_code"] = None
    row["provenance_result"] = "NOT_APPLICABLE"
    row["restoration_result"] = "NOT_APPLICABLE" if row.get("restoration_required") else "NOT_REQUIRED"
    row["status"] = "NOT_APPLICABLE"


def _row_map(rows: Sequence[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(row["test_id"]): row for row in rows}


def _run_normal(
    row: dict[str, Any],
    function: Callable[[], Any],
    *,
    normalize: Callable[[Any], Any] = _plain,
    provenance: str = "PRESERVED_OR_NOT_APPLICABLE",
) -> Any | None:
    if row.get("real_identity") is None:
        _mark_na(row, "semantic category absent from discovered live model")
        return None
    try:
        value = function()
    except Exception as exc:
        _mark_fail(row, exc)
        if _is_hard_failure(exc):
            raise
        return None
    _mark_pass(row, actual=normalize(value), provenance=provenance)
    return value


def _run_determinism(
    row: dict[str, Any],
    function: Callable[[], Any],
    *,
    normalize: Callable[[Any], Any] = _plain,
) -> None:
    if row.get("real_identity") is None:
        _mark_na(row, "representative factual category absent from discovered model")
        return
    try:
        first = normalize(function())
        second = normalize(function())
    except Exception as exc:
        _mark_fail(row, exc)
        if _is_hard_failure(exc):
            raise
        return
    if first != second:
        _mark_fail(row, "normalized typed factual outputs differ across identical repeated reads")
        row["actual"] = {"first": _plain(first), "second": _plain(second)}
        return
    _mark_pass(
        row,
        actual={"first": first, "second": second, "exact_equal": True},
        provenance="TYPED_OUTPUT_DETERMINISM_PRESERVED",
    )


def _csv_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (str, int, float, bool)):
        return str(value)
    return json.dumps(_plain(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _write_matrix_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=MATRIX_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({
                "TEST ID": row.get("test_id"),
                "LAYER": row.get("layer"),
                "CSI API": row.get("csi_api"),
                "REAL IDENTITY": _csv_value(row.get("real_identity")),
                "SELECTION REASON": row.get("selection_reason"),
                "EXPECTED INVARIANT": row.get("expected_invariant"),
                "ACTUAL": _csv_value(row.get("actual")),
                "RET CODE": _csv_value(row.get("ret_code")),
                "PROVENANCE RESULT": _csv_value(row.get("provenance_result")),
                "RESTORATION REQUIRED": str(bool(row.get("restoration_required"))).lower(),
                "RESTORATION RESULT": row.get("restoration_result"),
                "STATUS": row.get("status"),
            })


def _write_report(
    path: Path,
    *,
    handoff: Mapping[str, Any],
    inventory: Mapping[str, Any],
    rows: Sequence[Mapping[str, Any]],
) -> None:
    lines = [
        "# ETABS-OAPI-LAYER-1 — Live Acceptance Report",
        "",
        f"- Candidate SHA: `{handoff['candidate_sha']}`",
        f"- Model: `{handoff['model_path']}`",
        f"- Requested PID: `{handoff['requested_pid']}`",
        f"- Overall status: **{handoff['status']}**",
        f"- Reviewed length unit: `{handoff['reviewed_length_unit']}` ({handoff['reviewed_length_unit_source']})",
        "",
        "## PLANNED BEFORE MODEL DISCOVERY",
        "",
    ]
    lines.extend(f"- {item}" for item in inventory.get("planned_before_model_discovery", ()))
    lines.extend([
        "",
        "## ACTUAL TEST MATRIX AFTER MODEL DISCOVERY",
        "",
        "| TEST ID | LAYER | CSI API | REAL IDENTITY | STATUS | RESTORATION |",
        "| --- | --- | --- | --- | --- | --- |",
    ])
    for row in rows:
        identity = _csv_value(row.get("real_identity")).replace("|", "\\|")
        lines.append(
            f"| {row.get('test_id')} | {row.get('layer')} | {row.get('csi_api')} | "
            f"{identity} | {row.get('status')} | {row.get('restoration_result')} |"
        )
    lines.extend([
        "",
        "## State integrity",
        "",
        f"- PRE == POST: `{handoff.get('preflight_equals_postflight')}`",
        f"- Hard failure: `{handoff.get('hard_failure')}`",
        "",
        "## Status counts",
        "",
    ])
    for status, count in handoff.get("status_counts", {}).items():
        lines.append(f"- {status}: {count}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_artifacts(
    *,
    report_path: Path,
    handoff_path: Path,
    matrix_path: Path,
    handoff: dict[str, Any],
    inventory: Mapping[str, Any],
    rows: Sequence[Mapping[str, Any]],
) -> None:
    _write_matrix_csv(matrix_path, rows)
    handoff_path.parent.mkdir(parents=True, exist_ok=True)
    handoff_path.write_text(
        json.dumps(_plain(handoff), indent=2, sort_keys=True, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    _write_report(report_path, handoff=handoff, inventory=inventory, rows=rows)


def execute_stage2(
    *,
    inventory_path: Path,
    report_path: Path,
    handoff_path: Path,
    matrix_path: Path,
) -> dict[str, Any]:
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    candidate_sha = _git_head()
    inventory_sha = str(inventory.get("candidate_sha") or "")
    if candidate_sha != inventory_sha:
        raise RuntimeError(
            f"inventory candidate SHA {inventory_sha!r} does not equal current checkout {candidate_sha!r}"
        )

    model_path = str(inventory["model_path"])
    pid = int(inventory["requested_pid"])
    reviewed_length_unit = str(inventory["reviewed_length_unit"])
    rows = _augment_matrix(inventory)
    by_id = _row_map(rows)
    session: EtabsVerifiedSession | None = None
    session_closed = False
    preflight: dict[str, Any] | None = None
    postflight: dict[str, Any] | None = None
    hard_failure: dict[str, str] | None = None

    try:
        session = attach_verified_to_running_etabs(model_path, pid=pid, allow_pid_fallback=False)
        if session.identity.process_id != pid:
            raise LiveAcceptanceStateIntegrityError(
                f"exact PID mismatch requested={pid} observed={session.identity.process_id}"
            )
        if _normalize_path(session.identity.model_full_path) != _normalize_path(model_path):
            raise LiveAcceptanceStateIntegrityError("exact target model path changed before Stage 2")

        preflight = _state_snapshot(session)
        _mark_pass(
            by_id["LIVE-GATEWAY-ATTACH-01"],
            actual=session.identity.as_dict(),
            provenance="GATEWAY_EXACT_PID_AND_MODEL_VERIFIED",
        )

        sta = read_verified_sta_execution_fact(session)
        _mark_pass(
            by_id["LIVE-GATEWAY-STA-01"],
            actual=sta,
            provenance="GATEWAY_STA_OWNERSHIP_VERIFIED",
        )

        identity = reread_verified_session_identity(session)
        _mark_pass(
            by_id["LIVE-SAFETY-IDENTITY-01"],
            actual=identity.as_dict(),
            provenance="VERIFIED_SESSION_IDENTITY_PRESERVED",
        )
        units = read_verified_unit_snapshot(session)
        _mark_pass(
            by_id["LIVE-SAFETY-UNITS-01"],
            actual=units,
            provenance="UNIT_PROVENANCE_FACTS_PRESERVED",
        )

        context = create_trusted_live_acquisition_context(session)
        context_actual = {
            "source_model_identity": _plain(context.source_model_identity),
            "EvidenceEpoch": _plain(context.evidence_epoch),
            "session_provenance_ref": context.session_provenance_ref,
            "acquisition_context_ref": context.acquisition_context_ref,
        }
        _mark_pass(
            by_id["LIVE-CONTEXT-PROVENANCE-01"],
            actual=context_actual,
            provenance="FACTORY_OWNED_EVIDENCE_EPOCH_AND_SESSION_PROVENANCE",
        )

        # Results.Setup temporary selection is an independent reversible safety transaction.
        result_setup_row = by_id["LIVE-RESULTS-SETUP-01"]
        load_cases = [str(item.get("name")) for item in inventory.get("load_cases", ()) if item.get("name")]
        response_combos = [
            str(item.get("name"))
            for item in inventory.get("response_combinations", ())
            if item.get("name")
        ]
        if load_cases:
            result_setup_row["real_identity"] = load_cases[0]
            fact = exercise_verified_results_setup_selection(session, case_name=load_cases[0])
            _mark_pass(
                result_setup_row,
                actual=fact,
                provenance="SAFETY_TRANSACTION_DIAGNOSTICS_PRESERVED",
                restoration="PASS",
            )
        elif response_combos:
            result_setup_row["real_identity"] = response_combos[0]
            fact = exercise_verified_results_setup_selection(session, combo_name=response_combos[0])
            _mark_pass(
                result_setup_row,
                actual=fact,
                provenance="SAFETY_TRANSACTION_DIAGNOSTICS_PRESERVED",
                restoration="PASS",
            )
        else:
            _mark_na(result_setup_row, "model contains no load case or response combination")

        # Model-adaptive OAPI/provider rows supplied by Stage 1.
        pattern_lookup = {
            str(item["name"]): item for item in inventory.get("load_patterns", ()) if item.get("name")
        }
        case_lookup = {
            str(item["name"]): item for item in inventory.get("load_cases", ()) if item.get("name")
        }
        for row in rows:
            test_id = str(row.get("test_id"))
            if row.get("status") != "NOT_RUN":
                continue
            identity_value = row.get("real_identity")

            if test_id.startswith("LIVE-OBJ-POINT-"):
                _run_normal(
                    row,
                    lambda name=str(identity_value): read_point_restraint_from_session(session, name),
                    provenance="FACTUAL_OAPI_IDENTITY_PRESERVED",
                )
            elif test_id.startswith("LIVE-OBJ-AREA-"):
                _run_normal(
                    row,
                    lambda name=str(identity_value): read_area_property_assignment_from_session(session, name),
                    provenance="FACTUAL_OAPI_IDENTITY_PRESERVED",
                )
            elif test_id.startswith("LIVE-LOAD-"):
                expected = pattern_lookup.get(str(identity_value))
                fact = _run_normal(
                    row,
                    lambda name=str(identity_value): read_load_pattern_type_from_session(session, name),
                    provenance="FACTUAL_OAPI_IDENTITY_PRESERVED",
                )
                if fact is not None and expected and fact.type_code != int(expected["type_code"]):
                    _mark_fail(row, "live type code differs from Stage-1 discovered type code")
            elif test_id.startswith("LIVE-CASE-META-"):
                expected = case_lookup.get(str(identity_value))
                fact = _run_normal(
                    row,
                    lambda name=str(identity_value): read_load_case_type_from_session(session, name),
                    provenance="FACTUAL_OAPI_CASE_METADATA_PRESERVED",
                )
                if fact is not None and expected:
                    actual_meta = {
                        "case_type_code": fact.case_type_code,
                        "subtype_code": fact.subtype_code,
                        "design_type_code": fact.design_type_code,
                        "design_type_option": fact.design_type_option,
                        "auto_flag": fact.auto_flag,
                    }
                    expected_meta = {key: expected.get(key) for key in actual_meta}
                    if actual_meta != expected_meta:
                        _mark_fail(row, "live case metadata differs from Stage-1 discovered metadata")
                        row["actual"] = {"expected": expected_meta, "actual": actual_meta}
            elif test_id.startswith("LIVE-CASE-STATIC-"):
                _run_normal(
                    row,
                    lambda name=str(identity_value): capture_etabs_static_linear_case_from_session(session, name),
                    provenance="SEMANTIC_PROVIDER_FACTUAL_EVIDENCE_PRESERVED",
                )
            elif test_id.startswith("LIVE-COMBO-"):
                _run_normal(
                    row,
                    lambda name=str(identity_value): capture_etabs_combo_definition_from_session(session, name),
                    provenance="SEMANTIC_PROVIDER_COMBO_EVIDENCE_PRESERVED",
                )
            elif test_id.startswith("LIVE-DB-") and test_id != "LIVE-DB-RESTORE-01":
                before = read_verified_database_tables_selection(session)
                value = _run_normal(
                    row,
                    lambda name=str(identity_value): fetch_display_table_from_session(session, name, max_rows=None),
                    normalize=_normalized_display_table,
                    provenance="DATABASETABLES_TYPED_READ_PRESERVED",
                )
                if value is not None:
                    after = read_verified_database_tables_selection(session)
                    if before != after:
                        _mark_fail(row, "DatabaseTables selection changed during factual read")
                        raise LiveAcceptanceStateIntegrityError(
                            f"DatabaseTables state changed during Stage-2 row {test_id}"
                        )
                    row["restoration_result"] = "PASS"
            elif test_id.startswith("LIVE-DESIGN-SECTION-"):
                _run_normal(
                    row,
                    lambda name=str(identity_value): read_design_section_from_session(session, name),
                    provenance="FACTUAL_CONCRETE_DESIGN_SECTION_PRESERVED",
                )
            elif test_id.startswith("LIVE-DESIGN-RESULT-"):
                _run_normal(
                    row,
                    lambda name=str(identity_value): read_summary_results_column_from_session(session, name),
                    provenance="FACTUAL_CONCRETE_DESIGN_RESULTS_PRESERVED",
                )
            elif test_id == "LIVE-DESIGN-NODATA-01":
                value = _run_normal(
                    row,
                    lambda name=str(identity_value): read_summary_results_column_from_session(session, name),
                    provenance="FACTUAL_ZERO_ROW_RESULT_PRESERVED",
                )
                if value is not None and value.reported_row_count != 0:
                    _mark_fail(row, "Stage-1 zero-row identity returned populated results in Stage 2")

        # Explicit DatabaseTables mutation/restoration proof.
        db_restore = by_id["LIVE-DB-RESTORE-01"]
        if db_restore.get("real_identity") is None:
            _mark_na(db_restore, "no table/output pair available for reversible display-selection proof")
        else:
            table = str(db_restore["real_identity"]["table"])
            output = str(db_restore["real_identity"]["output"])
            before = read_verified_database_tables_selection(session)
            value = _run_normal(
                db_restore,
                lambda: fetch_display_table_for_output_from_session(
                    session,
                    table,
                    preferred_output_case=output,
                    max_rows=None,
                ),
                normalize=_normalized_display_table,
                provenance="DATABASETABLES_TRANSACTION_DIAGNOSTICS_PRESERVED",
            )
            if value is not None:
                after = read_verified_database_tables_selection(session)
                if before != after:
                    _mark_fail(db_restore, "DatabaseTables temporary selection failed exact restoration")
                    raise LiveAcceptanceStateIntegrityError(
                        "DatabaseTables temporary display selection did not restore exactly"
                    )
                db_restore["restoration_result"] = "PASS"

        # Semantic provider E2E rows.
        _run_normal(
            by_id["LIVE-PROVIDER-LOAD-CATALOG-01"],
            lambda: capture_etabs_load_pattern_catalog_from_session(session),
            provenance="SEMANTIC_PROVIDER_FACTUAL_CATALOG_PRESERVED",
        )
        _run_normal(
            by_id["LIVE-PROVIDER-POINT-01"],
            lambda: capture_etabs_point_restraint_from_session(
                session, str(by_id["LIVE-PROVIDER-POINT-01"]["real_identity"])
            ),
            provenance="SEMANTIC_PROVIDER_POINT_EVIDENCE_PRESERVED",
        )
        _run_normal(
            by_id["LIVE-PROVIDER-FRAME-PROPERTY-01"],
            lambda: capture_etabs_column_rebar_intent_from_session(
                session,
                str(by_id["LIVE-PROVIDER-FRAME-PROPERTY-01"]["real_identity"]),
                reviewed_length_unit=reviewed_length_unit,
            ),
            provenance="SEMANTIC_PROVIDER_REBAR_INTENT_PRESERVED_NOT_FINAL_AUTHORITY",
        )
        topology_value = _run_normal(
            by_id["LIVE-PROVIDER-STRICT-TOPOLOGY-01"],
            lambda: capture_etabs_strict_column_topology_from_session(
                session,
                reviewed_length_unit=reviewed_length_unit,
            ),
            provenance="SEMANTIC_PROVIDER_STRICT_TOPOLOGY_PRESERVED",
        )
        if topology_value is not None:
            by_id["LIVE-PROVIDER-STRICT-TOPOLOGY-01"]["restoration_result"] = "PASS"

        # Invalid identity behavior: ordinary factual failure is the expected PASS.
        invalid_row = by_id["LIVE-DESIGN-INVALID-01"]
        try:
            unexpected = read_design_section_from_session(session, str(invalid_row["real_identity"]))
        except Exception as exc:
            if _is_hard_failure(exc):
                _mark_fail(invalid_row, exc)
                raise
            _mark_pass(
                invalid_row,
                actual={"expected_factual_failure_type": type(exc).__name__, "message": str(exc)},
                ret_code="NONZERO_OR_FACTUAL_FAILURE_VALIDATED",
                provenance="FAILURE_SEMANTICS_PRESERVED",
            )
        else:
            _mark_fail(invalid_row, "invalid discovered-absent frame identity unexpectedly succeeded")
            invalid_row["actual"] = _plain(unexpected)

        # Determinism: compare typed normalized factual outputs, not timing metadata.
        det_dispatch: dict[str, Callable[[], Any]] = {}
        if by_id["LIVE-DET-LOAD-01"].get("real_identity") is not None:
            det_dispatch["LIVE-DET-LOAD-01"] = lambda: read_load_pattern_type_from_session(
                session, str(by_id["LIVE-DET-LOAD-01"]["real_identity"])
            )
        if by_id["LIVE-DET-STATIC-01"].get("real_identity") is not None:
            det_dispatch["LIVE-DET-STATIC-01"] = lambda: capture_etabs_static_linear_case_from_session(
                session, str(by_id["LIVE-DET-STATIC-01"]["real_identity"])
            )
        if by_id["LIVE-DET-COMBO-01"].get("real_identity") is not None:
            det_dispatch["LIVE-DET-COMBO-01"] = lambda: capture_etabs_combo_definition_from_session(
                session, str(by_id["LIVE-DET-COMBO-01"]["real_identity"])
            )
        if by_id["LIVE-DET-DB-01"].get("real_identity") is not None:
            det_dispatch["LIVE-DET-DB-01"] = lambda: fetch_display_table_from_session(
                session, str(by_id["LIVE-DET-DB-01"]["real_identity"]), max_rows=None
            )
        if by_id["LIVE-DET-DESIGN-SECTION-01"].get("real_identity") is not None:
            det_dispatch["LIVE-DET-DESIGN-SECTION-01"] = lambda: read_design_section_from_session(
                session, str(by_id["LIVE-DET-DESIGN-SECTION-01"]["real_identity"])
            )
        if by_id["LIVE-DET-DESIGN-RESULT-01"].get("real_identity") is not None:
            det_dispatch["LIVE-DET-DESIGN-RESULT-01"] = lambda: read_summary_results_column_from_session(
                session, str(by_id["LIVE-DET-DESIGN-RESULT-01"]["real_identity"])
            )

        for test_id in (
            "LIVE-DET-LOAD-01",
            "LIVE-DET-STATIC-01",
            "LIVE-DET-COMBO-01",
            "LIVE-DET-DESIGN-SECTION-01",
            "LIVE-DET-DESIGN-RESULT-01",
        ):
            if test_id in det_dispatch:
                _run_determinism(by_id[test_id], det_dispatch[test_id])
            else:
                _mark_na(by_id[test_id], "determinism category absent from discovered model")
        if "LIVE-DET-DB-01" in det_dispatch:
            _run_determinism(
                by_id["LIVE-DET-DB-01"],
                det_dispatch["LIVE-DET-DB-01"],
                normalize=_normalized_display_table,
            )
        else:
            _mark_na(by_id["LIVE-DET-DB-01"], "DatabaseTables determinism category absent")

        postflight = _state_snapshot(session)
        if preflight != postflight:
            _mark_fail(by_id["LIVE-FINAL-STATE-01"], "protected preflight/postflight state differs")
            raise LiveAcceptanceStateIntegrityError("PRE-FLIGHT STATE != POST-FLIGHT STATE")
        _mark_pass(
            by_id["LIVE-FINAL-STATE-01"],
            actual={"preflight": preflight, "postflight": postflight, "exact_equal": True},
            provenance="FINAL_STATE_IDENTITY_PRESERVED",
            restoration="PASS",
        )

        # Explicit close rejection and reattach happen only after the state-safe read phase closes.
        session.close()
        session_closed = True
        closed_row = by_id["LIVE-GATEWAY-CLOSED-01"]
        try:
            read_verified_unit_snapshot(session)
        except (EtabsSafetyError, ETABSGatewayError) as exc:
            _mark_pass(
                closed_row,
                actual={"expected_rejection_type": type(exc).__name__, "message": str(exc)},
                ret_code="SESSION_CLOSED_REJECTED",
                provenance="NO_RAW_CAPABILITY_AFTER_CLOSE",
            )
        except Exception as exc:
            _mark_fail(closed_row, exc)
        else:
            _mark_fail(closed_row, "closed session unexpectedly allowed a factual read")

        reattach = attach_verified_to_running_etabs(model_path, pid=pid, allow_pid_fallback=False)
        try:
            reattached_state = _state_snapshot(reattach)
            reattach_ok = (
                reattach.identity.process_id == pid
                and _normalize_path(reattach.identity.model_full_path) == _normalize_path(model_path)
                and reattached_state == preflight
            )
            if not reattach_ok:
                _mark_fail(by_id["LIVE-GATEWAY-REATTACH-01"], "reattached target/state differs")
                raise LiveAcceptanceStateIntegrityError(
                    "detach/reattach did not preserve exact PID/model/protected state"
                )
            _mark_pass(
                by_id["LIVE-GATEWAY-REATTACH-01"],
                actual={"identity": reattach.identity.as_dict(), "state": reattached_state},
                provenance="EXACT_TARGET_REATTACH_VERIFIED",
            )
        finally:
            reattach.close()

    except Exception as exc:
        if _is_hard_failure(exc):
            hard_failure = {"type": type(exc).__name__, "message": str(exc)}
        else:
            hard_failure = {"type": type(exc).__name__, "message": str(exc)}
    finally:
        if session is not None and not session_closed:
            try:
                session.close()
            except Exception as close_exc:
                if hard_failure is None:
                    hard_failure = {
                        "type": type(close_exc).__name__,
                        "message": f"session close failed: {close_exc}",
                    }

    status_counts = {status: sum(row.get("status") == status for row in rows) for status in ALLOWED_STATUSES}
    any_fail = status_counts["FAIL"] > 0
    any_not_run = status_counts["NOT_RUN"] > 0
    overall = "FAIL" if hard_failure or any_fail or any_not_run else "PASS"
    handoff: dict[str, Any] = {
        "contract": "ETABS_OAPI_LAYER1_LIVE_ACCEPTANCE_HANDOFF_V1",
        "candidate_sha": candidate_sha,
        "inventory_candidate_sha": inventory_sha,
        "model_path": model_path,
        "requested_pid": pid,
        "reviewed_length_unit": reviewed_length_unit,
        "reviewed_length_unit_source": inventory.get("reviewed_length_unit_source"),
        "status": overall,
        "status_counts": status_counts,
        "hard_failure": hard_failure,
        "preflight_equals_postflight": (
            preflight == postflight if preflight is not None and postflight is not None else False
        ),
        "planned_before_model_discovery": inventory.get("planned_before_model_discovery", []),
        "actual_test_matrix_after_model_discovery": rows,
        "artifacts": {
            "inventory": str(inventory_path),
            "report": str(report_path),
            "handoff": str(handoff_path),
            "matrix": str(matrix_path),
        },
        "forbidden_mutation_claims": {
            "RunAnalysis": 0,
            "StartDesign": 0,
            "Save": 0,
            "SaveAs": 0,
            "SetPresentUnits": 0,
            "persistent_model_mutation": 0,
        },
    }
    _write_artifacts(
        report_path=report_path,
        handoff_path=handoff_path,
        matrix_path=matrix_path,
        handoff=handoff,
        inventory=inventory,
        rows=rows,
    )
    return handoff


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inventory", default="live_model_inventory.json")
    parser.add_argument("--report", default="live_acceptance_report.md")
    parser.add_argument("--handoff", default="live_acceptance_handoff.json")
    parser.add_argument("--matrix", default="live_acceptance_matrix.csv")
    args = parser.parse_args()
    result = execute_stage2(
        inventory_path=Path(args.inventory),
        report_path=Path(args.report),
        handoff_path=Path(args.handoff),
        matrix_path=Path(args.matrix),
    )
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
