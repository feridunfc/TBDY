from __future__ import annotations

from dataclasses import FrozenInstanceError, dataclass
from html import escape
from pathlib import Path
import re

import pytest

from tbdy_engine.checks.result import CheckResult, CheckStatus
from tbdy_engine.coverage.project_reconciliation import (
    AnalysisBasisRef,
    ProjectCoverageReconciler,
    ReportBindingRef,
    ReportContributionRef,
    canonical_closure_report_source_ref,
)
from tbdy_engine.product_reports.building_report_html import (
    HtmlRenderIntegrityError,
    HtmlRenderOptions,
    render_building_report_html,
)
from tbdy_engine.product_reports.building_report_projection import (
    BuildingReportProjection,
    ReportView,
    project_building_report_view,
)
from tbdy_engine.product_reports.report_presentation_selection import (
    ComponentFacetRef,
    ReportPresentationSelection,
    ReportPresentationSelectionError,
    default_presentation_selection,
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
                    applicability_input=_AppInput(
                        applicability.get(rule, ApplicabilityState.APPLIES)
                    ),
                )
                for rule in rules
            )
        ),
    )


def _id(program, rule: str) -> RuleInstanceId:
    return next(
        item for item in program.plan.compiled_rule_instances
        if item.rule_id == RuleId(rule)
    )


def _formal(instance_id: RuleInstanceId, status: CheckStatus) -> FormalResultRecord:
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


def _basis() -> ProjectBasisLedger:
    return ProjectBasisLedger(
        (
            ProjectBasisEntry(
                key="design_basis",
                label="Design basis",
                value="TOY",
                unit=None,
                source_ids=("SRC:REG",),
            ),
        )
    )


def _manifest(locator: str = "TOY §1") -> SourceManifest:
    return SourceManifest(
        (
            SourceManifestEntry(
                source_id="SRC:REG",
                source_kind=ReportSourceKind.REGULATORY_DOCUMENT,
                title="Toy regulatory source",
                fingerprint="sha256:toy",
                locator=locator,
                authority_refs=("AUTH:TOY",),
                evidence_refs=("EVIDENCE:TOY",),
            ),
        )
    )


def _contribution(
    rule: str,
    *,
    status: str,
    component_type: str | None = "toy",
    component_id: str | None | object = ...,
    title: str | None = None,
    formula: str | None = None,
    value: float = 123.4567890123,
    unit: str = "kN",
) -> SliceReportContribution:
    if component_id is ...:
        component_id = f"SCOPE_{rule}"
    calculations = ()
    if formula is not None:
        calculations = (
            ReportCalculation(
                calculation_id=f"calc:{rule}",
                title=f"Resolved {rule} calculation",
                formula=formula,
                inputs=(
                    ReportField("demand", "Demand", value, unit, "INPUT"),
                ),
                outputs=(
                    ReportField("ratio", "Ratio", 0.625, None, "RESULT"),
                ),
                authority_refs=("AUTH:TOY",),
                evidence_refs=("EVIDENCE:TOY",),
                governing_ref="GOV:ROW:1",
            ),
        )
    return SliceReportContribution(
        slice_id=f"slice:{rule}",
        title=title or f"Rule {rule}",
        contribution_kind="CHECK",
        status=status,
        component_type=component_type,
        component_id=component_id,  # type: ignore[arg-type]
        summary_fields=(
            ReportField("resolved", "Resolved value", value, unit, "RESULT"),
        ),
        tables=(
            ReportTable(
                table_id=f"table:{rule}",
                title=f"Resolved {rule} rows",
                columns=("case", "value"),
                rows=({"case": "LC1", "value": value},),
            ),
        ),
        calculations=calculations,
        authority_refs=("AUTH:TOY",),
        evidence_refs=("EVIDENCE:TOY",),
        warnings=("UPSTREAM_WARNING",),
        render_views=("EXECUTIVE", "ENGINEERING", "AUDIT"),
    )


