from __future__ import annotations

import inspect
from dataclasses import FrozenInstanceError, fields
from fractions import Fraction
from pathlib import Path

import pytest

from tbdy_engine.checks.result import CheckResult, CheckStatus
from tbdy_engine.regulatory import (
    ApplicabilityBinding,
    ApplicabilityState,
    AvailabilityState,
    CheckEvaluatorBinding,
    CheckSpec,
    ClosureExecutionStatus,
    CompiledClosureRecord,
    DependencyBindingRef,
    DependencyKey,
    DependencySourceKind,
    DependencySpec,
    DerivationEvaluatorBinding,
    DirectionPolicy,
    Grain,
    PhysicalDimension,
    PopulationRequirement,
    RegulatoryDerivationSpec,
    RegulatoryOutputContract,
    RegulatoryQuantity,
    RuleClosureOutcome,
    RuleId,
    RuleInstanceId,
    ScopePolicy,
    SemanticType,
    TBDYExecutionPlan,
    TypedDagContract,
    UNIT_DIMENSIONLESS,
    UNIT_KN,
    UNIT_KN_M,
    UNIT_N_MM,
    Unit,
    UnitConversionError,
    conversion_factor,
    units_convertible,
)


class ToyInput:
    pass


class MutablePayload:
    def __init__(self) -> None:
        self.items = []


def _applies(_: object) -> ApplicabilityState:
    return ApplicabilityState.APPLIES


def _derive(_: object) -> RegulatoryQuantity:
    raise AssertionError("F0.0 tests must not execute derivation evaluators")


def _check(_: object) -> CheckResult:
    raise AssertionError("F0.0 tests must not execute check evaluators")


def _dep(*, key: str = "FACT_A", unit=UNIT_DIMENSIONLESS, full: bool = False) -> DependencySpec:
    return DependencySpec(
        key=DependencyKey(key),
        source_kind=DependencySourceKind.FACT,
        semantic_type=SemanticType.TOY_INPUT,
        physical_dimension=PhysicalDimension.DIMENSIONLESS,
        grain=Grain.COMPONENT,
        scope_policy=ScopePolicy.SAME_SCOPE,
        direction_policy=DirectionPolicy.NO_DIRECTION,
        required_availability=AvailabilityState.RESOLVED,
        population_completeness_requirement=(
            PopulationRequirement.FULL if full else PopulationRequirement.ANY_RESOLVED
        ),
        unit_requirement=unit,
    )


def _bindings():
    return (
        ApplicabilityBinding("toy-applicability", ToyInput, _applies),
        DerivationEvaluatorBinding("toy-derivation", ToyInput, _derive),
        CheckEvaluatorBinding("toy-check", ToyInput, _check),
    )


def test_rule_id_rejects_blank_and_padded_aliases():
    with pytest.raises(ValueError):
        RuleId("")
    with pytest.raises(ValueError):
        RuleId("   ")
    with pytest.raises(ValueError, match="leading or trailing whitespace"):
        RuleId(" TOY_RULE")
    with pytest.raises(ValueError, match="leading or trailing whitespace"):
        RuleId("TOY_RULE ")
    assert RuleId("TOY_RULE").value == "TOY_RULE"


def test_rule_id_deterministic_equality_and_hash():
    assert RuleId("TOY_RULE") == RuleId("TOY_RULE")
    assert hash(RuleId("TOY_RULE")) == hash(RuleId("TOY_RULE"))


def test_rule_instance_id_is_deterministic_and_candidate_identity_is_not_implicit():
    rule = RuleId("TOY_RULE")
    first = RuleInstanceId.build(rule_id=rule, grain=Grain.COMPONENT, scope_ref="C1", direction="X")
    second = RuleInstanceId.build(rule_id=rule, grain=Grain.COMPONENT, scope_ref="C1", direction="X")
    assert first == second
    assert first.value == '["TOY_RULE","COMPONENT","C1","X"]'
    assert "candidate" not in inspect.signature(RuleInstanceId.build).parameters
    with pytest.raises(ValueError, match="deterministic canonical construction"):
        RuleInstanceId(rule_id=rule, grain=Grain.COMPONENT, scope_ref="C1", direction="X", value="unstable")


