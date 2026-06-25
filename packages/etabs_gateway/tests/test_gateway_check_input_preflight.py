from __future__ import annotations

import ast
import sys
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
GATEWAY_SOURCE = REPO_ROOT / "packages" / "etabs_gateway" / "src"
if str(GATEWAY_SOURCE) not in sys.path:
    sys.path.insert(0, str(GATEWAY_SOURCE))

from etabs_gateway.replay import FixtureReplayProvider  # noqa: E402
from tbdy_engine.features.etabs_gateway_handoff import (  # noqa: E402
    GatewayContextOrigin,
    GatewayFeatureSnapshotInput,
    build_feature_snapshot_from_gateway_context,
)
from tbdy_engine.features.evidence import (  # noqa: E402
    FeatureEvidence,
    FeatureEvidenceStatus,
)
from tbdy_engine.features.gateway_check_input_preflight import (  # noqa: E402
    CheckInputFeatureRequirement,
    CheckInputPreflightSpec,
    CheckInputReadiness,
    FeatureRequirementState,
    evaluate_check_input_preflight,
    evaluate_check_input_preflights,
)
from tbdy_engine.features.snapshot import FeatureSnapshot  # noqa: E402
from tbdy_engine.features.value import (  # noqa: E402
    FeatureValue,
    FeatureValueStatus,
)

FIXTURE_PATH = (
    REPO_ROOT
    / "packages"
    / "etabs_gateway"
    / "tests"
    / "fixtures"
    / "gateway_context_v1.json"
)


def gateway_snapshot() -> FeatureSnapshot:
    provider = FixtureReplayProvider.from_path(FIXTURE_PATH)
    return build_feature_snapshot_from_gateway_context(
        GatewayFeatureSnapshotInput(
            context=provider.read_context(),
            origin=GatewayContextOrigin.FIXTURE_REPLAY,
            source_fingerprint=provider.fingerprint,
        )
    )


def req(feature_name: str, **kwargs):
    return CheckInputFeatureRequirement(
        feature_name=feature_name,
        **kwargs,
    )


def test_ready_when_required_features_and_evidence_are_full() -> None:
    assessment = evaluate_check_input_preflight(
        snapshot=gateway_snapshot(),
        spec=CheckInputPreflightSpec(
            consumer_id="gateway_model_context_adapter",
            required_features=(
                req("etabs.application.version"),
                req("etabs.model.open"),
                req("etabs.model.path"),
                req("etabs.model.units_code"),
            ),
        ),
    )
    assert assessment.readiness is CheckInputReadiness.READY
    assert assessment.adapter_unlock_allowed is True
    assert assessment.blocked_features == ()
    assert assessment.snapshot_origin == "FIXTURE_REPLAY"


def test_not_present_feature_blocks_fail_closed() -> None:
    assessment = evaluate_check_input_preflight(
        snapshot=gateway_snapshot(),
        spec=CheckInputPreflightSpec(
            consumer_id="future_force_adapter",
            required_features=(
                req("etabs.results.base_shear"),
            ),
        ),
    )
    assert assessment.readiness is CheckInputReadiness.BLOCKED
    assert assessment.blocked_features == (
        "etabs.results.base_shear",
    )
    assert assessment.feature_assessments[0].state is (
        FeatureRequirementState.NOT_PRESENT
    )


def test_explicit_missing_feature_blocks() -> None:
    assessment = evaluate_check_input_preflight(
        snapshot=gateway_snapshot(),
        spec=CheckInputPreflightSpec(
            consumer_id="unit_display_adapter",
            required_features=(
                req("etabs.model.units_display_name"),
            ),
        ),
    )
    assert assessment.feature_assessments[0].state is (
        FeatureRequirementState.VALUE_MISSING
    )


def test_partial_value_blocks_by_default() -> None:
    evidence = FeatureEvidence(
        evidence_status=FeatureEvidenceStatus.PARTIAL,
        source_table="fixture",
        actual_table_name="fixture",
        source_column="value",
        reason="Partial fixture evidence.",
    )
    snapshot = FeatureSnapshot(
        component_type="TEST",
        component_id="1",
        features={
            "test.value": FeatureValue(
                feature_name="test.value",
                value=1,
                status=FeatureValueStatus.PARTIAL,
                evidence=(evidence,),
            )
        },
    )
    assessment = evaluate_check_input_preflight(
        snapshot=snapshot,
        spec=CheckInputPreflightSpec(
            consumer_id="partial_blocked",
            required_features=(req("test.value"),),
        ),
    )
    assert assessment.feature_assessments[0].state is (
        FeatureRequirementState.VALUE_PARTIAL
    )


def test_partial_value_can_be_explicitly_accepted() -> None:
    evidence = FeatureEvidence(
        evidence_status=FeatureEvidenceStatus.PARTIAL,
        source_table="fixture",
        actual_table_name="fixture",
        source_column="value",
        reason="Partial fixture evidence.",
    )
    snapshot = FeatureSnapshot(
        component_type="TEST",
        component_id="2",
        features={
            "test.value": FeatureValue(
                feature_name="test.value",
                value=1,
                status=FeatureValueStatus.PARTIAL,
                evidence=(evidence,),
            )
        },
    )
    assessment = evaluate_check_input_preflight(
        snapshot=snapshot,
        spec=CheckInputPreflightSpec(
            consumer_id="partial_allowed",
            required_features=(
                req(
                    "test.value",
                    allow_partial=True,
                    accepted_evidence_statuses=(
                        FeatureEvidenceStatus.PARTIAL,
                    ),
                ),
            ),
        ),
    )
    assert assessment.readiness is CheckInputReadiness.READY


