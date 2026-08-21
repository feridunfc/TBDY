from __future__ import annotations

import math
from pathlib import Path

import pytest

from tbdy_engine.checks.result import CheckStatus
from tbdy_engine.checks.wall_evaluators import WALL_EVALUATORS
from tbdy_engine.checks.wall_pack_a_contract import PACK_A_CHECK_DEFINITIONS
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
from tbdy_engine.regulatory.wall_pack_a_geometry_parity import (
    EVIDENCE_TRACE_KEY,
    RULE_VERSION,
    SECTION_KEY,
    STORY_KEY,
    WALL_DEFINITION_CODE_REF,
    WALL_DEFINITION_GE6_CHECK_SPEC,
    WALL_DEFINITION_RULE_ID,
    WALL_GEOM_DEFINITION_LW_BW_GE6,
    WALL_GEOM_RESTRAINED_LEG_THICKNESS,
    WALL_GEOM_UNRESTRAINED_THICKNESS_GE_L30,
    WALL_LENGTH_KEY,
    WALL_RESTRAINED_LEG_CODE_REF,
    WALL_RESTRAINED_LEG_RULE_ID,
    WALL_RESTRAINED_LEG_THICKNESS_CHECK_SPEC,
    WALL_STORY_HEIGHT_KEY,
    WALL_THICKNESS_KEY,
    WALL_UNRESTRAINED_CODE_REF,
    WALL_UNRESTRAINED_LENGTH_KEY,
    WALL_UNRESTRAINED_RULE_ID,
    WALL_UNRESTRAINED_THICKNESS_CHECK_SPEC,
    WallDefinitionGE6ApplicabilityInput,
    WallDefinitionGE6ExecutionInput,
    WallRestrainedLegApplicabilityInput,
    WallRestrainedLegThicknessExecutionInput,
    WallUnrestrainedThicknessApplicabilityInput,
    WallUnrestrainedThicknessExecutionInput,
    evaluate_wall_definition_ge6,
    evaluate_wall_restrained_leg_thickness,
    evaluate_wall_unrestrained_thickness,
    wall_definition_ge6_applicability,
    wall_restrained_leg_applicability,
    wall_unrestrained_thickness_applicability,
)


def _envelope(rule_id: RuleId, scope: str = "W1") -> RuleExecutionEnvelope:
    instance = RuleInstanceId.build(rule_id=rule_id, grain=Grain.COMPONENT, scope_ref=scope)
    return RuleExecutionEnvelope(
        plan_identity="plan:f0.8:wall",
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
        scope_ref="W1",
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
        _dep(SECTION_KEY, value="W250", semantic=SemanticType.COMPONENT_SECTION, dimension=PhysicalDimension.ENUM_STATE, unit=UNIT_ENUM_STATE),
        _dep(EVIDENCE_TRACE_KEY, value=("evidence:wall:W1",), semantic=SemanticType.CHECK_EVIDENCE_TRACE, dimension=PhysicalDimension.DIMENSIONLESS, unit=UNIT_DIMENSIONLESS),
    )


def _definition(length: object, thickness: object) -> WallDefinitionGE6ExecutionInput:
    return WallDefinitionGE6ExecutionInput.from_declared_dependencies(
        _envelope(WALL_DEFINITION_RULE_ID),
        (
            _dep(WALL_LENGTH_KEY, value=length, semantic=SemanticType.WALL_LENGTH, dimension=PhysicalDimension.LENGTH, unit=UNIT_MM),
            _dep(WALL_THICKNESS_KEY, value=thickness, semantic=SemanticType.WALL_THICKNESS, dimension=PhysicalDimension.LENGTH, unit=UNIT_MM),
            *_context(),
        ),
    )


def _unrestrained(thickness: object, length: object) -> WallUnrestrainedThicknessExecutionInput:
    return WallUnrestrainedThicknessExecutionInput.from_declared_dependencies(
        _envelope(WALL_UNRESTRAINED_RULE_ID),
        (
            _dep(WALL_THICKNESS_KEY, value=thickness, semantic=SemanticType.WALL_THICKNESS, dimension=PhysicalDimension.LENGTH, unit=UNIT_MM),
            _dep(WALL_UNRESTRAINED_LENGTH_KEY, value=length, semantic=SemanticType.WALL_UNRESTRAINED_PLAN_LENGTH, dimension=PhysicalDimension.LENGTH, unit=UNIT_MM),
            *_context(),
        ),
    )


