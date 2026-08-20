from __future__ import annotations

import ast
from pathlib import Path

import pytest

from tbdy_engine.checks.engine import MinimalCheckEngine
from tbdy_engine.checks.input_adapter import CheckExecutionContext, GeometryCheckInput
from tbdy_engine.checks.member_geometry import (
    BEAM_7411_APPLICABILITY_CONTEXT,
    BEAM_MIN_WIDTH,
    MEMBER_GEOMETRY_REGISTRATIONS,
    registration_check_definitions,
)
from tbdy_engine.checks.result import CheckResult, CheckStatus, EvaluationLevel
from tbdy_engine.coverage.models import CoverageRow
from tbdy_engine.features.evidence import FeatureEvidence
from tbdy_engine.features.snapshot import FeatureSnapshot
from tbdy_engine.features.value import FeatureValue
from tbdy_engine.regulatory.beam_min_width import (
    BEAM_MIN_WIDTH_CHECK_SPEC,
    BEAM_MIN_WIDTH_DEPENDENCIES,
    BEAM_WIDTH_KEY,
    EVIDENCE_TRACE_KEY,
    F0_2_BEAM_MIN_WIDTH_REGISTRY,
    RULE_ID,
    RULE_VERSION,
    SECTION_KEY,
    STORY_KEY,
    BeamMinWidthApplicabilityInput,
    BeamMinWidthExecutionInput,
)
from tbdy_engine.regulatory.contracts import (
    ApplicabilityState,
    AvailabilityState,
    ClosureExecutionStatus,
    DependencySourceKind,
    Grain,
    PhysicalDimension,
    RuleId,
    SemanticType,
)
from tbdy_engine.regulatory.kernel import (
    AssessmentEngine,
    ExternalDependencyAuthority,
    PopulationCompleteness,
    RegulatoryCompileInputs,
    RegulatoryCompiler,
    RegulatoryEngine,
    RuleScopeTarget,
    StructuralAssessmentStatus,
)
from tbdy_engine.regulatory.units import UNIT_DIMENSIONLESS, UNIT_ENUM_STATE, UNIT_MM

COMPONENT_ID = "B1"
STORY = "S1"
SECTION = "SEC1"


def _evidence(width_mm: float) -> FeatureEvidence:
    return FeatureEvidence(
        evidence_status="FULL",
        source_table="F0.2 parity fixture",
        actual_table_name="F0.2 parity fixture",
        source_column="beam_width_mm",
        raw_value=width_mm,
        normalized_value=width_mm,
        unit="mm",
        resolver="f0.2-parity-fixture",
    )


def _legacy_result(width_mm: float, evidence: FeatureEvidence) -> CheckResult:
    feature = FeatureValue(
        feature_name="beam_width_mm",
        value=width_mm,
        unit="mm",
        semantic_role="GEOMETRY",
        status="RESOLVED",
        evidence=[evidence],
    )
    snapshot = FeatureSnapshot(
        component_type="beam",
        component_id=COMPONENT_ID,
        identity={"story": STORY, "section": SECTION},
        features={"beam_width_mm": feature},
    )
    coverage = CoverageRow(
        check_id=BEAM_MIN_WIDTH,
        component_type="beam",
        component_id=COMPONENT_ID,
        required_features=("beam_width_mm",),
        resolved_features=("beam_width_mm",),
        coverage_status="RUNNABLE",
        evidence_status="FULL",
    )
    check_input = GeometryCheckInput(
        check_id=BEAM_MIN_WIDTH,
        component_id=COMPONENT_ID,
        component_type="beam",
        story=STORY,
        section=SECTION,
        required_features=("beam_width_mm",),
        snapshot=snapshot,
        coverage=coverage,
        evidence_by_feature={"beam_width_mm": (evidence,)},
        execution_context=CheckExecutionContext(
            values={BEAM_7411_APPLICABILITY_CONTEXT: True}
        ),
    )
    return MinimalCheckEngine(registration_check_definitions()).run_input(check_input)


