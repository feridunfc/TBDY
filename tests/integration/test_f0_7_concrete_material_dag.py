from __future__ import annotations

import pytest

from tbdy_engine.checks.result import CheckStatus
from tbdy_engine.findings import build_finding_from_check_result
from tbdy_engine.regulatory.beam_min_width import (
    BEAM_MIN_WIDTH_CHECK_SPEC,
    BEAM_WIDTH_KEY,
    EVIDENCE_TRACE_KEY as BEAM_EVIDENCE_TRACE_KEY,
    SECTION_KEY,
    STORY_KEY,
    BeamMinWidthApplicabilityInput,
)
from tbdy_engine.regulatory.concrete_material_min_strength import (
    CONCRETE_MATERIAL_MIN_STRENGTH_CHECK_SPEC,
    EVIDENCE_TRACE_KEY,
    FCK_KEY,
    RULE_ID,
    ConcreteMaterialMinStrengthApplicabilityInput,
)
from tbdy_engine.regulatory.contracts import (
    AvailabilityState,
    ClosureExecutionStatus,
    DependencySourceKind,
    Grain,
    PhysicalDimension,
    SemanticType,
)
from tbdy_engine.regulatory.kernel import (
    AnalysisBasisStatus,
    AssessmentEngine,
    ExternalDependencyAuthority,
    KernelCompileError,
    PopulationCompleteness,
    RegulatoryCompileInputs,
    RegulatoryCompiler,
    RegulatoryEngine,
    RuleScopeTarget,
    StructuralAssessmentStatus,
)
from tbdy_engine.regulatory.registry import RegulatoryRegistry
from tbdy_engine.regulatory.units import UNIT_DIMENSIONLESS, UNIT_ENUM_STATE, UNIT_MM, UNIT_MPA


def _material_target(scope: str, *, concrete: bool | None = True, used: bool | None = True) -> RuleScopeTarget:
    return RuleScopeTarget(
        rule_id=RULE_ID,
        grain=Grain.MATERIAL_DEFINITION,
        scope_ref=scope,
        applicability_input=ConcreteMaterialMinStrengthApplicabilityInput(
            is_concrete_material=concrete,
            used_in_scope_rc_building=used,
        ),
    )


def _fck_authority(
    scope: str,
    *,
    value: object,
    availability: AvailabilityState = AvailabilityState.RESOLVED,
    completeness: PopulationCompleteness = PopulationCompleteness.FULL,
) -> ExternalDependencyAuthority:
    return ExternalDependencyAuthority(
        authority_id=f"f0.7:fck:{scope}:{availability.value}:{completeness.value}",
        key=FCK_KEY,
        source_kind=DependencySourceKind.FACT,
        semantic_type=SemanticType.CONCRETE_FCK,
        physical_dimension=PhysicalDimension.STRESS,
        grain=Grain.MATERIAL_DEFINITION,
        scope_ref=scope,
        direction=None,
        unit=UNIT_MPA,
        availability=availability,
        population_completeness=completeness,
        value=value,
        provenance_refs=(f"evidence:fck:{scope}",),
    )


def _trace_authority(scope: str) -> ExternalDependencyAuthority:
    return ExternalDependencyAuthority(
        authority_id=f"f0.7:evidence:{scope}",
        key=EVIDENCE_TRACE_KEY,
        source_kind=DependencySourceKind.CONTEXT,
        semantic_type=SemanticType.CHECK_EVIDENCE_TRACE,
        physical_dimension=PhysicalDimension.DIMENSIONLESS,
        grain=Grain.MATERIAL_DEFINITION,
        scope_ref=scope,
        direction=None,
        unit=UNIT_DIMENSIONLESS,
        availability=AvailabilityState.RESOLVED,
        population_completeness=PopulationCompleteness.FULL,
        value=(f"evidence:material:{scope}",),
        provenance_refs=(f"source:material:{scope}",),
    )


