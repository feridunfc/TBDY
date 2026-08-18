from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from tbdy_engine.checks.result import CheckResult
from tbdy_engine.regulatory import (
    ApplicabilityBinding,
    ApplicabilityState,
    AvailabilityState,
    CheckEvaluatorBinding,
    CheckSpec,
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
    RegulatoryRegistry,
    RuleId,
    ScopePolicy,
    SemanticType,
    UNIT_DIMENSIONLESS,
)


class ToyInput:
    pass


def _dependency() -> DependencySpec:
    return DependencySpec(
        key=DependencyKey("FACT_A"),
        source_kind=DependencySourceKind.FACT,
        semantic_type=SemanticType.TOY_INPUT,
        physical_dimension=PhysicalDimension.DIMENSIONLESS,
        grain=Grain.COMPONENT,
        scope_policy=ScopePolicy.SAME_SCOPE,
        direction_policy=DirectionPolicy.NO_DIRECTION,
        required_availability=AvailabilityState.RESOLVED,
        population_completeness_requirement=PopulationRequirement.ANY_RESOLVED,
        unit_requirement=UNIT_DIMENSIONLESS,
    )


def _app(counter: list[str] | None = None):
    def evaluator(_: object) -> ApplicabilityState:
        if counter is not None:
            counter.append("applicability")
        return ApplicabilityState.APPLIES
    return ApplicabilityBinding("toy-app", ToyInput, evaluator)


def _derivation(rule: str, authority: str, counter: list[str] | None = None):
    def evaluator(_: object) -> RegulatoryQuantity:
        if counter is not None:
            counter.append(rule)
        raise AssertionError("registry must not execute derivation evaluator")

    return RegulatoryDerivationSpec(
        rule_id=RuleId(rule),
        code_refs=("TOY",),
        rule_version="v1",
        output_contract=RegulatoryOutputContract(
            authority_key=DependencyKey(authority),
            semantic_type=SemanticType.TOY_DERIVED_STATE,
            physical_dimension=PhysicalDimension.DIMENSIONLESS,
            grain=Grain.COMPONENT,
            unit=UNIT_DIMENSIONLESS,
        ),
        dependencies=(_dependency(),),
        applicability=_app(counter),
        evaluator=DerivationEvaluatorBinding(f"{rule}-eval", ToyInput, evaluator),
    )


def _check(rule: str, counter: list[str] | None = None):
    def evaluator(_: object) -> CheckResult:
        if counter is not None:
            counter.append(rule)
        raise AssertionError("registry must not execute check evaluator")

    return CheckSpec(
        rule_id=RuleId(rule),
        code_refs=("TOY",),
        rule_version="v1",
        formal_result_type=CheckResult,
        dependencies=(_dependency(),),
        applicability=_app(counter),
        evaluator=CheckEvaluatorBinding(f"{rule}-eval", ToyInput, evaluator),
    )


def test_registry_rejects_duplicate_rule_id_across_rule_kinds():
    with pytest.raises(ValueError, match="duplicate RuleId"):
        RegulatoryRegistry(
            derivations=(_derivation("RULE_A", "OUT_A"),),
            checks=(_check("RULE_A"),),
        )


def test_registry_rejects_duplicate_derivation_output_authority():
    with pytest.raises(ValueError, match="duplicate regulatory output authority"):
        RegulatoryRegistry(
            derivations=(
                _derivation("RULE_A", "OUT_SHARED"),
                _derivation("RULE_B", "OUT_SHARED"),
            )
        )


def test_registry_is_deterministic_independent_of_insertion_order():
    first = RegulatoryRegistry(
        derivations=(
            _derivation("RULE_B", "OUT_B"),
            _derivation("RULE_A", "OUT_A"),
        ),
        checks=(_check("RULE_C"),),
    )
    second = RegulatoryRegistry(
        derivations=(
            _derivation("RULE_A", "OUT_A"),
            _derivation("RULE_B", "OUT_B"),
        ),
        checks=(_check("RULE_C"),),
    )
    assert first.registry_version == second.registry_version
    assert tuple(item.rule_id.value for item in first.derivations) == ("RULE_A", "RULE_B")
    assert first.rule(RuleId("RULE_C")).rule_id == RuleId("RULE_C")


def test_registry_is_immutable_and_has_no_dynamic_registration_surface():
    registry = RegulatoryRegistry(derivations=(_derivation("RULE_A", "OUT_A"),))
    assert not hasattr(registry, "register")
    assert not hasattr(registry, "add")
    with pytest.raises(FrozenInstanceError):
        registry.registry_version = "changed"  # type: ignore[misc]
    with pytest.raises(TypeError):
        registry._rules_by_id[RuleId("RULE_X")] = _check("RULE_X")  # type: ignore[index]


def test_registry_composition_never_executes_evaluators():
    calls: list[str] = []
    registry = RegulatoryRegistry(
        derivations=(_derivation("RULE_A", "OUT_A", calls),),
        checks=(_check("RULE_B", calls),),
    )
    assert registry.rule_count == 2
    assert calls == []