def _authority(
    *,
    authority_id: str,
    key,
    source_kind: DependencySourceKind,
    semantic_type: SemanticType,
    physical_dimension: PhysicalDimension,
    unit,
    value: object,
    availability: AvailabilityState = AvailabilityState.RESOLVED,
    provenance_refs: tuple[str, ...] = (),
) -> ExternalDependencyAuthority:
    return ExternalDependencyAuthority(
        authority_id=authority_id,
        key=key,
        source_kind=source_kind,
        semantic_type=semantic_type,
        physical_dimension=physical_dimension,
        grain=Grain.COMPONENT,
        scope_ref=COMPONENT_ID,
        direction=None,
        unit=unit,
        availability=availability,
        population_completeness=PopulationCompleteness.FULL,
        value=value,
        provenance_refs=provenance_refs,
    )


def _compile_program(
    *,
    width_mm: float | None,
    evidence: FeatureEvidence,
    applies: bool | None = True,
    width_availability: AvailabilityState = AvailabilityState.RESOLVED,
):
    evidence_payload = (evidence.as_dict(),)
    target = RuleScopeTarget(
        rule_id=RULE_ID,
        grain=Grain.COMPONENT,
        scope_ref=COMPONENT_ID,
        direction=None,
        applicability_input=BeamMinWidthApplicabilityInput(
            component_type="beam",
            tbdy_7411_applies=applies,
        ),
    )
    authorities = (
        _authority(
            authority_id="f0.2:beam-width:B1",
            key=BEAM_WIDTH_KEY,
            source_kind=DependencySourceKind.FACT,
            semantic_type=SemanticType.BEAM_WIDTH,
            physical_dimension=PhysicalDimension.LENGTH,
            unit=UNIT_MM,
            value=width_mm,
            availability=width_availability,
            provenance_refs=("fixture:beam-width:B1",),
        ),
        _authority(
            authority_id="f0.2:story:B1",
            key=STORY_KEY,
            source_kind=DependencySourceKind.CONTEXT,
            semantic_type=SemanticType.COMPONENT_STORY,
            physical_dimension=PhysicalDimension.ENUM_STATE,
            unit=UNIT_ENUM_STATE,
            value=STORY,
            provenance_refs=("fixture:story:B1",),
        ),
        _authority(
            authority_id="f0.2:section:B1",
            key=SECTION_KEY,
            source_kind=DependencySourceKind.CONTEXT,
            semantic_type=SemanticType.COMPONENT_SECTION,
            physical_dimension=PhysicalDimension.ENUM_STATE,
            unit=UNIT_ENUM_STATE,
            value=SECTION,
            provenance_refs=("fixture:section:B1",),
        ),
        _authority(
            authority_id="f0.2:evidence:B1",
            key=EVIDENCE_TRACE_KEY,
            source_kind=DependencySourceKind.CONTEXT,
            semantic_type=SemanticType.CHECK_EVIDENCE_TRACE,
            physical_dimension=PhysicalDimension.DIMENSIONLESS,
            unit=UNIT_DIMENSIONLESS,
            value=evidence_payload,
            provenance_refs=("fixture:evidence:B1",),
        ),
    )
    inputs = RegulatoryCompileInputs(
        rule_targets=(target,),
        external_authorities=authorities,
    )
    return RegulatoryCompiler.compile(F0_2_BEAM_MIN_WIDTH_REGISTRY, inputs)


def _dag_result(width_mm: float, evidence: FeatureEvidence) -> CheckResult:
    program = _compile_program(width_mm=width_mm, evidence=evidence)
    snapshot = RegulatoryEngine.execute(program)
    instance = program.plan.compiled_rule_instances[0]
    results = snapshot.formal_results_for(instance)
    assert len(results) == 1
    return results[0]


