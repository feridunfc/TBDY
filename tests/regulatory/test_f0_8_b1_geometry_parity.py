from __future__ import annotations

import math
from pathlib import Path

import pytest

from tbdy_engine.checks.member_geometry import (
    BEAM_DEPTH_WIDTH_RATIO,
    BEAM_MIN_DEPTH_300,
    COLUMN_MIN_DIMENSION,
    MEMBER_GEOMETRY_REGISTRATIONS,
    evaluate_member_rule,
)
from tbdy_engine.checks.result import CheckStatus
from tbdy_engine.regulatory.b1_geometry_parity import (
    BEAM_DEPTH_KEY,
    BEAM_DEPTH_WIDTH_RATIO_CHECK_SPEC,
    BEAM_DEPTH_WIDTH_RATIO_DEPENDENCIES,
    BEAM_DEPTH_WIDTH_RATIO_RULE_ID,
    BEAM_MIN_DEPTH_CHECK_SPEC,
    BEAM_MIN_DEPTH_DEPENDENCIES,
    BEAM_MIN_DEPTH_RULE_ID,
    BEAM_WIDTH_KEY,
    COLUMN_DEPTH_KEY,
    COLUMN_MIN_DIMENSION_CHECK_SPEC,
    COLUMN_MIN_DIMENSION_DEPENDENCIES,
    COLUMN_MIN_DIMENSION_RULE_ID,
    COLUMN_WIDTH_KEY,
    EVIDENCE_TRACE_KEY,
    RULE_VERSION,
    SECTION_KEY,
    STORY_KEY,
    Beam7411ApplicabilityInput,
    BeamDepthWidthRatioExecutionInput,
    BeamMinDepthExecutionInput,
    ColumnMinDimensionApplicabilityInput,
    ColumnMinDimensionExecutionInput,
    beam_7411_applicability,
    column_min_dimension_applicability,
    evaluate_beam_depth_width_ratio,
    evaluate_beam_min_depth,
    evaluate_column_min_dimension,
)
from tbdy_engine.regulatory.contracts import (
    ApplicabilityState,
    AvailabilityState,
    DependencyKey,
    DependencySourceKind,
    Grain,
    PhysicalDimension,
    RuleId,
    RuleInstanceId,
    SemanticType,
)
from tbdy_engine.regulatory.kernel import MaterializedDependency, PopulationCompleteness, RuleExecutionEnvelope
from tbdy_engine.regulatory.units import UNIT_DIMENSIONLESS, UNIT_ENUM_STATE, UNIT_MM


def _envelope(rule_id: RuleId, scope: str = "B1") -> RuleExecutionEnvelope:
    instance = RuleInstanceId.build(rule_id=rule_id, grain=Grain.COMPONENT, scope_ref=scope)
    return RuleExecutionEnvelope(
        plan_identity="plan:f0.8:b1",
        instance_id=instance,
        rule_id=rule_id,
        rule_version=RULE_VERSION,
        declared_dependency_refs=(),
    )


def _dep(
    key: DependencyKey,
    *,
    value: object,
    semantic: SemanticType,
    dimension: PhysicalDimension,
    unit,
) -> MaterializedDependency:
    return MaterializedDependency(
        key=key,
        source_kind=DependencySourceKind.FACT if dimension is PhysicalDimension.LENGTH else DependencySourceKind.CONTEXT,
        semantic_type=semantic,
        physical_dimension=dimension,
        grain=Grain.COMPONENT,
        scope_ref="B1",
        direction=None,
        unit=unit,
        availability=AvailabilityState.RESOLVED,
        population_completeness=PopulationCompleteness.FULL,
        value=value,
        authority_ref=f"external:{key.value}",
        evidence_refs=(f"external:{key.value}",),
    )


def _context() -> tuple[MaterializedDependency, ...]:
    return (
        _dep(STORY_KEY, value="S1", semantic=SemanticType.COMPONENT_STORY, dimension=PhysicalDimension.ENUM_STATE, unit=UNIT_ENUM_STATE),
        _dep(SECTION_KEY, value="SEC", semantic=SemanticType.COMPONENT_SECTION, dimension=PhysicalDimension.ENUM_STATE, unit=UNIT_ENUM_STATE),
        _dep(EVIDENCE_TRACE_KEY, value=("evidence:B1",), semantic=SemanticType.CHECK_EVIDENCE_TRACE, dimension=PhysicalDimension.DIMENSIONLESS, unit=UNIT_DIMENSIONLESS),
    )


def _column(width: object, depth: object) -> ColumnMinDimensionExecutionInput:
    return ColumnMinDimensionExecutionInput.from_declared_dependencies(
        _envelope(COLUMN_MIN_DIMENSION_RULE_ID),
        (
            _dep(COLUMN_WIDTH_KEY, value=width, semantic=SemanticType.COLUMN_WIDTH, dimension=PhysicalDimension.LENGTH, unit=UNIT_MM),
            _dep(COLUMN_DEPTH_KEY, value=depth, semantic=SemanticType.COLUMN_DEPTH, dimension=PhysicalDimension.LENGTH, unit=UNIT_MM),
            *_context(),
        ),
    )


