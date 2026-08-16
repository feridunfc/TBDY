from __future__ import annotations

from tbdy_engine.checks.engine import MinimalCheckEngine
from tbdy_engine.checks.input_adapter import CheckExecutionContext, GeometryCheckInput
from tbdy_engine.checks.member_geometry import (
    BEAM_7411_APPLICABILITY_CONTEXT,
    BEAM_MIN_WIDTH,
    COLUMN_MIN_DIMENSION,
    COLUMN_SECTION_SHAPE_CONTEXT,
    registration_check_definitions,
)
from tbdy_engine.checks.result import CheckStatus
from tbdy_engine.coverage.models import CoverageRow, CoverageStatus
from tbdy_engine.features.evidence import FeatureEvidence, FeatureEvidenceStatus
from tbdy_engine.features.snapshot import FeatureSnapshot
from tbdy_engine.features.value import FeatureValue, FeatureValueStatus


def _feature(name: str, value: float) -> FeatureValue:
    evidence = FeatureEvidence(
        evidence_status=FeatureEvidenceStatus.FULL,
        source_table="fixture",
        actual_table_name="fixture",
        source_column=name,
        source_row={"component": "fixture"},
        raw_value=value,
        normalized_value=value,
        unit="mm",
        resolver="test_fixture",
    )
    return FeatureValue(
        feature_name=name,
        value=value,
        unit="mm",
        semantic_role="GEOMETRY",
        status=FeatureValueStatus.RESOLVED,
        evidence=(evidence,),
    )


def _snapshot(component_type: str, component_id: str = "X1", **features: float) -> FeatureSnapshot:
    return FeatureSnapshot(
        component_type=component_type,
        component_id=component_id,
        identity={"story": "+14.5", "section": "TEST"},
        features={name: _feature(name, value) for name, value in features.items()},
    )


def _run(check_id: str, snapshot: FeatureSnapshot, context: dict[str, object]):
    definition = registration_check_definitions()[check_id]
    required = tuple(definition["required_features"])
    coverage = CoverageRow(
        check_id=check_id,
        component_type=snapshot.component_type,
        component_id=snapshot.component_id,
        required_features=required,
        resolved_features=required,
        coverage_status=CoverageStatus.RUNNABLE,
    )
    check_input = GeometryCheckInput(
        check_id=check_id,
        component_id=snapshot.component_id,
        component_type=snapshot.component_type,
        story="+14.5",
        section="TEST",
        required_features=required,
        snapshot=snapshot,
        coverage=coverage,
        evidence_by_feature={name: tuple(snapshot.features[name].evidence) for name in required},
        execution_context=CheckExecutionContext(values=context),
    )
    return MinimalCheckEngine(registration_check_definitions()).run_input(check_input)


def test_uppercase_beam_component_type_runs_beam_geometry_check():
    result = _run(
        BEAM_MIN_WIDTH,
        _snapshot("BEAM", beam_width_mm=400),
        {BEAM_7411_APPLICABILITY_CONTEXT: True},
    )

    assert result.status == CheckStatus.OK
    assert result.value == 400
    assert result.limit == 250


def test_uppercase_column_component_type_runs_column_geometry_check():
    result = _run(
        COLUMN_MIN_DIMENSION,
        _snapshot("COLUMN", column_width_mm=800, column_depth_mm=800),
        {COLUMN_SECTION_SHAPE_CONTEXT: "RECTANGULAR"},
    )

    assert result.status == CheckStatus.OK
    assert result.value == 800
    assert result.limit == 300


def test_real_component_type_mismatch_still_returns_out_of_scope():
    result = _run(
        BEAM_MIN_WIDTH,
        _snapshot("WALL", beam_width_mm=400),
        {BEAM_7411_APPLICABILITY_CONTEXT: True},
    )

    assert result.status == CheckStatus.OUT_OF_SCOPE