def _restrained(thickness: object, story_height: object) -> WallRestrainedLegThicknessExecutionInput:
    return WallRestrainedLegThicknessExecutionInput.from_declared_dependencies(
        _envelope(WALL_RESTRAINED_LEG_RULE_ID),
        (
            _dep(WALL_THICKNESS_KEY, value=thickness, semantic=SemanticType.WALL_THICKNESS, dimension=PhysicalDimension.LENGTH, unit=UNIT_MM),
            _dep(WALL_STORY_HEIGHT_KEY, value=story_height, semantic=SemanticType.WALL_STORY_HEIGHT, dimension=PhysicalDimension.LENGTH, unit=UNIT_MM),
            *_context(),
        ),
    )


def _assert_wall_parity(result, check_id: str, variables: dict[str, float]) -> None:
    legacy = WALL_EVALUATORS[check_id](variables, {})
    definition = PACK_A_CHECK_DEFINITIONS[check_id]
    assert result.value == legacy.value
    assert result.limit == legacy.limit
    assert result.ratio == legacy.ratio
    assert result.ratio_type == legacy.ratio_type
    assert result.pass_rule == legacy.pass_rule
    assert result.unit == legacy.unit
    assert result.status is (CheckStatus.OK if legacy.is_satisfied else CheckStatus.FAIL)
    assert result.code_ref == definition["code_ref"]
    assert result.component_type == "wall"
    assert result.story == "S1"
    assert result.section == "W250"
    assert result.evidence == ("evidence:wall:W1",)


def test_wall_rule_ids_code_refs_and_versions_are_exact() -> None:
    assert WALL_DEFINITION_RULE_ID == RuleId("WALL_GEOM_DEFINITION_LW_BW_GE6")
    assert WALL_UNRESTRAINED_RULE_ID == RuleId("WALL_GEOM_UNRESTRAINED_THICKNESS_GE_L30")
    assert WALL_RESTRAINED_LEG_RULE_ID == RuleId("WALL_GEOM_RESTRAINED_LEG_THICKNESS")
    assert RULE_VERSION == "f0.8-parity-v1"
    assert WALL_DEFINITION_CODE_REF == "TBDY 2018 §7.6.1.2 first sentence"
    assert WALL_UNRESTRAINED_CODE_REF == "TBDY 2018 §7.6.1.2(b)"
    assert WALL_RESTRAINED_LEG_CODE_REF == "TBDY 2018 §7.6.1.2(c)"
    for spec in (
        WALL_DEFINITION_GE6_CHECK_SPEC,
        WALL_UNRESTRAINED_THICKNESS_CHECK_SPEC,
        WALL_RESTRAINED_LEG_THICKNESS_CHECK_SPEC,
    ):
        assert spec.rule_version == RULE_VERSION
        assert all(dep.grain is Grain.COMPONENT for dep in spec.dependencies)


def test_wall_definition_applicability_truth_table_is_exact() -> None:
    for is_wall, basement, expected in (
        (False, False, ApplicabilityState.PROVEN_NOT_APPLICABLE),
        (False, None, ApplicabilityState.PROVEN_NOT_APPLICABLE),
        (True, True, ApplicabilityState.PROVEN_NOT_APPLICABLE),
        (None, True, ApplicabilityState.PROVEN_NOT_APPLICABLE),
        (True, False, ApplicabilityState.APPLIES),
        (True, None, ApplicabilityState.UNRESOLVED),
        (None, False, ApplicabilityState.UNRESOLVED),
        (None, None, ApplicabilityState.UNRESOLVED),
    ):
        assert wall_definition_ge6_applicability(
            WallDefinitionGE6ApplicabilityInput(is_wall, basement)
        ) is expected


def test_wall_unrestrained_applicability_truth_table_is_exact() -> None:
    assert wall_unrestrained_thickness_applicability(
        WallUnrestrainedThicknessApplicabilityInput(True, False, True)
    ) is ApplicabilityState.APPLIES
    for args in (
        (False, False, True),
        (True, True, True),
        (True, False, False),
        (False, None, None),
    ):
        assert wall_unrestrained_thickness_applicability(
            WallUnrestrainedThicknessApplicabilityInput(*args)
        ) is ApplicabilityState.PROVEN_NOT_APPLICABLE
    for args in (
        (True, False, None),
        (True, None, True),
        (None, False, True),
        (None, None, None),
    ):
        assert wall_unrestrained_thickness_applicability(
            WallUnrestrainedThicknessApplicabilityInput(*args)
        ) is ApplicabilityState.UNRESOLVED


