from __future__ import annotations

from dataclasses import asdict, replace
from decimal import Decimal
import importlib.util
import inspect
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

import tbdy_engine.analysis_basis.frame_gross_flexural_basis as continuity
import tbdy_engine.application.column_execution as column_execution
import tbdy_engine.application.column_public_a5 as a5
import tbdy_engine.application.project_execution as project_execution
import tbdy_engine.integration.etabs_analysis_execution as b5
import tbdy_engine.integration.etabs_controlled_design_execution as b6
from tbdy_engine.application.column_execution import (
    ColumnDomainArtifact,
    ColumnExecutionContractError,
    ColumnPopulationExecution,
    ColumnPopulationState,
    STATUS_APPLICATION_BLOCKED,
)
from tbdy_engine.application.contracts import (
    ColumnExecutionRequest,
    ProjectExecutionRequest,
)
from tbdy_engine.coverage.column_denominator import (
    ColumnDenominatorLeafIdentity,
    ColumnExpectedLeaf,
    ColumnLeafApplicability,
    ColumnLeafOutcome,
    ColumnLeafOutcomeStatus,
    SupportedColumnDenominator,
    canonical_column_leaf_source_ref,
)
from tbdy_engine.etabs.oapi.concrete_design import (
    ConcreteDesignResultsAvailabilityFact,
    ConcreteDesignStartFact,
)
from tbdy_engine.etabs.oapi.frame_modifiers import (
    FrameModifierReadFact,
    FrameModifierSurface,
)
from tbdy_engine.integration.etabs_controlled_design_execution import (
    design_component_scope_ref,
)
from tbdy_engine.integration.etabs_design_execution import DesignPreflightStatus
from tbdy_engine.product_reports.building_report_projection import (
    ReportView,
    project_building_report_view,
)
from tbdy_engine.providers.etabs_column_force_result_population_provider import (
    ColumnForcePopulationExpectation,
    ColumnForceResultPopulationFact,
)


COMPONENT_1 = "Story1:C1:1"
COMPONENT_2 = "Story1:C2:2"
ABSENT_FOCUS = "Story9:C99:999"
SELECTED_POPULATION = "selected-design-combo-population:sha256:" + "9" * 64
DEFINITION_REF = "combo-definition:sha256:" + "a" * 64