def test_rule_instance_id_structured_serialization_is_collision_safe():
    rule = RuleId("TOY_RULE")
    first = RuleInstanceId.build(
        rule_id=rule, grain=Grain.COMPONENT, scope_ref="S|X", direction="Y"
    )
    second = RuleInstanceId.build(
        rule_id=rule, grain=Grain.COMPONENT, scope_ref="S", direction="X|Y"
    )
    assert "|".join((rule.value, Grain.COMPONENT.value, "S|X", "Y")) == "|".join(
        (rule.value, Grain.COMPONENT.value, "S", "X|Y")
    )
    assert first.value != second.value


def test_grain_and_physical_dimension_are_bounded():
    assert tuple(item.value for item in Grain) == (
        "MODEL",
        "STRUCTURAL_ZONE",
        "DIRECTION",
        "STORY",
        "COMPONENT",
        "COMPONENT_DIRECTION",
        "COMPONENT_END",
        "COMPONENT_END_DIRECTION",
        "MATERIAL_DEFINITION",
    )
    assert tuple(item.value for item in PhysicalDimension) == (
        "FORCE",
        "MOMENT",
        "STRESS",
        "AREA",
        "LENGTH",
        "DIMENSIONLESS",
        "BOOLEAN_STATE",
        "ENUM_STATE",
    )
    with pytest.raises(ValueError):
        Grain("FREE_TEXT")
    with pytest.raises(ValueError):
        PhysicalDimension("ENERGY")


def test_semantic_type_is_bounded_and_neutral():
    assert set(SemanticType) == {
        SemanticType.TOY_INPUT,
        SemanticType.TOY_DERIVED_STATE,
        SemanticType.TOY_RESULT,
        SemanticType.BEAM_WIDTH,
        SemanticType.COMPONENT_STORY,
        SemanticType.COMPONENT_SECTION,
        SemanticType.CHECK_EVIDENCE_TRACE,
        SemanticType.CONCRETE_FCK,
        SemanticType.MODAL_CUMULATIVE_EFFECTIVE_MASS_RATIO,
        SemanticType.TORSIONAL_IRREGULARITY_COEFFICIENT,
        SemanticType.BEAM_DEPTH,
        SemanticType.COLUMN_WIDTH,
        SemanticType.COLUMN_DEPTH,
        SemanticType.WALL_LENGTH,
        SemanticType.WALL_THICKNESS,
        SemanticType.WALL_STORY_HEIGHT,
        SemanticType.WALL_UNRESTRAINED_PLAN_LENGTH,
        SemanticType.RC_TABLE_4_1_ROW,
        SemanticType.RC_DTS,
        SemanticType.RC_BYS,
        SemanticType.RC_DUCTILITY_CLASS,
        SemanticType.RC_BASE_R,
        SemanticType.RC_BASE_D,
        SemanticType.RC_BYS_POLICY,
        SemanticType.RC_POST_ANALYSIS_QUALIFICATION_REQUIREMENT,
        SemanticType.RC_DIRECTIONAL_BASELINE_SYSTEM_POLICY,
        SemanticType.RC_ORTHOGONAL_SYSTEM_DECLARATION,
        SemanticType.RC_A16_SPECIAL_CONTEXT,
        SemanticType.RC_ANALYSIS_SYSTEM_ASSUMPTION,
        SemanticType.RC_ANALYSIS_BASIS_STATUS,
        SemanticType.RC_ELIGIBILITY_STATE,
        SemanticType.RC_PREANALYSIS_SYSTEM_ELIGIBILITY,
    }
    with pytest.raises(ValueError):
        SemanticType("ARBITRARY_RUNTIME_TEXT")


def test_unit_contract_dimension_and_explicit_conversion_authority():
    with pytest.raises(TypeError):
        Unit("bad", "FORCE")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="leading or trailing whitespace"):
        Unit(" kN", PhysicalDimension.FORCE)
    with pytest.raises(ValueError, match="leading or trailing whitespace"):
        Unit("kN ", PhysicalDimension.FORCE)
    assert conversion_factor(UNIT_KN_M, UNIT_N_MM) == Fraction(1_000_000, 1)
    assert conversion_factor(UNIT_N_MM, UNIT_KN_M) == Fraction(1, 1_000_000)
    assert units_convertible(UNIT_KN_M, UNIT_N_MM)
    unreviewed_moment_unit = Unit("review_not_registered", PhysicalDimension.MOMENT)
    assert not units_convertible(UNIT_KN_M, unreviewed_moment_unit)
    with pytest.raises(UnitConversionError):
        conversion_factor(UNIT_KN_M, UNIT_KN)
    assert not units_convertible(UNIT_KN_M, UNIT_KN)


