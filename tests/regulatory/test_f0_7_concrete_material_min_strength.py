from __future__ import annotations

from dataclasses import FrozenInstanceError, fields
import math
from pathlib import Path

import pytest

from tbdy_engine.checks.result import CheckResult, CheckStatus, EvaluationLevel
from tbdy_engine.regulatory.concrete_material_min_strength import (
    CODE_REF,
    CONCRETE_MATERIAL_MIN_STRENGTH_CHECK_SPEC,
    CONCRETE_MATERIAL_MIN_STRENGTH_DEPENDENCIES,
    EVIDENCE_TRACE_KEY,
    F0_7_CONCRETE_MATERIAL_MIN_STRENGTH_REGISTRY,
    FCK_KEY,
    MIN_FCK_MPA,
    RULE_ID,
    RULE_VERSION,
    ConcreteMaterialMinStrengthApplicabilityInput,
    ConcreteMaterialMinStrengthExecutionInput,
    concrete_material_min_strength_applicability,
    evaluate_concrete_material_min_strength,
)
from tbdy_engine.regulatory.contracts import (
    ApplicabilityState,
    AvailabilityState,
    DependencyKey,
    DependencySourceKind,
    DirectionPolicy,
    Grain,
    PhysicalDimension,
    PopulationRequirement,
    RuleId,
    RuleInstanceId,
    ScopePolicy,
    SemanticType,
)
from tbdy_engine.regulatory.kernel import MaterializedDependency, PopulationCompleteness, RuleExecutionEnvelope
from tbdy_engine.regulatory.units import UNIT_DIMENSIONLESS, UNIT_MPA


def _envelope(scope: str = "MAT_C25") -> RuleExecutionEnvelope:
    instance = RuleInstanceId.build(rule_id=RULE_ID, grain=Grain.MATERIAL_DEFINITION, scope_ref=scope)
    return RuleExecutionEnvelope(
        plan_identity="plan:f0.7:test",
        instance_id=instance,
        rule_id=RULE_ID,
        rule_version=RULE_VERSION,
        declared_dependency_refs=(FCK_KEY, EVIDENCE_TRACE_KEY),
    )


def _dep(key: DependencyKey, *, value: object, semantic: SemanticType, dimension: PhysicalDimension, unit) -> MaterializedDependency:
    return MaterializedDependency(
        key=key,
        source_kind=DependencySourceKind.FACT if key == FCK_KEY else DependencySourceKind.CONTEXT,
        semantic_type=semantic,
        physical_dimension=dimension,
        grain=Grain.MATERIAL_DEFINITION,
        scope_ref="MAT_C25",
        direction=None,
        unit=unit,
        availability=AvailabilityState.RESOLVED,
        population_completeness=PopulationCompleteness.FULL,
        value=value,
        authority_ref=f"external:{key.value}",
        evidence_refs=(f"external:{key.value}",),
    )


def _execution_input(fck: object, *, evidence=("evidence:material:MAT_C25",)) -> ConcreteMaterialMinStrengthExecutionInput:
    return ConcreteMaterialMinStrengthExecutionInput.from_declared_dependencies(
        _envelope(),
        (
            _dep(FCK_KEY, value=fck, semantic=SemanticType.CONCRETE_FCK, dimension=PhysicalDimension.STRESS, unit=UNIT_MPA),
            _dep(EVIDENCE_TRACE_KEY, value=evidence, semantic=SemanticType.CHECK_EVIDENCE_TRACE, dimension=PhysicalDimension.DIMENSIONLESS, unit=UNIT_DIMENSIONLESS),
        ),
    )