def _load_public_a5_harness():
    path = Path(__file__).with_name("test_column_public_a5_product_path.py")
    spec = importlib.util.spec_from_file_location(
        "_t3_p0_public_a5_harness",
        path,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
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


def _two_column_force_rows(module, case_name: str):
    first = tuple(module._force_rows(case_name))
    second = tuple(
        {
            **row,
            "Column": "C2",
            "UniqueName": "2",
            "Element": "2",
        }
        for row in first
    )
    return (*first, *second)


def _install_two_column_harness(monkeypatch):
    module = _load_public_a5_harness()
    harness = _invoke_fixture_factory(module.product_harness, monkeypatch)

    column_1 = harness.column
    column_2 = replace(
        column_1,
        component_id=COMPONENT_2,
        unique_name="2",
        column_label="C2",
        section="C50x80B",
        bottom_coord_m=(4.0, 0.0, 0.0),
        top_coord_m=(4.0, 0.0, 3.0),
    )
    topology = SimpleNamespace(columns=(column_1, column_2))

    frame_1 = harness.frame_population.rows[0]
    base_1 = frame_1.base_fact
    base_2 = replace(
        base_1,
        component_unique_name="2",
        assigned_section_name="C50x80B",
        semantic_state_ref="frame-semantic:2",
        evidence_ref="frame-base-pre:2",
        capture_event_ref="frame-capture:pre:2",
        source_refs=("frame-base-row:2",),
    )
    property_2 = FrameModifierReadFact(
        surface=FrameModifierSurface.FRAME_SECTION_PROPERTY,
        target_name="C50x80B",
        modifiers=harness.section_initial,
        return_code=0,
    )
    object_2 = FrameModifierReadFact(
        surface=FrameModifierSurface.FRAME_OBJECT,
        target_name="2",
        modifiers=harness.object_initial,
        return_code=0,
    )
    frame_2 = SimpleNamespace(
        frame_name="2",
        member_role="COLUMN",
        base_fact=base_2,
        section_mechanics=SimpleNamespace(
            evidence_ref="section-mechanics:C50x80B"
        ),
        property_modifiers=property_2,
        object_modifiers=object_2,
        releases=SimpleNamespace(evidence_ref="release:2"),
        isotropic_material=SimpleNamespace(evidence_ref="isotropic:C35:2"),
        factual_ec_mpa=Decimal("33000"),
        factual_gc_mpa=Decimal("13200"),
        source_refs=(
            "frame-fact:2",
            base_2.evidence_ref,
            "section-mechanics:C50x80B",
            property_2.evidence_ref,
            object_2.evidence_ref,
            "release:2",
            "isotropic:C35:2",
        ),
        supported_end_condition=True,
    )
    frame_population = SimpleNamespace(
        expected_frame_names=("1", "2"),
        rows=(frame_1, frame_2),
        source_refs=(
            "frame-population:1-2",
            base_1.evidence_ref,
            base_2.evidence_ref,
        ),
    )

    harness.modifier_values[
        (FrameModifierSurface.FRAME_SECTION_PROPERTY.value, "C50x80B")
    ] = harness.section_initial
    harness.modifier_values[
        (FrameModifierSurface.FRAME_OBJECT.value, "2")
    ] = harness.object_initial

    monkeypatch.setattr(
        a5,
        "capture_etabs_strict_column_topology_from_session",
        lambda _session: topology,
    )
    monkeypatch.setattr(
        a5,
        "capture_frame_eq713_factual_population",
        lambda *_args, **_kwargs: frame_population,
    )

    post_by_unique = {
        "1": replace(
            base_1,
            evidence_ref="frame-base-post:1",
            capture_event_ref="frame-capture:post:1",
        ),
        "2": replace(
            base_2,
            evidence_ref="frame-base-post:2",
            capture_event_ref="frame-capture:post:2",
        ),
    }
    monkeypatch.setattr(
        continuity,
        "capture_frame_flexural_base_fact",
        lambda **kwargs: post_by_unique[kwargs["component_unique_name"]],
    )

    expectation = ColumnForcePopulationExpectation(
        expected_unique_names=("1", "2"),
        source_row_count=2,
    )
    monkeypatch.setattr(
        b5,
        "capture_column_force_population_expectation_from_session",
        lambda *_args, **_kwargs: expectation,
    )
    monkeypatch.setattr(
        b5,
        "capture_column_force_result_population_from_session",
        lambda _session, *, case_name, expectation, timeout_seconds=30.0:
        ColumnForceResultPopulationFact(
            case_name=case_name,
            expectation_ref=expectation.evidence_ref,
            expected_unique_names=expectation.expected_unique_names,
            observed_unique_names=expectation.expected_unique_names,
            rows=_two_column_force_rows(module, case_name),
        ),
    )

    original_slenderness = module._slenderness

    def second_order(*, component_id, **_kwargs):
        payload = asdict(original_slenderness())
        payload["component_id"] = component_id
        return payload

    monkeypatch.setattr(
        a5,
        "build_public_a5_canonical_second_order_payload",
        second_order,
    )

    selected = SimpleNamespace(
        capture_complete=True,
        model_fingerprint="model-fingerprint:public-a5",
        evidence_epoch_id="evidence-epoch:public-a5",
        rows=(
            SimpleNamespace(
                combo_type="Strength",
                combo_name="ULS",
                source_row_ref="selected-combo-row:ULS",
            ),
        ),
        names=("ULS",),
        source_refs=(
            "session-provenance:public-a5",
            SELECTED_POPULATION,
        ),
    )
    combo = SimpleNamespace(
        name="ULS",
        combo_type="LINEAR_ADD",
        constituents=(
            SimpleNamespace(
                cname_type="LOAD_CASE",
                name="EX",
                scale_factor=1.0,
            ),
        ),
        nested_combos=(),
    )
    monkeypatch.setattr(
        a5,
        "acquire_actual_concrete_design_combo_selection_from_session",
        lambda *_args, **_kwargs: selected,
    )
    monkeypatch.setattr(
        a5,
        "capture_etabs_combo_definitions_from_session",
        lambda *_args, **_kwargs: (combo,),
    )

    return SimpleNamespace(
        module=module,
        harness=harness,
        topology=topology,
        columns=(column_1, column_2),
        frame_population=frame_population,
        selected=selected,
        combo=combo,
    )


class _Envelope:
    def __init__(
        self,
        *,
        topology,
        model_fingerprint,
        evidence_epoch_id,
        source_refs,
    ):
        self.topology = topology
        self.model_fingerprint = model_fingerprint
        self.evidence_epoch_id = evidence_epoch_id
        self.source_refs = tuple(source_refs)


def _install_real_b6_owner(monkeypatch, setup, *, result_component_ids=None):
    module = setup.module
    harness = setup.harness
    expected_ids = tuple(sorted((COMPONENT_1, COMPONENT_2)))
    captured_ids = (
        expected_ids
        if result_component_ids is None
        else tuple(sorted(result_component_ids))
    )

    monkeypatch.setattr(
        column_execution,
        "ColumnTopologyEvidenceEnvelope",
        _Envelope,
    )
    monkeypatch.setattr(
        column_execution,
        "read_design_code_from_session",
        lambda _session: SimpleNamespace(
            design_code_ref="etabs-concrete-design-code:sha256:" + "b" * 64
        ),
    )
    procedure = SimpleNamespace(
        capture_complete=True,
        design_procedure_ref="design-procedure-population:sha256:" + "c" * 64,
        source_refs=("design-procedure-row:t3-p0",),
    )
    monkeypatch.setattr(
        column_execution,
        "capture_column_design_procedure_population_from_session",
        lambda _session, *, topology: procedure,
    )
    monkeypatch.setattr(
        column_execution,
        "normalized_combo_definition_fingerprint",
        lambda _definition: DEFINITION_REF,
    )

    monkeypatch.setattr(
        b6,
        "TrustedLiveAcquisitionContext",
        module._FakeContext,
    )
    monkeypatch.setattr(
        b6,
        "OwnedScratchContext",
        module._FakeOwnedScratch,
    )
    monkeypatch.setattr(
        b6,
        "ColumnTopologyEvidenceEnvelope",
        _Envelope,
    )
    monkeypatch.setattr(
        b6,
        "capture_design_preflight",
        lambda **_kwargs: SimpleNamespace(
            status=DesignPreflightStatus.ABSENT,
            preflight_ref="b6-preflight:t3-p0",
        ),
    )
    monkeypatch.setattr(
        b6,
        "acquire_actual_concrete_design_combo_selection_from_context",
        lambda **_kwargs: setup.selected,
    )
    monkeypatch.setattr(
        b6,
        "reread_verified_session_identity",
        lambda _session, *, timeout_seconds=30.0: SimpleNamespace(
            model_full_path=r"C:\tmp\public-a5-scratch.edb",
            model_locked=False,
        ),
    )

    counters = {
        "controlled_design": 0,
        "start_design": 0,
    }

    def start_design(_session, *, timeout_seconds=300.0):
        counters["start_design"] += 1
        return ConcreteDesignStartFact(return_code=0)

    monkeypatch.setattr(
        b6,
        "start_concrete_design_from_session",
        start_design,
    )
    monkeypatch.setattr(
        b6,
        "read_results_available_from_session",
        lambda _session, *, timeout_seconds=30.0:
        ConcreteDesignResultsAvailabilityFact(
            results_available=True,
            raw_response=True,
        ),
    )
    monkeypatch.setattr(
        b6,
        "capture_concrete_column_design_sections_from_context",
        lambda **_kwargs: SimpleNamespace(rows=("section:1", "section:2")),
    )

    factual_results = SimpleNamespace(
        capture_complete=True,
        expected_component_ids=captured_ids,
        attempted_component_ids=captured_ids,
        captured_component_ids=captured_ids,
        reported_result_row_count=len(captured_ids),
        rows=tuple(f"design-row:{item}" for item in captured_ids),
        source_refs=("design-results:t3-p0",),
    )
    monkeypatch.setattr(
        b6,
        "capture_concrete_column_design_results_from_context",
        lambda **_kwargs: factual_results,
    )

    real_owner = b6.execute_controlled_concrete_design

    def controlled_owner(**kwargs):
        counters["controlled_design"] += 1
        return real_owner(**kwargs)

    monkeypatch.setattr(
        column_execution,
        "execute_controlled_concrete_design",
        controlled_owner,
    )

    return counters, factual_results


def _install_lifecycle_counters(monkeypatch, setup):
    scratch_counter = {"count": 0}
    analysis_counter = {"count": 0}
    context_counter = {"count": 0}

    original_scratch = a5.create_owned_scratch_context
    original_analysis = a5.execute_controlled_analysis
    original_context = project_execution.create_trusted_live_acquisition_context

    def scratch(context):
        scratch_counter["count"] += 1
        return original_scratch(context)

    def analysis(**kwargs):
        analysis_counter["count"] += 1
        return original_analysis(**kwargs)

    def context(session):
        context_counter["count"] += 1
        return original_context(session)

    monkeypatch.setattr(a5, "create_owned_scratch_context", scratch)
    monkeypatch.setattr(a5, "execute_controlled_analysis", analysis)
    monkeypatch.setattr(
        project_execution,
        "create_trusted_live_acquisition_context",
        context,
    )
    return context_counter, scratch_counter, analysis_counter


def _two_column_request(focus=COMPONENT_1):
    return ProjectExecutionRequest(
        project_id="project:t3-p0",
        report_id="report:t3-p0",
        title="T3-P0 factual Column population",
        column=ColumnExecutionRequest(focus),
    )


def _fields(contribution):
    return {
        item.key: item.value
        for item in contribution.summary_fields
    }


def _projection_leaf_ids(projection_dict):
    rows = []
    for contribution in projection_dict["contributions"]:
        if not contribution["slice_id"].startswith("column-r1:leaf:"):
            continue
        fields = {
            item["key"]: item["value"]
            for item in contribution["summary_fields"]
        }
        rows.append(fields["column_leaf_identity"])
    return tuple(sorted(rows))


def test_project_request_remains_intent_only_no_population_authority():
    assert set(ProjectExecutionRequest.__dataclass_fields__) == {
        "project_id",
        "report_id",
        "title",
        "column",
    }


def test_canonical_project_root_reaches_population_only_through_column_composer():
    source = inspect.getsource(project_execution)
    assert "execute_column_domain(" in source
    assert "_execute_column_population" not in source

    column_source = inspect.getsource(column_execution)
    a5_source = inspect.getsource(a5)
    assert column_source.count("class ColumnPopulationState") == 1
    assert "class ColumnPopulationState" not in a5_source


def test_population_wide_vs5_is_reused_without_broadcasting_component_context(
    monkeypatch,
):
    class _Context:
        model_fingerprint = "model:dependency-policy"
        evidence_epoch_id = "epoch:dependency-policy"

    class _Vs5:
        pass

    class _P7:
        def __init__(self, component_id):
            self.component_id = component_id

    context = _Context()
    vs5 = _Vs5()
    p7 = _P7(COMPONENT_1)
    base_columns = (
        ColumnDomainArtifact(
            component_id=COMPONENT_1,
            model_fingerprint=context.model_fingerprint,
            evidence_epoch_id=context.evidence_epoch_id,
            status="READY",
            blockers=(),
        ),
        ColumnDomainArtifact(
            component_id=COMPONENT_2,
            model_fingerprint=context.model_fingerprint,
            evidence_epoch_id=context.evidence_epoch_id,
            status="READY",
            blockers=(),
        ),
    )
    topology = SimpleNamespace(
        columns=(
            SimpleNamespace(component_id=COMPONENT_1),
            SimpleNamespace(component_id=COMPONENT_2),
        )
    )
    population = a5.PublicA5PopulationExecution(
        population_state=ColumnPopulationState.KNOWN,
        acquisition_context=context,
        focus_component_id=COMPONENT_1,
        focus_present=True,
        topology=topology,
        owned_scratch=SimpleNamespace(),
        analysis_execution=SimpleNamespace(),
        selected_combo_population=SimpleNamespace(),
        combo_definitions=(),
        flattened_combos=(),
        columns=tuple(
            a5.PublicA5ColumnMaterialization(
                request=ColumnExecutionRequest(item.component_id),
                column=item,
                free_length=None,
                canonical_second_order=None,
            )
            for item in base_columns
        ),
    )

    monkeypatch.setattr(
        column_execution,
        "TrustedLiveAcquisitionContext",
        _Context,
    )
    monkeypatch.setattr(
        column_execution,
        "ReviewedVs5ColumnAxialContext",
        _Vs5,
    )
    monkeypatch.setattr(
        column_execution,
        "ReviewedColumnP7RuntimeContext",
        _P7,
    )
    monkeypatch.setattr(
        a5,
        "execute_public_a5_column",
        lambda *_args, **_kwargs: population,
    )
    monkeypatch.setattr(
        column_execution,
        "_establish_public_b6_generation",
        lambda *_args, **_kwargs: SimpleNamespace(),
    )

    seen = []

    def complete(column, **kwargs):
        seen.append(
            (
                column.component_id,
                kwargs["reviewed_vs5_column_axial_context"],
                kwargs["reviewed_column_p7_context"],
            )
        )
        return column

    monkeypatch.setattr(
        column_execution,
        "_complete_public_b6_after_fnd2",
        complete,
    )

    result = column_execution.execute_column_domain(
        ColumnExecutionRequest(COMPONENT_1),
        acquisition_context=context,
        reviewed_vs5_column_axial_context=vs5,
        reviewed_column_p7_context=p7,
        _population_mode=True,
    )

    assert isinstance(result, ColumnPopulationExecution)
    assert result.population_state is ColumnPopulationState.KNOWN
    assert [item[1] for item in seen] == [vs5, vs5]
    assert seen[0][2] is p7
    assert seen[1][2] is None


def test_two_column_public_root_uses_one_shared_live_generation_and_one_b6(
    monkeypatch,
):
    setup = _install_two_column_harness(monkeypatch)
    context_count, scratch_count, analysis_count = _install_lifecycle_counters(
        monkeypatch,
        setup,
    )
    b6_counts, factual_results = _install_real_b6_owner(
        monkeypatch,
        setup,
    )

    result = project_execution.execute_project(
        _two_column_request(),
        verified_session=setup.module._FakeSession(),
    )

    assert context_count["count"] == 1
    assert scratch_count["count"] == 1
    assert analysis_count["count"] == 1
    assert setup.harness.runtime["run_calls"] == 1
    assert b6_counts["controlled_design"] == 1
    assert b6_counts["start_design"] == 1

    assert result.population_state == ColumnPopulationState.KNOWN
    assert tuple(sorted(item.component_id for item in result.columns)) == (
        COMPONENT_1,
        COMPONENT_2,
    )

    expected_scopes = tuple(
        sorted(
            design_component_scope_ref(item)
            for item in (COMPONENT_1, COMPONENT_2)
        )
    )
    shared_state_refs = {
        item.design_state.identity_ref
        for item in result.columns
    }
    shared_result_refs = {
        item.design_result_identity.identity_ref
        for item in result.columns
    }
    shared_lineage_refs = {
        item.design_lineage.qualification_ref
        for item in result.columns
    }
    assert len(shared_state_refs) == 1
    assert len(shared_result_refs) == 1
    assert len(shared_lineage_refs) == 1
    assert result.columns[0].design_state.design_component_population_refs == (
        expected_scopes
    )
    assert factual_results.expected_component_ids == (
        COMPONENT_1,
        COMPONENT_2,
    )
    assert result.columns[0].design_result_identity.result_scope_refs == (
        expected_scopes
    )

    denominator = result.column_denominator
    reconciliation = result.reconciliation
    model = result.building_report_model
    assert denominator is not None
    assert reconciliation is not None
    assert model is not None
    assert denominator.expected_component_ids == (
        COMPONENT_1,
        COMPONENT_2,
    )
    assert denominator.silent_missing_count == 0
    assert denominator.duplicate_count == 0
    assert denominator.orphan_count == 0
    assert (
        reconciliation.column_expected_leaf_ids
        == reconciliation.column_accounted_leaf_ids
    )
    assert reconciliation.column_partition_complete is True
    assert reconciliation.column_population_reconciled is True
    assert reconciliation.column_silent_missing_leaf_ids == ()
    assert reconciliation.column_duplicate_outcome_leaf_ids == ()
    assert reconciliation.column_orphan_outcome_leaf_ids == ()

    engineering = project_building_report_view(
        model,
        ReportView.ENGINEERING,
    ).as_dict()
    audit = project_building_report_view(
        model,
        ReportView.AUDIT,
    ).as_dict()
    expected_leaf_ids = tuple(
        sorted(item.identity.value for item in denominator.outcomes)
    )
    assert _projection_leaf_ids(engineering) == expected_leaf_ids
    assert _projection_leaf_ids(audit) == expected_leaf_ids
    assert engineering["contributions"] == audit["contributions"]
    assert project_building_report_view(
        model,
        ReportView.ENGINEERING,
    ).as_dict() == engineering

    primary_summary = next(
        item
        for item in model.contributions
        if item.slice_id.startswith("product-spine-col-1:readiness:")
    )
    assert _fields(primary_summary)["summary_scope"] == (
        "PRIMARY_REQUESTED_COLUMN"
    )
    assert result.status == result.column.status


def test_requested_focus_absent_never_builds_fake_denominator_or_report(
    monkeypatch,
):
    setup = _install_two_column_harness(monkeypatch)
    result = project_execution.execute_project(
        _two_column_request(ABSENT_FOCUS),
        verified_session=setup.module._FakeSession(),
    )

    assert result.population_state == ColumnPopulationState.KNOWN
    assert tuple(sorted(item.component_id for item in result.columns)) == (
        COMPONENT_1,
        COMPONENT_2,
    )
    assert result.column.component_id == ABSENT_FOCUS
    assert result.column_denominator is None
    assert result.reconciliation is None
    assert result.building_report_model is None
    assert setup.harness.runtime["run_calls"] == 0


def test_duplicate_factual_component_identity_is_population_unknown(
    monkeypatch,
):
    setup = _install_two_column_harness(monkeypatch)
    duplicate = replace(
        setup.columns[1],
        component_id=COMPONENT_1,
    )
    monkeypatch.setattr(
        a5,
        "capture_etabs_strict_column_topology_from_session",
        lambda _session: SimpleNamespace(
            columns=(setup.columns[0], duplicate)
        ),
    )

    result = project_execution.execute_project(
        _two_column_request(),
        verified_session=setup.module._FakeSession(),
    )

    assert result.population_state == ColumnPopulationState.UNKNOWN
    assert result.columns == ()
    assert result.column_denominator is None
    assert result.reconciliation is None
    assert result.building_report_model is None


def test_one_component_fnd2_materialization_failure_preserves_population(
    monkeypatch,
):
    setup = _install_two_column_harness(monkeypatch)
    original = a5._materialize_fnd2_inputs

    def materialize(**kwargs):
        if kwargs["target_column"].component_id == COMPONENT_2:
            raise RuntimeError("bounded C2 materialization failure")
        return original(**kwargs)

    monkeypatch.setattr(a5, "_materialize_fnd2_inputs", materialize)

    result = project_execution.execute_project(
        _two_column_request(),
        verified_session=setup.module._FakeSession(),
    )

    assert result.population_state == ColumnPopulationState.KNOWN
    assert tuple(sorted(item.component_id for item in result.columns)) == (
        COMPONENT_1,
        COMPONENT_2,
    )
    by_component = {
        item.component_id: item
        for item in result.columns
    }
    assert by_component[COMPONENT_1].fnd_col_2_execution is not None
    assert by_component[COMPONENT_2].fnd_col_2_execution is None
    assert by_component[COMPONENT_2].status == (
        "FACTUAL_ACQUISITION_BLOCKED"
    )
    assert result.column_denominator is not None
    assert result.column_denominator.expected_component_ids == (
        COMPONENT_1,
        COMPONENT_2,
    )
    assert setup.harness.runtime["run_calls"] == 1


def test_shared_post_topology_failure_blocks_every_factual_component(
    monkeypatch,
):
    setup = _install_two_column_harness(monkeypatch)

    def fail_generation(**_kwargs):
        raise RuntimeError("bounded shared B5 failure")

    monkeypatch.setattr(a5, "_run_a3_generation", fail_generation)
    result = project_execution.execute_project(
        _two_column_request(),
        verified_session=setup.module._FakeSession(),
    )

    assert result.population_state == ColumnPopulationState.KNOWN
    assert tuple(sorted(item.component_id for item in result.columns)) == (
        COMPONENT_1,
        COMPONENT_2,
    )
    assert all(
        item.status == "FACTUAL_ACQUISITION_BLOCKED"
        for item in result.columns
    )
    assert result.column_denominator is not None
    assert result.column_denominator.expected_component_ids == (
        COMPONENT_1,
        COMPONENT_2,
    )
    assert result.reconciliation is None
    assert result.building_report_model is None


def test_b6_component_set_mismatch_fails_before_start_design(
    monkeypatch,
):
    setup = _install_two_column_harness(monkeypatch)
    population = a5.execute_public_a5_column(
        ColumnExecutionRequest(COMPONENT_1),
        acquisition_context=setup.module._FakeContext(
            setup.module._FakeSession()
        ),
        execute_fnd2=column_execution._execute_fnd2,
        materialize_full_population=True,
    )
    assert population.population_state == ColumnPopulationState.KNOWN
    assert all(item.column.status == "READY" for item in population.columns)

    start_calls = {"count": 0}

    def forbidden_controlled(**_kwargs):
        start_calls["count"] += 1
        raise AssertionError("StartDesign owner must not be reached")

    monkeypatch.setattr(
        column_execution,
        "execute_controlled_concrete_design",
        forbidden_controlled,
    )
    with pytest.raises(
        ColumnExecutionContractError,
        match="supplied component set differs from strict topology",
    ):
        column_execution._establish_public_b6_generation(
            (population.columns[0].column,),
            acquisition_context=population.acquisition_context,
            owned_scratch=population.owned_scratch,
            analysis_execution=population.analysis_execution,
            topology=population.topology,
            selected_combo_population=population.selected_combo_population,
            combo_definitions=population.combo_definitions,
            flattened_combos=population.flattened_combos,
            require_full_population=True,
        )
    assert start_calls["count"] == 0


def test_b6_result_population_mismatch_has_no_subset_salvage(
    monkeypatch,
):
    setup = _install_two_column_harness(monkeypatch)
    b6_counts, _ = _install_real_b6_owner(
        monkeypatch,
        setup,
        result_component_ids=(COMPONENT_1,),
    )

    result = project_execution.execute_project(
        _two_column_request(),
        verified_session=setup.module._FakeSession(),
    )

    assert b6_counts["controlled_design"] == 1
    assert b6_counts["start_design"] == 1
    assert tuple(sorted(item.component_id for item in result.columns)) == (
        COMPONENT_1,
        COMPONENT_2,
    )
    assert all(
        item.status == STATUS_APPLICATION_BLOCKED
        for item in result.columns
    )
    assert all(item.controlled_design_result is None for item in result.columns)
    assert all(item.design_state is None for item in result.columns)


def _bare_column(component_id: str):
    return ColumnDomainArtifact(
        component_id=component_id,
        model_fingerprint="model:t3-p0",
        evidence_epoch_id="epoch:t3-p0",
        status="FACTUAL_ACQUISITION_BLOCKED",
        blockers=("bounded",),
    )


def test_missing_component_artifact_before_a38_fails_closed():
    c1 = _bare_column(COMPONENT_1)
    with pytest.raises(
        ColumnExecutionContractError,
        match="reconcile exactly to factual topology",
    ):
        ColumnPopulationExecution(
            population_state=ColumnPopulationState.KNOWN,
            expected_component_ids=(COMPONENT_1, COMPONENT_2),
            columns=(c1,),
            focus_component_id=COMPONENT_1,
            focus_present=True,
            focus_column=c1,
        )


def test_duplicate_component_artifact_before_a38_fails_closed():
    c1 = _bare_column(COMPONENT_1)
    with pytest.raises(
        ColumnExecutionContractError,
        match="reconcile exactly to factual topology",
    ):
        ColumnPopulationExecution(
            population_state=ColumnPopulationState.KNOWN,
            expected_component_ids=(COMPONENT_1, COMPONENT_2),
            columns=(c1, c1),
            focus_component_id=COMPONENT_1,
            focus_present=True,
            focus_column=c1,
        )


def _rich_selected_rebar(tag: str):
    return SimpleNamespace(
        selected_rebar_ref=f"engine-selected-rebar:{tag}",
        candidate_id=f"candidate:{tag}",
        candidate_geometry_fingerprint=f"geometry:{tag}",
        selected_candidate=SimpleNamespace(
            bar_diameter_mm=20.0,
            n_bars_dir2=4,
            n_bars_dir3=5,
            rho=0.01875,
        ),
        as_total_mm2=Decimal("2450.125"),
        rank=1,
        material_context_ref=f"material:{tag}",
        provenance_refs=(f"rebar-provenance:{tag}",),
        required_area_decision_ids=(f"area-decision:{tag}",),
        pmm_decision_ids=(f"pmm-decision:{tag}",),
        requirement_ids=(f"requirement:{tag}",),
        demand_state_ids=(f"demand-state:{tag}",),
    )


def _rich_final_cage(tag: str):
    return SimpleNamespace(
        authority="REVIEWED_PROJECT_FINAL_TRANSVERSE_CAGE",
        semantic_role="USER_PROVIDED_REBAR",
        tie_size_name=f"T10-{tag}",
        number_2_dir_tie_bars=3,
        number_3_dir_tie_bars=4,
        confinement_spacing_mm=100.0,
        middle_spacing_mm=150.0,
        shear_spacing_mm=100.0,
        provided_confinement_region_length_mm=900.0,
        horizontal_leg_spacing_dir2_mm=120.0,
        horizontal_leg_spacing_dir3_mm=110.0,
        restrained_longitudinal_bar_spacing_mm=180.0,
        review_refs=(f"final-cage:{tag}",),
    )


def _rich_column(component_id: str, tag: str):
    return ColumnDomainArtifact(
        component_id=component_id,
        model_fingerprint="model:rich",
        evidence_epoch_id="epoch:rich",
        status="SELECTED",
        blockers=(),
        fnd_col_2_execution=SimpleNamespace(readiness=None),
        longitudinal_selection=SimpleNamespace(
            status="SELECTED",
            selected_rebar=_rich_selected_rebar(tag),
        ),
        final_transverse_cage=_rich_final_cage(tag),
        transverse_confinement=SimpleNamespace(
            complete=True,
            source_refs=(f"transverse:{tag}",),
        ),
    )


def _rich_denominator():
    expected = []
    outcomes = []
    for component_id in (COMPONENT_1, COMPONENT_2):
        for leaf_key in ("ENGINE_SELECTED_REBAR", "TRANSVERSE_CONFINEMENT"):
            identity = ColumnDenominatorLeafIdentity.build(
                component_id=component_id,
                leaf_key=leaf_key,
                model_fingerprint="model:rich",
                evidence_epoch_id="epoch:rich",
                scope_ref=component_id,
            )
            expected.append(
                ColumnExpectedLeaf(
                    identity=identity,
                    family=leaf_key,
                    applicability=ColumnLeafApplicability.MANDATORY,
                )
            )
            outcomes.append(
                ColumnLeafOutcome(
                    identity=identity,
                    status=ColumnLeafOutcomeStatus.EXECUTED_PASS,
                    source_ref=canonical_column_leaf_source_ref(identity),
                    evidence_refs=(f"leaf:{component_id}:{leaf_key}",),
                )
            )
    return SupportedColumnDenominator(expected, outcomes)


def test_a40_rich_leaf_projection_reuses_the_single_summary_field_owner():
    leaf_source = inspect.getsource(
        project_execution._column_leaf_component_projection
    )
    module_source = inspect.getsource(project_execution)
    assert "_report_contribution(column)" in leaf_source
    assert "ReportField(" not in leaf_source
    for field_key in (
        "selected_rebar_ref",
        "selected_rebar_candidate_id",
        "selected_rebar_geometry_fingerprint",
        "selected_rebar_as_total_mm2",
        "selected_rebar_rank",
        "selected_rebar_bar_diameter_mm",
        "selected_rebar_n_bars_dir2",
        "selected_rebar_n_bars_dir3",
        "selected_rebar_rho",
        "final_transverse_cage_authority",
        "final_transverse_cage_semantic_role",
        "final_transverse_tie_size_name",
        "final_transverse_number_2_dir_tie_bars",
        "final_transverse_number_3_dir_tie_bars",
        "final_transverse_confinement_spacing_mm",
        "final_transverse_middle_spacing_mm",
        "final_transverse_shear_spacing_mm",
        "final_transverse_confinement_region_length_mm",
        "final_transverse_horizontal_leg_spacing_dir2_mm",
        "final_transverse_horizontal_leg_spacing_dir3_mm",
        "final_transverse_restrained_longitudinal_bar_spacing_mm",
    ):
        assert module_source.count(f'key="{field_key}"') == 1


def test_nonfocus_a40_leaf_projection_preserves_all_existing_rich_facts():
    c1 = _rich_column(COMPONENT_1, "C1")
    c2 = _rich_column(COMPONENT_2, "C2")
    contributions, _ = project_execution._column_leaf_report_population(
        _rich_denominator(),
        columns=(c1, c2),
    )
    c2_by_leaf = {
        _fields(item)["column_leaf_key"]: item
        for item in contributions
        if item.component_id == COMPONENT_2
    }

    selected = _fields(c2_by_leaf["ENGINE_SELECTED_REBAR"])
    assert selected["selected_rebar_ref"] == "engine-selected-rebar:C2"
    assert selected["selected_rebar_candidate_id"] == "candidate:C2"
    assert selected["selected_rebar_geometry_fingerprint"] == "geometry:C2"
    assert selected["selected_rebar_as_total_mm2"] == "2450.125"
    assert selected["selected_rebar_rank"] == 1
    assert selected["selected_rebar_bar_diameter_mm"] == 20.0
    assert selected["selected_rebar_n_bars_dir2"] == 4
    assert selected["selected_rebar_n_bars_dir3"] == 5
    assert selected["selected_rebar_rho"] == 0.01875

    cage = _fields(c2_by_leaf["TRANSVERSE_CONFINEMENT"])
    assert cage["final_transverse_cage_authority"] == (
        "REVIEWED_PROJECT_FINAL_TRANSVERSE_CAGE"
    )
    assert cage["final_transverse_cage_semantic_role"] == (
        "USER_PROVIDED_REBAR"
    )
    assert cage["final_transverse_tie_size_name"] == "T10-C2"
    assert cage["final_transverse_number_2_dir_tie_bars"] == 3
    assert cage["final_transverse_number_3_dir_tie_bars"] == 4
    assert cage["final_transverse_confinement_spacing_mm"] == 100.0
    assert cage["final_transverse_middle_spacing_mm"] == 150.0
    assert cage["final_transverse_shear_spacing_mm"] == 100.0
    assert cage["final_transverse_confinement_region_length_mm"] == 900.0
    assert cage["final_transverse_horizontal_leg_spacing_dir2_mm"] == 120.0
    assert cage["final_transverse_horizontal_leg_spacing_dir3_mm"] == 110.0
    assert (
        cage["final_transverse_restrained_longitudinal_bar_spacing_mm"]
        == 180.0
    )
    assert cage["transverse_confinement_complete"] is True