def test_unit_api_has_no_magnitude_or_field_name_inference_surface():
    public = set(dir(Unit))
    assert "from_value" not in public
    assert "infer" not in public
    assert tuple(inspect.signature(conversion_factor).parameters) == ("source", "target")


def test_dependency_key_and_spec_are_typed_immutable_and_population_aware():
    with pytest.raises(ValueError):
        DependencyKey(" ")
    with pytest.raises(ValueError, match="leading or trailing whitespace"):
        DependencyKey(" FACT_A")
    with pytest.raises(ValueError, match="leading or trailing whitespace"):
        DependencyKey("FACT_A ")
    dep = _dep(full=True)
    assert dep.population_completeness_requirement is PopulationRequirement.FULL
    assert dep.source_kind is DependencySourceKind.FACT
    with pytest.raises(FrozenInstanceError):
        dep.grain = Grain.MODEL  # type: ignore[misc]
    with pytest.raises(TypeError):
        DependencySpec(
            key=DependencyKey("X"),
            source_kind="FACT",  # type: ignore[arg-type]
            semantic_type=SemanticType.TOY_INPUT,
            physical_dimension=PhysicalDimension.DIMENSIONLESS,
            grain=Grain.COMPONENT,
            scope_policy=ScopePolicy.SAME_SCOPE,
            direction_policy=DirectionPolicy.NO_DIRECTION,
        )
    with pytest.raises(TypeError, match="unit_requirement must be Unit"):
        DependencySpec(
            key=DependencyKey("X2"),
            source_kind=DependencySourceKind.FACT,
            semantic_type=SemanticType.TOY_INPUT,
            physical_dimension=PhysicalDimension.DIMENSIONLESS,
            grain=Grain.COMPONENT,
            scope_policy=ScopePolicy.SAME_SCOPE,
            direction_policy=DirectionPolicy.NO_DIRECTION,
            unit_requirement=object(),  # type: ignore[arg-type]
        )


def test_dependency_spec_rejects_dimension_unit_mismatch():
    with pytest.raises(ValueError):
        _dep(unit=UNIT_KN)


def test_applicability_and_availability_state_vocabularies_are_exact_and_separate():
    assert tuple(item.value for item in ApplicabilityState) == (
        "APPLIES",
        "PROVEN_NOT_APPLICABLE",
        "UNRESOLVED",
        "INVALID_CONTEXT",
    )
    assert tuple(item.value for item in AvailabilityState) == (
        "RESOLVED",
        "BLOCKED",
        "NO_DATA",
        "NOT_APPLICABLE",
     )
    assert AvailabilityState is not CheckStatus
    assert not issubclass(AvailabilityState, CheckStatus)


def test_regulatory_quantity_freezes_nested_containers_and_remains_immutable():
    instance = RuleInstanceId.build(
        rule_id=RuleId("TOY_DERIVE"), grain=Grain.COMPONENT, scope_ref="C1"
    )
    quantity = RegulatoryQuantity(
        quantity_key=DependencyKey("TOY_OUT"),
        producer_instance_id=instance,
        semantic_type=SemanticType.TOY_DERIVED_STATE,
        physical_dimension=PhysicalDimension.DIMENSIONLESS,
        grain=Grain.COMPONENT,
        scope_ref="C1",
        direction=None,
        value={"series": [1, 2]},
        unit=UNIT_DIMENSIONLESS,
        availability=AvailabilityState.RESOLVED,
        code_refs=("TOY",),
        rule_version="v1",
        dependency_refs=(DependencyKey("FACT_A"),),
        evidence_refs=("evidence:1",),
        provenance={"source": ["fact:1"]},
        derivation_trace=[{"candidate": [1, 2]}],
        governing_trace={"selected": [2]},
    )
    assert tuple(quantity.value["series"]) == (1, 2)
    assert tuple(quantity.provenance["source"]) == ("fact:1",)
    assert tuple(quantity.derivation_trace[0]["candidate"]) == (1, 2)
    assert tuple(quantity.governing_trace["selected"]) == (2,)
    with pytest.raises(TypeError):
        quantity.value["series"] = (3,)  # type: ignore[index]
    with pytest.raises(TypeError):
        quantity.provenance["source"] = ("changed",)  # type: ignore[index]
    with pytest.raises(TypeError):
        quantity.derivation_trace[0]["candidate"] = (3,)  # type: ignore[index]
    with pytest.raises(TypeError):
        quantity.governing_trace["selected"] = (3,)  # type: ignore[index]
    with pytest.raises(FrozenInstanceError):
        quantity.value = 3  # type: ignore[misc]


