from __future__ import annotations

from dataclasses import dataclass

import pytest

from tbdy_engine.checks.result import CheckResult, CheckStatus
from tbdy_engine.coverage.project_reconciliation import (
    AnalysisBasisRef,
    ProjectCoverageReconciler,
    ReportBindingRef,
    ReportContributionRef,
    canonical_closure_report_source_ref,
)
from tbdy_engine.product_reports.slice_report_contribution import SliceReportContribution
from tbdy_engine.product_reports.unified_building_report import (
    BuildingReportIntegrityError,
    BuildingReportModel,
    ProjectBasisEntry,
    ProjectBasisLedger,
    ReportSourceKind,
    SourceManifest,
    SourceManifestEntry,
    mandatory_report_source_refs,
)
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
    FormalResultRecord,
    RegulatoryCompileInputs,
    RegulatoryCompiler,
    RegulatoryStoreSnapshot,
    RuleScopeTarget,
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


def _program(*rules: str, applicability: dict[str, ApplicabilityState] | None = None):
    applicability = applicability or {}
    registry = RegulatoryRegistry(checks=tuple(_check(rule) for rule in rules))
    return RegulatoryCompiler.compile(
        registry,
        RegulatoryCompileInputs(
            rule_targets=tuple(
                RuleScopeTarget(
                    rule_id=RuleId(rule),
                    grain=Grain.COMPONENT,
                    scope_ref=f"SCOPE_{rule}",
                    applicability_input=_AppInput(applicability.get(rule, ApplicabilityState.APPLIES)),
                )
                for rule in rules
            )
        ),
    )