def _inputs(
    scopes: tuple[str, ...],
    values: dict[str, object],
    *,
    availability: AvailabilityState = AvailabilityState.RESOLVED,
    completeness: PopulationCompleteness = PopulationCompleteness.FULL,
    concrete: bool | None = True,
    used: bool | None = True,
    reverse: bool = False,
) -> RegulatoryCompileInputs:
    targets = tuple(_material_target(scope, concrete=concrete, used=used) for scope in scopes)
    authorities = tuple(
        item
        for scope in scopes
        for item in (
            _fck_authority(scope, value=values[scope], availability=availability, completeness=completeness),
            _trace_authority(scope),
        )
    )
    if reverse:
        targets = tuple(reversed(targets))
        authorities = tuple(reversed(authorities))
    return RegulatoryCompileInputs(rule_targets=targets, external_authorities=authorities)


def _program(inputs: RegulatoryCompileInputs):
    return RegulatoryCompiler.compile(
        RegulatoryRegistry(checks=(CONCRETE_MATERIAL_MIN_STRENGTH_CHECK_SPEC,)),
        inputs,
    )


def _instance_for(program, scope: str):
    return next(
        item for item in program.plan.compiled_rule_instances
        if item.rule_id == RULE_ID and item.scope_ref == scope
    )


def test_resolved_full_materials_execute_with_formal_verdict_and_executed_closure() -> None:
    values = {"MAT_C24": 24.0, "MAT_C25": 25.0, "MAT_C30": 30.0}
    program = _program(_inputs(tuple(values), values))
    snapshot = RegulatoryEngine.execute(program)
    assessment = AssessmentEngine.reconcile(program, snapshot)

    expected = {"MAT_C24": CheckStatus.FAIL, "MAT_C25": CheckStatus.OK, "MAT_C30": CheckStatus.OK}
    for scope, status in expected.items():
        instance = _instance_for(program, scope)
        results = snapshot.formal_results_for(instance)
        assert len(results) == 1
        assert results[0].status is status
        assert results[0].value == values[scope]
        assert snapshot.outcome_for(instance).execution_status is ClosureExecutionStatus.EXECUTED

    assert assessment.structural_status is StructuralAssessmentStatus.COMPLETE
    assert assessment.incomplete_mandatory_instances == ()
    assert assessment.full_tbdy_compliance_status == "NOT_EVALUATED"


def test_no_data_full_compiles_then_readiness_emits_no_data_closure_without_result() -> None:
    inputs = _inputs(
        ("MAT_MISSING",), {"MAT_MISSING": None},
        availability=AvailabilityState.NO_DATA,
        completeness=PopulationCompleteness.FULL,
    )
    program = _program(inputs)
    snapshot = RegulatoryEngine.execute(program)
    instance = _instance_for(program, "MAT_MISSING")
    assert snapshot.formal_results_for(instance) == ()
    assert snapshot.outcome_for(instance).execution_status is ClosureExecutionStatus.NO_DATA


def test_blocked_full_compiles_then_readiness_emits_blocked_closure_without_result() -> None:
    inputs = _inputs(
        ("MAT_BLOCKED",), {"MAT_BLOCKED": None},
        availability=AvailabilityState.BLOCKED,
        completeness=PopulationCompleteness.FULL,
    )
    program = _program(inputs)
    snapshot = RegulatoryEngine.execute(program)
    instance = _instance_for(program, "MAT_BLOCKED")
    assert snapshot.formal_results_for(instance) == ()
    assert snapshot.outcome_for(instance).execution_status is ClosureExecutionStatus.BLOCKED


def test_incomplete_population_is_static_compile_rejection_not_runtime_closure() -> None:
    inputs = _inputs(
        ("MAT_INCOMPLETE",), {"MAT_INCOMPLETE": 25.0},
        availability=AvailabilityState.RESOLVED,
        completeness=PopulationCompleteness.INCOMPLETE,
    )
    with pytest.raises(KernelCompileError, match="FULL population requirement is not satisfiable"):
        _program(inputs)


