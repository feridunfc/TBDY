from __future__ import annotations

from dataclasses import FrozenInstanceError, dataclass
from pathlib import Path

import pytest

from tbdy_engine.checks.result import CheckResult, CheckStatus
from tbdy_engine.coverage.project_reconciliation import (
    AnalysisBasisRef,
    ProjectCoverageReconciler,
    ReportBindingRef,
    ReportContributionRef,
    canonical_closure_report_source_ref,
)
from tbdy_engine.product_reports.building_report_projection import (
    BuildingReportProjection,
    ReportProjectionIntegrityError,
    ReportView,
    project_building_report_view,
)
from tbdy_engine.product_reports.slice_report_contribution import (
    ReportCalculation,
    ReportField,
    ReportTable,
    SliceReportContribution,
)
from tbdy_engine.product_reports.unified_building_report import (
    BuildingReportModel,
    ProjectBasisEntry,
    ProjectBasisLedger,
    ReportSourceKind,
    SourceManifest,
    SourceManifestEntry,
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
    return next(item for item in program.plan.compiled_rule_instances if item.rule_id == RuleId(rule))


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


def _snapshot(program, *, formal_results=(), closure_outcomes=()):
    return RegulatoryStoreSnapshot(
        plan_identity=program.plan.plan_identity,
        regulatory_quantities=(),
        formal_results=tuple(formal_results),
        closure_outcomes=tuple(closure_outcomes),
        diagnostics=(),
    )


def _contribution(
    rule: str,
    *,
    status: str = "PASS",
    render_views: tuple[str, ...] = ("EXECUTIVE", "ENGINEERING", "AUDIT"),
    calculation: bool = False,
) -> SliceReportContribution:
    calculations = ()
    if calculation:
        calculations = (
            ReportCalculation(
                calculation_id=f"calc:{rule}",
                title=f"Resolved {rule} calculation",
                formula="demand / capacity",
                inputs=(ReportField("demand", "Demand", 125.0, "kN", "INPUT"),),
                outputs=(ReportField("ratio", "Ratio", 0.625, None, "RESULT"),),
                authority_refs=("AUTH:TOY",),
                evidence_refs=("EVIDENCE:TOY",),
                governing_ref="GOV:ROW:1",
            ),
        )
    return SliceReportContribution(
        slice_id=f"slice:{rule}",
        title=f"Rule {rule}",
        contribution_kind="CHECK",
        status=status,
        component_type="toy",
        component_id=f"SCOPE_{rule}",
        summary_fields=(ReportField("resolved", "Resolved value", 125.0, "kN", "RESULT"),),
        tables=(
            ReportTable(
                table_id=f"table:{rule}",
                title=f"Resolved {rule} rows",
                columns=("case", "value"),
                rows=({"case": "LC1", "value": 125.0},),
            ),
        ),
        calculations=calculations,
        authority_refs=("AUTH:TOY",),
        evidence_refs=("EVIDENCE:TOY",),
        warnings=("UPSTREAM_WARNING",),
        render_views=render_views,
    )


def _basis() -> ProjectBasisLedger:
    return ProjectBasisLedger(
        (
            ProjectBasisEntry(
                key="design_basis",
                label="Design basis",
                value="TOY",
                source_ids=("SRC:REG",),
            ),
        )
    )


def _manifest() -> SourceManifest:
    return SourceManifest(
        (
            SourceManifestEntry(
                source_id="SRC:REG",
                source_kind=ReportSourceKind.REGULATORY_DOCUMENT,
                title="Toy regulatory source",
                fingerprint="sha256:toy",
                locator="TOY §1",
                authority_refs=("AUTH:TOY",),
                evidence_refs=("EVIDENCE:TOY",),
            ),
        )
    )


def _executed_model(
    statuses: tuple[tuple[str, str], ...] = (("A", "PASS"),),
    *,
    render_views_by_rule: dict[str, tuple[str, ...]] | None = None,
    analysis_basis_by_rule: dict[str, AnalysisBasisStatus] | None = None,
    calculation_rule: str | None = None,
) -> BuildingReportModel:
    render_views_by_rule = render_views_by_rule or {}
    analysis_basis_by_rule = analysis_basis_by_rule or {}
    rules = tuple(rule for rule, _ in statuses)
    program = _program(*rules)
    records = tuple(
        _formal(_id(program, rule), CheckStatus.FAIL if status == "FAIL" else CheckStatus.OK)
        for rule, status in statuses
    )
    closures = tuple(
        RuleClosureOutcome(
            compiled_record_ref=record.instance_id,
            execution_status=ClosureExecutionStatus.EXECUTED,
            formal_result_ref=f"{record.instance_id.value}:CheckResult",
        )
        for record in records
    )
    contributions = tuple(
        _contribution(
            rule,
            status=status,
            render_views=render_views_by_rule.get(
                rule, ("EXECUTIVE", "ENGINEERING", "AUDIT")
            ),
            calculation=rule == calculation_rule,
        )
        for rule, status in statuses
    )
    refs = tuple(f"{_id(program, rule).value}:CheckResult" for rule in rules)
    bindings = tuple(
        ReportBindingRef(source_ref, ReportContributionRef.from_contribution(contribution))
        for source_ref, contribution in zip(refs, contributions)
    )
    basis_refs = tuple(
        AnalysisBasisRef(
            instance_id=_id(program, rule),
            status=analysis_basis_by_rule.get(rule, AnalysisBasisStatus.MATCH),
            source_ref=f"ANALYSIS_BASIS:{rule}",
        )
        for rule in rules
    )
    reconciliation = ProjectCoverageReconciler.reconcile(
        compiled_program=program,
        store_snapshot=_snapshot(program, formal_results=records, closure_outcomes=closures),
        report_contributions=contributions,
        required_report_source_refs=refs,
        report_bindings=bindings,
        analysis_basis_refs=basis_refs,
    )
    return BuildingReportModel(
        report_id="REPORT:1",
        project_id="PROJECT:1",
        title="Unified structural assessment",
        reconciliation=reconciliation,
        project_basis=_basis(),
        source_manifest=_manifest(),
        contributions=contributions,
        report_bindings=bindings,
    )


def _resultless_model(closure_status: ClosureExecutionStatus, contribution_status: str) -> BuildingReportModel:
    program = _program("A")
    instance_id = _id(program, "A")
    source_ref = canonical_closure_report_source_ref(instance_id)
    contribution = _contribution("A", status=contribution_status)
    binding = ReportBindingRef(source_ref, ReportContributionRef.from_contribution(contribution))
    reconciliation = ProjectCoverageReconciler.reconcile(
        compiled_program=program,
        store_snapshot=_snapshot(
            program,
            closure_outcomes=(RuleClosureOutcome(instance_id, closure_status),),
        ),
        report_contributions=(contribution,),
        required_report_source_refs=(source_ref,),
        report_bindings=(binding,),
    )
    return BuildingReportModel(
        report_id="REPORT:1",
        project_id="PROJECT:1",
        title="Unified structural assessment",
        reconciliation=reconciliation,
        project_basis=_basis(),
        source_manifest=_manifest(),
        contributions=(contribution,),
        report_bindings=(binding,),
    )


def _pna_model() -> BuildingReportModel:
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
    return BuildingReportModel(
        report_id="REPORT:1",
        project_id="PROJECT:1",
        title="Unified structural assessment",
        reconciliation=reconciliation,
        project_basis=_basis(),
        source_manifest=_manifest(),
        contributions=(contribution,),
        report_bindings=(binding,),
    )


def _statuses(payload: dict[str, object]) -> list[str]:
    return [item["status"] for item in payload["contributions"]]  # type: ignore[index]


def test_engineering_projection_from_valid_building_report_model():
    model = _executed_model()
    projection = project_building_report_view(model, ReportView.ENGINEERING)
    payload = projection.as_dict()
    assert isinstance(projection, BuildingReportProjection)
    assert payload["view"] == "ENGINEERING"
    assert payload["report_id"] == model.report_id
    assert payload["report_integrity_status"] == "RECONCILED"
    assert payload["presentation_contract"]["global_compliance_verdict_emitted"] is False


def test_audit_projection_from_same_building_report_model():
    model = _executed_model()
    payload = project_building_report_view(model, ReportView.AUDIT).as_dict()
    assert payload["view"] == "AUDIT"
    assert payload["coverage_reconciliation"] == model.reconciliation.as_dict()
    assert payload["source_manifest"] == model.source_manifest.as_dict()


@pytest.mark.parametrize("view", [ReportView.ENGINEERING, ReportView.AUDIT])
def test_both_views_preserve_canonical_contribution_status_exactly(view):
    model = _executed_model((("A", "PASS"), ("B", "FAIL")))
    payload = project_building_report_view(model, view).as_dict()
    assert _statuses(payload) == [item.status for item in model.contributions]


def test_blocked_survives_projection_unchanged():
    model = _resultless_model(ClosureExecutionStatus.BLOCKED, "BLOCKED")
    assert _statuses(project_building_report_view(model, ReportView.ENGINEERING).as_dict()) == [
        "BLOCKED"
    ]


def test_no_data_survives_projection_unchanged():
    model = _resultless_model(ClosureExecutionStatus.NO_DATA, "NO_DATA")
    assert _statuses(project_building_report_view(model, ReportView.AUDIT).as_dict()) == ["NO_DATA"]


def test_proven_not_applicable_remains_explicit_and_is_not_pass():
    model = _pna_model()
    payload = project_building_report_view(model, ReportView.ENGINEERING).as_dict()
    assert _statuses(payload) == ["OUT_OF_SCOPE"]
    assert payload["coverage_summary"]["proven_not_applicable_count"] == 1
    assert "PASS" not in _statuses(payload)


def test_reanalysis_required_remains_exact_analysis_basis_warning_and_status():
    model = _executed_model(
        (("A", "REANALYSIS_REQUIRED"),),
        analysis_basis_by_rule={"A": AnalysisBasisStatus.REANALYSIS_REQUIRED},
    )
    payload = project_building_report_view(model, ReportView.ENGINEERING).as_dict()
    assert _statuses(payload) == ["REANALYSIS_REQUIRED"]
    assert payload["analysis_basis_warnings"][0]["status"] == "REANALYSIS_REQUIRED"


def test_fail_remains_fail_without_project_or_global_verdict():
    payload = project_building_report_view(
        _executed_model((("A", "FAIL"),)), ReportView.ENGINEERING
    ).as_dict()
    assert _statuses(payload) == ["FAIL"]
    assert "global_status" not in payload
    assert "global_verdict" not in payload
    assert "compliance" not in payload


def test_pass_remains_pass_without_project_global_pass():
    payload = project_building_report_view(_executed_model(), ReportView.AUDIT).as_dict()
    assert _statuses(payload) == ["PASS"]
    assert "global_status" not in payload
    assert "global_verdict" not in payload
    assert payload["presentation_contract"]["global_compliance_verdict_emitted"] is False


@pytest.mark.parametrize("view", [ReportView.ENGINEERING, ReportView.AUDIT])
def test_all_mandatory_bound_contributions_appear_in_each_canonical_view(view):
    model = _executed_model((("C", "NO_DATA"), ("A", "PASS"), ("B", "FAIL")))
    projected = project_building_report_view(model, view).as_dict()["contributions"]
    assert [item["slice_id"] for item in projected] == [item.slice_id for item in model.contributions]


def test_mandatory_contribution_excluding_engineering_fails_closed():
    model = _executed_model(render_views_by_rule={"A": ("AUDIT",)})
    with pytest.raises(ReportProjectionIntegrityError, match="excludes canonical ENGINEERING"):
        project_building_report_view(model, ReportView.ENGINEERING)


def test_mandatory_contribution_excluding_audit_fails_closed():
    model = _executed_model(render_views_by_rule={"A": ("ENGINEERING",)})
    with pytest.raises(ReportProjectionIntegrityError, match="excludes canonical AUDIT"):
        project_building_report_view(model, ReportView.AUDIT)


def test_audit_view_exposes_exact_fcr_bindings_and_source_provenance():
    model = _executed_model()
    payload = project_building_report_view(model, ReportView.AUDIT).as_dict()
    assert payload["coverage_reconciliation"] == model.reconciliation.as_dict()
    assert payload["report_bindings"] == model.as_dict()["report_bindings"]
    assert payload["project_basis"] == model.project_basis.as_dict()
    assert payload["source_manifest"] == model.source_manifest.as_dict()
    assert payload["source_manifest"]["entries"][0]["fingerprint"] == "sha256:toy"
    assert payload["source_manifest"]["entries"][0]["locator"] == "TOY §1"


def test_engineering_view_does_not_invent_or_expand_audit_source_data():
    model = _executed_model()
    payload = project_building_report_view(model, ReportView.ENGINEERING).as_dict()
    assert "coverage_reconciliation" not in payload
    assert "report_bindings" not in payload
    assert "source_manifest" not in payload
    contribution = payload["contributions"][0]
    assert contribution["authority_refs"] == ["AUTH:TOY"]
    assert contribution["evidence_refs"] == ["EVIDENCE:TOY"]
    assert contribution["warnings"] == ["UPSTREAM_WARNING"]


def test_calculation_formula_values_and_governing_ref_are_copied_never_recalculated():
    model = _executed_model(calculation_rule="A")
    source = model.contributions[0].calculations[0].as_dict()
    for view in (ReportView.ENGINEERING, ReportView.AUDIT):
        payload = project_building_report_view(model, view).as_dict()
        assert payload["contributions"][0]["calculations"][0] == source
        assert payload["contributions"][0]["calculations"][0]["formula"] == "demand / capacity"
        assert payload["contributions"][0]["calculations"][0]["outputs"][0]["value"] == 0.625
        assert payload["contributions"][0]["calculations"][0]["governing_ref"] == "GOV:ROW:1"


def test_input_order_does_not_affect_projection_json():
    model = _executed_model((("A", "PASS"), ("B", "FAIL")))
    reversed_model = BuildingReportModel(
        report_id=model.report_id,
        project_id=model.project_id,
        title=model.title,
        reconciliation=model.reconciliation,
        project_basis=model.project_basis,
        source_manifest=model.source_manifest,
        contributions=tuple(reversed(model.contributions)),
        report_bindings=tuple(reversed(model.report_bindings)),
    )
    for view in (ReportView.ENGINEERING, ReportView.AUDIT):
        assert project_building_report_view(model, view).to_json() == project_building_report_view(
            reversed_model, view
        ).to_json()


def test_projection_does_not_mutate_building_report_model():
    model = _executed_model(calculation_rule="A")
    before = model.to_json()
    project_building_report_view(model, ReportView.ENGINEERING).to_json()
    project_building_report_view(model, ReportView.AUDIT).to_json()
    assert model.to_json() == before


def test_projection_contract_is_immutable():
    projection = project_building_report_view(_executed_model(), ReportView.ENGINEERING)
    with pytest.raises(FrozenInstanceError):
        projection.view = ReportView.AUDIT  # type: ignore[misc]


def test_projection_module_is_not_eagerly_imported_from_product_reports_package():
    root = Path(__file__).resolve().parents[2]
    package_init = (root / "tbdy_engine" / "product_reports" / "__init__.py").read_text(
        encoding="utf-8"
    )
    assert "building_report_projection" not in package_init


def test_executive_view_is_not_supported_by_ur_1b():
    model = _executed_model()
    with pytest.raises(ReportProjectionIntegrityError, match="supports only"):
        project_building_report_view(model, "EXECUTIVE")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        ReportView("EXECUTIVE")