def _beam_depth(depth: object) -> BeamMinDepthExecutionInput:
    return BeamMinDepthExecutionInput.from_declared_dependencies(
        _envelope(BEAM_MIN_DEPTH_RULE_ID),
        (
            _dep(BEAM_DEPTH_KEY, value=depth, semantic=SemanticType.BEAM_DEPTH, dimension=PhysicalDimension.LENGTH, unit=UNIT_MM),
            *_context(),
        ),
    )


def _beam_ratio(depth: object, width: object) -> BeamDepthWidthRatioExecutionInput:
    return BeamDepthWidthRatioExecutionInput.from_declared_dependencies(
        _envelope(BEAM_DEPTH_WIDTH_RATIO_RULE_ID),
        (
            _dep(BEAM_DEPTH_KEY, value=depth, semantic=SemanticType.BEAM_DEPTH, dimension=PhysicalDimension.LENGTH, unit=UNIT_MM),
            _dep(BEAM_WIDTH_KEY, value=width, semantic=SemanticType.BEAM_WIDTH, dimension=PhysicalDimension.LENGTH, unit=UNIT_MM),
            *_context(),
        ),
    )


def _assert_parity(result, registration_id: str, variables: dict[str, float]) -> None:
    registration = MEMBER_GEOMETRY_REGISTRATIONS[registration_id]
    legacy = evaluate_member_rule(registration, variables)
    assert result.value == legacy.value
    assert result.limit == legacy.limit
    assert result.ratio == legacy.ratio
    assert result.ratio_type == legacy.ratio_type
    assert result.pass_rule == legacy.ratio_type
    assert result.unit == legacy.unit
    assert result.status is (CheckStatus.OK if legacy.is_satisfied else CheckStatus.FAIL)
    assert result.code_ref == registration.code_ref
    assert result.component_type == registration.component_type
    assert result.story == "S1"
    assert result.section == "SEC"
    assert result.evidence == ("evidence:B1",)


def test_b1_rule_ids_versions_and_dependency_contracts_are_exact() -> None:
    assert COLUMN_MIN_DIMENSION_RULE_ID == RuleId("column_geometry_min_dimension")
    assert BEAM_MIN_DEPTH_RULE_ID == RuleId("beam_geometry_min_depth")
    assert BEAM_DEPTH_WIDTH_RATIO_RULE_ID == RuleId("beam_depth_width_ratio")
    assert RULE_VERSION == "f0.8-parity-v1"
    assert COLUMN_MIN_DIMENSION_CHECK_SPEC.rule_version == RULE_VERSION
    assert BEAM_MIN_DEPTH_CHECK_SPEC.rule_version == RULE_VERSION
    assert BEAM_DEPTH_WIDTH_RATIO_CHECK_SPEC.rule_version == RULE_VERSION
    assert tuple(dep.key for dep in COLUMN_MIN_DIMENSION_DEPENDENCIES) == (
        COLUMN_WIDTH_KEY, COLUMN_DEPTH_KEY, STORY_KEY, SECTION_KEY, EVIDENCE_TRACE_KEY
    )
    assert tuple(dep.key for dep in BEAM_MIN_DEPTH_DEPENDENCIES) == (
        BEAM_DEPTH_KEY, STORY_KEY, SECTION_KEY, EVIDENCE_TRACE_KEY
    )
    assert tuple(dep.key for dep in BEAM_DEPTH_WIDTH_RATIO_DEPENDENCIES) == (
        BEAM_DEPTH_KEY, BEAM_WIDTH_KEY, STORY_KEY, SECTION_KEY, EVIDENCE_TRACE_KEY
    )
    for spec in (COLUMN_MIN_DIMENSION_CHECK_SPEC, BEAM_MIN_DEPTH_CHECK_SPEC, BEAM_DEPTH_WIDTH_RATIO_CHECK_SPEC):
        assert all(dep.grain is Grain.COMPONENT for dep in spec.dependencies)
        assert all(dep.direction_policy.value == "NO_DIRECTION" for dep in spec.dependencies)


