from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from tbdy_engine.checks.result import CheckResult, CheckStatus
from tbdy_engine.coverage.project_reconciliation import (
    ActionBindingRef,
    AnalysisBasisRef,
    ProjectCoverageReconciler,
    ProjectReconciliationError,
    ReportBindingIdentityBlocked,
    ReportBindingRef,
    ReportContributionRef,
    canonical_closure_report_source_ref,
    canonical_quantity_report_source_ref,
)
from tbdy_engine.findings.builder import build_finding_from_rule_closure
from tbdy_engine.product_reports.slice_report_contribution import SliceReportContribution
from tbdy_engine.regulatory.contracts import (
    ApplicabilityBinding,
    ApplicabilityState,
    AvailabilityState,
    CheckEvaluatorBinding,
    CheckSpec,
    ClosureExecutionStatus,
    DependencyKey,
    DerivationEvaluatorBinding,
    Grain,
    PhysicalDimension,
    RegulatoryDerivationSpec,
    RegulatoryOutputContract,
    RegulatoryQuantity,
    RuleClosureOutcome,
    RuleId,
    RuleInstanceId,
    SemanticType,
)
from tbdy_engine.regulatory.kernel import (
    AnalysisBasisStatus,
    AssessmentEngine,
    DeclaredDependencyView,
    FormalResultRecord,
    RegulatoryCompileInputs,
    RegulatoryCompiler,
    RegulatoryEngine,
    RegulatoryStoreSnapshot,
    RuleExecutionEnvelope,
    RuleScopeTarget,
    StructuralAssessmentStatus,
)
from tbdy_engine.regulatory.registry import RegulatoryRegistry
from tbdy_engine.regulatory.units import UNIT_DIMENSIONLESS


@dataclass(frozen=True, slots=True)
class _AppInput:
    state: ApplicabilityState = ApplicabilityState.APPLIES


@dataclass(frozen=True, slots=True)
class _ExecInput:
    envelope: RuleExecutionEnvelope
    dependencies: DeclaredDependencyView

    @classmethod
    def from_declared_dependencies(cls, envelope, dependencies):
        return cls(envelope, DeclaredDependencyView(tuple(dependencies)))


def _app(value: _AppInput) -> ApplicabilityState:
    return value.state


def _check(rule: str) -> CheckSpec:
    return CheckSpec(
        rule_id=RuleId(rule),
        code_refs=("TOY",),
        rule_version="v1",
        formal_result_type=CheckResult,
        dependencies=(),
        applicability=ApplicabilityBinding(f"app:{rule}", _AppInput, _app),
        evaluator=CheckEvaluatorBinding(f"eval:{rule}", object, lambda _: None),
    )


def _derivation(rule: str, key: str) -> RegulatoryDerivationSpec:
    def evaluator(inp: _ExecInput) -> RegulatoryQuantity:
        return RegulatoryQuantity(
            quantity_key=DependencyKey(key),
            producer_instance_id=inp.envelope.instance_id,
            semantic_type=SemanticType.TOY_DERIVED_STATE,
            physical_dimension=PhysicalDimension.DIMENSIONLESS,
            grain=Grain.COMPONENT,
            scope_ref=inp.envelope.instance_id.scope_ref,
            direction=None,
            value=2.0,
            unit=UNIT_DIMENSIONLESS,
            availability=AvailabilityState.RESOLVED,
            rule_version="v1",
            code_refs=("TOY",),
            dependency_refs=(),
            provenance=("toy",),
            derivation_trace=("stable", 2.0),
            governing_trace=("selected", 2.0),
        )

    return RegulatoryDerivationSpec(
        rule_id=RuleId(rule),
        code_refs=("TOY",),
        rule_version="v1",
        output_contract=RegulatoryOutputContract(
            authority_key=DependencyKey(key),
            semantic_type=SemanticType.TOY_DERIVED_STATE,
            physical_dimension=PhysicalDimension.DIMENSIONLESS,
            grain=Grain.COMPONENT,
            unit=UNIT_DIMENSIONLESS,
        ),
        dependencies=(),
        applicability=ApplicabilityBinding(f"app:{rule}", _AppInput, _app),
        evaluator=DerivationEvaluatorBinding(f"eval:{rule}", _ExecInput, evaluator),
    )


