from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, dataclass
from pathlib import Path

import pytest

from tbdy_engine.checks.result import CheckResult, CheckStatus
from tbdy_engine.regulatory import (
    ApplicabilityBinding, ApplicabilityState, AvailabilityState,
    CheckEvaluatorBinding, CheckSpec, ClosureExecutionStatus,
    DependencyKey, DependencySourceKind, DependencySpec,
    DerivationEvaluatorBinding, DirectionPolicy, Grain, PhysicalDimension,
    PopulationRequirement, RegulatoryDerivationSpec, RegulatoryOutputContract,
    RegulatoryQuantity, RegulatoryRegistry, RuleId, ScopePolicy, SemanticType,
    UNIT_DIMENSIONLESS, UNIT_MM, UNIT_N, Unit,
)
from tbdy_engine.regulatory.kernel import (
    AnalysisBasisStatus, AssessmentEngine, BindingAuthorityKind,
    DeclaredDependencyView, ExternalDependencyAuthority, KernelCompileError,
    KernelExecutionError, PopulationCompleteness, RegulatoryCompileInputs,
    RegulatoryCompiler, RegulatoryEngine, RegulatoryStore, RuleExecutionEnvelope,
    RuleScopeTarget, StructuralAssessmentStatus,
)


@dataclass(frozen=True, slots=True)
class AppInput:
    state: ApplicabilityState = ApplicabilityState.APPLIES


@dataclass(frozen=True, slots=True)
class ExecInput:
    envelope: RuleExecutionEnvelope
    dependencies: DeclaredDependencyView

    @classmethod
    def from_declared_dependencies(cls, envelope, dependencies):
        return cls(envelope, DeclaredDependencyView(tuple(dependencies)))


def _app(value: AppInput) -> ApplicabilityState:
    return value.state


def dep(
    key: str, *, kind=DependencySourceKind.FACT,
    semantic=SemanticType.TOY_INPUT, dimension=PhysicalDimension.DIMENSIONLESS,
    grain=Grain.COMPONENT, scope=ScopePolicy.SAME_SCOPE,
    direction=DirectionPolicy.NO_DIRECTION, unit=UNIT_DIMENSIONLESS, full=False,
):
    return DependencySpec(
        key=DependencyKey(key), source_kind=kind, semantic_type=semantic,
        physical_dimension=dimension, grain=grain, scope_policy=scope,
        direction_policy=direction, unit_requirement=unit,
        required_availability=AvailabilityState.RESOLVED,
        population_completeness_requirement=PopulationRequirement.FULL if full else PopulationRequirement.ANY_RESOLVED,
    )


def external(
    authority_id: str, key: str, *, value=2.0, kind=DependencySourceKind.FACT,
    semantic=SemanticType.TOY_INPUT, dimension=PhysicalDimension.DIMENSIONLESS,
    grain=Grain.COMPONENT, scope_ref="C1", direction=None, unit=UNIT_DIMENSIONLESS,
    availability=AvailabilityState.RESOLVED, completeness=PopulationCompleteness.FULL,
):
    return ExternalDependencyAuthority(
        authority_id=authority_id, key=DependencyKey(key), source_kind=kind,
        semantic_type=semantic, physical_dimension=dimension, grain=grain,
        scope_ref=scope_ref, direction=direction, unit=unit, availability=availability,
        population_completeness=completeness, value=value,
        provenance_refs=(f"source:{authority_id}",),
    )


def target(
    rule: str, *, scope_ref="C1", grain=Grain.COMPONENT, direction=None,
    applicability=ApplicabilityState.APPLIES, analysis=AnalysisBasisStatus.MATCH,
):
    return RuleScopeTarget(
        rule_id=RuleId(rule), grain=grain, scope_ref=scope_ref, direction=direction,
        applicability_input=AppInput(applicability), analysis_basis_status=analysis,
    )