def test_column_and_beam_applicability_truth_tables_are_exact() -> None:
    for is_column, rectangular, expected in (
        (True, True, ApplicabilityState.APPLIES),
        (False, True, ApplicabilityState.PROVEN_NOT_APPLICABLE),
        (True, False, ApplicabilityState.PROVEN_NOT_APPLICABLE),
        (False, None, ApplicabilityState.PROVEN_NOT_APPLICABLE),
        (None, False, ApplicabilityState.PROVEN_NOT_APPLICABLE),
        (True, None, ApplicabilityState.UNRESOLVED),
        (None, True, ApplicabilityState.UNRESOLVED),
        (None, None, ApplicabilityState.UNRESOLVED),
    ):
        assert column_min_dimension_applicability(
            ColumnMinDimensionApplicabilityInput(is_column, rectangular)
        ) is expected

    for is_beam, applies, expected in (
        (True, True, ApplicabilityState.APPLIES),
        (False, True, ApplicabilityState.PROVEN_NOT_APPLICABLE),
        (True, False, ApplicabilityState.PROVEN_NOT_APPLICABLE),
        (False, None, ApplicabilityState.PROVEN_NOT_APPLICABLE),
        (None, False, ApplicabilityState.PROVEN_NOT_APPLICABLE),
        (True, None, ApplicabilityState.UNRESOLVED),
        (None, True, ApplicabilityState.UNRESOLVED),
        (None, None, ApplicabilityState.UNRESOLVED),
    ):
        assert beam_7411_applicability(Beam7411ApplicabilityInput(is_beam, applies)) is expected

    with pytest.raises(TypeError, match="bool or None"):
        Beam7411ApplicabilityInput("beam", True)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="bool or None"):
        ColumnMinDimensionApplicabilityInput(True, "RECTANGULAR")  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "width,depth",
    [(299.999, 300.0), (300.0, 300.0), (300.0, 299.999), (301.0, 500.0)],
)
def test_column_min_dimension_direct_legacy_parity(width: float, depth: float) -> None:
    result = evaluate_column_min_dimension(_column(width, depth))
    _assert_parity(
        result,
        COLUMN_MIN_DIMENSION,
        {"column_width_mm": width, "column_depth_mm": depth},
    )


@pytest.mark.parametrize("depth", [299.999, 300.0, 300.001])
def test_beam_min_depth_direct_legacy_parity(depth: float) -> None:
    result = evaluate_beam_min_depth(_beam_depth(depth))
    _assert_parity(result, BEAM_MIN_DEPTH_300, {"beam_depth_mm": depth})


@pytest.mark.parametrize("depth", [349.9, 350.0, 350.1])
def test_beam_depth_width_ratio_direct_legacy_parity(depth: float) -> None:
    result = evaluate_beam_depth_width_ratio(_beam_ratio(depth, 100.0))
    _assert_parity(
        result,
        BEAM_DEPTH_WIDTH_RATIO,
        {"beam_depth_mm": depth, "beam_width_mm": 100.0},
    )


@pytest.mark.parametrize("bad", [None, True, False, "300", 0.0, -1.0, math.nan, math.inf, -math.inf])
def test_resolved_b1_geometry_must_be_positive_finite_numeric(bad: object) -> None:
    expectation = TypeError if bad is None or isinstance(bad, (bool, str)) else ValueError
    with pytest.raises(expectation):
        _beam_depth(bad)


def test_execution_inputs_require_exact_dependency_sets_and_component_grain() -> None:
    envelope = _envelope(BEAM_MIN_DEPTH_RULE_ID)
    depth = _dep(BEAM_DEPTH_KEY, value=300.0, semantic=SemanticType.BEAM_DEPTH, dimension=PhysicalDimension.LENGTH, unit=UNIT_MM)
    with pytest.raises(ValueError, match="unexpected dependency keys"):
        BeamMinDepthExecutionInput.from_declared_dependencies(envelope, (depth,))

    wrong = RuleExecutionEnvelope(
        plan_identity="plan:f0.8:wrong",
        instance_id=RuleInstanceId.build(
            rule_id=BEAM_MIN_DEPTH_RULE_ID,
            grain=Grain.MATERIAL_DEFINITION,
            scope_ref="B1",
        ),
        rule_id=BEAM_MIN_DEPTH_RULE_ID,
        rule_version=RULE_VERSION,
        declared_dependency_refs=(),
    )
    with pytest.raises(ValueError, match="Grain.COMPONENT"):
        BeamMinDepthExecutionInput.from_declared_dependencies(wrong, (depth, *_context()))


def test_b1_module_static_architecture_guards() -> None:
    path = Path(__file__).resolve().parents[2] / "tbdy_engine" / "regulatory" / "b1_geometry_parity.py"
    source = path.read_text(encoding="utf-8")
    for token in (
        "tbdy_engine.product_reports",
        "tbdy_engine.etabs",
        "packages.etabs_gateway",
        "tbdy_engine.features",
        "tbdy_engine.integration",
        "tbdy_engine.findings",
        "tbdy_engine.remediation",
        "tbdy_engine.catalogs",
        "yaml",
        "MinimalCheckEngine",
        "MutationExecutor",
        "RemediationPlan",
        "full_tbdy_compliance_status",
        "GenericGeometryRule",
        "GenericThresholdRule",
        "GenericRatioRule",
        "FormulaDSL",
        "ComparatorRegistry",
        "> 1000",
        "/ 1000",
    ):
        assert token not in source