@pytest.mark.parametrize(
    "field_name",
    ("value", "provenance", "derivation_trace", "governing_trace"),
)
def test_regulatory_quantity_rejects_unsupported_custom_payload(field_name):
    instance = RuleInstanceId.build(
        rule_id=RuleId("TOY_DERIVE"), grain=Grain.COMPONENT, scope_ref="C1"
    )
    kwargs = {
        "quantity_key": DependencyKey("TOY_OUT"),
        "producer_instance_id": instance,
        "semantic_type": SemanticType.TOY_DERIVED_STATE,
        "physical_dimension": PhysicalDimension.DIMENSIONLESS,
        "grain": Grain.COMPONENT,
        "scope_ref": "C1",
        "direction": None,
        "value": {"series": [1, 2]},
        "unit": UNIT_DIMENSIONLESS,
        "availability": AvailabilityState.RESOLVED,
        "rule_version": "v1",
        "provenance": {"source": ["fact:1"]},
        "derivation_trace": [{"candidate": 1}],
        "governing_trace": {"selected": [1]},
    }
    kwargs[field_name] = MutablePayload()
    with pytest.raises(TypeError, match="unsupported payload type"):
        RegulatoryQuantity(**kwargs)


def test_regulatory_quantity_rejects_unit_dimension_mismatch():
    instance = RuleInstanceId.build(
        rule_id=RuleId("TOY_DERIVE"), grain=Grain.COMPONENT, scope_ref="C1"
    )
    with pytest.raises(ValueError):
        RegulatoryQuantity(
            quantity_key=DependencyKey("TOY_OUT"),
            producer_instance_id=instance,
            semantic_type=SemanticType.TOY_DERIVED_STATE,
            physical_dimension=PhysicalDimension.DIMENSIONLESS,
            grain=Grain.COMPONENT,
            scope_ref="C1",
            direction=None,
            value=1.0,
            unit=UNIT_KN,
            availability=AvailabilityState.RESOLVED,
            rule_version="v1",
        )


def test_rule_specs_are_immutable_canonical_and_have_no_formula_dsl_fields():
    applicability, derive_binding, check_binding = _bindings()
    output = RegulatoryOutputContract(
        authority_key=DependencyKey("TOY_OUT"),
        semantic_type=SemanticType.TOY_DERIVED_STATE,
        physical_dimension=PhysicalDimension.DIMENSIONLESS,
        grain=Grain.COMPONENT,
        unit=UNIT_DIMENSIONLESS,
    )
    derivation = RegulatoryDerivationSpec(
        rule_id=RuleId("TOY_DERIVE"),
        code_refs=("TOY",),
        rule_version="v1",
        output_contract=output,
        dependencies=(_dep(),),
        applicability=applicability,
        evaluator=derive_binding,
    )
    check = CheckSpec(
        rule_id=RuleId("TOY_CHECK"),
        code_refs=("TOY",),
        rule_version="v1",
        formal_result_type=CheckResult,
        dependencies=(_dep(),),
        applicability=applicability,
        evaluator=check_binding,
    )
    assert derivation.output_contract == output
    assert check.formal_result_type is CheckResult
    forbidden_fields = {"formula", "operator", "expression", "expression_tree", "yaml_formula"}
    assert forbidden_fields.isdisjoint({item.name for item in fields(RegulatoryDerivationSpec)})
    assert forbidden_fields.isdisjoint({item.name for item in fields(CheckSpec)})
    with pytest.raises(FrozenInstanceError):
        check.rule_version = "v2"  # type: ignore[misc]