def test_rule_identity_basis_registry_and_exact_dependency_contracts() -> None:
    assert RULE_ID == RuleId("CONCRETE_MATERIAL_MIN_STRENGTH")
    assert RULE_VERSION == "f0.7-v1"
    assert CODE_REF == "TBDY-2018-7.2.5.1"
    assert MIN_FCK_MPA == 25.0
    spec = CONCRETE_MATERIAL_MIN_STRENGTH_CHECK_SPEC
    assert spec.rule_id == RULE_ID
    assert spec.rule_version == RULE_VERSION
    assert spec.code_refs == (CODE_REF,)
    assert spec.formal_result_type is CheckResult
    assert F0_7_CONCRETE_MATERIAL_MIN_STRENGTH_REGISTRY.rule_count == 1
    assert F0_7_CONCRETE_MATERIAL_MIN_STRENGTH_REGISTRY.rule(RULE_ID) is spec
    assert tuple(dep.key for dep in CONCRETE_MATERIAL_MIN_STRENGTH_DEPENDENCIES) == (FCK_KEY, EVIDENCE_TRACE_KEY)

    fck, evidence = CONCRETE_MATERIAL_MIN_STRENGTH_DEPENDENCIES
    assert (fck.source_kind, fck.semantic_type, fck.physical_dimension, fck.grain) == (
        DependencySourceKind.FACT, SemanticType.CONCRETE_FCK, PhysicalDimension.STRESS, Grain.MATERIAL_DEFINITION
    )
    assert fck.scope_policy is ScopePolicy.SAME_SCOPE
    assert fck.direction_policy is DirectionPolicy.NO_DIRECTION
    assert fck.unit_requirement == UNIT_MPA
    assert fck.required_availability is AvailabilityState.RESOLVED
    assert fck.population_completeness_requirement is PopulationRequirement.FULL

    assert (evidence.source_kind, evidence.semantic_type, evidence.physical_dimension, evidence.grain) == (
        DependencySourceKind.CONTEXT, SemanticType.CHECK_EVIDENCE_TRACE, PhysicalDimension.DIMENSIONLESS, Grain.MATERIAL_DEFINITION
    )
    assert evidence.scope_policy is ScopePolicy.SAME_SCOPE
    assert evidence.direction_policy is DirectionPolicy.NO_DIRECTION
    assert evidence.unit_requirement == UNIT_DIMENSIONLESS
    assert evidence.required_availability is AvailabilityState.RESOLVED
    assert evidence.population_completeness_requirement is PopulationRequirement.FULL


def test_applicability_truth_table_is_exact_and_typed() -> None:
    cases = (
        (True, True, ApplicabilityState.APPLIES),
        (False, True, ApplicabilityState.PROVEN_NOT_APPLICABLE),
        (True, False, ApplicabilityState.PROVEN_NOT_APPLICABLE),
        (False, None, ApplicabilityState.PROVEN_NOT_APPLICABLE),
        (None, False, ApplicabilityState.PROVEN_NOT_APPLICABLE),
        (True, None, ApplicabilityState.UNRESOLVED),
        (None, True, ApplicabilityState.UNRESOLVED),
        (None, None, ApplicabilityState.UNRESOLVED),
    )
    for concrete, used, expected in cases:
        value = ConcreteMaterialMinStrengthApplicabilityInput(concrete, used)
        assert concrete_material_min_strength_applicability(value) is expected
    with pytest.raises(TypeError, match="bool or None"):
        ConcreteMaterialMinStrengthApplicabilityInput("Concrete", True)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="bool or None"):
        ConcreteMaterialMinStrengthApplicabilityInput(True, "Beam")  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "fck,status,ratio",
    [
        (24.999, CheckStatus.FAIL, 24.999 / 25.0),
        (25.000, CheckStatus.OK, 1.0),
        (25.001, CheckStatus.OK, 25.001 / 25.0),
        (30.0, CheckStatus.OK, 30.0 / 25.0),
    ],
)
def test_evaluator_exact_boundary_ratio_and_canonical_result_fields(fck: float, status: CheckStatus, ratio: float) -> None:
    evidence = ("evidence:material:MAT_C25", ("source-row", "17"))
    result = evaluate_concrete_material_min_strength(_execution_input(fck, evidence=evidence))
    assert type(result) is CheckResult
    assert result.check_id == "CONCRETE_MATERIAL_MIN_STRENGTH"
    assert result.component == "MAT_C25"
    assert result.component_type == "concrete_material"
    assert result.story is None and result.section is None
    assert result.status is status
    assert result.value == fck and result.limit == 25.0
    assert result.demand is None and result.capacity is None
    assert result.ratio == ratio
    assert result.ratio_type == "actual_over_minimum"
    assert result.pass_rule == "fck_mpa >= 25.0"
    assert result.unit == "MPa"
    assert result.evaluation_level is EvaluationLevel.DESIGN_LEVEL
    assert result.evidence == evidence
    assert result.code_ref == "TBDY-2018-7.2.5.1"
    assert result.diagnostics == ()
    assert result.messages == ("Formal TBDY concrete material minimum-strength CheckResult",)