def _id(program, rule: str) -> RuleInstanceId:
    return next(
        item for item in program.plan.compiled_rule_instances if item.rule_id == RuleId(rule)
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


def _snapshot(program, *, formal_results=(), closure_outcomes=()):
    return RegulatoryStoreSnapshot(
        plan_identity=program.plan.plan_identity,
        regulatory_quantities=(),
        formal_results=tuple(formal_results),
        closure_outcomes=tuple(closure_outcomes),
        diagnostics=(),
    )


def _contribution(rule: str, *, status: str = "PASS") -> SliceReportContribution:
    return SliceReportContribution(
        slice_id=f"slice:{rule}",
        title=f"Rule {rule}",
        contribution_kind="CHECK",
        status=status,
        component_type="toy",
        component_id=f"SCOPE_{rule}",
    )


def _basis(source_id: str = "SRC:REG") -> ProjectBasisLedger:
    return ProjectBasisLedger(
        (
            ProjectBasisEntry(
                key="design_basis",
                label="Design basis",
                value="TOY",
                source_ids=(source_id,),
            ),
        )
    )


def _manifest(source_id: str = "SRC:REG") -> SourceManifest:
    return SourceManifest(
        (
            SourceManifestEntry(
                source_id=source_id,
                source_kind=ReportSourceKind.REGULATORY_DOCUMENT,
                title="Toy regulatory source",
                fingerprint="sha256:toy",
            ),
        )
    )


def _executed_reconciliation(*rules: str, analysis_basis_refs=None):
    program = _program(*rules)
    records = tuple(_formal(_id(program, rule)) for rule in rules)
    snapshot = _snapshot(
        program,
        formal_results=records,
        closure_outcomes=tuple(_closure_for_formal(item) for item in records),
    )
    contributions = tuple(_contribution(rule) for rule in rules)
    refs = tuple(f"{_id(program, rule).value}:CheckResult" for rule in rules)
    bindings = tuple(
        ReportBindingRef(source_ref, ReportContributionRef.from_contribution(contribution))
        for source_ref, contribution in zip(refs, contributions)
    )
    reconciliation = ProjectCoverageReconciler.reconcile(
        compiled_program=program,
        store_snapshot=snapshot,
        report_contributions=contributions,
        required_report_source_refs=refs,
        report_bindings=bindings,
        analysis_basis_refs=analysis_basis_refs,
    )
    return program, reconciliation, contributions, bindings


def _model(reconciliation, contributions, bindings, *, basis=None, manifest=None):
    return BuildingReportModel(
        report_id="REPORT:1",
        project_id="PROJECT:1",
        title="Unified structural assessment",
        reconciliation=reconciliation,
        project_basis=basis or _basis(),
        source_manifest=manifest or _manifest(),
        contributions=contributions,
        report_bindings=bindings,
    )


def test_valid_model_uses_one_canonical_truth_model_and_never_emits_global_pass():
    _, reconciliation, contributions, bindings = _executed_reconciliation("A")
    model = _model(reconciliation, contributions, bindings)
    payload = model.as_dict()

    assert model.report_integrity_status == "RECONCILED"
    assert payload["artifact_type"] == "BUILDING_REPORT_MODEL"
    assert payload["presentation_contract"]["default_view"] == "ENGINEERING"
    assert payload["presentation_contract"]["supported_views"] == ["ENGINEERING", "AUDIT"]
    assert payload["presentation_contract"]["renderer_may_recalculate_engineering"] is False
    assert payload["presentation_contract"]["global_compliance_verdict_emitted"] is False
    assert model.to_json() == model.to_json()


def test_fcr_cannot_omit_a_mandatory_report_source_even_if_empty_reporting_request_reconciles():
    program = _program("A")
    record = _formal(_id(program, "A"))
    snapshot = _snapshot(
        program,
        formal_results=(record,),
        closure_outcomes=(_closure_for_formal(record),),
    )
    reconciliation = ProjectCoverageReconciler.reconcile(
        compiled_program=program,
        store_snapshot=snapshot,
    )
    assert reconciliation.report_reconciled is True

    with pytest.raises(BuildingReportIntegrityError, match="mandatory closure/artifact population"):
        _model(reconciliation, (), ())


@pytest.mark.parametrize(
    ("closure_status", "contribution_status"),
    [
        (ClosureExecutionStatus.BLOCKED, "BLOCKED"),
        (ClosureExecutionStatus.NO_DATA, "NO_DATA"),
    ],
)
def test_resultless_mandatory_closure_must_bind_by_exact_closure_identity(
    closure_status, contribution_status
):
    program = _program("A")
    instance_id = _id(program, "A")
    snapshot = _snapshot(
        program,
        closure_outcomes=(RuleClosureOutcome(instance_id, closure_status),),
    )
    contribution = _contribution("A", status=contribution_status)
    source_ref = canonical_closure_report_source_ref(instance_id)
    binding = ReportBindingRef(source_ref, ReportContributionRef.from_contribution(contribution))
    reconciliation = ProjectCoverageReconciler.reconcile(
        compiled_program=program,
        store_snapshot=snapshot,
        report_contributions=(contribution,),
        required_report_source_refs=(source_ref,),
        report_bindings=(binding,),
    )

    assert mandatory_report_source_refs(reconciliation) == (source_ref,)
    model = _model(reconciliation, (contribution,), (binding,))
    assert model.as_dict()["report_bindings"][0]["source_ref"] == source_ref


def test_proven_not_applicable_stays_in_denominator_and_cannot_disappear_from_report():
    program = _program("A", applicability={"A": ApplicabilityState.PROVEN_NOT_APPLICABLE})
    instance_id = _id(program, "A")
    source_ref = canonical_closure_report_source_ref(instance_id)
    contribution = _contribution("A", status="OUT_OF_SCOPE")
    binding = ReportBindingRef(source_ref, ReportContributionRef.from_contribution(contribution))
    reconciliation = ProjectCoverageReconciler.reconcile(
        compiled_program=program,
        store_snapshot=_snapshot(program),
        report_contributions=(contribution,),
        required_report_source_refs=(source_ref,),
        report_bindings=(binding,),
    )

    model = _model(reconciliation, (contribution,), (binding,))
    assert reconciliation.proven_not_applicable_count == 1
    assert mandatory_report_source_refs(reconciliation) == (source_ref,)
    assert model.as_dict()["coverage_reconciliation"]["summary"]["proven_not_applicable_count"] == 1


def test_duplicate_contribution_identity_is_rejected_at_building_model_boundary():
    _, reconciliation, contributions, bindings = _executed_reconciliation("A")
    contribution = contributions[0]
    with pytest.raises(BuildingReportIntegrityError, match="exact and unique"):
        _model(reconciliation, (contribution, contribution), bindings)


def test_every_contribution_requires_a_canonical_source_binding():
    _, reconciliation, contributions, bindings = _executed_reconciliation("A")
    extra = SliceReportContribution(
        slice_id="slice:extra",
        title="Unbound factual slice",
        contribution_kind="FACTUAL",
        status="PROVEN",
        component_type="toy",
        component_id="EXTRA",
    )
    with pytest.raises(BuildingReportIntegrityError, match="without canonical source binding"):
        _model(reconciliation, (*contributions, extra), bindings)


def test_project_basis_source_must_exist_in_source_manifest():
    _, reconciliation, contributions, bindings = _executed_reconciliation("A")
    with pytest.raises(BuildingReportIntegrityError, match="missing source manifest"):
        _model(
            reconciliation,
            contributions,
            bindings,
            basis=_basis("SRC:MISSING"),
            manifest=_manifest("SRC:REG"),
        )


def test_runtime_reanalysis_required_is_preserved_without_reporter_reinterpretation():
    program = _program("A")
    instance_id = _id(program, "A")
    record = _formal(instance_id)
    snapshot = _snapshot(
        program,
        formal_results=(record,),
        closure_outcomes=(_closure_for_formal(record),),
    )
    contribution = _contribution("A", status="REANALYSIS_REQUIRED")
    source_ref = f"{instance_id.value}:CheckResult"
    binding = ReportBindingRef(source_ref, ReportContributionRef.from_contribution(contribution))
    basis_ref = AnalysisBasisRef(
        instance_id=instance_id,
        status=AnalysisBasisStatus.REANALYSIS_REQUIRED,
        source_ref="ENGINE:ANALYSIS_BASIS:A",
    )
    reconciliation = ProjectCoverageReconciler.reconcile(
        compiled_program=program,
        store_snapshot=snapshot,
        report_contributions=(contribution,),
        required_report_source_refs=(source_ref,),
        report_bindings=(binding,),
        analysis_basis_refs=(basis_ref,),
    )

    payload = _model(reconciliation, (contribution,), (binding,)).as_dict()
    assert payload["coverage_reconciliation"]["analysis_basis"][0]["status"] == "REANALYSIS_REQUIRED"
    assert payload["contributions"][0]["status"] == "REANALYSIS_REQUIRED"


def test_serialization_is_deterministic_for_input_order():
    _, reconciliation, contributions, bindings = _executed_reconciliation("A", "B")
    forward = _model(reconciliation, contributions, bindings)
    reverse = _model(reconciliation, tuple(reversed(contributions)), tuple(reversed(bindings)))
    assert forward.to_json() == reverse.to_json()


def test_basis_and_source_manifest_are_canonicalized_deterministically():
    basis = ProjectBasisLedger(
        (
            ProjectBasisEntry("zeta", "Zeta", 2, ("SRC:2",)),
            ProjectBasisEntry("alpha", "Alpha", 1, ("SRC:1",)),
        )
    )
    manifest = SourceManifest(
        (
            SourceManifestEntry("SRC:2", ReportSourceKind.ENGINE_ARTIFACT, "Second"),
            SourceManifestEntry("SRC:1", ReportSourceKind.REVIEWED_DECLARATION, "First"),
        )
    )
    _, reconciliation, contributions, bindings = _executed_reconciliation("A")
    payload = _model(
        reconciliation,
        contributions,
        bindings,
        basis=basis,
        manifest=manifest,
    ).as_dict()

    assert [item["key"] for item in payload["project_basis"]["entries"]] == ["alpha", "zeta"]
    assert [item["source_id"] for item in payload["source_manifest"]["entries"]] == ["SRC:1", "SRC:2"]