def derivation(
    rule: str, out_key: str, *, dependencies=(), output_grain=Grain.COMPONENT,
    output_semantic=SemanticType.TOY_DERIVED_STATE,
    output_dimension=PhysicalDimension.DIMENSIONLESS, output_unit=UNIT_DIMENSIONLESS,
    evaluator=None,
):
    if evaluator is None:
        def evaluator(inp: ExecInput):
            values = [x.value for x in inp.dependencies.dependencies if isinstance(x.value, (int, float)) and not isinstance(x.value, bool)]
            value = float(sum(values)) + 1.0
            return RegulatoryQuantity(
                quantity_key=DependencyKey(out_key), producer_instance_id=inp.envelope.instance_id,
                semantic_type=output_semantic, physical_dimension=output_dimension,
                grain=output_grain, scope_ref=inp.envelope.instance_id.scope_ref,
                direction=inp.envelope.instance_id.direction, value=value, unit=output_unit,
                availability=AvailabilityState.RESOLVED, rule_version="v1",
                code_refs=("TOY",), dependency_refs=inp.envelope.declared_dependency_refs,
                provenance=("toy",), derivation_trace=("stable", value), governing_trace=("selected", value),
            )
    return RegulatoryDerivationSpec(
        rule_id=RuleId(rule), code_refs=("TOY",), rule_version="v1",
        output_contract=RegulatoryOutputContract(
            authority_key=DependencyKey(out_key), semantic_type=output_semantic,
            physical_dimension=output_dimension, grain=output_grain, unit=output_unit,
        ),
        dependencies=tuple(dependencies),
        applicability=ApplicabilityBinding(f"app:{rule}", AppInput, _app),
        evaluator=DerivationEvaluatorBinding(f"eval:{rule}", ExecInput, evaluator),
    )


def check(rule: str, *, dependencies=(), evaluator=None):
    if evaluator is None:
        def evaluator(inp: ExecInput):
            values = [x.value for x in inp.dependencies.dependencies if isinstance(x.value, (int, float)) and not isinstance(x.value, bool)]
            return CheckResult(
                check_id=inp.envelope.rule_id.value, component=inp.envelope.instance_id.scope_ref,
                component_type="toy", status=CheckStatus.OK, value=float(sum(values)), code_ref="TOY",
            )
    return CheckSpec(
        rule_id=RuleId(rule), code_refs=("TOY",), rule_version="v1",
        formal_result_type=CheckResult, dependencies=tuple(dependencies),
        applicability=ApplicabilityBinding(f"app:{rule}", AppInput, _app),
        evaluator=CheckEvaluatorBinding(f"eval:{rule}", ExecInput, evaluator),
    )


def simple(*, target_order=("D_X", "C_Y"), authority_id="A_FACT", fact_value=2.0):
    fact = dep("FACT_A")
    out = dep("OUT_X", kind=DependencySourceKind.REGULATORY_QUANTITY, semantic=SemanticType.TOY_DERIVED_STATE)
    registry = RegulatoryRegistry(derivations=(derivation("D_X", "OUT_X", dependencies=(fact,)),), checks=(check("C_Y", dependencies=(out,)),))
    targets = {"D_X": target("D_X"), "C_Y": target("C_Y")}
    inputs = RegulatoryCompileInputs(
        rule_targets=tuple(targets[x] for x in target_order),
        external_authorities=(external(authority_id, "FACT_A", value=fact_value),),
    )
    return registry, inputs, RegulatoryCompiler.compile(registry, inputs)


def test_A_and_R_duplicate_producer_authority_rejected():
    with pytest.raises(ValueError, match="duplicate regulatory output authority"):
        RegulatoryRegistry(derivations=(derivation("D1", "OUT"), derivation("D2", "OUT")))


def test_B_missing_regulatory_producer_and_external_source_fail():
    missing_reg = check("C", dependencies=(dep("NO_OUT", kind=DependencySourceKind.REGULATORY_QUANTITY, semantic=SemanticType.TOY_DERIVED_STATE),))
    with pytest.raises(KernelCompileError, match="missing regulatory producer"):
        RegulatoryCompiler.compile(RegulatoryRegistry(checks=(missing_reg,)), RegulatoryCompileInputs(rule_targets=(target("C"),)))
    missing_ext = check("C2", dependencies=(dep("FACT"),))
    with pytest.raises(KernelCompileError, match="missing declared external source authority"):
        RegulatoryCompiler.compile(RegulatoryRegistry(checks=(missing_ext,)), RegulatoryCompileInputs(rule_targets=(target("C2"),)))


