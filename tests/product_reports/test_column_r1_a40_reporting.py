from __future__ import annotations

from dataclasses import dataclass
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import SimpleNamespace
import sys

from tbdy_engine.application.column_execution import ColumnDomainArtifact
from tbdy_engine.application.contracts import ColumnExecutionRequest, ProjectExecutionRequest
import tbdy_engine.application.project_execution as project_execution
import tbdy_engine.product_reports.building_report_package as package_module
from tbdy_engine.checks.result import CheckResult
from tbdy_engine.coverage.column_denominator import (
    ColumnDenominatorLeafIdentity,
    ColumnExpectedLeaf,
    ColumnLeafApplicability,
    ColumnLeafOutcome,
    ColumnLeafOutcomeStatus,
    SupportedColumnDenominator,
    canonical_column_leaf_source_ref,
)
from tbdy_engine.coverage.project_reconciliation import (
    ProjectCoverageReconciler,
)
from tbdy_engine.product_reports.building_report_package import (
    build_building_report_package,
    build_report_delivery_artifacts,
    verify_building_report_package,
)
from tbdy_engine.product_reports.building_report_projection import (
    ReportView,
    project_building_report_view,
)
from tbdy_engine.product_reports.report_artifact import ReportArtifact
from tbdy_engine.product_reports.unified_building_report import (
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
    Grain,
    RuleId,
)
from tbdy_engine.regulatory.kernel import (
    AnalysisBasisStatus,
    RegulatoryCompileInputs,
    RegulatoryCompiler,
    RegulatoryStoreSnapshot,
    RuleScopeTarget,
)
from tbdy_engine.regulatory.registry import RegulatoryRegistry


COMPONENT = "Story1:C1:1"
MODEL = "model:a40"
EPOCH = "epoch:a40"


@dataclass(frozen=True, slots=True)
class _AppInput:
    state: ApplicabilityState = ApplicabilityState.PROVEN_NOT_APPLICABLE


def _app(value: _AppInput) -> ApplicabilityState:
    return value.state


def _program_and_snapshot():
    rule = "F0_A40_SENTINEL"
    registry = RegulatoryRegistry(
        checks=(
            CheckSpec(
                rule_id=RuleId(rule),
                code_refs=("TEST",),
                rule_version="v1",
                formal_result_type=CheckResult,
                dependencies=(),
                applicability=ApplicabilityBinding("app:a40", _AppInput, _app),
                evaluator=CheckEvaluatorBinding("eval:a40", object, lambda _: None),
            ),
        )
    )
    program = RegulatoryCompiler.compile(
        registry,
        RegulatoryCompileInputs(
            rule_targets=(
                RuleScopeTarget(
                    rule_id=RuleId(rule),
                    grain=Grain.COMPONENT,
                    scope_ref="A40:F0",
                    mandatory=True,
                    applicability_input=_AppInput(),
                ),
            )
        ),
    )
    snapshot = RegulatoryStoreSnapshot(
        plan_identity=program.plan.plan_identity,
        regulatory_quantities=(),
        formal_results=(),
        closure_outcomes=(),
        diagnostics=(),
    )
    return program, snapshot


def _leaf(
    key: str,
    status: ColumnLeafOutcomeStatus,
    *,
    applicability: ColumnLeafApplicability = ColumnLeafApplicability.MANDATORY,
    canonical_artifact_ref: str | None = None,
    evidence_refs: tuple[str, ...] = (),
    blocker_refs: tuple[str, ...] = (),
    analysis_basis_ref: str | None = None,
    dependency_refs: tuple[str, ...] = (),
    deferred_owner: str | None = None,
    generation_ref: str | None = None,
):
    identity = ColumnDenominatorLeafIdentity.build(
        component_id=COMPONENT,
        leaf_key=key,
        model_fingerprint=MODEL,
        evidence_epoch_id=EPOCH,
        scope_ref=COMPONENT,
        generation_ref=generation_ref,
    )
    expected = ColumnExpectedLeaf(
        identity=identity,
        family="CROSS_DOMAIN" if deferred_owner is not None else key,
        applicability=applicability,
    )
    outcome = ColumnLeafOutcome(
        identity=identity,
        status=status,
        source_ref=canonical_column_leaf_source_ref(identity),
        canonical_artifact_ref=canonical_artifact_ref,
        evidence_refs=evidence_refs,
        blocker_refs=blocker_refs,
        analysis_basis_ref=analysis_basis_ref,
        dependency_refs=dependency_refs,
        deferred_owner=deferred_owner,
    )
    return expected, outcome