@pytest.mark.parametrize("bad", [True, False, "25", "C25", "C25/30", "25 MPa", None])
def test_execution_input_rejects_non_numeric_fck_without_parsing_or_conversion(bad) -> None:
    with pytest.raises(TypeError, match="numeric scalar"):
        _execution_input(bad)


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_execution_input_rejects_nonfinite_fck(bad: float) -> None:
    with pytest.raises(ValueError, match="finite"):
        _execution_input(bad)


def test_execution_input_requires_exact_declared_dependency_keys_and_shapes() -> None:
    envelope = _envelope()
    fck = _dep(FCK_KEY, value=25.0, semantic=SemanticType.CONCRETE_FCK, dimension=PhysicalDimension.STRESS, unit=UNIT_MPA)
    evidence = _dep(EVIDENCE_TRACE_KEY, value=("evidence:1",), semantic=SemanticType.CHECK_EVIDENCE_TRACE, dimension=PhysicalDimension.DIMENSIONLESS, unit=UNIT_DIMENSIONLESS)
    with pytest.raises(ValueError, match="unexpected dependency keys"):
        ConcreteMaterialMinStrengthExecutionInput.from_declared_dependencies(envelope, (fck,))
    with pytest.raises(ValueError, match="unexpected dependency keys"):
        ConcreteMaterialMinStrengthExecutionInput.from_declared_dependencies(envelope, (fck, evidence, evidence))
    extra = MaterializedDependency(
        key=DependencyKey("extra"), source_kind=DependencySourceKind.CONTEXT,
        semantic_type=SemanticType.CHECK_EVIDENCE_TRACE, physical_dimension=PhysicalDimension.DIMENSIONLESS,
        grain=Grain.MATERIAL_DEFINITION, scope_ref="MAT_C25", direction=None, unit=UNIT_DIMENSIONLESS,
        availability=AvailabilityState.RESOLVED, population_completeness=PopulationCompleteness.FULL,
        value=("extra",), authority_ref="external:extra",
    )
    with pytest.raises(ValueError, match="unexpected dependency keys"):
        ConcreteMaterialMinStrengthExecutionInput.from_declared_dependencies(envelope, (fck, evidence, extra))
    with pytest.raises(TypeError, match="MaterializedDependency"):
        ConcreteMaterialMinStrengthExecutionInput.from_declared_dependencies(envelope, (fck, object()))  # type: ignore[arg-type]


def test_material_identity_comes_only_from_envelope_scope_and_input_is_frozen() -> None:
    inp = _execution_input(25.0, evidence=("material_ref:NOT_THE_SCOPE",))
    assert inp.material_ref == "MAT_C25"
    assert inp.evidence == ("material_ref:NOT_THE_SCOPE",)
    assert {item.name for item in fields(ConcreteMaterialMinStrengthExecutionInput)} == {"envelope", "material_ref", "fck_mpa", "evidence"}
    assert not hasattr(inp, "dependencies")
    with pytest.raises(FrozenInstanceError):
        inp.fck_mpa = 30.0  # type: ignore[misc]
    with pytest.raises(ValueError, match="scope_ref"):
        ConcreteMaterialMinStrengthExecutionInput(envelope=_envelope(), material_ref="OTHER", fck_mpa=25.0, evidence=())


def test_rule_module_static_architecture_guards() -> None:
    module_path = Path(__file__).resolve().parents[2] / "tbdy_engine" / "regulatory" / "concrete_material_min_strength.py"
    source = module_path.read_text(encoding="utf-8")
    for token in (
        "tbdy_engine.product_reports", "tbdy_engine.etabs", "packages.etabs_gateway",
        "tbdy_engine.contracts", "tbdy_engine.catalogs", "tbdy_engine.features",
        "tbdy_engine.integration", "tbdy_engine.findings", "tbdy_engine.remediation",
        "tbdy_engine.assessment", "FeatureSnapshot", "F0EvidenceBinding", "MutationExecutor",
        "RemediationPlan", "FindingEngine", "full_tbdy_compliance_status", "_material_strength_row",
        "MATERIAL_LIMIT_CONTRACT_ID", "PENDING_CLAUSE_BINDING", "> 1000", "/ 1000",
    ):
        assert token not in source