@pytest.mark.parametrize(
    "authority, message",
    [
        (external("A", "FACT", semantic=SemanticType.TOY_RESULT), "semantic type mismatch"),
        (external("A", "FACT", dimension=PhysicalDimension.LENGTH, unit=UNIT_MM), "physical dimension mismatch"),
        (external("A", "FACT", grain=Grain.MODEL, scope_ref="MODEL"), "external source scope mismatch"),
    ],
)
def test_C_D_and_scope_mismatch_fail(authority, message):
    c = check("C", dependencies=(dep("FACT"),))
    with pytest.raises(KernelCompileError, match=message):
        RegulatoryCompiler.compile(RegulatoryRegistry(checks=(c,)), RegulatoryCompileInputs(rule_targets=(target("C"),), external_authorities=(authority,)))


def test_E_grain_mismatch_fails_after_scope_binding():
    c = check("C", dependencies=(dep("FACT", grain=Grain.COMPONENT),))
    a = external("A", "FACT", grain=Grain.STORY, scope_ref="C1")
    with pytest.raises(KernelCompileError, match="grain mismatch"):
        RegulatoryCompiler.compile(RegulatoryRegistry(checks=(c,)), RegulatoryCompileInputs(rule_targets=(target("C"),), external_authorities=(a,)))


def test_F_direction_mismatch_fails():
    c = check("C", dependencies=(dep("FACT", grain=Grain.COMPONENT_DIRECTION, direction=DirectionPolicy.SAME_DIRECTION),))
    inputs = RegulatoryCompileInputs(
        rule_targets=(target("C", grain=Grain.COMPONENT_DIRECTION, direction="X"),),
        external_authorities=(external("A", "FACT", grain=Grain.COMPONENT_DIRECTION, direction="Y"),),
    )
    with pytest.raises(KernelCompileError, match="direction mismatch"):
        RegulatoryCompiler.compile(RegulatoryRegistry(checks=(c,)), inputs)


def test_G_nonconvertible_unit_fails():
    custom = Unit("toy-unreviewed-length", PhysicalDimension.LENGTH)
    c = check("C", dependencies=(dep("FACT", dimension=PhysicalDimension.LENGTH, unit=UNIT_MM),))
    a = external("A", "FACT", dimension=PhysicalDimension.LENGTH, unit=custom)
    with pytest.raises(KernelCompileError, match="unit mismatch"):
        RegulatoryCompiler.compile(RegulatoryRegistry(checks=(c,)), RegulatoryCompileInputs(rule_targets=(target("C"),), external_authorities=(a,)))


def test_H_cycle_prevents_plan_and_reports_identities():
    d1 = derivation("D1", "O1", dependencies=(dep("O2", kind=DependencySourceKind.REGULATORY_QUANTITY, semantic=SemanticType.TOY_DERIVED_STATE),))
    d2 = derivation("D2", "O2", dependencies=(dep("O1", kind=DependencySourceKind.REGULATORY_QUANTITY, semantic=SemanticType.TOY_DERIVED_STATE),))
    with pytest.raises(KernelCompileError, match="dependency cycle prevents plan creation") as exc:
        RegulatoryCompiler.compile(RegulatoryRegistry(derivations=(d1, d2)), RegulatoryCompileInputs(rule_targets=(target("D1"), target("D2"))))
    assert "D1" in str(exc.value) and "D2" in str(exc.value)


def test_I_undeclared_dependency_access_is_structurally_unavailable():
    def evaluator(inp: ExecInput):
        inp.dependencies.value(DependencyKey("SECRET"))
        raise AssertionError
    c = check("C", dependencies=(dep("FACT"),), evaluator=evaluator)
    program = RegulatoryCompiler.compile(
        RegulatoryRegistry(checks=(c,)),
        RegulatoryCompileInputs(rule_targets=(target("C"),), external_authorities=(external("A", "FACT"), external("S", "SECRET", value=99),)),
    )
    with pytest.raises(KeyError, match="undeclared dependency"):
        RegulatoryEngine.execute(program)