def _denominator() -> SupportedColumnDenominator:
    analysis = "analysis-result:sha256:" + "1" * 64
    design_state = "design-state:sha256:" + "2" * 64
    design_result = "design-result:sha256:" + "3" * 64
    design_generation = "design-generation:sha256:" + "4" * 64
    selected_rebar = "engine-selected-rebar:sha256:" + "5" * 64
    design_basis = "column-design-basis-binding:sha256:" + "6" * 64

    rows = (
        _leaf(
            "B5_ANALYSIS_RESULT_GENERATION",
            ColumnLeafOutcomeStatus.EXECUTED_PASS,
            canonical_artifact_ref=analysis,
            evidence_refs=("B5:EVIDENCE",),
            generation_ref=analysis,
        ),
        _leaf(
            "DESIGN_STATE_IDENTITY",
            ColumnLeafOutcomeStatus.EXECUTED_PASS,
            canonical_artifact_ref=design_state,
            evidence_refs=(analysis, "B6:STATE:EVIDENCE"),
            generation_ref=analysis,
        ),
        _leaf(
            "DESIGN_RESULT_IDENTITY_LINEAGE",
            ColumnLeafOutcomeStatus.EXECUTED_PASS,
            canonical_artifact_ref=design_result,
            evidence_refs=("design-lineage:qualification:exact", design_generation),
            generation_ref=design_generation,
        ),
        _leaf(
            "FACTUAL_MATERIAL_DESIGN_BASIS",
            ColumnLeafOutcomeStatus.EXECUTED_PASS,
            canonical_artifact_ref=design_basis,
            evidence_refs=("DESIGN_BASIS:EVIDENCE",),
        ),
        _leaf(
            "ENGINE_SELECTED_REBAR",
            ColumnLeafOutcomeStatus.EXECUTED_PASS,
            canonical_artifact_ref=selected_rebar,
            evidence_refs=("REBAR:EVIDENCE",),
        ),
        _leaf(
            "TRANSVERSE_CONFINEMENT",
            ColumnLeafOutcomeStatus.EXECUTED_FAIL,
            evidence_refs=("TRANSVERSE:FINAL_CAGE:EVIDENCE",),
        ),
        _leaf(
            "NO_DATA_LEAF",
            ColumnLeafOutcomeStatus.NO_DATA,
            blocker_refs=("MISSING:FACT",),
        ),
        _leaf(
            "REANALYSIS_LEAF",
            ColumnLeafOutcomeStatus.REANALYSIS_REQUIRED,
            blocker_refs=("REANALYSIS:REQUIRED",),
            analysis_basis_ref=AnalysisBasisStatus.REANALYSIS_REQUIRED.value,
        ),
        _leaf(
            "PNA_LEAF",
            ColumnLeafOutcomeStatus.PROVEN_NOT_APPLICABLE,
            applicability=ColumnLeafApplicability.PROVEN_NOT_APPLICABLE,
        ),
        _leaf(
            "SCWB",
            ColumnLeafOutcomeStatus.EXPLICIT_UNRESOLVED,
            blocker_refs=("BEAM:AUTHORITY:NOT_AVAILABLE",),
            dependency_refs=("CANONICAL_BEAM_CAPACITY_AUTHORITY",),
            deferred_owner="BEAM_DOMAIN",
        ),
    )
    return SupportedColumnDenominator(
        tuple(item[0] for item in rows),
        tuple(item[1] for item in rows),
    )


