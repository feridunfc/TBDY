from __future__ import annotations

from pathlib import Path

import pytest
import yaml

import tbdy_engine.checks.input_adapter as adapter_module
from tbdy_engine.checks.engine import MinimalCheckEngine
from tbdy_engine.checks.input_adapter import (
    GeometryCheckInput,
    build_geometry_check_inputs_from_feature_snapshot,
    build_geometry_check_inputs_from_feature_snapshot_and_coverage,
)
from tbdy_engine.coverage.models import (
    CoverageEvidenceStatus,
    CoveragePolicyStatus,
    CoverageRow,
    CoverageStatus,
)
from tbdy_engine.features.evidence import FeatureEvidence, FeatureEvidenceStatus
from tbdy_engine.features.snapshot import FeatureSnapshot
from tbdy_engine.features.value import FeatureValue

ROOT = Path(__file__).resolve().parents[3]


def _evidence(name: str, value: float) -> FeatureEvidence:
    return FeatureEvidence(
        evidence_status=FeatureEvidenceStatus.FULL,
        source_table="fixture_geometry",
        actual_table_name="Fixture Geometry",
        source_column=name,
        source_row={"component": "B1"},
        raw_value=value,
        normalized_value=value,
        unit="mm",
        resolver="p1_10_fixture",
    )


def _feature(name: str, value: float) -> FeatureValue:
    return FeatureValue(
        feature_name=name,
        value=value,
        unit="mm",
        semantic_role="GEOMETRY",
        evidence=(_evidence(name, value),),
    )


def _snapshot() -> FeatureSnapshot:
    return FeatureSnapshot(
        component_type="beam",
        component_id="B1",
        identity={"story": "+14.5", "section": "B30x60"},
        features={
            "beam_width_mm": _feature("beam_width_mm", 300.0),
            "beam_depth_mm": _feature("beam_depth_mm", 600.0),
        },
    )


def _coverage(
    check_id: str,
    required_features: tuple[str, ...],
    *,
    component_id: str = "B1",
    component_type: str = "beam",
    status: CoverageStatus = CoverageStatus.RUNNABLE,
    evidence_status: CoverageEvidenceStatus = CoverageEvidenceStatus.FULL,
) -> CoverageRow:
    extra = {}
    if status is not CoverageStatus.RUNNABLE:
        extra = {
            "reason": "Fixture coverage is not runnable",
            "expected_evidence_requirements": {
                required_features[0]: ("source_table",)
            },
        }
    return CoverageRow(
        check_id=check_id,
        component_type=component_type,
        component_id=component_id,
        required_features=required_features,
        resolved_features=(
            required_features if status is CoverageStatus.RUNNABLE else ()
        ),
        missing_features=(),
        required_design_context=(),
        resolved_design_context=(),
        missing_design_context=(),
        combo_policy_status=CoveragePolicyStatus.NOT_APPLICABLE,
        section_state_status=CoveragePolicyStatus.NOT_APPLICABLE,
        ductility_context_status=CoveragePolicyStatus.NOT_APPLICABLE,
        evidence_status=evidence_status,
        coverage_status=status,
        **extra,
    )


def _definitions():
    return yaml.safe_load(
        (ROOT / "tbdy_engine/catalogs/check_catalog.yaml").read_text(
            encoding="utf-8"
        )
    )["checks"]


def test_authoritative_coverage_row_is_preserved_on_input() -> None:
    snapshot = _snapshot()
    coverage = _coverage(
        "beam_geometry_min_width",
        ("beam_width_mm",),
    )
    result = build_geometry_check_inputs_from_feature_snapshot_and_coverage(
        snapshot,
        (coverage,),
    )
    assert result.diagnostics == ()
    assert len(result.check_inputs) == 1
    item = result.check_inputs[0]
    assert isinstance(item, GeometryCheckInput)
    assert item.coverage is coverage