def _model(
    statuses: tuple[tuple[str, str], ...] = (("A", "PASS"),),
    *,
    component_ids: dict[str, str | None] | None = None,
    analysis: dict[str, AnalysisBasisStatus] | None = None,
    formula_rule: str | None = None,
    formula: str = "1 / 0 SHOULD_NOT_EVALUATE",
    title: str = "Unified structural assessment",
    locator: str = "TOY §1",
    value: float = 123.4567890123,
    unit: str = "kN",
) -> BuildingReportModel:
    component_ids = component_ids or {}
    analysis = analysis or {}
    rules = tuple(rule for rule, _ in statuses)
    program = _program(*rules)
    records = tuple(
        _formal(
            _id(program, rule),
            CheckStatus.FAIL if status == "FAIL" else CheckStatus.OK,
        )
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
            component_id=component_ids.get(rule, f"SCOPE_{rule}"),
            formula=formula if rule == formula_rule else None,
            title=(title if len(statuses) == 1 else None),
            value=value,
            unit=unit,
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
            status=analysis.get(rule, AnalysisBasisStatus.MATCH),
            source_ref=f"ANALYSIS_BASIS:{rule}",
        )
        for rule in rules
    )
    reconciliation = ProjectCoverageReconciler.reconcile(
        compiled_program=program,
        store_snapshot=_snapshot(
            program,
            formal_results=records,
            closure_outcomes=closures,
        ),
        report_contributions=contributions,
        required_report_source_refs=refs,
        report_bindings=bindings,
        analysis_basis_refs=basis_refs,
    )
    return BuildingReportModel(
        report_id="REPORT:1",
        project_id="PROJECT:1",
        title=title,
        reconciliation=reconciliation,
        project_basis=_basis(),
        source_manifest=_manifest(locator),
        contributions=contributions,
        report_bindings=bindings,
    )