def test_J_FULL_population_rejects_incomplete_population():
    c = check("C", dependencies=(dep("POP", kind=DependencySourceKind.SOURCE_POPULATION, full=True),))
    a = external("A", "POP", kind=DependencySourceKind.SOURCE_POPULATION, completeness=PopulationCompleteness.INCOMPLETE)
    with pytest.raises(KernelCompileError, match="FULL population requirement is not satisfiable"):
        RegulatoryCompiler.compile(RegulatoryRegistry(checks=(c,)), RegulatoryCompileInputs(rule_targets=(target("C"),), external_authorities=(a,)))


def test_K_UNRESOLVED_applicability_remains_in_closure_and_blocks():
    c = check("C")
    program = RegulatoryCompiler.compile(RegulatoryRegistry(checks=(c,)), RegulatoryCompileInputs(rule_targets=(target("C", applicability=ApplicabilityState.UNRESOLVED),)))
    record = program.plan.compiled_closure_inventory[0]
    assert record.applicability is ApplicabilityState.UNRESOLVED
    snapshot = RegulatoryEngine.execute(program)
    assert snapshot.formal_results == ()
    assert snapshot.closure_outcomes[0].execution_status is ClosureExecutionStatus.BLOCKED


def test_L_runtime_cannot_mutate_plan_or_add_scope():
    _, _, program = simple()
    plan_before = program.plan
    RegulatoryEngine.execute(program)
    assert program.plan == plan_before
    with pytest.raises(FrozenInstanceError):
        program.plan.plan_identity = "changed"  # type: ignore[misc]
    assert not hasattr(RegulatoryEngine, "register") and not hasattr(RegulatoryEngine, "add_rule")


def test_M_N_T1_deterministic_order_instances_and_plan_identity():
    _, _, p1 = simple(target_order=("C_Y", "D_X"))
    _, _, p2 = simple(target_order=("D_X", "C_Y"))
    assert p1.plan.compiled_rule_instances == p2.plan.compiled_rule_instances
    assert p1.plan.deterministic_execution_order == p2.plan.deterministic_execution_order
    assert p1.plan.plan_identity == p2.plan.plan_identity
    assert p1.plan.deterministic_execution_order[0].rule_id == RuleId("D_X")


def test_O_outputs_traces_and_outcomes_are_deterministic():
    _, _, p1 = simple()
    _, _, p2 = simple(target_order=("C_Y", "D_X"))
    assert RegulatoryEngine.execute(p1) == RegulatoryEngine.execute(p2)
    assert AssessmentEngine.reconcile(p1, RegulatoryEngine.execute(p1)) == AssessmentEngine.reconcile(p2, RegulatoryEngine.execute(p2))


def test_P_RegulatoryQuantity_remains_immutable():
    _, _, program = simple()
    quantity = RegulatoryEngine.execute(program).regulatory_quantities[0]
    with pytest.raises(FrozenInstanceError):
        quantity.value = 7  # type: ignore[misc]


def test_Q_one_upstream_quantity_feeds_multiple_consumers():
    fact = dep("FACT")
    out = dep("OUT", kind=DependencySourceKind.REGULATORY_QUANTITY, semantic=SemanticType.TOY_DERIVED_STATE)
    registry = RegulatoryRegistry(
        derivations=(derivation("D", "OUT", dependencies=(fact,)), derivation("D2", "OUT2", dependencies=(out,))),
        checks=(check("C", dependencies=(out,)),),
    )
    program = RegulatoryCompiler.compile(registry, RegulatoryCompileInputs(rule_targets=(target("D2"), target("C"), target("D")), external_authorities=(external("A", "FACT"),)))
    consumers = [b for n in program.nodes for b in n.dependency_bindings if b.dependency.key == DependencyKey("OUT")]
    assert len(consumers) == 2 and len({b.producer_instance_id for b in consumers}) == 1
    snapshot = RegulatoryEngine.execute(program)
    assert len(snapshot.regulatory_quantities) == 2 and len(snapshot.formal_results) == 1