def test_proven_not_applicable_compiles_without_result_and_closes_pna() -> None:
    program = _program(_inputs(("MAT_STEEL",), {"MAT_STEEL": 25.0}, concrete=False, used=True))
    snapshot = RegulatoryEngine.execute(program)
    instance = _instance_for(program, "MAT_STEEL")
    assert snapshot.formal_results_for(instance) == ()
    assert snapshot.outcome_for(instance).execution_status is ClosureExecutionStatus.PROVEN_NOT_APPLICABLE


def test_unresolved_applicability_compiles_without_result_and_closes_blocked() -> None:
    program = _program(_inputs(("MAT_UNKNOWN",), {"MAT_UNKNOWN": 25.0}, concrete=True, used=None))
    snapshot = RegulatoryEngine.execute(program)
    instance = _instance_for(program, "MAT_UNKNOWN")
    assert snapshot.formal_results_for(instance) == ()
    assert snapshot.outcome_for(instance).execution_status is ClosureExecutionStatus.BLOCKED


def test_finding_projects_fail_only_and_does_not_recompute_material_verdict() -> None:
    values = {"MAT_C24": 24.0, "MAT_C25": 25.0}
    program = _program(_inputs(tuple(values), values))
    snapshot = RegulatoryEngine.execute(program)
    fail_instance = _instance_for(program, "MAT_C24")
    ok_instance = _instance_for(program, "MAT_C25")
    fail_result = snapshot.formal_results_for(fail_instance)[0]
    ok_result = snapshot.formal_results_for(ok_instance)[0]

    finding = build_finding_from_check_result(
        instance_id=fail_instance,
        result=fail_result,
        evidence_refs=("evidence:finding:MAT_C24",),
    )
    assert finding is not None
    assert finding.source_status is CheckStatus.FAIL
    assert finding.source_ref == f"check-result:{fail_instance.value}"
    assert build_finding_from_check_result(instance_id=ok_instance, result=ok_result) is None


def test_registry_composition_with_f0_2_is_immutable_and_deterministic() -> None:
    first = RegulatoryRegistry(checks=(BEAM_MIN_WIDTH_CHECK_SPEC, CONCRETE_MATERIAL_MIN_STRENGTH_CHECK_SPEC))
    second = RegulatoryRegistry(checks=(CONCRETE_MATERIAL_MIN_STRENGTH_CHECK_SPEC, BEAM_MIN_WIDTH_CHECK_SPEC))
    assert first.rule_count == 2
    assert first.rule(BEAM_MIN_WIDTH_CHECK_SPEC.rule_id) is BEAM_MIN_WIDTH_CHECK_SPEC
    assert first.rule(RULE_ID) is CONCRETE_MATERIAL_MIN_STRENGTH_CHECK_SPEC
    assert first.registry_version == second.registry_version
    assert first.checks == second.checks


def test_equivalent_input_order_produces_deterministic_plan_results_and_closure() -> None:
    values = {"MAT_C24": 24.0, "MAT_C25": 25.0, "MAT_C30": 30.0}
    first = _program(_inputs(tuple(values), values, reverse=False))
    second = _program(_inputs(tuple(values), values, reverse=True))
    first_snapshot = RegulatoryEngine.execute(first)
    second_snapshot = RegulatoryEngine.execute(second)
    assert first.plan.plan_identity == second.plan.plan_identity
    assert first.plan.deterministic_execution_order == second.plan.deterministic_execution_order
    assert first.plan.compiled_closure_inventory == second.plan.compiled_closure_inventory
    assert first_snapshot == second_snapshot