def _synthetic_model():
    # Bounded A40 fixture: do not fabricate a typed FND2 readiness binding
    # for the toy sentinel. The public-root test below covers the real
    # _build_closure_and_report production path.
    program, snapshot = _program_and_snapshot()
    column = ColumnDomainArtifact(
        component_id=COMPONENT,
        model_fingerprint=MODEL,
        evidence_epoch_id=EPOCH,
        status="BLOCKED",
        blockers=("A40:SYNTHETIC:SUMMARY",),
        fnd_col_2_program=program,
        fnd_col_2_execution=SimpleNamespace(readiness=None, snapshot=snapshot),
    )
    request = ProjectExecutionRequest(
        project_id="project:a40",
        report_id="report:a40",
        title="Column-R1 A40",
        column=ColumnExecutionRequest(COMPONENT),
    )
    denominator = _denominator()

    summary_contribution = project_execution._report_contribution(column)
    summary_binding = project_execution._report_binding(
        column,
        summary_contribution,
    )
    leaf_contributions, leaf_bindings = (
        project_execution._column_leaf_report_population(denominator)
    )
    contributions = (summary_contribution, *leaf_contributions)
    bindings = (summary_binding, *leaf_bindings)

    reconciliation = ProjectCoverageReconciler.reconcile(
        compiled_program=program,
        store_snapshot=snapshot,
        report_contributions=contributions,
        required_report_source_refs=tuple(
            item.source_ref for item in bindings
        ),
        report_bindings=bindings,
        analysis_basis_refs=None,
        column_denominator=denominator,
    )

    basis = ProjectBasisLedger(
        (
            ProjectBasisEntry(
                key="execution_mode",
                label="Execution mode",
                value="OFFLINE_TEST",
                source_ids=("source:a40",),
            ),
            ProjectBasisEntry(
                key="model_fingerprint",
                label="Source model fingerprint",
                value=MODEL,
                source_ids=("source:a40",),
            ),
            ProjectBasisEntry(
                key="evidence_epoch_id",
                label="Factual acquisition epoch",
                value=EPOCH,
                source_ids=("source:a40",),
            ),
        )
    )
    manifest = SourceManifest(
        (
            SourceManifestEntry(
                source_id="source:a40",
                source_kind=ReportSourceKind.ETABS_MODEL,
                title="A40 source",
                fingerprint=MODEL,
            ),
        )
    )
    model = BuildingReportModel(
        report_id=request.report_id,
        project_id=request.project_id,
        title=request.title,
        reconciliation=reconciliation,
        project_basis=basis,
        source_manifest=manifest,
        contributions=contributions,
        report_bindings=bindings,
    )
    return denominator, reconciliation, model


def _fields(contribution):
    return {item.key: item.value for item in contribution.summary_fields}


def test_summary_contribution_exposes_selected_reinforcement_and_final_cage_verbatim():
    from decimal import Decimal

    selected_candidate = SimpleNamespace(
        bar_diameter_mm=20.0,
        n_bars_dir2=4,
        n_bars_dir3=5,
        rho=0.01875,
    )
    selected_rebar = SimpleNamespace(
        selected_rebar_ref="engine-selected-rebar:sha256:" + "7" * 64,
        candidate_id="candidate:a40:selected",
        candidate_geometry_fingerprint="candidate-geometry:sha256:" + "8" * 64,
        selected_candidate=selected_candidate,
        as_total_mm2=Decimal("2450.125"),
        rank=1,
        material_context_ref="material-context:a40",
        provenance_refs=("rebar:provenance:a40",),
        required_area_decision_ids=("area-decision:a40",),
        pmm_decision_ids=("pmm-decision:a40",),
        requirement_ids=("requirement:a40",),
        demand_state_ids=("demand-state:a40",),
    )
    final_cage = SimpleNamespace(
        authority="REVIEWED_PROJECT_FINAL_TRANSVERSE_CAGE",
        semantic_role="USER_PROVIDED_REBAR",
        tie_size_name="T10",
        number_2_dir_tie_bars=3,
        number_3_dir_tie_bars=4,
        confinement_spacing_mm=100.0,
        middle_spacing_mm=150.0,
        shear_spacing_mm=100.0,
        provided_confinement_region_length_mm=900.0,
        horizontal_leg_spacing_dir2_mm=120.0,
        horizontal_leg_spacing_dir3_mm=110.0,
        restrained_longitudinal_bar_spacing_mm=180.0,
        review_refs=("final-cage:review:a40",),
    )
    column = ColumnDomainArtifact(
        component_id=COMPONENT,
        model_fingerprint=MODEL,
        evidence_epoch_id=EPOCH,
        status="READY",
        blockers=(),
        fnd_col_2_execution=SimpleNamespace(readiness=None),
        longitudinal_selection=SimpleNamespace(
            status="SELECTED",
            selected_rebar=selected_rebar,
        ),
        final_transverse_cage=final_cage,
    )

    contribution = project_execution._report_contribution(column)
    fields = _fields(contribution)

    assert fields["selected_rebar_ref"] == selected_rebar.selected_rebar_ref
    assert fields["selected_rebar_candidate_id"] == selected_rebar.candidate_id
    assert (
        fields["selected_rebar_geometry_fingerprint"]
        == selected_rebar.candidate_geometry_fingerprint
    )
    assert fields["selected_rebar_as_total_mm2"] == "2450.125"
    assert fields["selected_rebar_rank"] == 1
    assert fields["selected_rebar_bar_diameter_mm"] == 20.0
    assert fields["selected_rebar_n_bars_dir2"] == 4
    assert fields["selected_rebar_n_bars_dir3"] == 5
    assert fields["selected_rebar_rho"] == 0.01875

    assert (
        fields["final_transverse_cage_authority"]
        == "REVIEWED_PROJECT_FINAL_TRANSVERSE_CAGE"
    )
    assert fields["final_transverse_cage_semantic_role"] == "USER_PROVIDED_REBAR"
    assert fields["final_transverse_tie_size_name"] == "T10"
    assert fields["final_transverse_number_2_dir_tie_bars"] == 3
    assert fields["final_transverse_number_3_dir_tie_bars"] == 4
    assert fields["final_transverse_confinement_spacing_mm"] == 100.0
    assert fields["final_transverse_middle_spacing_mm"] == 150.0
    assert fields["final_transverse_shear_spacing_mm"] == 100.0
    assert fields["final_transverse_confinement_region_length_mm"] == 900.0
    assert (
        fields["final_transverse_horizontal_leg_spacing_dir2_mm"]
        == 120.0
    )
    assert (
        fields["final_transverse_horizontal_leg_spacing_dir3_mm"]
        == 110.0
    )
    assert (
        fields["final_transverse_restrained_longitudinal_bar_spacing_mm"]
        == 180.0
    )

    expected_evidence = {
        selected_rebar.selected_rebar_ref,
        "material-context:a40",
        "rebar:provenance:a40",
        "area-decision:a40",
        "pmm-decision:a40",
        "requirement:a40",
        "demand-state:a40",
        "final-cage:review:a40",
    }
    assert expected_evidence.issubset(set(contribution.evidence_refs))