def test_resolved_none_blocks_unless_explicitly_allowed() -> None:
    evidence = FeatureEvidence(
        evidence_status=FeatureEvidenceStatus.FULL,
        source_table="fixture",
        actual_table_name="fixture",
        source_column="value",
    )
    snapshot = FeatureSnapshot(
        component_type="TEST",
        component_id="3",
        features={
            "test.value": FeatureValue(
                feature_name="test.value",
                value=None,
                evidence=(evidence,),
            )
        },
    )
    blocked = evaluate_check_input_preflight(
        snapshot=snapshot,
        spec=CheckInputPreflightSpec(
            consumer_id="none_blocked",
            required_features=(req("test.value"),),
        ),
    )
    allowed = evaluate_check_input_preflight(
        snapshot=snapshot,
        spec=CheckInputPreflightSpec(
            consumer_id="none_allowed",
            required_features=(
                req("test.value", allow_none=True),
            ),
        ),
    )
    assert blocked.feature_assessments[0].state is (
        FeatureRequirementState.NONE_NOT_ALLOWED
    )
    assert allowed.readiness is CheckInputReadiness.READY


def test_evidence_quality_blocks_when_not_accepted() -> None:
    evidence = FeatureEvidence(
        evidence_status=FeatureEvidenceStatus.PARTIAL,
        source_table="fixture",
        actual_table_name="fixture",
        source_column="value",
        reason="Partial evidence.",
    )
    snapshot = FeatureSnapshot(
        component_type="TEST",
        component_id="4",
        features={
            "test.value": FeatureValue(
                feature_name="test.value",
                value=1,
                status=FeatureValueStatus.RESOLVED,
                evidence=(evidence,),
            )
        },
    )
    assessment = evaluate_check_input_preflight(
        snapshot=snapshot,
        spec=CheckInputPreflightSpec(
            consumer_id="evidence_gate",
            required_features=(req("test.value"),),
        ),
    )
    assert assessment.feature_assessments[0].state is (
        FeatureRequirementState.EVIDENCE_INCOMPLETE
    )


def test_duplicate_feature_requirements_are_rejected() -> None:
    with pytest.raises(ValueError, match="duplicate feature"):
        CheckInputPreflightSpec(
            consumer_id="duplicate_features",
            required_features=(
                req("etabs.model.open"),
                req("etabs.model.open"),
            ),
        )


def test_empty_consumer_id_is_rejected() -> None:
    with pytest.raises(ValueError, match="consumer_id"):
        CheckInputPreflightSpec(
            consumer_id=" ",
            required_features=(req("etabs.model.open"),),
        )


def test_batch_evaluation_preserves_spec_order() -> None:
    assessments = evaluate_check_input_preflights(
        snapshot=gateway_snapshot(),
        specs=(
            CheckInputPreflightSpec(
                consumer_id="first",
                required_features=(req("etabs.model.open"),),
            ),
            CheckInputPreflightSpec(
                consumer_id="second",
                required_features=(
                    req("etabs.results.base_shear"),
                ),
            ),
        ),
    )
    assert tuple(item.consumer_id for item in assessments) == (
        "first",
        "second",
    )
    assert tuple(item.readiness for item in assessments) == (
        CheckInputReadiness.READY,
        CheckInputReadiness.BLOCKED,
    )


def test_assessment_contract_is_immutable() -> None:
    assessment = evaluate_check_input_preflight(
        snapshot=gateway_snapshot(),
        spec=CheckInputPreflightSpec(
            consumer_id="immutable",
            required_features=(req("etabs.model.open"),),
        ),
    )
    with pytest.raises(FrozenInstanceError):
        assessment.consumer_id = "changed"  # type: ignore[misc]
    with pytest.raises(TypeError):
        assessment.diagnostics["changed"] = True  # type: ignore[index]


def test_preflight_diagnostics_prove_no_execution() -> None:
    assessment = evaluate_check_input_preflight(
        snapshot=gateway_snapshot(),
        spec=CheckInputPreflightSpec(
            consumer_id="diagnostic_only",
            required_features=(req("etabs.model.open"),),
        ),
    )
    assert assessment.diagnostics == {
        "diagnostic_only": True,
        "check_input_constructed": False,
        "check_engine_invoked": False,
        "engineering_calculation_performed": False,
        "engineering_verdict_emitted": False,
        "purpose": "",
    }


def test_preflight_source_has_no_engine_or_result_boundary() -> None:
    path = (
        REPO_ROOT
        / "tbdy_engine"
        / "features"
        / "gateway_check_input_preflight.py"
    )
    tree = ast.parse(
        path.read_text(encoding="utf-8"),
        filename=str(path),
    )
    forbidden_modules = {
        "tbdy_engine.checks",
        "tbdy_engine.engine",
    }
    forbidden_calls = {
        "CheckEngine",
        "CheckResult",
        "evaluate_check",
        "run_checks",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            assert node.module not in forbidden_modules
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                name = node.func.id
            elif isinstance(node.func, ast.Attribute):
                name = node.func.attr
            else:
                name = ""
            assert name not in forbidden_calls