def _beam_authorities(scope: str) -> tuple[ExternalDependencyAuthority, ...]:
    return (
        ExternalDependencyAuthority(
            authority_id=f"beam:width:{scope}", key=BEAM_WIDTH_KEY,
            source_kind=DependencySourceKind.FACT, semantic_type=SemanticType.BEAM_WIDTH,
            physical_dimension=PhysicalDimension.LENGTH, grain=Grain.COMPONENT,
            scope_ref=scope, direction=None, unit=UNIT_MM,
            availability=AvailabilityState.RESOLVED, population_completeness=PopulationCompleteness.FULL,
            value=300.0,
        ),
        ExternalDependencyAuthority(
            authority_id=f"beam:story:{scope}", key=STORY_KEY,
            source_kind=DependencySourceKind.CONTEXT, semantic_type=SemanticType.COMPONENT_STORY,
            physical_dimension=PhysicalDimension.ENUM_STATE, grain=Grain.COMPONENT,
            scope_ref=scope, direction=None, unit=UNIT_ENUM_STATE,
            availability=AvailabilityState.RESOLVED, population_completeness=PopulationCompleteness.FULL,
            value="S1",
        ),
        ExternalDependencyAuthority(
            authority_id=f"beam:section:{scope}", key=SECTION_KEY,
            source_kind=DependencySourceKind.CONTEXT, semantic_type=SemanticType.COMPONENT_SECTION,
            physical_dimension=PhysicalDimension.ENUM_STATE, grain=Grain.COMPONENT,
            scope_ref=scope, direction=None, unit=UNIT_ENUM_STATE,
            availability=AvailabilityState.RESOLVED, population_completeness=PopulationCompleteness.FULL,
            value="B300x500",
        ),
        ExternalDependencyAuthority(
            authority_id=f"beam:evidence:{scope}", key=BEAM_EVIDENCE_TRACE_KEY,
            source_kind=DependencySourceKind.CONTEXT, semantic_type=SemanticType.CHECK_EVIDENCE_TRACE,
            physical_dimension=PhysicalDimension.DIMENSIONLESS, grain=Grain.COMPONENT,
            scope_ref=scope, direction=None, unit=UNIT_DIMENSIONLESS,
            availability=AvailabilityState.RESOLVED, population_completeness=PopulationCompleteness.FULL,
            value=(f"beam:evidence:{scope}",),
        ),
    )


def test_material_rule_remains_executable_when_unrelated_rule_requires_reanalysis() -> None:
    material_scope, beam_scope = "MAT_C25", "B1"
    registry = RegulatoryRegistry(checks=(BEAM_MIN_WIDTH_CHECK_SPEC, CONCRETE_MATERIAL_MIN_STRENGTH_CHECK_SPEC))
    inputs = RegulatoryCompileInputs(
        rule_targets=(
            RuleScopeTarget(
                rule_id=BEAM_MIN_WIDTH_CHECK_SPEC.rule_id,
                grain=Grain.COMPONENT,
                scope_ref=beam_scope,
                applicability_input=BeamMinWidthApplicabilityInput("beam", True),
                analysis_basis_status=AnalysisBasisStatus.REANALYSIS_REQUIRED,
            ),
            _material_target(material_scope),
        ),
        external_authorities=(
            *_beam_authorities(beam_scope),
            _fck_authority(material_scope, value=25.0),
            _trace_authority(material_scope),
        ),
    )
    program = RegulatoryCompiler.compile(registry, inputs)
    snapshot = RegulatoryEngine.execute(program)
    material_instance = _instance_for(program, material_scope)
    beam_instance = next(item for item in program.plan.compiled_rule_instances if item.rule_id == BEAM_MIN_WIDTH_CHECK_SPEC.rule_id)
    assert snapshot.formal_results_for(material_instance)[0].status is CheckStatus.OK
    assert snapshot.outcome_for(material_instance).execution_status is ClosureExecutionStatus.EXECUTED
    assert snapshot.formal_results_for(beam_instance) == ()
    assert snapshot.outcome_for(beam_instance).execution_status is ClosureExecutionStatus.BLOCKED