def test_full_column_denominator_is_exactly_bound_into_existing_building_report_model():
    denominator, reconciliation, model = _synthetic_model()

    assert reconciliation.report_reconciled is True
    assert reconciliation.column_population_reconciled is True
    assert len(model.contributions) == denominator.expected_instance_count + 1
    assert len(model.report_bindings) == denominator.expected_instance_count + 1

    mandatory = set(mandatory_report_source_refs(reconciliation))
    assert set(reconciliation.required_report_source_refs) == mandatory
    assert {item.source_ref for item in model.report_bindings} == mandatory
    assert set(denominator.required_report_source_refs).issubset(mandatory)


def test_column_leaf_reporting_preserves_exact_truth_and_does_not_recalculate():
    denominator, _, model = _synthetic_model()
    leaf_contributions = {
        _fields(item)["column_leaf_key"]: item
        for item in model.contributions
        if item.slice_id.startswith("column-r1:leaf:")
    }
    assert set(leaf_contributions) == {
        item.identity.leaf_key for item in denominator.outcomes
    }

    expected_status = {
        "B5_ANALYSIS_RESULT_GENERATION": "PASS",
        "DESIGN_STATE_IDENTITY": "PASS",
        "DESIGN_RESULT_IDENTITY_LINEAGE": "PASS",
        "FACTUAL_MATERIAL_DESIGN_BASIS": "PASS",
        "ENGINE_SELECTED_REBAR": "PASS",
        "TRANSVERSE_CONFINEMENT": "FAIL",
        "NO_DATA_LEAF": "NO_DATA",
        "REANALYSIS_LEAF": "REANALYSIS_REQUIRED",
        "PNA_LEAF": "OUT_OF_SCOPE",
        "SCWB": "NOT_EVALUATED",
    }
    assert {key: item.status for key, item in leaf_contributions.items()} == expected_status

    by_key = {item.identity.leaf_key: item for item in denominator.outcomes}
    for key, contribution in leaf_contributions.items():
        fields = _fields(contribution)
        outcome = by_key[key]
        assert fields["column_leaf_identity"] == outcome.identity.value
        assert fields["column_leaf_runtime_outcome"] == outcome.status.value
        assert fields["column_leaf_source_ref"] == outcome.source_ref
        assert fields["canonical_artifact_ref"] == outcome.canonical_artifact_ref
        assert fields["model_fingerprint"] == MODEL
        assert fields["evidence_epoch_id"] == EPOCH
        assert contribution.evidence_refs == outcome.evidence_refs

    scwb = leaf_contributions["SCWB"]
    scwb_fields = _fields(scwb)
    assert scwb_fields["column_leaf_runtime_outcome"] == "EXPLICIT_UNRESOLVED"
    assert scwb_fields["deferred_cross_domain"] is True
    assert scwb_fields["deferred_owner"] == "BEAM_DOMAIN"
    assert scwb.authority_refs == ("CANONICAL_BEAM_CAPACITY_AUTHORITY",)
    assert "DEFERRED_CROSS_DOMAIN:BEAM_DOMAIN" in scwb.warnings