def test_wall_restrained_leg_applicability_truth_table_is_exact() -> None:
    assert wall_restrained_leg_applicability(
        WallRestrainedLegApplicabilityInput(True, False, True)
    ) is ApplicabilityState.APPLIES
    for args in (
        (False, False, True),
        (True, True, True),
        (True, False, False),
        (False, None, None),
    ):
        assert wall_restrained_leg_applicability(
            WallRestrainedLegApplicabilityInput(*args)
        ) is ApplicabilityState.PROVEN_NOT_APPLICABLE
    for args in (
        (True, False, None),
        (True, None, True),
        (None, False, True),
        (None, None, None),
    ):
        assert wall_restrained_leg_applicability(
            WallRestrainedLegApplicabilityInput(*args)
        ) is ApplicabilityState.UNRESOLVED


@pytest.mark.parametrize("length", [1499.9, 1500.0, 1500.1])
def test_wall_definition_ge6_direct_legacy_parity(length: float) -> None:
    result = evaluate_wall_definition_ge6(_definition(length, 250.0))
    _assert_wall_parity(
        result,
        WALL_GEOM_DEFINITION_LW_BW_GE6,
        {"wall_length_mm": length, "wall_thickness_mm": 250.0},
    )


@pytest.mark.parametrize("thickness", [249.9, 250.0, 250.1])
def test_wall_unrestrained_direct_legacy_parity(thickness: float) -> None:
    result = evaluate_wall_unrestrained_thickness(_unrestrained(thickness, 7500.0))
    _assert_wall_parity(
        result,
        WALL_GEOM_UNRESTRAINED_THICKNESS_GE_L30,
        {"wall_thickness_mm": thickness, "unrestrained_plan_length_mm": 7500.0},
    )


@pytest.mark.parametrize(
    "thickness,story_height",
    [(249.9, 4000.0), (250.0, 4000.0), (299.9, 6000.0), (300.0, 6000.0)],
)
def test_wall_restrained_leg_direct_legacy_parity(thickness: float, story_height: float) -> None:
    result = evaluate_wall_restrained_leg_thickness(_restrained(thickness, story_height))
    _assert_wall_parity(
        result,
        WALL_GEOM_RESTRAINED_LEG_THICKNESS,
        {"wall_thickness_mm": thickness, "story_height_mm": story_height},
    )


@pytest.mark.parametrize("bad", [None, True, False, "250", 0.0, -1.0, math.nan, math.inf, -math.inf])
def test_resolved_wall_geometry_must_be_positive_finite_numeric(bad: object) -> None:
    expectation = TypeError if bad is None or isinstance(bad, (bool, str)) else ValueError
    with pytest.raises(expectation):
        _definition(1500.0, bad)


def test_wall_execution_input_requires_exact_dependency_set() -> None:
    envelope = _envelope(WALL_DEFINITION_RULE_ID)
    length = _dep(WALL_LENGTH_KEY, value=1500.0, semantic=SemanticType.WALL_LENGTH, dimension=PhysicalDimension.LENGTH, unit=UNIT_MM)
    with pytest.raises(ValueError, match="unexpected dependency keys"):
        WallDefinitionGE6ExecutionInput.from_declared_dependencies(envelope, (length,))


def test_wall_production_module_has_no_legacy_yaml_runtime_dependency() -> None:
    path = Path(__file__).resolve().parents[2] / "tbdy_engine" / "regulatory" / "wall_pack_a_geometry_parity.py"
    source = path.read_text(encoding="utf-8")
    for token in (
        "yaml",
        "catalog",
        "wall_evaluators",
        "wall_pack_a_contract",
        "tbdy_engine.product_reports",
        "tbdy_engine.etabs",
        "packages.etabs_gateway",
        "tbdy_engine.features",
        "tbdy_engine.integration",
        "tbdy_engine.findings",
        "tbdy_engine.remediation",
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