def _program(
    *rules: str,
    mandatory: dict[str, bool] | None = None,
    applicability: dict[str, ApplicabilityState] | None = None,
    analysis: dict[str, AnalysisBasisStatus] | None = None,
    scopes: dict[str, str] | None = None,
):
    mandatory = mandatory or {}
    applicability = applicability or {}
    analysis = analysis or {}
    scopes = scopes or {}
    registry = RegulatoryRegistry(checks=tuple(_check(rule) for rule in rules))
    targets = tuple(
        RuleScopeTarget(
            rule_id=RuleId(rule),
            grain=Grain.COMPONENT,
            scope_ref=scopes.get(rule, f"SCOPE_{rule}"),
            mandatory=mandatory.get(rule, True),
            applicability_input=_AppInput(applicability.get(rule, ApplicabilityState.APPLIES)),
            analysis_basis_status=analysis.get(rule, AnalysisBasisStatus.MATCH),
        )
        for rule in rules
    )
    return RegulatoryCompiler.compile(
        registry,
        RegulatoryCompileInputs(rule_targets=targets),
    )


def _derivation_program():
    registry = RegulatoryRegistry(derivations=(_derivation("D", "OUT"),))
    return RegulatoryCompiler.compile(
        registry,
        RegulatoryCompileInputs(
            rule_targets=(
                RuleScopeTarget(
                    rule_id=RuleId("D"),
                    grain=Grain.COMPONENT,
                    scope_ref="SCOPE_D",
                    applicability_input=_AppInput(),
                ),
            ),
        ),
    )


def _id(program, rule: str) -> RuleInstanceId:
    return next(
        item
        for item in program.plan.compiled_rule_instances
        if item.rule_id == RuleId(rule)
    )


def _formal(instance_id: RuleInstanceId, status: CheckStatus = CheckStatus.OK) -> FormalResultRecord:
    return FormalResultRecord(
        instance_id=instance_id,
        result=CheckResult(
            check_id=instance_id.rule_id.value,
            component=instance_id.scope_ref,
            component_type="toy",
            status=status,
            code_ref="TOY",
        ),
    )


def _closure_for_formal(record: FormalResultRecord) -> RuleClosureOutcome:
    status = (
        ClosureExecutionStatus.NO_DATA
        if record.result.status is CheckStatus.NO_DATA
        else ClosureExecutionStatus.BLOCKED
        if record.result.status is CheckStatus.BLOCKED
        else ClosureExecutionStatus.EXECUTED
    )
    return RuleClosureOutcome(
        compiled_record_ref=record.instance_id,
        execution_status=status,
        formal_result_ref=f"{record.instance_id.value}:CheckResult",
    )


def _snapshot(program, *, formal_results=(), closure_outcomes=(), regulatory_quantities=()):
    return RegulatoryStoreSnapshot(
        plan_identity=program.plan.plan_identity,
        regulatory_quantities=tuple(regulatory_quantities),
        formal_results=tuple(formal_results),
        closure_outcomes=tuple(closure_outcomes),
        diagnostics=(),
    )


def _executed_snapshot(program, statuses: dict[str, CheckStatus] | None = None):
    statuses = statuses or {}
    records = tuple(
        _formal(
            record.instance_id,
            statuses.get(record.instance_id.rule_id.value, CheckStatus.OK),
        )
        for record in program.plan.compiled_closure_inventory
        if record.applicability is not ApplicabilityState.PROVEN_NOT_APPLICABLE
    )
    return _snapshot(
        program,
        formal_results=records,
        closure_outcomes=tuple(_closure_for_formal(record) for record in records),
    )


