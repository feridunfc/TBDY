from __future__ import annotations

import pytest

from tbdy_engine.checks.result import CheckStatus
from tbdy_engine.findings import build_finding_from_check_result
from tbdy_engine.regulatory.b1_geometry_parity import (
    BEAM_DEPTH_KEY,
    BEAM_DEPTH_WIDTH_RATIO_CHECK_SPEC,
    BEAM_DEPTH_WIDTH_RATIO_RULE_ID,
    BEAM_MIN_DEPTH_CHECK_SPEC,
    BEAM_MIN_DEPTH_RULE_ID,
    BEAM_WIDTH_KEY,
    B1_GEOMETRY_PARITY_CHECK_SPECS,
    COLUMN_DEPTH_KEY,
    COLUMN_MIN_DIMENSION_CHECK_SPEC,
    COLUMN_MIN_DIMENSION_RULE_ID,
    COLUMN_WIDTH_KEY,
    EVIDENCE_TRACE_KEY as B1_EVIDENCE_TRACE_KEY,
    SECTION_KEY as B1_SECTION_KEY,
    STORY_KEY as B1_STORY_KEY,
    Beam7411ApplicabilityInput,
    ColumnMinDimensionApplicabilityInput,
)
from tbdy_engine.regulatory.beam_min_width import BEAM_MIN_WIDTH_CHECK_SPEC
from tbdy_engine.regulatory.concrete_material_min_strength import (
    CONCRETE_MATERIAL_MIN_STRENGTH_CHECK_SPEC,
)
from tbdy_engine.regulatory.contracts import (
    AvailabilityState,
    ClosureExecutionStatus,
    DependencyKey,
    DependencySourceKind,
    Grain,
    PhysicalDimension,
    SemanticType,
)
from tbdy_engine.regulatory.kernel import (
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
from tbdy_engine.regulatory.units import UNIT_DIMENSIONLESS, UNIT_ENUM_STATE, UNIT_MM
from tbdy_engine.regulatory.wall_pack_a_geometry_parity import (
    WALL_DEFINITION_GE6_CHECK_SPEC,
    WALL_DEFINITION_RULE_ID,
    WALL_LENGTH_KEY,
    WALL_PACK_A_GEOMETRY_PARITY_CHECK_SPECS,
    WALL_RESTRAINED_LEG_RULE_ID,
    WALL_RESTRAINED_LEG_THICKNESS_CHECK_SPEC,
    WALL_STORY_HEIGHT_KEY,
    WALL_THICKNESS_KEY,
    WALL_UNRESTRAINED_LENGTH_KEY,
    WALL_UNRESTRAINED_RULE_ID,
    WallDefinitionGE6ApplicabilityInput,
    WallRestrainedLegApplicabilityInput,
    WallUnrestrainedThicknessApplicabilityInput,
)

F0_8_REGISTRY = RegulatoryRegistry(
    checks=(*B1_GEOMETRY_PARITY_CHECK_SPECS, *WALL_PACK_A_GEOMETRY_PARITY_CHECK_SPECS)
)


def _authority(
    scope: str,
    key: DependencyKey,
    *,
    source_kind: DependencySourceKind,
    semantic: SemanticType,
    dimension: PhysicalDimension,
    unit,
    value: object,
    availability: AvailabilityState = AvailabilityState.RESOLVED,
    completeness: PopulationCompleteness = PopulationCompleteness.FULL,
) -> ExternalDependencyAuthority:
    return ExternalDependencyAuthority(
        authority_id=f"f0.8:{scope}:{key.value}:{availability.value}:{completeness.value}",
        key=key,
        source_kind=source_kind,
        semantic_type=semantic,
        physical_dimension=dimension,
        grain=Grain.COMPONENT,
        scope_ref=scope,
        direction=None,
        unit=unit,
        availability=availability,
        population_completeness=completeness,
        value=value,
        provenance_refs=(f"evidence:{scope}:{key.value}",),
    )


def _fact(
    scope: str,
    key: DependencyKey,
    semantic: SemanticType,
    value: object,
    *,
    availability: AvailabilityState = AvailabilityState.RESOLVED,
) -> ExternalDependencyAuthority:
    return _authority(
        scope,
        key,
        source_kind=DependencySourceKind.FACT,
        semantic=semantic,
        dimension=PhysicalDimension.LENGTH,
        unit=UNIT_MM,
        value=value,
        availability=availability,
    )


def _contexts(
    scope: str,
    *,
    evidence_completeness: PopulationCompleteness = PopulationCompleteness.FULL,
) -> tuple[ExternalDependencyAuthority, ...]:
    return (
        _authority(
            scope,
            B1_STORY_KEY,
            source_kind=DependencySourceKind.CONTEXT,
            semantic=SemanticType.COMPONENT_STORY,
            dimension=PhysicalDimension.ENUM_STATE,
            unit=UNIT_ENUM_STATE,
            value="S1",
        ),
        _authority(
            scope,
            B1_SECTION_KEY,
            source_kind=DependencySourceKind.CONTEXT,
            semantic=SemanticType.COMPONENT_SECTION,
            dimension=PhysicalDimension.ENUM_STATE,
            unit=UNIT_ENUM_STATE,
            value=f"SEC:{scope}",
        ),
        _authority(
            scope,
            B1_EVIDENCE_TRACE_KEY,
            source_kind=DependencySourceKind.CONTEXT,
            semantic=SemanticType.CHECK_EVIDENCE_TRACE,
            dimension=PhysicalDimension.DIMENSIONLESS,
            unit=UNIT_DIMENSIONLESS,
            value=(f"trace:{scope}",),
            completeness=evidence_completeness,
        ),
    )


def _target(rule_id, scope: str, applicability_input, *, grain: Grain = Grain.COMPONENT) -> RuleScopeTarget:
    return RuleScopeTarget(
        rule_id=rule_id,
        grain=grain,
        scope_ref=scope,
        applicability_input=applicability_input,
    )


def _six_rule_fixture(*, reverse: bool = False) -> RegulatoryCompileInputs:
    targets = (
        _target(
            COLUMN_MIN_DIMENSION_RULE_ID,
            "C_PASS",
            ColumnMinDimensionApplicabilityInput(True, True),
        ),
        _target(
            BEAM_MIN_DEPTH_RULE_ID,
            "B_DEPTH_FAIL",
            Beam7411ApplicabilityInput(True, True),
        ),
        _target(
            BEAM_DEPTH_WIDTH_RATIO_RULE_ID,
            "B_RATIO_PASS",
            Beam7411ApplicabilityInput(True, True),
        ),
        _target(
            WALL_DEFINITION_RULE_ID,
            "W_DEF_FAIL",
            WallDefinitionGE6ApplicabilityInput(True, False),
        ),
        _target(
            WALL_UNRESTRAINED_RULE_ID,
            "W_UNREST_PASS",
            WallUnrestrainedThicknessApplicabilityInput(True, False, True),
        ),
        _target(
            WALL_RESTRAINED_LEG_RULE_ID,
            "W_REST_FAIL",
            WallRestrainedLegApplicabilityInput(True, False, True),
        ),
    )
    authorities = (
        _fact("C_PASS", COLUMN_WIDTH_KEY, SemanticType.COLUMN_WIDTH, 300.0),
        _fact("C_PASS", COLUMN_DEPTH_KEY, SemanticType.COLUMN_DEPTH, 500.0),
        *_contexts("C_PASS"),
        _fact("B_DEPTH_FAIL", BEAM_DEPTH_KEY, SemanticType.BEAM_DEPTH, 299.999),
        *_contexts("B_DEPTH_FAIL"),
        _fact("B_RATIO_PASS", BEAM_DEPTH_KEY, SemanticType.BEAM_DEPTH, 350.0),
        _fact("B_RATIO_PASS", BEAM_WIDTH_KEY, SemanticType.BEAM_WIDTH, 100.0),
        *_contexts("B_RATIO_PASS"),
        _fact("W_DEF_FAIL", WALL_LENGTH_KEY, SemanticType.WALL_LENGTH, 1499.9),
        _fact("W_DEF_FAIL", WALL_THICKNESS_KEY, SemanticType.WALL_THICKNESS, 250.0),
        *_contexts("W_DEF_FAIL"),
        _fact("W_UNREST_PASS", WALL_THICKNESS_KEY, SemanticType.WALL_THICKNESS, 250.0),
        _fact(
            "W_UNREST_PASS",
            WALL_UNRESTRAINED_LENGTH_KEY,
            SemanticType.WALL_UNRESTRAINED_PLAN_LENGTH,
            7500.0,
        ),
        *_contexts("W_UNREST_PASS"),
        _fact("W_REST_FAIL", WALL_THICKNESS_KEY, SemanticType.WALL_THICKNESS, 249.9),
        _fact("W_REST_FAIL", WALL_STORY_HEIGHT_KEY, SemanticType.WALL_STORY_HEIGHT, 4000.0),
        *_contexts("W_REST_FAIL"),
    )
    if reverse:
        targets = tuple(reversed(targets))
        authorities = tuple(reversed(authorities))
    return RegulatoryCompileInputs(rule_targets=targets, external_authorities=authorities)


def _instance(program, rule_id, scope: str):
    return next(
        item for item in program.plan.compiled_rule_instances
        if item.rule_id == rule_id and item.scope_ref == scope
    )


def test_all_six_existing_checks_compile_and_execute_together_with_canonical_closure() -> None:
    program = RegulatoryCompiler.compile(F0_8_REGISTRY, _six_rule_fixture())
    snapshot = RegulatoryEngine.execute(program)
    assessment = AssessmentEngine.reconcile(program, snapshot)

    expected = {
        (COLUMN_MIN_DIMENSION_RULE_ID, "C_PASS"): CheckStatus.OK,
        (BEAM_MIN_DEPTH_RULE_ID, "B_DEPTH_FAIL"): CheckStatus.FAIL,
        (BEAM_DEPTH_WIDTH_RATIO_RULE_ID, "B_RATIO_PASS"): CheckStatus.OK,
        (WALL_DEFINITION_RULE_ID, "W_DEF_FAIL"): CheckStatus.FAIL,
        (WALL_UNRESTRAINED_RULE_ID, "W_UNREST_PASS"): CheckStatus.OK,
        (WALL_RESTRAINED_LEG_RULE_ID, "W_REST_FAIL"): CheckStatus.FAIL,
    }
    assert len(program.plan.compiled_rule_instances) == 6
    for (rule_id, scope), status in expected.items():
        instance = _instance(program, rule_id, scope)
        results = snapshot.formal_results_for(instance)
        assert len(results) == 1
        assert results[0].status is status
        assert snapshot.outcome_for(instance).execution_status is ClosureExecutionStatus.EXECUTED

    assert assessment.structural_status is StructuralAssessmentStatus.COMPLETE
    assert assessment.incomplete_mandatory_instances == ()
    assert assessment.full_tbdy_compliance_status == "NOT_EVALUATED"


@pytest.mark.parametrize(
    "availability,expected",
    [
        (AvailabilityState.NO_DATA, ClosureExecutionStatus.NO_DATA),
        (AvailabilityState.BLOCKED, ClosureExecutionStatus.BLOCKED),
    ],
)
def test_geometry_availability_is_runtime_readiness_not_formal_result(
    availability: AvailabilityState,
    expected: ClosureExecutionStatus,
) -> None:
    scope = f"B_AVAIL_{availability.value}"
    inputs = RegulatoryCompileInputs(
        rule_targets=(
            _target(
                BEAM_MIN_DEPTH_RULE_ID,
                scope,
                Beam7411ApplicabilityInput(True, True),
            ),
        ),
        external_authorities=(
            _fact(scope, BEAM_DEPTH_KEY, SemanticType.BEAM_DEPTH, None, availability=availability),
            *_contexts(scope),
        ),
    )
    program = RegulatoryCompiler.compile(
        RegulatoryRegistry(checks=(BEAM_MIN_DEPTH_CHECK_SPEC,)),
        inputs,
    )
    snapshot = RegulatoryEngine.execute(program)
    instance = _instance(program, BEAM_MIN_DEPTH_RULE_ID, scope)
    assert snapshot.formal_results_for(instance) == ()
    assert snapshot.outcome_for(instance).execution_status is expected


def test_incomplete_evidence_trace_is_static_full_population_compile_rejection() -> None:
    scope = "B_INCOMPLETE_TRACE"
    inputs = RegulatoryCompileInputs(
        rule_targets=(
            _target(
                BEAM_MIN_DEPTH_RULE_ID,
                scope,
                Beam7411ApplicabilityInput(True, True),
            ),
        ),
        external_authorities=(
            _fact(scope, BEAM_DEPTH_KEY, SemanticType.BEAM_DEPTH, 300.0),
            *_contexts(scope, evidence_completeness=PopulationCompleteness.INCOMPLETE),
        ),
    )
    with pytest.raises(KernelCompileError, match="FULL population requirement is not satisfiable"):
        RegulatoryCompiler.compile(
            RegulatoryRegistry(checks=(BEAM_MIN_DEPTH_CHECK_SPEC,)),
            inputs,
        )


def test_applicability_pna_and_unresolved_are_non_result_closure_states() -> None:
    pna_scope = "B_PNA"
    unresolved_scope = "B_UNRESOLVED"
    inputs = RegulatoryCompileInputs(
        rule_targets=(
            _target(
                BEAM_MIN_DEPTH_RULE_ID,
                pna_scope,
                Beam7411ApplicabilityInput(False, True),
            ),
            _target(
                BEAM_DEPTH_WIDTH_RATIO_RULE_ID,
                unresolved_scope,
                Beam7411ApplicabilityInput(True, None),
            ),
        ),
        external_authorities=(
            _fact(pna_scope, BEAM_DEPTH_KEY, SemanticType.BEAM_DEPTH, 300.0),
            *_contexts(pna_scope),
            _fact(unresolved_scope, BEAM_DEPTH_KEY, SemanticType.BEAM_DEPTH, 350.0),
            _fact(unresolved_scope, BEAM_WIDTH_KEY, SemanticType.BEAM_WIDTH, 100.0),
            *_contexts(unresolved_scope),
        ),
    )
    registry = RegulatoryRegistry(
        checks=(BEAM_MIN_DEPTH_CHECK_SPEC, BEAM_DEPTH_WIDTH_RATIO_CHECK_SPEC)
    )
    program = RegulatoryCompiler.compile(registry, inputs)
    snapshot = RegulatoryEngine.execute(program)
    pna = _instance(program, BEAM_MIN_DEPTH_RULE_ID, pna_scope)
    unresolved = _instance(program, BEAM_DEPTH_WIDTH_RATIO_RULE_ID, unresolved_scope)
    assert snapshot.formal_results_for(pna) == ()
    assert snapshot.outcome_for(pna).execution_status is ClosureExecutionStatus.PROVEN_NOT_APPLICABLE
    assert snapshot.formal_results_for(unresolved) == ()
    assert snapshot.outcome_for(unresolved).execution_status is ClosureExecutionStatus.BLOCKED


@pytest.mark.parametrize(
    "rule_id,spec,applicability,facts",
    [
        (
            BEAM_MIN_DEPTH_RULE_ID,
            BEAM_MIN_DEPTH_CHECK_SPEC,
            Beam7411ApplicabilityInput(True, True),
            ((BEAM_DEPTH_KEY, SemanticType.BEAM_DEPTH, 300.0),),
        ),
        (
            WALL_DEFINITION_RULE_ID,
            WALL_DEFINITION_GE6_CHECK_SPEC,
            WallDefinitionGE6ApplicabilityInput(True, False),
            (
                (WALL_LENGTH_KEY, SemanticType.WALL_LENGTH, 1500.0),
                (WALL_THICKNESS_KEY, SemanticType.WALL_THICKNESS, 250.0),
            ),
        ),
    ],
)
def test_wrong_grain_target_never_emits_f0_8_formal_result(
    rule_id,
    spec,
    applicability,
    facts,
) -> None:
    scope = f"WRONG_{rule_id.value}"
    inputs = RegulatoryCompileInputs(
        rule_targets=(
            RuleScopeTarget(
                rule_id=rule_id,
                grain=Grain.MATERIAL_DEFINITION,
                scope_ref=scope,
                applicability_input=applicability,
            ),
        ),
        external_authorities=(
            *(_fact(scope, key, semantic, value) for key, semantic, value in facts),
            *_contexts(scope),
        ),
    )
    program = RegulatoryCompiler.compile(RegulatoryRegistry(checks=(spec,)), inputs)
    instance = _instance(program, rule_id, scope)
    assert instance.grain is Grain.MATERIAL_DEFINITION
    with pytest.raises(ValueError, match="Grain.COMPONENT"):
        RegulatoryEngine.execute(program)


def test_findings_project_existing_failures_only_for_b1_and_wall() -> None:
    program = RegulatoryCompiler.compile(F0_8_REGISTRY, _six_rule_fixture())
    snapshot = RegulatoryEngine.execute(program)

    b1_fail = _instance(program, BEAM_MIN_DEPTH_RULE_ID, "B_DEPTH_FAIL")
    b1_ok = _instance(program, COLUMN_MIN_DIMENSION_RULE_ID, "C_PASS")
    wall_fail = _instance(program, WALL_DEFINITION_RULE_ID, "W_DEF_FAIL")
    wall_ok = _instance(program, WALL_UNRESTRAINED_RULE_ID, "W_UNREST_PASS")

    b1_finding = build_finding_from_check_result(
        instance_id=b1_fail,
        result=snapshot.formal_results_for(b1_fail)[0],
        evidence_refs=("finding:b1",),
    )
    wall_finding = build_finding_from_check_result(
        instance_id=wall_fail,
        result=snapshot.formal_results_for(wall_fail)[0],
        evidence_refs=("finding:wall",),
    )
    assert b1_finding is not None and b1_finding.source_status is CheckStatus.FAIL
    assert wall_finding is not None and wall_finding.source_status is CheckStatus.FAIL
    assert build_finding_from_check_result(
        instance_id=b1_ok, result=snapshot.formal_results_for(b1_ok)[0]
    ) is None
    assert build_finding_from_check_result(
        instance_id=wall_ok, result=snapshot.formal_results_for(wall_ok)[0]
    ) is None


def test_combined_registry_has_exactly_eight_unique_independently_resolvable_rules() -> None:
    checks = (
        BEAM_MIN_WIDTH_CHECK_SPEC,
        CONCRETE_MATERIAL_MIN_STRENGTH_CHECK_SPEC,
        *B1_GEOMETRY_PARITY_CHECK_SPECS,
        *WALL_PACK_A_GEOMETRY_PARITY_CHECK_SPECS,
    )
    first = RegulatoryRegistry(checks=checks)
    second = RegulatoryRegistry(checks=tuple(reversed(checks)))
    assert first.rule_count == 8
    assert len({spec.rule_id for spec in first.checks}) == 8
    assert first.registry_version == second.registry_version
    for spec in checks:
        assert first.rule(spec.rule_id) is spec
    assert sum(spec.rule_id == BEAM_MIN_WIDTH_CHECK_SPEC.rule_id for spec in first.checks) == 1


def test_equivalent_input_order_is_deterministic() -> None:
    first = RegulatoryCompiler.compile(F0_8_REGISTRY, _six_rule_fixture(reverse=False))
    second = RegulatoryCompiler.compile(F0_8_REGISTRY, _six_rule_fixture(reverse=True))
    first_snapshot = RegulatoryEngine.execute(first)
    second_snapshot = RegulatoryEngine.execute(second)
    assert first.plan.plan_identity == second.plan.plan_identity
    assert first.plan.deterministic_execution_order == second.plan.deterministic_execution_order
    assert first.plan.compiled_closure_inventory == second.plan.compiled_closure_inventory
    assert first_snapshot == second_snapshot
