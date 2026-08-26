from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from tbdy_engine.checks.result import CheckResult, CheckStatus
from tbdy_engine.coverage.project_reconciliation import (
    ActionBindingRef,
    ProjectCoverageReconciler,
    ProjectReconciliationError,
    ReportBindingIdentityBlocked,
    ReportBindingRef,
    ReportContributionRef,
)
from tbdy_engine.findings.builder import build_finding_from_rule_closure
from tbdy_engine.product_reports.slice_report_contribution import SliceReportContribution
from tbdy_engine.regulatory.contracts import (
    ApplicabilityBinding,
    ApplicabilityState,
    CheckEvaluatorBinding,
    CheckSpec,
    ClosureExecutionStatus,
    Grain,
    RuleClosureOutcome,
    RuleId,
    RuleInstanceId,
)
from tbdy_engine.regulatory.kernel import (
    AnalysisBasisStatus,
    AssessmentEngine,
    FormalResultRecord,
    RegulatoryCompileInputs,
    RegulatoryCompiler,
    RegulatoryStoreSnapshot,
    RuleScopeTarget,
    StructuralAssessmentStatus,
)
from tbdy_engine.regulatory.registry import RegulatoryRegistry


@dataclass(frozen=True, slots=True)
class _AppInput:
    state: ApplicabilityState = ApplicabilityState.APPLIES


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
            applicability_input=_AppInput(
                applicability.get(rule, ApplicabilityState.APPLIES)
            ),
            analysis_basis_status=analysis.get(rule, AnalysisBasisStatus.MATCH),
        )
        for rule in rules
    )
    return RegulatoryCompiler.compile(
        registry,
        RegulatoryCompileInputs(rule_targets=targets),
    )


def _id(program, rule: str) -> RuleInstanceId:
    return next(
        item
        for item in program.plan.compiled_rule_instances
        if item.rule_id == RuleId(rule)
    )