def _contribution(*, slice_id="slice:toy", component_id="C1", status="PASS"):
    return SliceReportContribution(
        slice_id=slice_id,
        title="Toy contribution",
        contribution_kind="CHECK",
        status=status,
        component_type="toy",
        component_id=component_id,
    )


def test_expected_mandatory_instances_reconcile_exactly_once():
    program = _program("A", "B")
    snapshot = _executed_snapshot(program)
    result = ProjectCoverageReconciler.reconcile(
        compiled_program=program,
        store_snapshot=snapshot,
    )
    assert result.expected_mandatory_instance_count == 2
    assert result.accounted_instance_count == 2
    assert result.executed_result_count == 2
    assert result.silent_missing_count == 0
    assert result.unresolved_count == 0
    assert result.closure_partition_complete is True
    assert result.population_reconciled is True
    assert result.mandatory_closure_complete is True
    assert result.structural_assessment == AssessmentEngine.reconcile(program, snapshot)


def test_silent_missing_is_raw_absence_and_is_canonical_missing():
    program = _program("A")
    instance_id = _id(program, "A")
    result = ProjectCoverageReconciler.reconcile(
        compiled_program=program,
        store_snapshot=_snapshot(program),
    )
    assert result.accounted_instance_count == 0
    assert result.silent_missing_mandatory_ids == (instance_id,)
    assert result.missing_mandatory_ids == (instance_id,)
    assert result.unresolved_mandatory_ids == (instance_id,)
    assert result.population_reconciled is False
    assert result.closure_partition_complete is True


def test_duplicate_formal_result_uses_exact_instance_id_and_fails_population_gate():
    program = _program("A")
    instance_id = _id(program, "A")
    one = _formal(instance_id)
    two = _formal(instance_id)
    result = ProjectCoverageReconciler.reconcile(
        compiled_program=program,
        store_snapshot=_snapshot(
            program,
            formal_results=(one, two),
            closure_outcomes=(_closure_for_formal(one),),
        ),
    )
    assert result.duplicate_result_instance_ids == (instance_id,)
    assert result.duplicate_mandatory_ids == (instance_id,)
    assert result.population_reconciled is False


def test_invalid_canonical_artifact_is_not_hidden_by_presence_accounting():
    program = _program("A")
    instance_id = _id(program, "A")
    bad = FormalResultRecord(
        instance_id=instance_id,
        result=CheckResult(
            check_id="WRONG_RULE",
            component=instance_id.scope_ref,
            component_type="toy",
            status=CheckStatus.OK,
            code_ref="TOY",
        ),
    )
    result = ProjectCoverageReconciler.reconcile(
        compiled_program=program,
        store_snapshot=_snapshot(program, formal_results=(bad,)),
    )
    assert result.accounted_mandatory_ids == (instance_id,)
    assert result.silent_missing_count == 0
    assert result.invalid_mandatory_ids == (instance_id,)
    assert result.unresolved_mandatory_ids == (instance_id,)
    assert result.population_reconciled is False


def test_unexpected_result_is_orphan_not_absorbed_into_denominator():
    program = _program("A")
    expected = _formal(_id(program, "A"))
    orphan_id = RuleInstanceId.build(
        rule_id=RuleId("ORPHAN"),
        grain=Grain.COMPONENT,
        scope_ref="SCOPE_ORPHAN",
    )
    orphan = _formal(orphan_id)
    result = ProjectCoverageReconciler.reconcile(
        compiled_program=program,
        store_snapshot=_snapshot(
            program,
            formal_results=(expected, orphan),
            closure_outcomes=(_closure_for_formal(expected),),
        ),
    )
    assert result.orphan_result_instance_ids == (orphan_id,)
    assert result.population_reconciled is True