def test_closure_record_and_outcome_are_separate_immutable_contracts():
    instance = RuleInstanceId.build(
        rule_id=RuleId("TOY_CHECK"), grain=Grain.COMPONENT, scope_ref="C1"
    )
    record = CompiledClosureRecord(
        instance_id=instance,
        rule_id=instance.rule_id,
        grain=instance.grain,
        scope_ref=instance.scope_ref,
        mandatory=True,
        applicability=ApplicabilityState.UNRESOLVED,
        declared_dependency_refs=(DependencyKey("FACT_A"),),
        code_refs=("TOY",),
        rule_version="v1",
    )
    outcome = RuleClosureOutcome(
        compiled_record_ref=instance,
        execution_status=ClosureExecutionStatus.NOT_EXECUTED,
        diagnostic_refs=("diag:1",),
    )
    assert not hasattr(record, "execution_status")
    assert outcome.compiled_record_ref == record.instance_id
    with pytest.raises(FrozenInstanceError):
        record.mandatory = False  # type: ignore[misc]


def test_execution_plan_is_immutable_shell_without_compile_or_execute_methods():
    instance = RuleInstanceId.build(
        rule_id=RuleId("TOY_CHECK"), grain=Grain.COMPONENT, scope_ref="C1"
    )
    binding = DependencyBindingRef(instance, DependencyKey("FACT_A"), "external:FACT_A")
    record = CompiledClosureRecord(
        instance_id=instance,
        rule_id=instance.rule_id,
        grain=instance.grain,
        scope_ref=instance.scope_ref,
        mandatory=True,
        applicability=ApplicabilityState.APPLIES,
        declared_dependency_refs=(DependencyKey("FACT_A"),),
        code_refs=("TOY",),
        rule_version="v1",
    )
    plan = TBDYExecutionPlan(
        registry_version="f0.0:test",
        plan_identity="plan:test",
        compiled_rule_instances=(instance,),
        compiled_dependency_bindings=(binding,),
        typed_dag=TypedDagContract((instance,), (binding,)),
        compiled_closure_inventory=(record,),
        deterministic_execution_order=(instance,),
        analysis_basis_compatibility_refs=("basis:test",),
        compile_diagnostics=(),
     )
    assert not hasattr(plan, "compile")
    assert not hasattr(plan, "execute")
    with pytest.raises(FrozenInstanceError):
        plan.plan_identity = "changed"  # type: ignore[misc]


def test_execution_plan_compile_diagnostics_reject_non_string_without_coercion():
    instance = RuleInstanceId.build(
        rule_id=RuleId("TOY_CHECK"), grain=Grain.COMPONENT, scope_ref="C1"
    )
    with pytest.raises(TypeError, match="strings only"):
        TBDYExecutionPlan(
            registry_version="f0.0:test",
            plan_identity="plan:test",
            compiled_rule_instances=(instance,),
            compiled_dependency_bindings=(),
            typed_dag=TypedDagContract((instance,), ()),
            compiled_closure_inventory=(),
            deterministic_execution_order=(instance,),
            analysis_basis_compatibility_refs=(),
            compile_diagnostics=(object(),),  # type: ignore[arg-type]
        )


def test_regulatory_package_static_architecture_guards():
    package_dir = Path(__file__).resolve().parents[2] / "tbdy_engine" / "regulatory"
    core_files = ("contracts.py", "registry.py", "kernel.py", "units.py", "authority.py")
    source = "\n".join(
        (package_dir / name).read_text(encoding="utf-8") for name in core_files
    )
    assert "tbdy_engine.etabs" not in source
    assert "tbdy_engine.product_reports" not in source
    assert "_ALLOWED_CHECKS" not in source
    assert "MinimalCheckEngine" not in source
    assert "GeometryCheckInput" not in source
    forbidden_domain_tokens = (
        "25 MPa",
        "A11",
        "A12",
        "Mpi",
        "Mpj",
        "SCWB",
        "beam shear",
        "column shear",
        "joint shear",
        "wall shear",
    )
    assert all(token not in source for token in forbidden_domain_tokens)