def test_f0_2_registry_contains_exactly_one_real_check_spec() -> None:
    assert F0_2_BEAM_MIN_WIDTH_REGISTRY.rule_count == 1
    assert F0_2_BEAM_MIN_WIDTH_REGISTRY.derivations == ()
    assert len(F0_2_BEAM_MIN_WIDTH_REGISTRY.checks) == 1
    assert F0_2_BEAM_MIN_WIDTH_REGISTRY.checks[0] is BEAM_MIN_WIDTH_CHECK_SPEC
    assert BEAM_MIN_WIDTH_CHECK_SPEC.rule_id == RuleId("beam_geometry_min_width")
    assert RULE_ID == RuleId(BEAM_MIN_WIDTH)
    assert RULE_VERSION == "f0.2-parity-v1"


def test_f0_2_dependencies_are_exact_narrow_typed_authorities() -> None:
    assert tuple(dep.key for dep in BEAM_MIN_WIDTH_DEPENDENCIES) == (
        BEAM_WIDTH_KEY,
        STORY_KEY,
        SECTION_KEY,
        EVIDENCE_TRACE_KEY,
    )
    width = BEAM_MIN_WIDTH_DEPENDENCIES[0]
    assert width.source_kind is DependencySourceKind.FACT
    assert width.semantic_type is SemanticType.BEAM_WIDTH
    assert width.physical_dimension is PhysicalDimension.LENGTH
    assert width.grain is Grain.COMPONENT
    assert width.unit_requirement == UNIT_MM
    assert all(dep.direction_policy.value == "NO_DIRECTION" for dep in BEAM_MIN_WIDTH_DEPENDENCIES)


def test_f0_2_execution_input_has_no_generic_dependency_escape_hatch() -> None:
    assert tuple(BeamMinWidthExecutionInput.__dataclass_fields__) == (
        "envelope",
        "component_id",
        "beam_width_mm",
        "story",
        "section",
        "evidence",
    )
    assert "dependencies" not in BeamMinWidthExecutionInput.__dataclass_fields__