def _formal(
    instance_id: RuleInstanceId,
    status: CheckStatus = CheckStatus.OK,
    *,
    evidence=(),
) -> FormalResultRecord:
    return FormalResultRecord(
        instance_id=instance_id,
        result=CheckResult(
            check_id=instance_id.rule_id.value,
            component=instance_id.scope_ref,
            component_type="toy",
            status=status,
            evidence=evidence,
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


def _snapshot(
    program,
    *,
    formal_results=(),
    closure_outcomes=(),
    regulatory_quantities=(),
    diagnostics=(),
) -> RegulatoryStoreSnapshot:
    return RegulatoryStoreSnapshot(
        plan_identity=program.plan.plan_identity,
        regulatory_quantities=tuple(regulatory_quantities),
        formal_results=tuple(formal_results),
        closure_outcomes=tuple(closure_outcomes),
        diagnostics=tuple(diagnostics),
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
    outcomes = tuple(_closure_for_formal(record) for record in records)
    return _snapshot(program, formal_results=records, closure_outcomes=outcomes)


def _contribution(
    *,
    slice_id="slice:toy",
    component_id="C1",
    status="PASS",
    authority_refs=(),
):
    return SliceReportContribution(
        slice_id=slice_id,
        title="Toy contribution",
        contribution_kind="CHECK",
        status=status,
        component_type="toy",
        component_id=component_id,
        authority_refs=tuple(authority_refs),
    )


def test_A_all_expected_mandatory_instances_are_reconciled_exactly_once():
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
    assert result.duplicate_result_count == 0
    assert result.orphan_result_count == 0
    assert result.population_reconciled is True
    assert result.mandatory_closure_complete is True
    assert result.structural_assessment == AssessmentEngine.reconcile(program, snapshot)


def test_B_silent_missing_requires_raw_absence_of_artifact_and_explicit_closure():
    program = _program("A")
    result = ProjectCoverageReconciler.reconcile(
        compiled_program=program,
        store_snapshot=_snapshot(program),
    )

    assert result.expected_mandatory_instance_count == 1
    assert result.accounted_instance_count == 0
    assert result.silent_missing_count == 1
    assert result.population_reconciled is False
    assert result.mandatory_closure_complete is False


def test_C_duplicate_formal_result_uses_exact_formal_result_record_instance_id():
    program = _program("A")
    instance_id = _id(program, "A")
    one = _formal(instance_id)
    two = _formal(instance_id)
    snapshot = _snapshot(
        program,
        formal_results=(one, two),
        closure_outcomes=(_closure_for_formal(one),),
    )

    result = ProjectCoverageReconciler.reconcile(
        compiled_program=program,
        store_snapshot=snapshot,
    )

    assert result.duplicate_result_instance_ids == (instance_id,)
    assert result.duplicate_result_count == 1
    assert result.population_reconciled is False


def test_D_unexpected_check_result_is_orphan_not_absorbed():
    program = _program("A")
    expected = _formal(_id(program, "A"))
    orphan_id = RuleInstanceId.build(
        rule_id=RuleId("ORPHAN"),
        grain=Grain.COMPONENT,
        scope_ref="SCOPE_ORPHAN",
    )
    orphan = _formal(orphan_id)
    snapshot = _snapshot(
        program,
        formal_results=(expected, orphan),
        closure_outcomes=(_closure_for_formal(expected),),
    )

    result = ProjectCoverageReconciler.reconcile(
        compiled_program=program,
        store_snapshot=snapshot,
    )

    assert result.orphan_result_instance_ids == (orphan_id,)
    assert result.orphan_result_count == 1
    assert result.population_reconciled is True


def test_E_pna_stays_in_mandatory_denominator_and_is_accounted_not_pass():
    program = _program(
        "A",
        applicability={"A": ApplicabilityState.PROVEN_NOT_APPLICABLE},
    )
    instance_id = _id(program, "A")
    result = ProjectCoverageReconciler.reconcile(
        compiled_program=program,
        store_snapshot=_snapshot(program),
    )

    assert result.expected_mandatory_ids == (instance_id,)
    assert result.expected_mandatory_instance_count == 1
    assert result.accounted_mandatory_ids == (instance_id,)
    assert result.proven_not_applicable_mandatory_ids == (instance_id,)
    assert result.executed_result_count == 0
    assert result.silent_missing_count == 0
    assert result.population_reconciled is True
    assert result.mandatory_closure_complete is True


@pytest.mark.parametrize(
    ("closure_status", "field_name"),
    [
        (ClosureExecutionStatus.BLOCKED, "blocked_mandatory_ids"),
        (ClosureExecutionStatus.NO_DATA, "no_data_mandatory_ids"),
    ],
)
def test_F_G_explicit_unresolved_closure_is_accounted_but_not_complete(
    closure_status,
    field_name,
):
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
    assert result.population_reconciled is True
    assert result.mandatory_closure_complete is False
    assert getattr(result, field_name) == (instance_id,)


def test_H_reanalysis_required_is_preserved_on_existing_analysis_basis_plane():
    program = _program(
        "A",
        analysis={"A": AnalysisBasisStatus.REANALYSIS_REQUIRED},
    )
    instance_id = _id(program, "A")
    snapshot = _snapshot(
        program,
        closure_outcomes=(
            RuleClosureOutcome(
                instance_id,
                ClosureExecutionStatus.BLOCKED,
                diagnostic_refs=("analysis basis REANALYSIS_REQUIRED",),
            ),
        ),
    )

    result = ProjectCoverageReconciler.reconcile(
        compiled_program=program,
        store_snapshot=snapshot,
    )

    assert result.reanalysis_required_instance_ids == (instance_id,)
    assert result.as_dict()["analysis_basis"] == [
        {"instance_id": instance_id.value, "status": "REANALYSIS_REQUIRED"}
    ]
    assert result.mandatory_closure_complete is False


def test_I_missing_required_report_binding_is_explicit():
    program = _program("A")
    snapshot = _executed_snapshot(program)
    source_ref = AssessmentEngine.reconcile(
        program, snapshot
    ).closure_outcomes[0].formal_result_ref
    assert source_ref is not None

    result = ProjectCoverageReconciler.reconcile(
        compiled_program=program,
        store_snapshot=snapshot,
        required_report_source_refs=(source_ref,),
        report_contributions=(_contribution(),),
    )

    assert result.missing_report_source_refs == (source_ref,)
    assert result.missing_report_binding_count == 1
    assert result.report_reconciled is False


def test_J_report_binding_with_unknown_canonical_source_is_orphan():
    program = _program("A")
    snapshot = _executed_snapshot(program)
    contribution = _contribution()
    target = ReportContributionRef.from_contribution(contribution)

    result = ProjectCoverageReconciler.reconcile(
        compiled_program=program,
        store_snapshot=snapshot,
        report_contributions=(contribution,),
        report_bindings=(
            ReportBindingRef(
                source_ref="unknown:canonical-source",
                contribution_ref=target,
            ),
        ),
    )

    assert result.orphan_report_binding_source_refs == (
        "unknown:canonical-source",
    )
    assert result.orphan_report_binding_count == 1
    assert result.report_reconciled is False


def test_report_binding_target_must_resolve_exactly_to_existing_contribution():
    program = _program("A")
    snapshot = _executed_snapshot(program)
    source_ref = AssessmentEngine.reconcile(
        program, snapshot
    ).closure_outcomes[0].formal_result_ref
    assert source_ref is not None
    missing_target = ReportContributionRef("missing:slice", "toy", "C1")

    result = ProjectCoverageReconciler.reconcile(
        compiled_program=program,
        store_snapshot=snapshot,
        report_bindings=(
            ReportBindingRef(source_ref=source_ref, contribution_ref=missing_target),
        ),
    )

    assert result.orphan_report_target_refs == (missing_target,)
    assert result.report_reconciled is False


def test_duplicate_report_contribution_identity_stops_reconciliation():
    program = _program("A")
    snapshot = _executed_snapshot(program)
    one = _contribution(status="PASS")
    two = _contribution(status="FAIL")

    with pytest.raises(
        ReportBindingIdentityBlocked,
        match="REPORT_BINDING_IDENTITY_BLOCKED",
    ):
        ProjectCoverageReconciler.reconcile(
            compiled_program=program,
            store_snapshot=snapshot,
            report_contributions=(one, two),
        )


def _blocked_finding(program):
    instance_id = _id(program, "A")
    outcome = RuleClosureOutcome(
        instance_id,
        ClosureExecutionStatus.BLOCKED,
        diagnostic_refs=("blocked:canonical",),
    )
    compiled_record = next(
        item
        for item in program.plan.compiled_closure_inventory
        if item.instance_id == instance_id
    )
    finding = build_finding_from_rule_closure(
        compiled_record=compiled_record,
        outcome=outcome,
    )
    assert finding is not None
    return finding, outcome


def test_K_action_requirement_is_explicit_input_not_inferred_from_finding_status():
    program = _program("A")
    finding, outcome = _blocked_finding(program)
    snapshot = _snapshot(program, closure_outcomes=(outcome,))

    without_policy = ProjectCoverageReconciler.reconcile(
        compiled_program=program,
        store_snapshot=snapshot,
        findings=(finding,),
    )
    assert without_policy.missing_action_binding_count == 0
    assert without_policy.action_reconciled is True

    with_policy = ProjectCoverageReconciler.reconcile(
        compiled_program=program,
        store_snapshot=snapshot,
        findings=(finding,),
        required_action_finding_ids=(finding.finding_id,),
    )
    assert with_policy.missing_action_finding_ids == (finding.finding_id,)
    assert with_policy.missing_action_binding_count == 1
    assert with_policy.action_reconciled is False


def test_L_action_binding_without_supplied_canonical_finding_is_orphan():
    program = _program("A")
    snapshot = _executed_snapshot(program)

    result = ProjectCoverageReconciler.reconcile(
        compiled_program=program,
        store_snapshot=snapshot,
        action_bindings=(
            ActionBindingRef(
                finding_id="finding:" + "0" * 64,
                action_ref="action:1",
            ),
        ),
    )

    assert result.orphan_action_binding_finding_ids == (
        "finding:" + "0" * 64,
    )
    assert result.orphan_action_binding_count == 1
    assert result.action_reconciled is False


def test_M_regulatory_metadata_conflict_is_only_surfaced_not_resolved():
    program = _program("A")
    result = ProjectCoverageReconciler.reconcile(
        compiled_program=program,
        store_snapshot=_executed_snapshot(program),
        regulatory_metadata_conflict_refs=("authority-conflict:1",),
    )

    assert result.regulatory_metadata_conflict_count == 1
    assert result.regulatory_metadata_clean is False
    assert result.mandatory_closure_complete is True


def test_N_deterministic_serialization_ignores_input_order():
    program = _program("A", "B")
    a = _formal(_id(program, "A"))
    b = _formal(_id(program, "B"))
    snapshot_one = _snapshot(
        program,
        formal_results=(a, b),
        closure_outcomes=(_closure_for_formal(a), _closure_for_formal(b)),
    )
    snapshot_two = _snapshot(
        program,
        formal_results=(b, a),
        closure_outcomes=(_closure_for_formal(b), _closure_for_formal(a)),
    )

    one = ProjectCoverageReconciler.reconcile(
        compiled_program=program,
        store_snapshot=snapshot_one,
    )
    two = ProjectCoverageReconciler.reconcile(
        compiled_program=program,
        store_snapshot=snapshot_two,
    )

    assert one.to_json().encode("utf-8") == two.to_json().encode("utf-8")


def test_O_optional_compiled_result_is_not_orphan_and_not_in_mandatory_denominator():
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


def test_P_similar_or_partial_identity_does_not_join_expected_instance():
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
        store_snapshot=_snapshot(
            program,
            formal_results=(similar,),
        ),
    )

    assert expected_id in result.silent_missing_mandatory_ids
    assert similar_id in result.orphan_result_instance_ids
    assert result.population_reconciled is False


def test_Q_report_projection_cannot_be_used_as_status_or_result_binding_authority():
    program = _program("A")
    snapshot = _executed_snapshot(program, {"A": CheckStatus.FAIL})
    assessment = AssessmentEngine.reconcile(program, snapshot)
    source_ref = assessment.closure_outcomes[0].formal_result_ref
    assert source_ref is not None
    contribution = _contribution(
        status="PASS",
        authority_refs=(source_ref,),
    )
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


def test_one_to_many_check_evidence_does_not_create_false_duplicate_result():
    program = _program("A")
    record = _formal(
        _id(program, "A"),
        evidence=({"source": "row:1"}, {"source": "row:2"}),
    )
    result = ProjectCoverageReconciler.reconcile(
        compiled_program=program,
        store_snapshot=_snapshot(
            program,
            formal_results=(record,),
            closure_outcomes=(_closure_for_formal(record),),
        ),
    )

    assert result.duplicate_result_count == 0
    assert result.population_reconciled is True


def test_raw_rule_closure_outcome_identity_is_exact_and_orphan_diagnostic_is_visible():
    program = _program("A")
    expected_id = _id(program, "A")
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

    assert expected_id in result.silent_missing_mandatory_ids
    assert orphan_id in result.orphan_closure_instance_ids
    assert result.orphan_diagnostic_refs == ("diagnostic:orphan",)


def test_report_binding_uses_canonical_outcome_formal_result_ref_exactly():
    program = _program("A")
    snapshot = _executed_snapshot(program)
    outcome = AssessmentEngine.reconcile(program, snapshot).closure_outcomes[0]
    source_ref = outcome.formal_result_ref
    assert source_ref is not None
    contribution = _contribution()
    target = ReportContributionRef.from_contribution(contribution)

    result = ProjectCoverageReconciler.reconcile(
        compiled_program=program,
        store_snapshot=snapshot,
        report_contributions=(contribution,),
        required_report_source_refs=(source_ref,),
        report_bindings=(
            ReportBindingRef(
                source_ref=source_ref,
                contribution_ref=target,
            ),
        ),
    )

    assert result.missing_report_binding_count == 0
    assert result.report_reconciled is True


def test_required_report_and_action_sources_must_be_canonical_supplied_refs():
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
    source = Path(
        "tbdy_engine/coverage/project_reconciliation.py"
    ).read_text(encoding="utf-8")

    assert "CoverageRow" not in source
    assert ".authority_refs" not in source
    assert ".casefold(" not in source
    assert "SetPresentUnits(" not in source
    assert "SetPresentUnits_2(" not in source
    assert "FULL_TBDY_COMPLIANT" not in source