def test_pna_remains_in_mandatory_denominator_and_is_not_executed_pass():
    program = _program("A", applicability={"A": ApplicabilityState.PROVEN_NOT_APPLICABLE})
    instance_id = _id(program, "A")
    result = ProjectCoverageReconciler.reconcile(
        compiled_program=program,
        store_snapshot=_snapshot(program),
    )
    assert result.expected_mandatory_ids == (instance_id,)
    assert result.accounted_mandatory_ids == (instance_id,)
    assert result.proven_not_applicable_mandatory_ids == (instance_id,)
    assert result.executed_result_count == 0
    assert result.population_reconciled is True
    assert result.mandatory_closure_complete is True


@pytest.mark.parametrize(
    ("closure_status", "field_name"),
    [
        (ClosureExecutionStatus.BLOCKED, "blocked_mandatory_ids"),
        (ClosureExecutionStatus.NO_DATA, "no_data_mandatory_ids"),
    ],
)
def test_explicit_blocked_or_no_data_is_accounted_but_not_complete(closure_status, field_name):
    program = _program("A")
    instance_id = _id(program, "A")
    snapshot = _snapshot(
        program,
        closure_outcomes=(
            RuleClosureOutcome(
                instance_id,
                closure_status,
                diagnostic_refs=(f"canonical:{closure_status.value}",),
            ),
        ),
    )
    result = ProjectCoverageReconciler.reconcile(
        compiled_program=program,
        store_snapshot=snapshot,
    )
    assert result.silent_missing_count == 0
    assert result.unresolved_count == 0
    assert result.population_reconciled is True
    assert result.mandatory_closure_complete is False
    assert getattr(result, field_name) == (instance_id,)


def test_mandatory_status_partition_equals_exact_denominator():
    program = _program(
        "EXEC",
        "PNA",
        "BLOCK",
        "NODATA",
        "MISS",
        applicability={"PNA": ApplicabilityState.PROVEN_NOT_APPLICABLE},
    )
    exec_record = _formal(_id(program, "EXEC"))
    block_id = _id(program, "BLOCK")
    no_data_id = _id(program, "NODATA")
    snapshot = _snapshot(
        program,
        formal_results=(exec_record,),
        closure_outcomes=(
            _closure_for_formal(exec_record),
            RuleClosureOutcome(block_id, ClosureExecutionStatus.BLOCKED),
            RuleClosureOutcome(no_data_id, ClosureExecutionStatus.NO_DATA),
        ),
    )
    result = ProjectCoverageReconciler.reconcile(
        compiled_program=program,
        store_snapshot=snapshot,
    )
    partition = (
        set(result.executed_mandatory_ids)
        | set(result.proven_not_applicable_mandatory_ids)
        | set(result.blocked_mandatory_ids)
        | set(result.no_data_mandatory_ids)
        | set(result.unresolved_mandatory_ids)
    )
    assert partition == set(result.expected_mandatory_ids)
    assert len(partition) == result.expected_mandatory_instance_count
    assert result.closure_partition_complete is True


def test_runtime_analysis_basis_can_preserve_post_execution_reanalysis_authority():
    program = _program("A")
    instance_id = _id(program, "A")
    supplied = AnalysisBasisRef(
        instance_id=instance_id,
        status=AnalysisBasisStatus.REANALYSIS_REQUIRED,
        source_ref="VS6-P7:CANONICAL_ANALYSIS_BASIS:C1:V2",
    )
    result = ProjectCoverageReconciler.reconcile(
        compiled_program=program,
        store_snapshot=_executed_snapshot(program),
        analysis_basis_refs=(supplied,),
    )
    assert result.reanalysis_required_instance_ids == (instance_id,)
    assert result.analysis_basis_refs == (supplied,)
    assert result.as_dict()["analysis_basis"][0]["source_ref"] == supplied.source_ref