def test_S_analysis_basis_mismatch_blocks_and_prevents_mandatory_closure():
    out = dep("OUT", kind=DependencySourceKind.REGULATORY_QUANTITY, semantic=SemanticType.TOY_DERIVED_STATE)
    registry = RegulatoryRegistry(derivations=(derivation("D", "OUT"),), checks=(check("C", dependencies=(out,)),))
    program = RegulatoryCompiler.compile(registry, RegulatoryCompileInputs(rule_targets=(target("D"), target("C", analysis=AnalysisBasisStatus.REANALYSIS_REQUIRED))))
    snapshot = RegulatoryEngine.execute(program)
    check_id = next(i for i in program.plan.compiled_rule_instances if i.rule_id == RuleId("C"))
    assert snapshot.formal_results_for(check_id) == ()
    assert snapshot.outcome_for(check_id).execution_status is ClosureExecutionStatus.BLOCKED
    assessment = AssessmentEngine.reconcile(program, snapshot)
    assert check_id in assessment.incomplete_mandatory_instances


def test_T2_materially_different_plan_inputs_change_plan_identity():
    registry, inputs, p1 = simple()
    changed = RegulatoryCompileInputs(rule_targets=inputs.rule_targets, external_authorities=(external("A_V2", "FACT_A"),))
    assert RegulatoryCompiler.compile(registry, changed).plan.plan_identity != p1.plan.plan_identity


def test_T3_store_rejects_duplicate_formal_output():
    _, _, program = simple()
    instance = next(i for i in program.plan.compiled_rule_instances if i.rule_id == RuleId("C_Y"))
    result = CheckResult(check_id="C_Y", component="C1", component_type="toy", status=CheckStatus.OK)
    store = RegulatoryStore(plan_identity=program.plan.plan_identity)
    store.record_check_result(instance, result)
    with pytest.raises(KernelExecutionError, match="duplicate formal output"):
        store.record_check_result(instance, result)


def test_T4_store_rejects_duplicate_quantity_authority_output():
    _, _, program = simple()
    quantity = RegulatoryEngine.execute(program).regulatory_quantities[0]
    store = RegulatoryStore(plan_identity=program.plan.plan_identity)
    store.record_regulatory_quantity(quantity)
    with pytest.raises(KernelExecutionError, match="duplicate RegulatoryQuantity"):
        store.record_regulatory_quantity(quantity)


def test_T5_invalid_derivation_output_contract_rejected():
    def bad(inp: ExecInput):
        return RegulatoryQuantity(
            quantity_key=DependencyKey("WRONG"), producer_instance_id=inp.envelope.instance_id,
            semantic_type=SemanticType.TOY_DERIVED_STATE, physical_dimension=PhysicalDimension.DIMENSIONLESS,
            grain=Grain.COMPONENT, scope_ref="C1", direction=None, value=1.0,
            unit=UNIT_DIMENSIONLESS, availability=AvailabilityState.RESOLVED,
            rule_version="v1", dependency_refs=inp.envelope.declared_dependency_refs,
        )
    program = RegulatoryCompiler.compile(RegulatoryRegistry(derivations=(derivation("D", "OUT", evaluator=bad),)), RegulatoryCompileInputs(rule_targets=(target("D"),)))
    with pytest.raises(KernelExecutionError, match="invalid derivation output contract"):
        RegulatoryEngine.execute(program)


def test_T6_check_evaluator_requires_canonical_CheckResult():
    c = check("C", evaluator=lambda _: {"status": "OK"})
    program = RegulatoryCompiler.compile(RegulatoryRegistry(checks=(c,)), RegulatoryCompileInputs(rule_targets=(target("C"),)))
    with pytest.raises(KernelExecutionError, match="canonical CheckResult"):
        RegulatoryEngine.execute(program)