def test_engineering_and_audit_projections_share_exact_same_column_truth():
    denominator, reconciliation, model = _synthetic_model()
    engineering = project_building_report_view(model, ReportView.ENGINEERING).as_dict()
    audit = project_building_report_view(model, ReportView.AUDIT).as_dict()

    assert engineering["coverage_summary"] == reconciliation.as_dict()["summary"]
    assert audit["coverage_summary"] == engineering["coverage_summary"]
    assert audit["contributions"] == engineering["contributions"]

    labels = {
        item["canonical_key"]: item["label"]
        for item in engineering["coverage_display"]
    }
    assert labels["column_expected_instance_count"] == "Column expected leaves"
    assert labels["column_executed_fail_count"] == "Column executed FAIL"
    assert labels["column_deferred_cross_domain_count"] == "Column deferred cross-domain"

    attention_statuses = {item["status"] for item in engineering["attention_items"]}
    assert {"FAIL", "NO_DATA", "NOT_EVALUATED", "REANALYSIS_REQUIRED"}.issubset(
        attention_statuses
    )

    assert audit["coverage_reconciliation"] == reconciliation.as_dict()
    assert len(
        [
            item
            for item in engineering["contributions"]
            if item["slice_id"].startswith("column-r1:leaf:")
        ]
    ) == denominator.expected_instance_count


def test_existing_delivery_package_consumes_same_model_deterministically(
    monkeypatch,
):
    _, _, model = _synthetic_model()

    def fake_pdf(projection, *, selection=None, pdf_options=None):
        content = (
            b"%PDF-1.7\\nA40-accepted-passive-package-stub:"
            + projection.view.value.encode("ascii")
        )
        return ReportArtifact(
            logical_role="UNIFIED_ENGINEERING_REVIEW",
            format="PDF",
            media_type="application/pdf",
            filename=f"{projection.view.value.lower()}.pdf",
            content=content,
            view=projection.view.value,
            source_report_id=projection.report_id,
            source_project_id=projection.project_id,
            source_projection_sha256="1" * 64,
            presentation_selection_sha256="2" * 64,
            source_render_sha256="3" * 64,
            options_sha256="4" * 64,
            renderer_toolchain_fingerprint="a40-accepted-pdf-stub",
        )

    monkeypatch.setattr(
        package_module,
        "render_building_report_pdf",
        fake_pdf,
    )

    first_members = build_report_delivery_artifacts(model)
    second_members = build_report_delivery_artifacts(model)
    assert [item.filename for item in first_members] == [
        item.filename for item in second_members
    ]
    assert [item.content for item in first_members] == [
        item.content for item in second_members
    ]

    first = build_building_report_package(model)
    second = build_building_report_package(model)
    assert first.content == second.content
    assert first.sha256 == second.sha256
    verify_building_report_package(first)


def _load_public_a5_harness():
    path = Path("tests/application/test_column_public_a5_product_path.py")
    spec = spec_from_file_location("_a40_public_a5_harness", path)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _invoke_fixture_factory(fixture_function, monkeypatch):
    wrapped = getattr(fixture_function, "__pytest_wrapped__", None)
    if wrapped is not None:
        return wrapped.obj(monkeypatch)
    wrapped = getattr(fixture_function, "__wrapped__", None)
    if wrapped is not None:
        return wrapped(monkeypatch)
    return fixture_function(monkeypatch)


def test_execute_project_public_root_materializes_full_column_report_population(monkeypatch):
    harness_module = _load_public_a5_harness()
    harness = _invoke_fixture_factory(harness_module.product_harness, monkeypatch)

    result = project_execution.execute_project(
        harness.request,
        verified_session=harness_module._FakeSession(),
    )

    assert result.column_denominator is not None
    assert result.reconciliation is not None
    assert result.building_report_model is not None

    denominator = result.column_denominator
    reconciliation = result.reconciliation
    model = result.building_report_model

    leaf_contributions = tuple(
        item
        for item in model.contributions
        if item.slice_id.startswith("column-r1:leaf:")
    )
    assert len(leaf_contributions) == denominator.expected_instance_count
    assert set(denominator.required_report_source_refs).issubset(
        set(reconciliation.required_report_source_refs)
    )
    assert set(denominator.required_report_source_refs).issubset(
        {item.source_ref for item in model.report_bindings}
    )
    assert reconciliation.report_reconciled is True
    assert model.report_integrity_status == "RECONCILED"