def test_authoritative_path_does_not_call_synthetic_coverage_builder(
    monkeypatch,
) -> None:
    snapshot = _snapshot()
    coverage = _coverage(
        "beam_geometry_min_width",
        ("beam_width_mm",),
    )

    def forbidden(**_kwargs):
        raise AssertionError("synthetic coverage builder was called")

    monkeypatch.setattr(
        adapter_module,
        "_build_runnable_coverage_row",
        forbidden,
    )
    result = build_geometry_check_inputs_from_feature_snapshot_and_coverage(
        snapshot,
        (coverage,),
    )
    assert len(result.check_inputs) == 1


def test_blocked_coverage_never_builds_check_input() -> None:
    result = build_geometry_check_inputs_from_feature_snapshot_and_coverage(
        _snapshot(),
        (
            _coverage(
                "beam_geometry_min_width",
                ("beam_width_mm",),
                status=CoverageStatus.BLOCKED,
                evidence_status=CoverageEvidenceStatus.MISSING,
            ),
        ),
    )
    assert result.check_inputs == ()
    assert result.diagnostics[0].status == "BLOCKED"


def test_partial_coverage_never_builds_check_input() -> None:
    result = build_geometry_check_inputs_from_feature_snapshot_and_coverage(
        _snapshot(),
        (
            _coverage(
                "beam_geometry_min_width",
                ("beam_width_mm",),
                status=CoverageStatus.PARTIAL,
                evidence_status=CoverageEvidenceStatus.PARTIAL,
            ),
        ),
    )
    assert result.check_inputs == ()
    assert result.diagnostics[0].status == "BLOCKED"


def test_component_identity_mismatch_blocks() -> None:
    result = build_geometry_check_inputs_from_feature_snapshot_and_coverage(
        _snapshot(),
        (
            _coverage(
                "beam_geometry_min_width",
                ("beam_width_mm",),
                component_id="OTHER",
            ),
        ),
    )
    assert result.check_inputs == ()
    assert "component_id" in result.diagnostics[0].reason


def test_required_feature_contract_mismatch_blocks() -> None:
    result = build_geometry_check_inputs_from_feature_snapshot_and_coverage(
        _snapshot(),
        (
            _coverage(
                "beam_geometry_min_width",
                ("beam_depth_mm",),
            ),
        ),
    )
    assert result.check_inputs == ()
    assert "required_features" in result.diagnostics[0].reason


def test_duplicate_coverage_rows_are_rejected() -> None:
    coverage = _coverage(
        "beam_geometry_min_width",
        ("beam_width_mm",),
    )
    with pytest.raises(ValueError, match="duplicate check_id"):
        build_geometry_check_inputs_from_feature_snapshot_and_coverage(
            _snapshot(),
            (coverage, coverage),
        )


def test_empty_coverage_is_diagnostic_and_fail_closed() -> None:
    result = build_geometry_check_inputs_from_feature_snapshot_and_coverage(
        _snapshot(),
        (),
    )
    assert result.check_inputs == ()
    assert result.diagnostics[0].status == "NO_DATA"


def test_authoritative_input_runs_through_existing_engine() -> None:
    snapshot = _snapshot()
    coverage = _coverage(
        "beam_geometry_min_width",
        ("beam_width_mm",),
    )
    adapter_result = (
        build_geometry_check_inputs_from_feature_snapshot_and_coverage(
            snapshot,
            (coverage,),
        )
    )
    item = adapter_result.check_inputs[0]
    engine = MinimalCheckEngine(_definitions())
    check_result = engine.run_check(
        item.check_id,
        item.snapshot,
        item.coverage,
    )
    assert check_result.check_id == "beam_geometry_min_width"
    assert check_result.component == "B1"


def test_legacy_compatibility_path_remains_available() -> None:
    result = build_geometry_check_inputs_from_feature_snapshot(_snapshot())
    assert len(result.check_inputs) == 3