def test_runtime_analysis_basis_population_must_match_compiled_inventory_exactly():
    program = _program("A", "B")
    only_a = AnalysisBasisRef(
        instance_id=_id(program, "A"),
        status=AnalysisBasisStatus.MATCH,
        source_ref="runtime:A",
    )
    with pytest.raises(ProjectReconciliationError, match="exactly"):
        ProjectCoverageReconciler.reconcile(
            compiled_program=program,
            store_snapshot=_executed_snapshot(program),
            analysis_basis_refs=(only_a,),
        )


def test_formal_result_report_binding_uses_canonical_assessment_ref():
    program = _program("A")
    snapshot = _executed_snapshot(program)
    source_ref = AssessmentEngine.reconcile(program, snapshot).closure_outcomes[0].formal_result_ref
    assert source_ref is not None
    contribution = _contribution()
    target = ReportContributionRef.from_contribution(contribution)
    result = ProjectCoverageReconciler.reconcile(
        compiled_program=program,
        store_snapshot=snapshot,
        report_contributions=(contribution,),
        required_report_source_refs=(source_ref,),
        report_bindings=(ReportBindingRef(source_ref, target),),
    )
    assert result.report_reconciled is True
    assert result.missing_report_binding_count == 0


def test_regulatory_quantity_can_be_exact_report_binding_source():
    program = _derivation_program()
    snapshot = RegulatoryEngine.execute(program)
    assessment = AssessmentEngine.reconcile(program, snapshot)
    outcome = assessment.closure_outcomes[0]
    assert len(outcome.regulatory_quantity_refs) == 1
    source_ref = canonical_quantity_report_source_ref(
        outcome.compiled_record_ref,
        outcome.regulatory_quantity_refs[0],
    )
    contribution = SliceReportContribution(
        slice_id="slice:derivation",
        title="Derived quantity",
        contribution_kind="REGULATORY",
        status="PROVEN",
        component_type="toy",
        component_id="SCOPE_D",
    )
    target = ReportContributionRef.from_contribution(contribution)
    result = ProjectCoverageReconciler.reconcile(
        compiled_program=program,
        store_snapshot=snapshot,
        report_contributions=(contribution,),
        required_report_source_refs=(source_ref,),
        report_bindings=(ReportBindingRef(source_ref, target),),
    )
    assert result.report_reconciled is True


def test_closure_outcome_is_canonical_report_source_for_nonexecuted_state():
    program = _program("A")
    instance_id = _id(program, "A")
    snapshot = _snapshot(
        program,
        closure_outcomes=(RuleClosureOutcome(instance_id, ClosureExecutionStatus.BLOCKED),),
    )
    source_ref = canonical_closure_report_source_ref(instance_id)
    contribution = _contribution(status="BLOCKED")
    target = ReportContributionRef.from_contribution(contribution)
    result = ProjectCoverageReconciler.reconcile(
        compiled_program=program,
        store_snapshot=snapshot,
        report_contributions=(contribution,),
        required_report_source_refs=(source_ref,),
        report_bindings=(ReportBindingRef(source_ref, target),),
    )
    assert result.report_reconciled is True


def test_missing_required_report_binding_is_explicit():
    program = _program("A")
    snapshot = _executed_snapshot(program)
    source_ref = AssessmentEngine.reconcile(program, snapshot).closure_outcomes[0].formal_result_ref
    assert source_ref is not None
    result = ProjectCoverageReconciler.reconcile(
        compiled_program=program,
        store_snapshot=snapshot,
        report_contributions=(_contribution(),),
        required_report_source_refs=(source_ref,),
    )
    assert result.missing_report_source_refs == (source_ref,)
    assert result.report_reconciled is False


def test_unknown_report_source_and_target_are_orphans():
    program = _program("A")
    snapshot = _executed_snapshot(program)
    missing_target = ReportContributionRef("missing:slice", "toy", "C1")
    result = ProjectCoverageReconciler.reconcile(
        compiled_program=program,
        store_snapshot=snapshot,
        report_bindings=(ReportBindingRef("unknown:source", missing_target),),
    )
    assert result.orphan_report_binding_source_refs == ("unknown:source",)
    assert result.orphan_report_target_refs == (missing_target,)
    assert result.report_reconciled is False


