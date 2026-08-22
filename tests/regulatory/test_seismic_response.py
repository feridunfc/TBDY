from __future__ import annotations

import pytest

from tbdy_engine.checks.result import CheckStatus, EvaluationLevel
from tbdy_engine.regulatory.contracts import (
    ApplicabilityState,
    AvailabilityState,
    DependencySourceKind,
    Grain,
    PhysicalDimension,
    SemanticType,
)
from tbdy_engine.regulatory.kernel import (
    ExternalDependencyAuthority,
    PopulationCompleteness,
    RegulatoryCompileInputs,
    RegulatoryCompiler,
    RegulatoryEngine,
    RuleScopeTarget,
)
from tbdy_engine.regulatory.seismic_response import (
    A1ApplicabilityInput,
    A1_EVIDENCE_TRACE_KEY,
    A1_PRESENT_LIMIT,
    A1_RATIO_KEY,
    A1_RULE_ID,
    MODAL_EVIDENCE_TRACE_KEY,
    MODAL_MIN_RATIO,
    MODAL_RATIO_KEY,
    MODAL_RULE_ID,
    Modal4812ApplicabilityInput,
    VS3_SEISMIC_REGISTRY,
    a1_applicability,
    modal_4812_applicability,
)
from tbdy_engine.regulatory.units import UNIT_DIMENSIONLESS


def _authority(*, authority_id, key, semantic_type, grain, scope_ref, direction, value, kind=DependencySourceKind.FACT):
    return ExternalDependencyAuthority(
        authority_id=authority_id,
        key=key,
        source_kind=kind,
        semantic_type=semantic_type,
        physical_dimension=PhysicalDimension.DIMENSIONLESS,
        grain=grain,
        scope_ref=scope_ref,
        direction=direction,
        unit=UNIT_DIMENSIONLESS,
        availability=AvailabilityState.RESOLVED,
        population_completeness=PopulationCompleteness.FULL,
        value=value,
        provenance_refs=(f"source:{authority_id}",),
    )


def _modal_target(direction: str, *, applies=True, basis="verified"):
    return RuleScopeTarget(
        rule_id=MODAL_RULE_ID,
        grain=Grain.DIRECTION,
        scope_ref="BUILDING",
        direction=direction,
        applicability_input=Modal4812ApplicabilityInput(applies, basis),
    )


def _a1_target(direction: str, *, basis="verified"):
    return RuleScopeTarget(
        rule_id=A1_RULE_ID,
        grain=Grain.STORY,
        scope_ref="S1",
        direction=direction,
        applicability_input=A1ApplicabilityInput(basis),
    )


def _modal_authorities(direction: str, ratio: float):
    return (
        _authority(
            authority_id=f"modal-ratio-{direction}",
            key=MODAL_RATIO_KEY,
            semantic_type=SemanticType.MODAL_CUMULATIVE_EFFECTIVE_MASS_RATIO,
            grain=Grain.DIRECTION,
            scope_ref="BUILDING",
            direction=direction,
            value=ratio,
        ),
        _authority(
            authority_id=f"modal-trace-{direction}",
            key=MODAL_EVIDENCE_TRACE_KEY,
            semantic_type=SemanticType.CHECK_EVIDENCE_TRACE,
            grain=Grain.DIRECTION,
            scope_ref="BUILDING",
            direction=direction,
            value=(f"modal-row-{direction}",),
            kind=DependencySourceKind.CONTEXT,
        ),
    )


def _a1_authorities(direction: str, eta: float):
    return (
        _authority(
            authority_id=f"a1-ratio-{direction}",
            key=A1_RATIO_KEY,
            semantic_type=SemanticType.TORSIONAL_IRREGULARITY_COEFFICIENT,
            grain=Grain.STORY,
            scope_ref="S1",
            direction=direction,
            value=eta,
        ),
        _authority(
            authority_id=f"a1-trace-{direction}",
            key=A1_EVIDENCE_TRACE_KEY,
            semantic_type=SemanticType.CHECK_EVIDENCE_TRACE,
            grain=Grain.STORY,
            scope_ref="S1",
            direction=direction,
            value=(f"a1-row-{direction}",),
            kind=DependencySourceKind.CONTEXT,
        ),
    )


def _execute_one(target, authorities):
    rule = VS3_SEISMIC_REGISTRY.rule(target.rule_id)
    from tbdy_engine.regulatory.registry import RegulatoryRegistry

    registry = RegulatoryRegistry(checks=(rule,))
    program = RegulatoryCompiler.compile(
        registry,
        RegulatoryCompileInputs(rule_targets=(target,), external_authorities=authorities),
    )
    snapshot = RegulatoryEngine.execute(program)
    return program, snapshot


