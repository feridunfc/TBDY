from __future__ import annotations

import importlib.util
import inspect
from pathlib import Path

import pytest

from tbdy_engine.etabs.oapi.contracts import EtabsOAPIError
from tbdy_engine.etabs.safety import (
    EtabsSafetyErrorCode,
    EtabsStateRestoreError,
)
from tbdy_engine.integration.live_etabs_acquisition_context import (
    LiveAcquisitionContextMismatchError,
)


HERE = Path(__file__).resolve().parent


def _load_module(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


discovery = _load_module(
    "etabs_oapi_live_acceptance_discovery_test_subject",
    "etabs_oapi_live_acceptance_discovery.py",
)
stage2 = _load_module(
    "etabs_oapi_live_acceptance_stage2_test_subject",
    "etabs_oapi_live_acceptance_stage2.py",
)


def test_stage1_requires_explicit_reviewed_length_unit():
    signature = inspect.signature(discovery.run_stage1)
    parameter = signature.parameters["reviewed_length_unit"]
    assert parameter.default is inspect.Parameter.empty
    assert discovery.REVIEWED_LENGTH_UNIT_SOURCE == "EXPLICIT_LIVE_RUNNER_ARGUMENT"


def test_stage1_never_downgrades_safety_restore_failure_to_factual_absence():
    error = EtabsStateRestoreError(
        "restore failed",
        code=EtabsSafetyErrorCode.STATE_RESTORE_FAILED,
    )
    with pytest.raises(EtabsStateRestoreError):
        discovery._factual_failure_payload(error)


def test_stage1_never_downgrades_live_context_identity_failure():
    error = LiveAcquisitionContextMismatchError("context mismatch")
    with pytest.raises(LiveAcquisitionContextMismatchError):
        discovery._factual_failure_payload(error)


def test_stage1_preserves_nonzero_and_malformed_oapi_failure_classes():
    nonzero = discovery._factual_failure_payload(
        EtabsOAPIError("DesignConcrete.GetDesignSection returned nonzero code 1")
    )
    malformed = discovery._factual_failure_payload(
        EtabsOAPIError("GetSummaryResultsColumn returned unsupported tuple shape")
    )

    assert nonzero["availability_status"] == "NONZERO_CSI_RETURN"
    assert malformed["availability_status"] == "MALFORMED_TUPLE_OR_SHAPE"
    assert nonzero["error_type"] == "EtabsOAPIError"
    assert malformed["error_type"] == "EtabsOAPIError"


def _minimal_inventory():
    inventory = {
        "requested_pid": 4321,
        "model_path": r"C:\tmp\B-BLOK_Revised.EDB",
        "acquisition_context_ref": "ctx:test",
        "representative_object_model_identities": {
            "points": ["P1"],
            "frames": ["F1"],
            "areas": ["A1"],
        },
        "point_identities": ["P1"],
        "frame_identities": ["F1"],
        "area_identities": ["A1"],
        "load_patterns": [{"name": "G", "type_code": 1}],
        "load_cases": [
            {
                "name": "LC_G",
                "case_type_code": 1,
                "subtype_code": 0,
                "design_type_code": 0,
                "design_type_option": 0,
                "auto_flag": False,
            }
        ],
        "static_linear_cases": [{"name": "LC_G", "loads": []}],
        "response_combinations": [{"name": "COMB_1", "constituents": []}],
        "available_table_keys_relevant_to_sprint": ["Point Object Connectivity"],
        "design_section_candidates": [
            {
                "component_id": "S1:C1:F1",
                "unique_name": "F1",
                "available": True,
                "design_section": "C40x40",
            }
        ],
        "concrete_design_result_candidates": [
            {
                "component_id": "S1:C1:F1",
                "unique_name": "F1",
                "api_success": True,
                "has_rows": True,
                "reported_row_count": 1,
            }
        ],
        "concrete_column_candidates": [
            {
                "component_id": "S1:C1:F1",
                "unique_name": "F1",
                "joint_bottom": "P1",
                "joint_top": "P2",
                "assigned_section": "C40x40",
            }
        ],
    }
    inventory["actual_test_matrix_after_model_discovery"] = discovery.build_stage2_matrix(
        inventory
    )
    return inventory


def test_stage2_final_matrix_has_every_supervisor_audit_field():
    rows = stage2._augment_matrix(_minimal_inventory())
    required = {
        "test_id",
        "layer",
        "csi_api",
        "real_identity",
        "selection_reason",
        "expected_invariant",
        "actual",
        "ret_code",
        "provenance_result",
        "restoration_required",
        "restoration_result",
        "status",
    }
    assert rows
    assert all(required.issubset(row) for row in rows)
    assert all(row["status"] in stage2.ALLOWED_STATUSES for row in rows)


def test_stage2_augmentation_covers_provider_restoration_determinism_and_invalid_identity():
    inventory = _minimal_inventory()
    rows = stage2._augment_matrix(inventory)
    ids = {row["test_id"] for row in rows}

    assert "LIVE-PROVIDER-LOAD-CATALOG-01" in ids
    assert "LIVE-PROVIDER-POINT-01" in ids
    assert "LIVE-PROVIDER-FRAME-PROPERTY-01" in ids
    assert "LIVE-PROVIDER-STRICT-TOPOLOGY-01" in ids
    assert "LIVE-DB-RESTORE-01" in ids
    assert "LIVE-DET-LOAD-01" in ids
    assert "LIVE-DET-STATIC-01" in ids
    assert "LIVE-DET-COMBO-01" in ids
    assert "LIVE-DET-DB-01" in ids
    assert "LIVE-DET-DESIGN-SECTION-01" in ids
    assert "LIVE-DET-DESIGN-RESULT-01" in ids
    assert "LIVE-DESIGN-INVALID-01" in ids

    invalid = next(row for row in rows if row["test_id"] == "LIVE-DESIGN-INVALID-01")
    assert invalid["real_identity"] not in set(inventory["frame_identities"])
    assert "TEST_ONLY" in invalid["selection_reason"]