def test_f0_2_production_module_reuses_member_authority_without_legacy_engine_or_etabs() -> None:
    import tbdy_engine.regulatory.beam_min_width as module

    source = Path(module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_names: list[str] = []
    calls: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported_names.append(node.module or "")
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            calls.append(node.func.id)

    assert "MinimalCheckEngine" not in source
    assert all("etabs" not in name.casefold() for name in imported_names)
    assert "evaluate_member_rule" in calls
    assert "ModelContext" not in source
    assert MEMBER_GEOMETRY_REGISTRATIONS[BEAM_MIN_WIDTH].limit == 250.0


@pytest.mark.parametrize(
    ("width_mm", "expected_status"),
    [
        (249.0, CheckStatus.FAIL),
        (250.0, CheckStatus.OK),
        (400.0, CheckStatus.OK),
    ],
)
def test_f0_2_exact_canonical_CheckResult_parity_for_executable_applies(
    width_mm: float,
    expected_status: CheckStatus,
) -> None:
    evidence = _evidence(width_mm)
    legacy_result = _legacy_result(width_mm, evidence)
    dag_result = _dag_result(width_mm, evidence)

    assert legacy_result.status is expected_status
    assert dag_result.status is expected_status
    assert dag_result == legacy_result
    assert dag_result.check_id == "beam_geometry_min_width"
    assert dag_result.component == COMPONENT_ID
    assert dag_result.component_type == "beam"
    assert dag_result.story == STORY
    assert dag_result.section == SECTION
    assert dag_result.ratio_type == "actual_over_minimum"
    assert dag_result.pass_rule == "actual_over_minimum"
    assert dag_result.unit == "mm"
    assert dag_result.evaluation_level is EvaluationLevel.DESIGN_LEVEL
    assert dag_result.messages == ("Formal canonical beam/column geometry CheckResult",)
    assert dag_result.code_ref == "TBDY-2018-7.4.1.1(a)"
    assert dag_result.diagnostics == ()
    assert dag_result.demand is None
    assert dag_result.capacity is None
    assert dag_result.evidence == legacy_result.evidence


def test_f0_2_proven_not_applicable_closes_without_fabricated_CheckResult() -> None:
    evidence = _evidence(400.0)
    program = _compile_program(width_mm=400.0, evidence=evidence, applies=False)
    record = program.plan.compiled_closure_inventory[0]
    assert record.applicability is ApplicabilityState.PROVEN_NOT_APPLICABLE

    snapshot = RegulatoryEngine.execute(program)
    assert snapshot.formal_results == ()
    assert snapshot.closure_outcomes[0].execution_status is ClosureExecutionStatus.PROVEN_NOT_APPLICABLE

    assessment = AssessmentEngine.reconcile(program, snapshot)
    assert assessment.structural_status is StructuralAssessmentStatus.COMPLETE
    assert assessment.full_tbdy_compliance_status == "NOT_EVALUATED"


def test_f0_2_unresolved_applicability_remains_fail_closed_without_result() -> None:
    evidence = _evidence(400.0)
    program = _compile_program(width_mm=400.0, evidence=evidence, applies=None)
    assert program.plan.compiled_closure_inventory[0].applicability is ApplicabilityState.UNRESOLVED

    snapshot = RegulatoryEngine.execute(program)
    assert snapshot.formal_results == ()
    assert snapshot.closure_outcomes[0].execution_status is ClosureExecutionStatus.BLOCKED

    assessment = AssessmentEngine.reconcile(program, snapshot)
    assert assessment.structural_status is StructuralAssessmentStatus.INCOMPLETE
    assert assessment.full_tbdy_compliance_status == "NOT_EVALUATED"


@pytest.mark.parametrize(
    ("availability", "expected_outcome"),
    [
        (AvailabilityState.BLOCKED, ClosureExecutionStatus.BLOCKED),
        (AvailabilityState.NO_DATA, ClosureExecutionStatus.NO_DATA),
    ],
)
def test_f0_2_unavailable_width_never_executes_or_fabricates_formal_result(
    availability: AvailabilityState,
    expected_outcome: ClosureExecutionStatus,
) -> None:
    evidence = _evidence(250.0)
    program = _compile_program(
        width_mm=None,
        evidence=evidence,
        applies=True,
        width_availability=availability,
    )
    snapshot = RegulatoryEngine.execute(program)
    assert snapshot.formal_results == ()
    assert snapshot.closure_outcomes[0].execution_status is expected_outcome

    assessment = AssessmentEngine.reconcile(program, snapshot)
    assert assessment.structural_status is StructuralAssessmentStatus.INCOMPLETE
    assert assessment.full_tbdy_compliance_status == "NOT_EVALUATED"


def test_f0_2_equivalent_immutable_inputs_are_deterministic() -> None:
    first_evidence = _evidence(250.0)
    second_evidence = _evidence(250.0)
    first = _compile_program(width_mm=250.0, evidence=first_evidence)
    second = _compile_program(width_mm=250.0, evidence=second_evidence)

    assert first.plan.compiled_rule_instances == second.plan.compiled_rule_instances
    assert first.plan.plan_identity == second.plan.plan_identity
    assert RegulatoryEngine.execute(first) == RegulatoryEngine.execute(second)


def test_f0_2_executable_instance_emits_exactly_one_canonical_result_and_structurally_closes() -> None:
    evidence = _evidence(250.0)
    program = _compile_program(width_mm=250.0, evidence=evidence)
    snapshot = RegulatoryEngine.execute(program)
    instance = program.plan.compiled_rule_instances[0]

    assert len(snapshot.formal_results) == 1
    assert len(snapshot.formal_results_for(instance)) == 1
    assert type(snapshot.formal_results_for(instance)[0]) is CheckResult
    assert snapshot.regulatory_quantities == ()

    assessment = AssessmentEngine.reconcile(program, snapshot)
    assert assessment.structural_status is StructuralAssessmentStatus.COMPLETE
    assert assessment.full_tbdy_compliance_status == "NOT_EVALUATED"