def test_T7_registry_and_plan_unchanged_after_execution():
    registry, _, program = simple()
    version, plan = registry.registry_version, program.plan
    RegulatoryEngine.execute(program)
    assert registry.registry_version == version and program.plan == plan


def test_T8_external_and_regulatory_bindings_structurally_distinct():
    fact = dep("FACT")
    out = dep("OUT", kind=DependencySourceKind.REGULATORY_QUANTITY, semantic=SemanticType.TOY_DERIVED_STATE)
    registry = RegulatoryRegistry(derivations=(derivation("D", "OUT", dependencies=(fact,)),), checks=(check("C", dependencies=(fact, out)),))
    program = RegulatoryCompiler.compile(registry, RegulatoryCompileInputs(rule_targets=(target("C"), target("D")), external_authorities=(external("A", "FACT"),)))
    node = next(n for n in program.nodes if n.instance_id.rule_id == RuleId("C"))
    assert {b.authority_kind for b in node.dependency_bindings} == {BindingAuthorityKind.EXTERNAL_AUTHORITY, BindingAuthorityKind.REGULATORY_PRODUCER}
    assert any(b.external_authority_id for b in node.dependency_bindings) and any(b.producer_instance_id for b in node.dependency_bindings)


def test_T9_reversed_registry_and_compile_input_order_are_deterministic():
    fact = dep("FACT")
    d1, d2 = derivation("D1", "O1", dependencies=(fact,)), derivation("D2", "O2", dependencies=(fact,))
    r1, r2 = RegulatoryRegistry(derivations=(d2, d1)), RegulatoryRegistry(derivations=(d1, d2))
    i1 = RegulatoryCompileInputs(rule_targets=(target("D2"), target("D1")), external_authorities=(external("A", "FACT"),))
    i2 = RegulatoryCompileInputs(rule_targets=(target("D1"), target("D2")), external_authorities=(external("A", "FACT"),))
    p1, p2 = RegulatoryCompiler.compile(r1, i1), RegulatoryCompiler.compile(r2, i2)
    assert r1.registry_version == r2.registry_version
    assert p1.plan.plan_identity == p2.plan.plan_identity
    assert RegulatoryEngine.execute(p1) == RegulatoryEngine.execute(p2)


def test_direction_aware_component_instances_are_deterministic():
    d = derivation("D", "OUT", output_grain=Grain.COMPONENT_DIRECTION)
    program = RegulatoryCompiler.compile(
        RegulatoryRegistry(derivations=(d,)),
        RegulatoryCompileInputs(rule_targets=(target("D", scope_ref="C2", grain=Grain.COMPONENT_DIRECTION, direction="Y"), target("D", scope_ref="C1", grain=Grain.COMPONENT_DIRECTION, direction="X"))),
    )
    assert {i.direction for i in program.plan.compiled_rule_instances} == {"X", "Y"}


def test_external_NO_DATA_is_readiness_not_formal_verdict():
    c = check("C", dependencies=(dep("FACT"),))
    program = RegulatoryCompiler.compile(
        RegulatoryRegistry(checks=(c,)),
        RegulatoryCompileInputs(rule_targets=(target("C"),), external_authorities=(external("A", "FACT", availability=AvailabilityState.NO_DATA, value=None),)),
    )
    snapshot = RegulatoryEngine.execute(program)
    assert snapshot.formal_results == () and snapshot.closure_outcomes[0].execution_status is ClosureExecutionStatus.NO_DATA


def test_assessment_is_structural_and_full_tbdy_status_remains_NOT_EVALUATED():
    _, _, program = simple()
    assessment = AssessmentEngine.reconcile(program, RegulatoryEngine.execute(program))
    assert assessment.structural_status is StructuralAssessmentStatus.COMPLETE
    assert assessment.full_tbdy_compliance_status == "NOT_EVALUATED"


def test_T10_f0_1_kernel_has_no_ETABS_import():
    import tbdy_engine.regulatory.kernel as module
    tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
    modules = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            modules.append(node.module or "")
    assert all("etabs" not in name.casefold() for name in modules)