def test_duplicate_report_contribution_identity_fails_closed():
    program = _program("A")
    with pytest.raises(ReportBindingIdentityBlocked, match="REPORT_BINDING_IDENTITY_BLOCKED"):
        ProjectCoverageReconciler.reconcile(
            compiled_program=program,
            store_snapshot=_executed_snapshot(program),
            report_contributions=(
                _contribution(status="PASS"),
                _contribution(status="FAIL"),
            ),
        )


def _blocked_finding(program):
    instance_id = _id(program, "A")
    outcome = RuleClosureOutcome(
        instance_id,
        ClosureExecutionStatus.BLOCKED,
        diagnostic_refs=("blocked:canonical",),
    )
    compiled_record = next(
        item for item in program.plan.compiled_closure_inventory if item.instance_id == instance_id
    )
    finding = build_finding_from_rule_closure(
        compiled_record=compiled_record,
        outcome=outcome,
    )
    assert finding is not None
    return finding, outcome


def test_action_requirement_is_explicit_policy_input_not_inferred_from_status():
    program = _program("A")
    finding, outcome = _blocked_finding(program)
    snapshot = _snapshot(program, closure_outcomes=(outcome,))
    without_policy = ProjectCoverageReconciler.reconcile(
        compiled_program=program,
        store_snapshot=snapshot,
        findings=(finding,),
    )
    assert without_policy.action_reconciled is True
    with_policy = ProjectCoverageReconciler.reconcile(
        compiled_program=program,
        store_snapshot=snapshot,
        findings=(finding,),
        required_action_finding_ids=(finding.finding_id,),
    )
    assert with_policy.missing_action_finding_ids == (finding.finding_id,)
    assert with_policy.action_reconciled is False


def test_action_binding_without_supplied_finding_is_orphan():
    program = _program("A")
    result = ProjectCoverageReconciler.reconcile(
        compiled_program=program,
        store_snapshot=_executed_snapshot(program),
        action_bindings=(
            ActionBindingRef(
                finding_id="finding:" + "0" * 64,
                action_ref="action:1",
            ),
        ),
    )
    assert result.orphan_action_binding_finding_ids == ("finding:" + "0" * 64,)
    assert result.action_reconciled is False


def test_regulatory_metadata_conflict_is_surfaced_never_resolved():
    program = _program("A")
    result = ProjectCoverageReconciler.reconcile(
        compiled_program=program,
        store_snapshot=_executed_snapshot(program),
        regulatory_metadata_conflict_refs=("authority-conflict:1",),
    )
    assert result.regulatory_metadata_conflict_count == 1
    assert result.regulatory_metadata_clean is False
    assert result.mandatory_closure_complete is True


def test_optional_compiled_result_is_not_orphan_and_not_mandatory_denominator():
    program = _program("A", "OPT", mandatory={"OPT": False})
    a = _formal(_id(program, "A"))
    opt = _formal(_id(program, "OPT"))
    result = ProjectCoverageReconciler.reconcile(
        compiled_program=program,
        store_snapshot=_snapshot(
            program,
            formal_results=(a, opt),
            closure_outcomes=(_closure_for_formal(a), _closure_for_formal(opt)),
        ),
    )
    assert result.expected_mandatory_instance_count == 1
    assert _id(program, "OPT") in result.expected_all_ids
    assert result.orphan_result_count == 0
    assert result.population_reconciled is True