def _resultless(status: ClosureExecutionStatus, contribution_status: str):
    program = _program("A")
    instance_id = _id(program, "A")
    source_ref = canonical_closure_report_source_ref(instance_id)
    contribution = _contribution("A", status=contribution_status)
    binding = ReportBindingRef(
        source_ref,
        ReportContributionRef.from_contribution(contribution),
    )
    reconciliation = ProjectCoverageReconciler.reconcile(
        compiled_program=program,
        store_snapshot=_snapshot(
            program,
            closure_outcomes=(RuleClosureOutcome(instance_id, status),),
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
    program = _program(
        "A",
        applicability={"A": ApplicabilityState.PROVEN_NOT_APPLICABLE},
    )
    instance_id = _id(program, "A")
    source_ref = canonical_closure_report_source_ref(instance_id)
    contribution = _contribution("A", status="OUT_OF_SCOPE")
    binding = ReportBindingRef(
        source_ref,
        ReportContributionRef.from_contribution(contribution),
    )
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


def _projection(model: BuildingReportModel, view: ReportView):
    return project_building_report_view(model, view)


def _result_card_refs(html: str) -> list[str]:
    return re.findall(r'<article[^>]+data-contribution-ref="([^"]+)"', html)


def test_engineering_projection_renders_standalone_html():
    html = render_building_report_html(_projection(_model(), ReportView.ENGINEERING))
    assert html.startswith("<!doctype html><html")
    assert html.endswith("</html>\n")
    assert "<style>" in html


def test_audit_projection_renders_standalone_html():
    html = render_building_report_html(_projection(_model(), ReportView.AUDIT))
    assert 'view</strong> <code>AUDIT</code>' in html
    assert "SourceManifest" in html


def test_same_input_is_byte_identical():
    projection = _projection(_model((("A", "PASS"), ("B", "FAIL"))), ReportView.ENGINEERING)
    assert render_building_report_html(projection) == render_building_report_html(projection)


def test_equivalent_model_input_order_does_not_change_html():
    model = _model((("A", "PASS"), ("B", "FAIL")))
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
    assert render_building_report_html(_projection(model, ReportView.AUDIT)) == render_building_report_html(
        _projection(reversed_model, ReportView.AUDIT)
    )


def test_no_current_timestamp_or_random_uuid_is_emitted():
    html = render_building_report_html(_projection(_model(), ReportView.ENGINEERING))
    assert re.search(r"20\d\d-\d\d-\d\dT\d\d:\d\d", html) is None
    assert re.search(r"\b[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-", html) is None


def test_all_canonical_contributions_present_by_default():
    projection = _projection(_model((("A", "PASS"), ("B", "FAIL"), ("C", "PASS"))), ReportView.ENGINEERING)
    assert _result_card_refs(render_building_report_html(projection)) == [
        item["contribution_ref"] for item in projection.as_dict()["contributions"]
    ]


def test_contribution_ref_survives_dom_identity_and_data_attribute():
    projection = _projection(_model(), ReportView.ENGINEERING)
    ref = projection.as_dict()["contributions"][0]["contribution_ref"]
    html = render_building_report_html(projection)
    assert f'data-contribution-ref="{escape(ref, quote=True)}"' in html
    assert re.search(r'id="contribution-[0-9a-f]{20}"', html)


def test_report_source_refs_survive_rendering():
    projection = _projection(_model(), ReportView.ENGINEERING)
    source_ref = projection.as_dict()["contributions"][0]["report_source_refs"][0]
    assert escape(source_ref, quote=True) in render_building_report_html(projection)


def test_project_level_contribution_remains_visible():
    projection = _projection(_model(component_ids={"A": None}), ReportView.ENGINEERING)
    html = render_building_report_html(projection)
    assert 'data-project-level="true"' in html
    assert "PROJECT / GLOBAL" in html


@pytest.mark.parametrize("status", ["PASS", "FAIL", "REANALYSIS_REQUIRED"])
def test_executed_status_text_survives_exactly(status):
    analysis = {"A": AnalysisBasisStatus.REANALYSIS_REQUIRED} if status == "REANALYSIS_REQUIRED" else {}
    projection = _projection(_model((("A", status),), analysis=analysis), ReportView.ENGINEERING)
    html = render_building_report_html(projection)
    assert f'data-status="{status}"' in html
    assert f">{status}</span>" in html


@pytest.mark.parametrize(
    ("closure", "status"),
    [
        (ClosureExecutionStatus.BLOCKED, "BLOCKED"),
        (ClosureExecutionStatus.NO_DATA, "NO_DATA"),
    ],
)
def test_resultless_status_survives_exactly(closure, status):
    html = render_building_report_html(
        _projection(_resultless(closure, status), ReportView.ENGINEERING)
    )
    assert f'data-status="{status}"' in html


def test_proven_not_applicable_remains_explicit_not_pass():
    html = render_building_report_html(_projection(_pna_model(), ReportView.ENGINEERING))
    assert 'data-status="OUT_OF_SCOPE"' in html
    assert "proven_not_applicable_count" in html


def test_renderer_generates_no_overall_pass_or_project_compliant_claim():
    html = render_building_report_html(_projection(_model(), ReportView.ENGINEERING))
    assert "overall PASS" not in html
    assert "project compliant = true" not in html
    assert "92% compliant" not in html


def test_coverage_values_are_projection_values():
    projection = _projection(_resultless(ClosureExecutionStatus.BLOCKED, "BLOCKED"), ReportView.ENGINEERING)
    summary = projection.as_dict()["coverage_summary"]
    html = render_building_report_html(projection)
    for key in (
        "expected_mandatory_instance_count",
        "executed_result_count",
        "blocked_count",
        "unresolved_count",
    ):
        assert f'data-coverage-key="{key}"' in html
        assert f'data-canonical-value="{summary[key]}' in html


def test_coverage_is_not_recomputed_from_selected_rows():
    projection = _projection(_model((("A", "PASS"), ("B", "FAIL"))), ReportView.ENGINEERING)
    selection = ReportPresentationSelection(statuses=("FAIL",))
    html = render_building_report_html(projection, selection=selection)
    assert len(_result_card_refs(html)) == 1
    assert 'data-coverage-key="expected_mandatory_instance_count"' in html
    assert 'data-canonical-value="2"' in html


def test_filtered_presentation_declares_scope_and_active_selection():
    projection = _projection(_model((("A", "PASS"), ("B", "FAIL"))), ReportView.ENGINEERING)
    html = render_building_report_html(
        projection,
        selection=ReportPresentationSelection(statuses=("FAIL",)),
    )
    assert "Presentation selection/filter applied." in html
    assert "Assessment scope ≠ presentation scope" in html
    assert "FILTERED / SELECTED PRESENTATION" in html


def test_presentation_selection_does_not_mutate_projection_or_fcr():
    projection = _projection(_model((("A", "PASS"), ("B", "FAIL"))), ReportView.ENGINEERING)
    before = projection.to_json()
    render_building_report_html(
        projection,
        selection=ReportPresentationSelection(statuses=("FAIL",)),
    )
    assert projection.to_json() == before


def test_unknown_contribution_ref_selection_fails_closed():
    projection = _projection(_model(), ReportView.ENGINEERING)
    with pytest.raises(ReportPresentationSelectionError, match="unknown exact contribution_ref"):
        render_building_report_html(
            projection,
            selection=ReportPresentationSelection(contribution_refs=("missing-ref",)),
        )


def test_unknown_component_selection_fails_closed():
    projection = _projection(_model(), ReportView.ENGINEERING)
    with pytest.raises(ReportPresentationSelectionError, match="unknown exact component"):
        render_building_report_html(
            projection,
            selection=ReportPresentationSelection(
                component_refs=(ComponentFacetRef("toy", "UNKNOWN"),)
            ),
        )


def test_exact_component_selection_uses_canonical_pair():
    projection = _projection(_model((("A", "PASS"), ("B", "FAIL"))), ReportView.ENGINEERING)
    selection = ReportPresentationSelection(
        component_refs=(ComponentFacetRef("toy", "SCOPE_B"),)
    )
    html = render_building_report_html(projection, selection=selection)
    assert len(_result_card_refs(html)) == 1
    assert "SCOPE_B" in html


def test_engineering_does_not_require_source_manifest_internals():
    html = render_building_report_html(_projection(_model(), ReportView.ENGINEERING))
    assert "sha256:toy" not in html
    assert "TOY §1" not in html


def test_engineering_audit_selection_fails_closed():
    projection = _projection(_model(), ReportView.ENGINEERING)
    with pytest.raises(ReportPresentationSelectionError, match="requires ReportView.AUDIT"):
        render_building_report_html(
            projection,
            selection=ReportPresentationSelection(include_evidence=True),
        )


def test_audit_exposes_fingerprint_and_locator():
    html = render_building_report_html(_projection(_model(), ReportView.AUDIT))
    assert "sha256:toy" in html
    assert "TOY §1" in html


def test_formula_text_is_rendered_without_evaluation():
    projection = _projection(_model(formula_rule="A"), ReportView.ENGINEERING)
    html = render_building_report_html(projection)
    assert "1 / 0 SHOULD_NOT_EVALUATE" in html
    assert "0.625" in html


def test_engineering_numeric_value_is_lossless():
    value = 123.4567890123
    html = render_building_report_html(
        _projection(_model(value=value), ReportView.ENGINEERING)
    )
    assert str(value) in html


def test_units_are_unchanged():
    html = render_building_report_html(
        _projection(_model(unit="kN·m"), ReportView.ENGINEERING)
    )
    assert "kN·m" in html


def test_governing_ref_is_copied_exactly():
    html = render_building_report_html(
        _projection(_model(formula_rule="A"), ReportView.ENGINEERING)
    )
    assert "GOV:ROW:1" in html


def test_projected_html_special_characters_are_escaped():
    title = 'Unsafe <tag> & "quoted"'
    html = render_building_report_html(
        _projection(_model(title=title), ReportView.ENGINEERING)
    )
    assert "Unsafe &lt;tag&gt; &amp; &quot;quoted&quot;" in html
    assert "Unsafe <tag>" not in html


def test_script_injection_text_is_inert_in_html_and_json():
    title = '</script><script>alert("owned")</script>'
    html = render_building_report_html(
        _projection(_model(title=title), ReportView.ENGINEERING)
    )
    assert title not in html
    assert "\\u003c/script\\u003e\\u003cscript\\u003ealert" in html
    assert "&lt;/script&gt;&lt;script&gt;alert" in html


@pytest.mark.parametrize(
    ("section_id", "label"),
    [
        ("overview", "Overview"),
        ("coverage", "Coverage"),
        ("results", "Results"),
        ("components", "Components"),
        ("evidence-audit", "Evidence / Audit"),
        ("actions", "Actions"),
        ("reports", "Reports"),
    ],
)
def test_primary_ui_section_and_navigation_exist(section_id, label):
    html = render_building_report_html(_projection(_model(), ReportView.ENGINEERING))
    assert f'id="{section_id}"' in html
    assert f'href="#{section_id}">{label}</a>' in html


def test_client_filter_metadata_uses_exact_canonical_facets():
    projection = _projection(_model((("A", "PASS"), ("B", "FAIL"))), ReportView.ENGINEERING)
    html = render_building_report_html(projection)
    for facet in projection.as_dict()["status_facets"]:
        assert f'value="{facet["status"]}"' in html
    assert 'data-status="PASS"' in html
    assert 'data-status="FAIL"' in html
    assert 'data-kind="CHECK"' in html


def test_no_fuzzy_engineering_rule_family_inference_is_coded():
    source = Path(__file__).resolve().parents[2] / "tbdy_engine" / "product_reports" / "building_report_html.py"
    text = source.read_text(encoding="utf-8").lower()
    for forbidden in ("column shear", "beam geometry", "axial family", "drift family", "irregularity family"):
        assert forbidden not in text


def test_renderer_imports_no_etabs_provider_or_regulatory_engine():
    source = Path(__file__).resolve().parents[2] / "tbdy_engine" / "product_reports" / "building_report_html.py"
    text = source.read_text(encoding="utf-8")
    assert "etabs" not in "\n".join(
        line for line in text.lower().splitlines() if line.startswith("from ") or line.startswith("import ")
    )
    assert "provider" not in text.lower().split("class HtmlRenderIntegrityError", 1)[0]
    assert "RegulatoryEngine" not in text


def test_print_stylesheet_and_a4_page_rule_exist():
    html = render_building_report_html(_projection(_model(), ReportView.ENGINEERING))
    assert "@media print" in html
    assert "@page{size:A4" in html
    assert "overflow-wrap:anywhere" in html


def test_long_source_locator_and_ids_are_render_safe():
    locator = "LOC:" + ("X" * 500)
    html = render_building_report_html(_projection(_model(locator=locator), ReportView.AUDIT))
    assert locator in html
    assert "overflow-wrap:anywhere" in html


def test_engineering_and_audit_use_same_renderer_function():
    engineering = render_building_report_html(_projection(_model(), ReportView.ENGINEERING))
    audit = render_building_report_html(_projection(_model(), ReportView.AUDIT))
    assert "Unified Engineering Review" in engineering
    assert "Unified Engineering Review" in audit
    assert engineering != audit


def test_actions_view_truthful_empty_state_without_action_register():
    html = render_building_report_html(_projection(_model(), ReportView.ENGINEERING))
    assert "No canonical action records are available in this projection." in html


def test_report_integrity_status_is_visibly_rendered():
    html = render_building_report_html(_projection(_model(), ReportView.ENGINEERING))
    assert "report_integrity_status: RECONCILED" in html


def test_nonreconciled_integrity_fails_closed(monkeypatch):
    projection = _projection(_model(), ReportView.ENGINEERING)
    monkeypatch.setattr(
        BuildingReportProjection,
        "report_integrity_status",
        property(lambda self: "BROKEN"),
    )
    with pytest.raises(HtmlRenderIntegrityError, match="RECONCILED"):
        render_building_report_html(projection)


def test_reanalysis_required_warning_is_prominent_and_exact():
    projection = _projection(
        _model(
            (("A", "REANALYSIS_REQUIRED"),),
            analysis={"A": AnalysisBasisStatus.REANALYSIS_REQUIRED},
        ),
        ReportView.ENGINEERING,
    )
    html = render_building_report_html(projection)
    assert "Analysis basis contains 1 REANALYSIS_REQUIRED instance(s)." in html
    assert "model fails" not in html


def test_inert_projection_json_is_deterministic_and_present():
    projection = _projection(_model(), ReportView.ENGINEERING)
    html = render_building_report_html(projection)
    assert 'id="canonical-projection-json" type="application/json"' in html
    assert html == render_building_report_html(projection)


def test_options_can_disable_json_and_interactivity_without_changing_truth():
    projection = _projection(_model(), ReportView.ENGINEERING)
    html = render_building_report_html(
        projection,
        options=HtmlRenderOptions(
            include_projection_json=False,
            enable_interactivity=False,
        ),
    )
    assert "canonical-projection-json" not in html
    assert "(function(){" not in html
    assert 'data-status="PASS"' in html


def test_html_render_options_are_immutable():
    options = HtmlRenderOptions()
    with pytest.raises(FrozenInstanceError):
        options.enable_interactivity = False  # type: ignore[misc]


def test_default_engineering_selection_has_all_engineering_sections_and_no_audit_payload():
    selection = default_presentation_selection(
        _projection(_model(), ReportView.ENGINEERING)
    )
    assert selection.include_overview
    assert selection.include_coverage
    assert selection.include_results
    assert selection.include_components
    assert selection.include_actions
    assert not selection.include_evidence


def test_default_audit_selection_includes_audit_trace():
    selection = default_presentation_selection(_projection(_model(), ReportView.AUDIT))
    assert selection.include_evidence


def test_selection_section_exclusion_is_explicit_not_silent():
    projection = _projection(_model(), ReportView.ENGINEERING)
    html = render_building_report_html(
        projection,
        selection=ReportPresentationSelection(include_components=False),
    )
    assert 'id="components"' in html
    assert 'data-presentation-state="excluded"' in html
    assert "Canonical assessment and coverage remain unchanged." in html


def test_renderer_accepts_only_building_report_projection():
    with pytest.raises(TypeError, match="BuildingReportProjection"):
        render_building_report_html({})  # type: ignore[arg-type]


def test_no_eager_product_reports_import_cycle_is_introduced():
    root = Path(__file__).resolve().parents[2]
    package_init = (root / "tbdy_engine" / "product_reports" / "__init__.py").read_text(
        encoding="utf-8"
    )
    assert "building_report_html" not in package_init
    assert "report_presentation_selection" not in package_init
