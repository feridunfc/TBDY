from __future__ import annotations

from pathlib import Path

import yaml

from tbdy_engine.checks.engine import MinimalCheckEngine
from tbdy_engine.checks.input_adapter import CheckExecutionContext, GeometryCheckInput
from tbdy_engine.checks.member_geometry import (
    BEAM_7411_APPLICABILITY_CONTEXT,
    BEAM_DEPTH_WIDTH_RATIO,
    BEAM_MIN_WIDTH,
    registration_check_definitions,
)
from tbdy_engine.checks.result import CheckStatus, EvaluationLevel
from tbdy_engine.coverage.models import CoverageExpectedSource, CoverageRow, CoverageStatus, ExpectedSourceKind
from tbdy_engine.features.evidence import FeatureEvidence, FeatureEvidenceStatus
from tbdy_engine.features.snapshot import FeatureSnapshot
from tbdy_engine.features.value import FeatureValue, FeatureValueStatus

ROOT = Path(__file__).resolve().parents[2]


def _defs():
    return yaml.safe_load((ROOT / "tbdy_engine/catalogs/check_catalog.yaml").read_text(encoding="utf-8"))["checks"]


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
    return FeatureValue(feature_name=name, value=value, unit="mm", semantic_role="GEOMETRY", status=FeatureValueStatus.RESOLVED, evidence=(evidence,))


def _snapshot(component_type: str = "beam", **features: float) -> FeatureSnapshot:
    return FeatureSnapshot(
        component_type=component_type,
        component_id="X1",
        identity={"story": "+14.5", "section": "TEST"},
        features={name: _feature(name, value) for name, value in features.items()},
    )


def _coverage(check_id: str, component_type: str = "beam", required: tuple[str, ...] = ("beam_width_mm",), status: CoverageStatus = CoverageStatus.RUNNABLE) -> CoverageRow:
    kwargs = {}
    reason = None
    if status == CoverageStatus.BLOCKED:
        reason = "policy pending"
        kwargs["missing_feature_sources"] = {
            required[0]: CoverageExpectedSource(source_kind=ExpectedSourceKind.UNKNOWN, feature_name=required[0])
        }
    return CoverageRow(
        check_id=check_id,
        component_type=component_type,
        component_id="X1",
        required_features=required,
        resolved_features=() if status == CoverageStatus.BLOCKED else required,
        coverage_status=status,
        reason=reason,
        **kwargs,
    )


def _run_member(check_id: str, snapshot: FeatureSnapshot, coverage: CoverageRow):
    required = tuple(coverage.required_features)
    check_input = GeometryCheckInput(
        check_id=check_id,
        component_id=snapshot.component_id,
        component_type=snapshot.component_type,
        story="+14.5",
        section="TEST",
        required_features=required,
        snapshot=snapshot,
        coverage=coverage,
        evidence_by_feature={
            name: tuple(snapshot.features[name].evidence) if name in snapshot.features else ()
            for name in required
        },
        execution_context=CheckExecutionContext(values={BEAM_7411_APPLICABILITY_CONTEXT: True}),
    )
    return MinimalCheckEngine(registration_check_definitions()).run_input(check_input)


def test_missing_required_feature_returns_no_data_not_failure():
    result = _run_member(
        BEAM_MIN_WIDTH,
        _snapshot("beam"),
        _coverage(BEAM_MIN_WIDTH, required=("beam_width_mm",)),
    )
    assert result.status == CheckStatus.NO_DATA
    assert result.evaluation_level == EvaluationLevel.NO_DATA


def test_zero_width_for_depth_width_ratio_blocks_invalid_formal_input():
    result = _run_member(
        BEAM_DEPTH_WIDTH_RATIO,
        _snapshot("beam", beam_depth_mm=700, beam_width_mm=0),
        _coverage(BEAM_DEPTH_WIDTH_RATIO, required=("beam_depth_mm", "beam_width_mm")),
    )
    assert result.status == CheckStatus.BLOCKED
    assert result.evaluation_level == EvaluationLevel.NO_DATA


def test_blocked_coverage_returns_blocked_not_no_data_or_failure():
    result = _run_member(
        BEAM_MIN_WIDTH,
        _snapshot("beam", beam_width_mm=400),
        _coverage(BEAM_MIN_WIDTH, required=("beam_width_mm",), status=CoverageStatus.BLOCKED),
    )
    assert result.status == CheckStatus.BLOCKED
    assert result.evaluation_level == EvaluationLevel.NO_DATA


def test_component_type_mismatch_returns_out_of_scope():
    result = _run_member(
        BEAM_MIN_WIDTH,
        _snapshot("column", beam_width_mm=400),
        _coverage(BEAM_MIN_WIDTH, component_type="beam", required=("beam_width_mm",)),
    )
    assert result.status == CheckStatus.OUT_OF_SCOPE
    assert result.evaluation_level == EvaluationLevel.NO_DATA


def test_forbidden_non_geometry_checks_cannot_execute():
    engine = MinimalCheckEngine(_defs())
    snapshot = _snapshot("beam", beam_width_mm=400, beam_depth_mm=700)
    for check_id in (
        "beam_flexure_top_selected_ge_governing_required",
        "beam_shear_ve_le_vr",
        "beam_capacity_design_shear",
    ):
        result = engine.run_check(check_id, snapshot, _coverage(check_id, required=("beam_width_mm",)))
        assert result.status == CheckStatus.BLOCKED
        assert result.evaluation_level == EvaluationLevel.NO_DATA
