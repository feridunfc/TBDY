from __future__ import annotations

import ast
from pathlib import Path

import pytest

from tbdy_engine.checks.member_geometry import BEAM_MIN_WIDTH
from tbdy_engine.checks.result import CheckResult, CheckStatus, EvaluationLevel
from tbdy_engine.features.used_rc_material_population import (
    ConcreteStrengthFactStatus,
    MaterialPopulationReadiness,
    MaterialUsageReference,
    MaterialUsageStatus,
    UsedMaterialDefinition,
    UsedRcMaterialPopulation,
)
from tbdy_engine.regulatory.beam_min_width import (
    BEAM_MIN_WIDTH_CHECK_SPEC,
    BEAM_WIDTH_KEY,
    EVIDENCE_TRACE_KEY as BEAM_EVIDENCE_TRACE_KEY,
    RULE_ID as BEAM_RULE_ID,
    SECTION_KEY as BEAM_SECTION_KEY,
    STORY_KEY as BEAM_STORY_KEY,
    BeamMinWidthApplicabilityInput,
)
from tbdy_engine.regulatory.concrete_material_min_strength import (
    CODE_REF,
    CONCRETE_FCK_KEY,
    CONCRETE_MATERIAL_MIN_STRENGTH_CHECK_SPEC,
    CONCRETE_MATERIAL_MIN_STRENGTH_DEPENDENCIES,
    F0_3_CONCRETE_MATERIAL_MIN_STRENGTH_REGISTRY,
    MATERIAL_EVIDENCE_TRACE_KEY,
    MATERIAL_NAME_KEY,
    MIN_CONCRETE_CLASS_LABEL,
    MIN_FCK_MPA,
    REVIEWED_ETABS_CONCRETE_TYPE_CODE,
    REVIEWED_ETABS_MATERIAL_TYPE_BINDING_ID,
    RULE_ID,
    RULE_VERSION,
    USED_RC_MATERIAL_POPULATION_KEY,
    ConcreteMaterialMinStrengthApplicabilityInput,
    ConcreteMaterialMinStrengthExecutionInput,
    build_concrete_material_min_strength_compile_inputs,
    concrete_material_min_strength_applicability,
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

MODEL_FINGERPRINT = "MODEL-F0-3"
MATERIAL_ID = "MAT-C25"


def _usage(index: int, *, material_name: str = "Concrete-C25") -> MaterialUsageReference:
    return MaterialUsageReference(
        usage_id=f"USAGE-{index:03d}",
        component_type="beam",
        component_identity=f"B{index}",
        story="S1",
        label=f"B{index}",
        assigned_property=f"SEC-{index}",
        material_name=material_name,
        material_type_code=2,
        status=MaterialUsageStatus.RESOLVED_CONCRETE_USAGE,
        source_references=(),
        diagnostics=(),
    )


def _material(
    *,
    material_id: str = MATERIAL_ID,
    material_name: str = "Concrete-C25",
    fck: float | None = 25.0,
    material_type_code: int = 2,
    is_concrete: bool = True,
    strength_status: ConcreteStrengthFactStatus = ConcreteStrengthFactStatus.RESOLVED,
    usages: tuple[MaterialUsageReference, ...] = (),
) -> UsedMaterialDefinition:
    return UsedMaterialDefinition(
        material_id=material_id,
        model_fingerprint=MODEL_FINGERPRINT,
        material_name=material_name,
        material_type_code=material_type_code,
        is_concrete=is_concrete,
        raw_fc=None,
        canonical_fck_mpa=fck,
        concrete_strength_status=strength_status,
        unit_context=None,
        usage_references=usages,
        diagnostics=(),
    )


def _population(
    *materials: UsedMaterialDefinition,
    readiness: MaterialPopulationReadiness = MaterialPopulationReadiness.COMPLETE,
) -> UsedRcMaterialPopulation:
    usages = tuple(
        usage
        for material in materials
        for usage in material.usage_references
    )
    return UsedRcMaterialPopulation(
        model_fingerprint=MODEL_FINGERPRINT,
        usages=usages,
        used_material_definitions=tuple(materials),
        reconciliations=(),
        readiness=readiness,
        diagnostics=(),
        source_binding=None,
    )


def _program(population: UsedRcMaterialPopulation):
    inputs = build_concrete_material_min_strength_compile_inputs(population)
    return RegulatoryCompiler.compile(F0_3_CONCRETE_MATERIAL_MIN_STRENGTH_REGISTRY, inputs)


def _execute_one(fck: float) -> CheckResult:
    program = _program(_population(_material(fck=fck)))
    snapshot = RegulatoryEngine.execute(program)
    assert len(snapshot.formal_results) == 1
    return snapshot.formal_results[0].result


def test_f0_3_rule_identity_authority_and_exact_single_registration() -> None:
    assert RULE_ID == RuleId("CONCRETE_MATERIAL_MIN_STRENGTH")
    assert RULE_VERSION == "f0.3-v1"
    assert CODE_REF == "TBDY-2018-7.2.5.1"
    assert MIN_FCK_MPA == 25.0
    assert MIN_CONCRETE_CLASS_LABEL == "C25"
    assert REVIEWED_ETABS_CONCRETE_TYPE_CODE == 2
    assert REVIEWED_ETABS_MATERIAL_TYPE_BINDING_ID == "CSI_ETABS_MATERIAL_TYPE_CODE_2_CONCRETE_V1"
    assert F0_3_CONCRETE_MATERIAL_MIN_STRENGTH_REGISTRY.rule_count == 1
    assert F0_3_CONCRETE_MATERIAL_MIN_STRENGTH_REGISTRY.derivations == ()
    assert F0_3_CONCRETE_MATERIAL_MIN_STRENGTH_REGISTRY.checks == (
        CONCRETE_MATERIAL_MIN_STRENGTH_CHECK_SPEC,
    )
    assert CONCRETE_MATERIAL_MIN_STRENGTH_CHECK_SPEC.evaluator.input_type is ConcreteMaterialMinStrengthExecutionInput


def test_f0_3_declared_dependencies_are_exact_and_typed() -> None:
    assert tuple(dep.key for dep in CONCRETE_MATERIAL_MIN_STRENGTH_DEPENDENCIES) == (
        USED_RC_MATERIAL_POPULATION_KEY,
        CONCRETE_FCK_KEY,
        MATERIAL_NAME_KEY,
        MATERIAL_EVIDENCE_TRACE_KEY,
    )
    population, fck, name, evidence = CONCRETE_MATERIAL_MIN_STRENGTH_DEPENDENCIES
    assert population.source_kind is DependencySourceKind.SOURCE_POPULATION
    assert population.semantic_type is SemanticType.USED_RC_MATERIAL_POPULATION
    assert population.physical_dimension is PhysicalDimension.ENUM_STATE
    assert population.grain is Grain.MODEL
    assert population.population_completeness_requirement.value == "FULL"
    assert fck.source_kind is DependencySourceKind.FACT
    assert fck.semantic_type is SemanticType.CONCRETE_FCK
    assert fck.physical_dimension is PhysicalDimension.STRESS
    assert fck.grain is Grain.MATERIAL_DEFINITION
    assert name.semantic_type is SemanticType.MATERIAL_NAME
    assert evidence.semantic_type is SemanticType.MATERIAL_EVIDENCE_TRACE
    assert all(dep.direction_policy.value == "NO_DIRECTION" for dep in CONCRETE_MATERIAL_MIN_STRENGTH_DEPENDENCIES)


def test_f0_3_execution_input_is_narrow_and_has_no_generic_dependency_escape_hatch() -> None:
    assert tuple(ConcreteMaterialMinStrengthExecutionInput.__dataclass_fields__) == (
        "envelope",
        "material_id",
        "canonical_fck_mpa",
        "material_name",
        "evidence",
    )
    assert "dependencies" not in ConcreteMaterialMinStrengthExecutionInput.__dataclass_fields__


@pytest.mark.parametrize(
    ("fck", "expected"),
    [
        (24.0, CheckStatus.FAIL),
        (24.999, CheckStatus.FAIL),
        (25.0, CheckStatus.OK),
        (30.0, CheckStatus.OK),
    ],
)
def test_f0_3_exact_formal_boundary_and_full_CheckResult_contract(
    fck: float,
    expected: CheckStatus,
) -> None:
    result = _execute_one(fck)
    assert result == CheckResult(
        check_id="CONCRETE_MATERIAL_MIN_STRENGTH",
        component=MATERIAL_ID,
        component_type="material_definition",
        story=None,
        section=None,
        status=expected,
        value=fck,
        limit=25.0,
        demand=None,
        capacity=None,
        ratio=fck / 25.0,
        ratio_type="actual_over_minimum",
        pass_rule="actual_over_minimum",
        unit="MPa",
        evaluation_level=EvaluationLevel.DESIGN_LEVEL,
        evidence=result.evidence,
        messages=("Formal TBDY concrete material minimum-strength CheckResult",),
        code_ref="TBDY-2018-7.2.5.1",
        diagnostics=(),
    )
    assert result.evidence
    assert result.evidence[0]["canonical_fck_mpa"] == fck


def test_f0_3_has_no_tolerance_rounding_or_epsilon_at_boundary() -> None:
    below = _execute_one(24.999999999999)
    exact = _execute_one(25.0)
    assert below.status is CheckStatus.FAIL
    assert exact.status is CheckStatus.OK
    assert below.value == 24.999999999999
    assert below.ratio == 24.999999999999 / 25.0


@pytest.mark.parametrize(
    ("material_type_code", "is_concrete", "binding_id", "expected"),
    [
        (2, True, REVIEWED_ETABS_MATERIAL_TYPE_BINDING_ID, ApplicabilityState.APPLIES),
        (1, False, REVIEWED_ETABS_MATERIAL_TYPE_BINDING_ID, ApplicabilityState.PROVEN_NOT_APPLICABLE),
        (2, False, REVIEWED_ETABS_MATERIAL_TYPE_BINDING_ID, ApplicabilityState.INVALID_CONTEXT),
        (1, True, REVIEWED_ETABS_MATERIAL_TYPE_BINDING_ID, ApplicabilityState.INVALID_CONTEXT),
        (2, True, "WRONG_BINDING", ApplicabilityState.INVALID_CONTEXT),
    ],
)
def test_f0_3_reviewed_material_type_applicability_is_exact(
    material_type_code: int,
    is_concrete: bool,
    binding_id: str,
    expected: ApplicabilityState,
) -> None:
    assert concrete_material_min_strength_applicability(
        ConcreteMaterialMinStrengthApplicabilityInput(
            material_type_code=material_type_code,
            is_concrete=is_concrete,
            api_semantic_binding_id=binding_id,
        )
    ) is expected


def test_f0_3_non_concrete_candidate_remains_inventory_pna_without_result() -> None:
    non_concrete = _material(
        material_id="MAT-STEEL",
        material_name="Steel",
        fck=None,
        material_type_code=1,
        is_concrete=False,
        strength_status=ConcreteStrengthFactStatus.NOT_APPLICABLE,
    )
    program = _program(_population(non_concrete))
    record = program.plan.compiled_closure_inventory[0]
    assert record.grain is Grain.MATERIAL_DEFINITION
    assert record.scope_ref == "MAT-STEEL"
    assert record.applicability is ApplicabilityState.PROVEN_NOT_APPLICABLE
    snapshot = RegulatoryEngine.execute(program)
    assert snapshot.formal_results == ()
    assert snapshot.closure_outcomes[0].execution_status is ClosureExecutionStatus.PROVEN_NOT_APPLICABLE
    assessment = AssessmentEngine.reconcile(program, snapshot)
    assert assessment.structural_status is StructuralAssessmentStatus.COMPLETE
    assert assessment.full_tbdy_compliance_status == "NOT_EVALUATED"


@pytest.mark.parametrize(
    ("type_code", "is_concrete"),
    [(2, False), (1, True)],
)
def test_f0_3_invalid_material_semantics_never_fabricate_CheckResult(
    type_code: int,
    is_concrete: bool,
) -> None:
    material = _material(
        material_type_code=type_code,
        is_concrete=is_concrete,
        strength_status=(
            ConcreteStrengthFactStatus.RESOLVED
            if is_concrete
            else ConcreteStrengthFactStatus.NOT_APPLICABLE
        ),
    )
    program = _program(_population(material))
    assert program.plan.compiled_closure_inventory[0].applicability is ApplicabilityState.INVALID_CONTEXT
    snapshot = RegulatoryEngine.execute(program)
    assert snapshot.formal_results == ()
    assert snapshot.closure_outcomes[0].execution_status is ClosureExecutionStatus.INVALID
    assert AssessmentEngine.reconcile(program, snapshot).structural_status is StructuralAssessmentStatus.INCOMPLETE


def test_f0_3_wrong_reviewed_binding_is_invalid_and_nonexecuting() -> None:
    population = _population(_material(fck=30.0))
    good = build_concrete_material_min_strength_compile_inputs(population)
    bad_target = RuleScopeTarget(
        rule_id=RULE_ID,
        grain=Grain.MATERIAL_DEFINITION,
        scope_ref=MATERIAL_ID,
        direction=None,
        applicability_input=ConcreteMaterialMinStrengthApplicabilityInput(
            material_type_code=2,
            is_concrete=True,
            api_semantic_binding_id="WRONG_BINDING",
        ),
    )
    inputs = RegulatoryCompileInputs(
        rule_targets=(bad_target,),
        external_authorities=good.external_authorities,
    )
    program = RegulatoryCompiler.compile(F0_3_CONCRETE_MATERIAL_MIN_STRENGTH_REGISTRY, inputs)
    snapshot = RegulatoryEngine.execute(program)
    assert program.plan.compiled_closure_inventory[0].applicability is ApplicabilityState.INVALID_CONTEXT
    assert snapshot.formal_results == ()
    assert snapshot.closure_outcomes[0].execution_status is ClosureExecutionStatus.INVALID


def test_f0_3_unresolved_concrete_fck_blocks_without_guessed_value_or_verdict() -> None:
    material = _material(
        fck=None,
        strength_status=ConcreteStrengthFactStatus.UNRESOLVED,
    )
    program = _program(_population(material))
    snapshot = RegulatoryEngine.execute(program)
    assert snapshot.formal_results == ()
    assert snapshot.closure_outcomes[0].execution_status is ClosureExecutionStatus.BLOCKED
    assessment = AssessmentEngine.reconcile(program, snapshot)
    assert assessment.structural_status is StructuralAssessmentStatus.INCOMPLETE
    assert assessment.full_tbdy_compliance_status == "NOT_EVALUATED"


def test_f0_3_nonfinite_resolved_fck_is_treated_as_blocked_fact() -> None:
    program = _program(_population(_material(fck=float("nan"))))
    snapshot = RegulatoryEngine.execute(program)
    assert snapshot.formal_results == ()
    assert snapshot.closure_outcomes[0].execution_status is ClosureExecutionStatus.BLOCKED


def test_f0_3_complete_population_maps_to_full_and_compile_proceeds() -> None:
    population = _population(_material(fck=25.0), readiness=MaterialPopulationReadiness.COMPLETE)
    inputs = build_concrete_material_min_strength_compile_inputs(population)
    authority = next(item for item in inputs.external_authorities if item.key == USED_RC_MATERIAL_POPULATION_KEY)
    assert authority.population_completeness is PopulationCompleteness.FULL
    assert authority.availability is AvailabilityState.RESOLVED
    program = RegulatoryCompiler.compile(F0_3_CONCRETE_MATERIAL_MIN_STRENGTH_REGISTRY, inputs)
    assert len(program.plan.compiled_rule_instances) == 1


@pytest.mark.parametrize(
    "readiness",
    [MaterialPopulationReadiness.PARTIAL, MaterialPopulationReadiness.BLOCKED],
)
def test_f0_3_incomplete_population_fails_closed_at_compile(
    readiness: MaterialPopulationReadiness,
) -> None:
    population = _population(_material(fck=25.0), readiness=readiness)
    inputs = build_concrete_material_min_strength_compile_inputs(population)
    authority = next(item for item in inputs.external_authorities if item.key == USED_RC_MATERIAL_POPULATION_KEY)
    assert authority.population_completeness is PopulationCompleteness.INCOMPLETE
    with pytest.raises(KernelCompileError, match="FULL population requirement"):
        RegulatoryCompiler.compile(F0_3_CONCRETE_MATERIAL_MIN_STRENGTH_REGISTRY, inputs)


def test_f0_3_duplicate_material_id_is_hard_failure() -> None:
    first = _material(material_id="DUP", fck=25.0)
    second = _material(material_id="DUP", material_name="Other", fck=30.0)
    with pytest.raises(ValueError, match="duplicate material_id"):
        build_concrete_material_min_strength_compile_inputs(_population(first, second))


def test_f0_3_empty_population_is_hard_failure_not_empty_success() -> None:
    with pytest.raises(ValueError, match="population is empty"):
        build_concrete_material_min_strength_compile_inputs(_population())


def test_f0_3_two_concrete_materials_produce_two_material_definition_results() -> None:
    population = _population(
        _material(material_id="MAT-A", fck=24.0),
        _material(material_id="MAT-B", fck=30.0),
    )
    program = _program(population)
    snapshot = RegulatoryEngine.execute(program)
    assert len(program.plan.compiled_rule_instances) == 2
    assert all(item.grain is Grain.MATERIAL_DEFINITION for item in program.plan.compiled_rule_instances)
    assert len(snapshot.formal_results) == 2
    assert {item.result.component for item in snapshot.formal_results} == {"MAT-A", "MAT-B"}
    assert {item.result.status for item in snapshot.formal_results} == {CheckStatus.FAIL, CheckStatus.OK}
    assert snapshot.regulatory_quantities == ()


def test_f0_3_one_concrete_and_one_nonconcrete_produce_one_result_plus_one_pna() -> None:
    concrete = _material(material_id="MAT-C", fck=30.0)
    non_concrete = _material(
        material_id="MAT-NC",
        material_name="Steel",
        fck=None,
        material_type_code=1,
        is_concrete=False,
        strength_status=ConcreteStrengthFactStatus.NOT_APPLICABLE,
    )
    program = _program(_population(non_concrete, concrete))
    snapshot = RegulatoryEngine.execute(program)
    assert len(program.plan.compiled_rule_instances) == 2
    assert len(snapshot.formal_results) == 1
    assert snapshot.formal_results[0].result.component == "MAT-C"
    statuses = {item.compiled_record_ref.scope_ref: item.execution_status for item in snapshot.closure_outcomes}
    assert statuses == {"MAT-C": ClosureExecutionStatus.EXECUTED, "MAT-NC": ClosureExecutionStatus.PROVEN_NOT_APPLICABLE}
    assessment = AssessmentEngine.reconcile(program, snapshot)
    assert assessment.structural_status is StructuralAssessmentStatus.COMPLETE


def test_f0_3_many_usages_of_same_material_still_produce_one_instance_one_result() -> None:
    usages = tuple(_usage(index) for index in range(1, 201))
    material = _material(usages=usages, fck=30.0)
    program = _program(_population(material))
    snapshot = RegulatoryEngine.execute(program)
    assert len(program.plan.compiled_rule_instances) == 1
    assert len(snapshot.formal_results) == 1
    assert len(snapshot.formal_results[0].result.evidence[0]["usage_references"]) == 200


def test_f0_3_equivalent_population_order_is_fully_deterministic() -> None:
    first_material = _material(material_id="MAT-A", fck=24.0)
    second_material = _material(material_id="MAT-B", fck=30.0)
    first_inputs = build_concrete_material_min_strength_compile_inputs(
        _population(first_material, second_material)
    )
    second_inputs = build_concrete_material_min_strength_compile_inputs(
        _population(second_material, first_material)
    )
    assert first_inputs.rule_targets == second_inputs.rule_targets
    assert first_inputs.external_authorities == second_inputs.external_authorities
    first = RegulatoryCompiler.compile(F0_3_CONCRETE_MATERIAL_MIN_STRENGTH_REGISTRY, first_inputs)
    second = RegulatoryCompiler.compile(F0_3_CONCRETE_MATERIAL_MIN_STRENGTH_REGISTRY, second_inputs)
    assert F0_3_CONCRETE_MATERIAL_MIN_STRENGTH_REGISTRY.registry_version == F0_3_CONCRETE_MATERIAL_MIN_STRENGTH_REGISTRY.registry_version
    assert first.plan.compiled_rule_instances == second.plan.compiled_rule_instances
    assert first.plan.plan_identity == second.plan.plan_identity
    assert first.plan.deterministic_execution_order == second.plan.deterministic_execution_order
    assert RegulatoryEngine.execute(first) == RegulatoryEngine.execute(second)


def test_f0_3_exactly_once_for_n_resolved_concrete_materials() -> None:
    population = _population(
        _material(material_id="M1", fck=25.0),
        _material(material_id="M2", fck=26.0),
        _material(material_id="M3", fck=27.0),
    )
    program = _program(population)
    snapshot = RegulatoryEngine.execute(program)
    assert len(program.plan.compiled_rule_instances) == 3
    assert len(snapshot.formal_results) == 3
    assert len({item.instance_id for item in snapshot.formal_results}) == 3
    assert snapshot.regulatory_quantities == ()
    assert all(item.execution_status is ClosureExecutionStatus.EXECUTED for item in snapshot.closure_outcomes)


def _beam_compile_inputs() -> RegulatoryCompileInputs:
    component_id = "B-F0-2"
    evidence = ({"fixture": "f0.2-coexistence", "beam_width_mm": 250.0},)
    target = RuleScopeTarget(
        rule_id=BEAM_RULE_ID,
        grain=Grain.COMPONENT,
        scope_ref=component_id,
        direction=None,
        applicability_input=BeamMinWidthApplicabilityInput(
            component_type="beam",
            tbdy_7411_applies=True,
        ),
    )
    authorities = (
        ExternalDependencyAuthority(
            authority_id="coexist:beam-width",
            key=BEAM_WIDTH_KEY,
            source_kind=DependencySourceKind.FACT,
            semantic_type=SemanticType.BEAM_WIDTH,
            physical_dimension=PhysicalDimension.LENGTH,
            grain=Grain.COMPONENT,
            scope_ref=component_id,
            direction=None,
            unit=UNIT_MM,
            availability=AvailabilityState.RESOLVED,
            population_completeness=PopulationCompleteness.FULL,
            value=250.0,
            provenance_refs=("coexist:beam-width",),
        ),
        ExternalDependencyAuthority(
            authority_id="coexist:beam-story",
            key=BEAM_STORY_KEY,
            source_kind=DependencySourceKind.CONTEXT,
            semantic_type=SemanticType.COMPONENT_STORY,
            physical_dimension=PhysicalDimension.ENUM_STATE,
            grain=Grain.COMPONENT,
            scope_ref=component_id,
            direction=None,
            unit=UNIT_ENUM_STATE,
            availability=AvailabilityState.RESOLVED,
            population_completeness=PopulationCompleteness.FULL,
            value="S1",
        ),
        ExternalDependencyAuthority(
            authority_id="coexist:beam-section",
            key=BEAM_SECTION_KEY,
            source_kind=DependencySourceKind.CONTEXT,
            semantic_type=SemanticType.COMPONENT_SECTION,
            physical_dimension=PhysicalDimension.ENUM_STATE,
            grain=Grain.COMPONENT,
            scope_ref=component_id,
            direction=None,
            unit=UNIT_ENUM_STATE,
            availability=AvailabilityState.RESOLVED,
            population_completeness=PopulationCompleteness.FULL,
            value="SEC1",
        ),
        ExternalDependencyAuthority(
            authority_id="coexist:beam-evidence",
            key=BEAM_EVIDENCE_TRACE_KEY,
            source_kind=DependencySourceKind.CONTEXT,
            semantic_type=SemanticType.CHECK_EVIDENCE_TRACE,
            physical_dimension=PhysicalDimension.DIMENSIONLESS,
            grain=Grain.COMPONENT,
            scope_ref=component_id,
            direction=None,
            unit=UNIT_DIMENSIONLESS,
            availability=AvailabilityState.RESOLVED,
            population_completeness=PopulationCompleteness.FULL,
            value=evidence,
        ),
    )
    return RegulatoryCompileInputs(rule_targets=(target,), external_authorities=authorities)


def test_f0_2_and_f0_3_coexist_in_one_plan_without_authority_collision() -> None:
    beam_inputs = _beam_compile_inputs()
    material_inputs = build_concrete_material_min_strength_compile_inputs(
        _population(_material(material_id="MAT-COEX", fck=30.0))
    )
    combined_registry = RegulatoryRegistry(
        checks=(BEAM_MIN_WIDTH_CHECK_SPEC, CONCRETE_MATERIAL_MIN_STRENGTH_CHECK_SPEC)
    )
    combined_inputs = RegulatoryCompileInputs(
        rule_targets=(*beam_inputs.rule_targets, *material_inputs.rule_targets),
        external_authorities=(*beam_inputs.external_authorities, *material_inputs.external_authorities),
    )
    combined = RegulatoryCompiler.compile(combined_registry, combined_inputs)
    snapshot = RegulatoryEngine.execute(combined)

    beam_alone = RegulatoryCompiler.compile(
        RegulatoryRegistry(checks=(BEAM_MIN_WIDTH_CHECK_SPEC,)),
        beam_inputs,
    )
    beam_alone_result = RegulatoryEngine.execute(beam_alone).formal_results[0].result

    assert len(combined.plan.compiled_rule_instances) == 2
    assert combined.plan.deterministic_execution_order == tuple(
        sorted(combined.plan.compiled_rule_instances, key=lambda item: item.value)
    )
    assert len(snapshot.formal_results) == 2
    by_check = {item.result.check_id: item.result for item in snapshot.formal_results}
    assert by_check[BEAM_MIN_WIDTH] == beam_alone_result
    assert by_check[BEAM_MIN_WIDTH].status is CheckStatus.OK
    assert by_check["CONCRETE_MATERIAL_MIN_STRENGTH"].component == "MAT-COEX"
    assert by_check["CONCRETE_MATERIAL_MIN_STRENGTH"].status is CheckStatus.OK
    assert snapshot.regulatory_quantities == ()
    assessment = AssessmentEngine.reconcile(combined, snapshot)
    assert assessment.structural_status is StructuralAssessmentStatus.COMPLETE
    assert assessment.full_tbdy_compliance_status == "NOT_EVALUATED"


def test_f0_3_compile_adapter_does_not_mutate_factual_population() -> None:
    population = _population(_material(fck=30.0, usages=(_usage(2), _usage(1))))
    before = population
    build_concrete_material_min_strength_compile_inputs(population)
    assert population == before


def test_f0_3_production_module_architecture_guards() -> None:
    import tbdy_engine.regulatory.concrete_material_min_strength as module

    source = Path(module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported_modules.append(node.module or "")

    assert all("tbdy_engine.etabs" not in name for name in imported_modules)
    assert all("product_reports" not in name for name in imported_modules)
    assert "MinimalCheckEngine" not in source
    assert "_material_strength_row" not in source
    assert "raw_fc" not in source
    assert "ModelContext" not in source
    assert "RegulatoryQuantity" not in source
    assert "tbdy_engine.product_reports" not in source
    assert source.count("MIN_FCK_MPA = 25.0") == 1
    assert "C80" not in source
    assert "TS EN 206" not in source
    assert "TS500" not in source
    assert "TS708" not in source