def test_similar_partial_identity_never_joins_expected_instance():
    program = _program("A", scopes={"A": "COLUMN:C1"})
    expected_id = _id(program, "A")
    similar_id = RuleInstanceId.build(
        rule_id=RuleId("A"),
        grain=Grain.COMPONENT,
        scope_ref="column:c1",
    )
    similar = _formal(similar_id)
    result = ProjectCoverageReconciler.reconcile(
        compiled_program=program,
        store_snapshot=_snapshot(program, formal_results=(similar,)),
    )
    assert expected_id in result.silent_missing_mandatory_ids
    assert similar_id in result.orphan_result_instance_ids
    assert result.population_reconciled is False


def test_report_projection_cannot_supply_binding_authority_implicitly():
    program = _program("A")
    snapshot = _executed_snapshot(program, {"A": CheckStatus.FAIL})
    assessment = AssessmentEngine.reconcile(program, snapshot)
    source_ref = assessment.closure_outcomes[0].formal_result_ref
    assert source_ref is not None
    contribution = _contribution(status="PASS")
    before = contribution.as_dict()
    result = ProjectCoverageReconciler.reconcile(
        compiled_program=program,
        store_snapshot=snapshot,
        report_contributions=(contribution,),
        required_report_source_refs=(source_ref,),
    )
    assert contribution.as_dict() == before
    assert result.missing_report_binding_count == 1
    assert result.report_reconciled is False
    assert result.mandatory_closure_complete is True
    assert assessment.structural_status is StructuralAssessmentStatus.COMPLETE


def test_orphan_closure_diagnostic_is_visible():
    program = _program("A")
    orphan_id = RuleInstanceId.build(
        rule_id=RuleId("A"),
        grain=Grain.COMPONENT,
        scope_ref="SCOPE_A_EXTRA",
    )
    orphan_closure = RuleClosureOutcome(
        orphan_id,
        ClosureExecutionStatus.BLOCKED,
        diagnostic_refs=("diagnostic:orphan",),
    )
    result = ProjectCoverageReconciler.reconcile(
        compiled_program=program,
        store_snapshot=_snapshot(program, closure_outcomes=(orphan_closure,)),
    )
    assert orphan_id in result.orphan_closure_instance_ids
    assert result.orphan_diagnostic_refs == ("diagnostic:orphan",)


def test_deterministic_serialization_ignores_input_order():
    program = _program("A", "B")
    a = _formal(_id(program, "A"))
    b = _formal(_id(program, "B"))
    one = ProjectCoverageReconciler.reconcile(
        compiled_program=program,
        store_snapshot=_snapshot(
            program,
            formal_results=(a, b),
            closure_outcomes=(_closure_for_formal(a), _closure_for_formal(b)),
        ),
    )
    two = ProjectCoverageReconciler.reconcile(
        compiled_program=program,
        store_snapshot=_snapshot(
            program,
            formal_results=(b, a),
            closure_outcomes=(_closure_for_formal(b), _closure_for_formal(a)),
        ),
    )
    assert one.to_json().encode("utf-8") == two.to_json().encode("utf-8")


def test_required_report_and_action_sources_must_be_canonical():
    program = _program("A")
    snapshot = _executed_snapshot(program)
    with pytest.raises(ProjectReconciliationError, match="required report source"):
        ProjectCoverageReconciler.reconcile(
            compiled_program=program,
            store_snapshot=snapshot,
            required_report_source_refs=("not-canonical",),
        )
    with pytest.raises(ProjectReconciliationError, match="required action source"):
        ProjectCoverageReconciler.reconcile(
            compiled_program=program,
            store_snapshot=snapshot,
            required_action_finding_ids=("finding:" + "1" * 64,),
        )


def test_fcr_source_has_no_catalog_denominator_fuzzy_match_or_etabs_mutation():
    source = Path("tbdy_engine/coverage/project_reconciliation.py").read_text(encoding="utf-8")
    assert "CoverageRow" not in source
    assert ".authority_refs" not in source
    assert ".casefold(" not in source
    assert "SetPresentUnits(" not in source
    assert "SetPresentUnits_2(" not in source
    assert "FULL_TBDY_COMPLIANT" not in source
