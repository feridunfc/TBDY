from __future__ import annotations

from dataclasses import dataclass

from tbdy_engine.checks.result import CheckResult, CheckStatus
from tbdy_engine.coverage.project_reconciliation import (
    AnalysisBasisRef,
    ProjectCoverageReconciler,
    ReportBindingRef,
    ReportContributionRef,
)
from tbdy_engine.product_reports.building_report_projection import (
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


def _contribution(
    rule: str,
    *,
    status: str,
    component_type: str | None,
    component_id: str | None,
    value: float,
    unit: str,
) -> SliceReportContribution:
    return SliceReportContribution(
        slice_id=f"slice:{rule}",
        title=f"Rule {rule}",
        contribution_kind="CHECK",
        status=status,
        component_type=component_type,
        component_id=component_id,
        summary_fields=(
            ReportField(
                key="resolved_value",
                label="Resolved value",
                value=value,
                unit=unit,
                role="RESULT",
            ),
        ),
        tables=(
            ReportTable(
                table_id=f"table:{rule}",
                title=f"Resolved {rule} rows",
                columns=("case", "value", "unit"),
                rows=({"case": "LC-EXACT", "value": value, "unit": unit},),
            ),
        ),
        calculations=(
            ReportCalculation(
                calculation_id=f"calc:{rule}",
                title=f"Resolved {rule} calculation",
                formula="upstream_formula_text",
                inputs=(ReportField("input", "Input", value, unit, "INPUT"),),
                outputs=(ReportField("output", "Output", value, unit, "RESULT"),),
                authority_refs=(f"AUTH:{rule}",),
                evidence_refs=(f"EVID:{rule}",),
                governing_ref=f"GOV:{rule}",
            ),
        ),
        authority_refs=(f"AUTH:{rule}",),
        evidence_refs=(f"EVID:{rule}",),
        warnings=(f"WARNING:{rule}",),
        render_views=("ENGINEERING", "AUDIT"),
    )


def _model(
    specs: tuple[tuple[str, str, str | None, str | None, float, str], ...],
    *,
    reanalysis_rules: tuple[str, ...] = (),
) -> BuildingReportModel:
    rules = tuple(item[0] for item in specs)
    registry = RegulatoryRegistry(checks=tuple(_check(rule) for rule in rules))
    program = RegulatoryCompiler.compile(
        registry,
        RegulatoryCompileInputs(
            rule_targets=tuple(
                RuleScopeTarget(
                    rule_id=RuleId(rule),
                    grain=Grain.COMPONENT,
                    scope_ref=f"SCOPE_{rule}",
                    applicability_input=_AppInput(),
                )
                for rule in rules
            )
        ),
    )
    ids = {
        item.rule_id.value: item
        for item in program.plan.compiled_rule_instances
    }
    formal_results = tuple(
        FormalResultRecord(
            instance_id=ids[rule],
            result=CheckResult(
                check_id=rule,
                component=ids[rule].scope_ref,
                component_type="toy",
                status=CheckStatus.FAIL if status == "FAIL" else CheckStatus.OK,
                code_ref="TOY",
            ),
        )
        for rule, status, *_ in specs
    )
    closure_outcomes = tuple(
        RuleClosureOutcome(
            compiled_record_ref=record.instance_id,
            execution_status=ClosureExecutionStatus.EXECUTED,
            formal_result_ref=f"{record.instance_id.value}:CheckResult",
        )
        for record in formal_results
    )
    contributions = tuple(
        _contribution(
            rule,
            status=status,
            component_type=component_type,
            component_id=component_id,
            value=value,
            unit=unit,
        )
        for rule, status, component_type, component_id, value, unit in specs
    )
    source_refs = tuple(f"{ids[rule].value}:CheckResult" for rule in rules)
    bindings = tuple(
        ReportBindingRef(source_ref, ReportContributionRef.from_contribution(contribution))
        for source_ref, contribution in zip(source_refs, contributions)
    )
    analysis_basis_refs = tuple(
        AnalysisBasisRef(
            instance_id=ids[rule],
            status=(
                AnalysisBasisStatus.REANALYSIS_REQUIRED
                if rule in reanalysis_rules
                else AnalysisBasisStatus.MATCH
            ),
            source_ref=f"ANALYSIS:{rule}",
        )
        for rule in rules
    )
    snapshot = RegulatoryStoreSnapshot(
        plan_identity=program.plan.plan_identity,
        regulatory_quantities=(),
        formal_results=formal_results,
        closure_outcomes=closure_outcomes,
        diagnostics=(),
    )
    reconciliation = ProjectCoverageReconciler.reconcile(
        compiled_program=program,
        store_snapshot=snapshot,
        report_contributions=contributions,
        report_bindings=bindings,
        required_report_source_refs=source_refs,
        analysis_basis_refs=analysis_basis_refs,
    )
    basis = ProjectBasisLedger(
        (
            ProjectBasisEntry(
                key="design_basis",
                label="Design basis",
                value="TOY",
                source_ids=("SRC:REG",),
            ),
        )
    )
    manifest = SourceManifest(
        (
            SourceManifestEntry(
                source_id="SRC:REG",
                source_kind=ReportSourceKind.REGULATORY_DOCUMENT,
                title="Toy source",
                fingerprint="sha256:exact",
                locator="TOY-LOCATOR",
                authority_refs=("AUTH:SOURCE",),
                evidence_refs=("EVID:SOURCE",),
            ),
        )
    )
    return BuildingReportModel(
        report_id="REPORT:UI",
        project_id="PROJECT:UI",
        title="UI-ready projection fixture",
        reconciliation=reconciliation,
        project_basis=basis,
        source_manifest=manifest,
        contributions=contributions,
        report_bindings=bindings,
    )


def test_coverage_accounting_survives_engineering_projection_exactly():
    model = _model(
        (
            ("A", "PASS", "column", "C1", 123.456789, "kN"),
            ("B", "FAIL", "beam", "B1", 98.7654321, "mm"),
        ),
        reanalysis_rules=("B",),
    )
    payload = project_building_report_view(model, ReportView.ENGINEERING).as_dict()

    assert payload["coverage_summary"] == model.reconciliation.as_dict()["summary"]
    assert payload["analysis_basis_summary"] == {
        "reanalysis_required_count": 1,
        "reanalysis_required_instance_ids": [
            model.reconciliation.reanalysis_required_instance_ids[0].value
        ],
    }
    assert "compliance_percentage" not in payload
    assert "project_compliant" not in payload


def test_status_facets_count_exact_statuses_without_changing_contributions():
    model = _model(
        (
            ("A", "PASS", "column", "C1", 1.0, "kN"),
            ("B", "FAIL", "column", "C1", 2.0, "kN"),
            ("C", "REANALYSIS_REQUIRED", "beam", "B2", 3.0, "kN"),
        )
    )
    payload = project_building_report_view(model, ReportView.ENGINEERING).as_dict()

    assert payload["status_facets"] == [
        {"status": "FAIL", "count": 1},
        {"status": "PASS", "count": 1},
        {"status": "REANALYSIS_REQUIRED", "count": 1},
    ]
    assert [item["status"] for item in payload["contributions"]] == [
        item.status for item in model.contributions
    ]
    assert "severity" not in payload


def test_component_facets_keep_project_level_contribution_with_none_identity():
    model = _model(
        (
            ("A", "PASS", "column", "C1", 1.0, "kN"),
            ("B", "PROVEN", None, None, 2.0, "unitless"),
        )
    )
    payload = project_building_report_view(model, ReportView.ENGINEERING).as_dict()

    project_level = next(
        item
        for item in payload["component_facets"]
        if item["component_type"] is None and item["component_id"] is None
    )
    assert project_level["contribution_count"] == 1
    assert any(item["component_id"] is None for item in payload["contributions"])


def test_stable_contribution_identity_and_binding_sources_survive_both_views():
    model = _model((("A", "PASS", "column", "C1", 1.0, "kN"),))
    source = model.contributions[0]
    canonical_ref = ReportContributionRef.from_contribution(source).value
    source_ref = model.report_bindings[0].source_ref

    for view in (ReportView.ENGINEERING, ReportView.AUDIT):
        contribution = project_building_report_view(model, view).as_dict()["contributions"][0]
        assert contribution["slice_id"] == source.slice_id
        assert contribution["contribution_kind"] == source.contribution_kind
        assert contribution["component_type"] == source.component_type
        assert contribution["component_id"] == source.component_id
        assert contribution["status"] == source.status
        assert contribution["contribution_ref"] == canonical_ref
        assert contribution["report_source_refs"] == [source_ref]


def test_projection_does_not_transform_engineering_values_units_or_calculations():
    model = _model((("A", "PASS", "column", "C1", 123.456789, "kN/m^2"),))
    source = model.contributions[0].as_dict()

    for view in (ReportView.ENGINEERING, ReportView.AUDIT):
        projected = project_building_report_view(model, view).as_dict()["contributions"][0]
        for key, value in source.items():
            assert projected[key] == value
        assert projected["summary_fields"][0]["value"] == 123.456789
        assert projected["summary_fields"][0]["unit"] == "kN/m^2"
        assert projected["calculations"][0]["formula"] == "upstream_formula_text"
        assert projected["calculations"][0]["governing_ref"] == "GOV:A"


def test_audit_projection_contains_exact_trace_needed_for_drill_down():
    model = _model((("A", "PASS", "column", "C1", 1.0, "kN"),))
    payload = project_building_report_view(model, ReportView.AUDIT).as_dict()

    assert payload["coverage_reconciliation"] == model.reconciliation.as_dict()
    assert payload["report_bindings"] == model.as_dict()["report_bindings"]
    assert payload["source_manifest"] == model.source_manifest.as_dict()
    assert payload["source_manifest"]["entries"][0]["fingerprint"] == "sha256:exact"
    assert payload["source_manifest"]["entries"][0]["locator"] == "TOY-LOCATOR"
    assert payload["analysis_basis_refs"][0]["source_ref"] == "ANALYSIS:A"
    assert payload["contributions"][0]["authority_refs"] == ["AUTH:A"]
    assert payload["contributions"][0]["evidence_refs"] == ["EVID:A"]


def test_engineering_projection_needs_no_source_manifest_internals_for_ordinary_content():
    model = _model((("A", "PASS", "column", "C1", 1.0, "kN"),))
    payload = project_building_report_view(model, ReportView.ENGINEERING).as_dict()

    assert "source_manifest" not in payload
    assert "coverage_reconciliation" not in payload
    assert "report_bindings" not in payload
    assert payload["contributions"][0]["summary_fields"]
    assert payload["contributions"][0]["report_source_refs"] == [
        model.report_bindings[0].source_ref
    ]


def test_projection_is_renderer_neutral_and_contains_no_frontend_artifacts():
    model = _model((("A", "PASS", "column", "C1", 1.0, "kN"),))
    payload = project_building_report_view(model, ReportView.ENGINEERING).as_dict()
    serialized = project_building_report_view(model, ReportView.ENGINEERING).to_json().lower()

    assert payload["presentation_contract"]["renderer_neutral"] is True
    assert "html" not in payload
    assert "css" not in payload
    assert "template" not in payload
    assert "javascript" not in payload
    assert "<html" not in serialized
    assert "<script" not in serialized