def test_registry_contains_exactly_two_formal_rule_families():
    assert VS3_SEISMIC_REGISTRY.rule_count == 2
    assert {item.rule_id for item in VS3_SEISMIC_REGISTRY.checks} == {MODAL_RULE_ID, A1_RULE_ID}


def test_modal_applicability_is_explicit_compile_time_context():
    assert modal_4812_applicability(Modal4812ApplicabilityInput(True, "verified")) is ApplicabilityState.APPLIES
    assert modal_4812_applicability(Modal4812ApplicabilityInput(False, "unknown")) is ApplicabilityState.PROVEN_NOT_APPLICABLE
    assert modal_4812_applicability(Modal4812ApplicabilityInput(None, "verified")) is ApplicabilityState.UNRESOLVED
    assert modal_4812_applicability(Modal4812ApplicabilityInput(True, "unknown")) is ApplicabilityState.UNRESOLVED


def test_a1_applicability_requires_reviewed_eccentricity_basis():
    assert a1_applicability(A1ApplicabilityInput("verified")) is ApplicabilityState.APPLIES
    assert a1_applicability(A1ApplicabilityInput("unknown")) is ApplicabilityState.UNRESOLVED


@pytest.mark.parametrize(
    "ratio, expected",
    [
        (0.95, CheckStatus.OK),
        (0.951, CheckStatus.OK),
        (0.949, CheckStatus.FAIL),
    ],
)
def test_modal_threshold_is_applied_only_by_formal_evaluator(ratio, expected):
    _program, snapshot = _execute_one(_modal_target("X"), _modal_authorities("X", ratio))
    result = snapshot.formal_results[0].result
    assert result.status is expected
    assert result.value == ratio
    assert result.limit == MODAL_MIN_RATIO
    assert result.evaluation_level is EvaluationLevel.DESIGN_LEVEL
    assert result.code_ref == "TBDY 2018 4.8.1.2(a), Eq. (4.30)"


@pytest.mark.parametrize(
    "eta, expected_status, expected_message",
    [
        (1.19, CheckStatus.OK, "A1_NOT_PRESENT"),
        (1.20, CheckStatus.OK, "A1_NOT_PRESENT"),
        (1.21, CheckStatus.WARNING, "A1_PRESENT"),
    ],
)
def test_a1_is_classification_warning_never_failure(eta, expected_status, expected_message):
    _program, snapshot = _execute_one(_a1_target("X"), _a1_authorities("X", eta))
    result = snapshot.formal_results[0].result
    assert result.status is expected_status
    assert CheckStatus.FAIL is not result.status
    assert result.messages == (expected_message,)
    assert result.limit == A1_PRESENT_LIMIT
    assert result.evaluation_level is EvaluationLevel.DESIGN_LEVEL


def test_unresolved_modal_context_blocks_without_fake_checkresult():
    program, snapshot = _execute_one(
        _modal_target("X", applies=True, basis="unknown"),
        _modal_authorities("X", 0.99),
    )
    assert snapshot.formal_results == ()
    assert snapshot.outcome_for(program.plan.compiled_rule_instances[0]).execution_status.value == "BLOCKED"


def test_unresolved_a1_basis_blocks_without_fake_checkresult():
    program, snapshot = _execute_one(_a1_target("Y", basis="unknown"), _a1_authorities("Y", 1.30))
    assert snapshot.formal_results == ()
    assert snapshot.outcome_for(program.plan.compiled_rule_instances[0]).execution_status.value == "BLOCKED"


def test_modal_and_a1_dependencies_use_exact_direction_and_expected_grains():
    modal = VS3_SEISMIC_REGISTRY.rule(MODAL_RULE_ID)
    a1 = VS3_SEISMIC_REGISTRY.rule(A1_RULE_ID)
    assert all(dep.grain is Grain.DIRECTION for dep in modal.dependencies)
    assert all(dep.direction_policy.value == "EXACT_DIRECTION" for dep in modal.dependencies)
    assert all(dep.grain is Grain.STORY for dep in a1.dependencies)
    assert all(dep.direction_policy.value == "EXACT_DIRECTION" for dep in a1.dependencies)


def test_a1_x_and_y_instances_bind_only_matching_story_direction_authorities():
    targets = (_a1_target("X"), _a1_target("Y"))
    authorities = (*_a1_authorities("X", 1.10), *_a1_authorities("Y", 1.25))
    from tbdy_engine.regulatory.registry import RegulatoryRegistry

    registry = RegulatoryRegistry(checks=(VS3_SEISMIC_REGISTRY.rule(A1_RULE_ID),))
    program = RegulatoryCompiler.compile(
        registry,
        RegulatoryCompileInputs(rule_targets=targets, external_authorities=authorities),
    )
    for node in program.nodes:
        for binding in node.dependency_bindings:
            assert binding.external_authority_id is not None
            assert program.authority(binding.external_authority_id).direction == node.instance_id.direction
