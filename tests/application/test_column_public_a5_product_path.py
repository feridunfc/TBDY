from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from types import SimpleNamespace

import pytest

import tbdy_engine.application.column_public_a5 as a5
import tbdy_engine.application.project_execution as project_execution
import tbdy_engine.analysis_basis.frame_gross_flexural_basis as continuity
import tbdy_engine.integration.etabs_analysis_execution as b5
import tbdy_engine.integration.etabs_analysis_state_mutation as b4b
import tbdy_engine.integration.etabs_analysis_state_revalidation as revalidation
from tbdy_engine.application.column_execution import BLOCKER_LIVE_FND2_INPUT_LINEAGE
from tbdy_engine.application.contracts import ColumnExecutionRequest, ProjectExecutionRequest
from tbdy_engine.design.columns.slenderness import SWAY_PREVENTED
from tbdy_engine.design.columns.slenderness_basis import (
    FACTUAL_CLEAR_LENGTH_CANDIDATE_AUTHORITY,
    MOMENT_RATIO_AUTHORITY,
    REGULATORY_FREE_LENGTH_AUTHORITY,
    SWAY_CLASSIFICATION_AUTHORITY,
    ColumnSlendernessAxisEvidence,
    ColumnSlendernessEvidence,
)
from tbdy_engine.etabs.oapi.analysis_execution import (
    CaseStatusPopulationFact,
    DefinedAnalysisCasePopulationFact,
    DeleteAnalysisResultsFact,
    EtabsRuntimeVersionFact,
    LoadCaseTypeRuntimeFact,
    RunAnalysisFact,
    RunCaseFlagSetFact,
    RunCaseFlagSnapshotFact,
)
from tbdy_engine.etabs.oapi.area_contributors import AreaDesignOrientation
from tbdy_engine.etabs.oapi.area_modifiers import AreaModifierVector
from tbdy_engine.etabs.oapi.frame_modifiers import (
    FrameModifierReadFact,
    FrameModifierSetFact,
    FrameModifierSurface,
    FrameModifierVector,
)
from tbdy_engine.etabs.safety import AnalysisReadiness
from tbdy_engine.integration.etabs_scratch_lifecycle import PhysicalFileSnapshot
from tbdy_engine.providers.etabs_area_contributor_provider import AreaPropertyFamily
from tbdy_engine.providers.etabs_column_force_result_population_provider import (
    ColumnForcePopulationExpectation,
    ColumnForceResultPopulationFact,
)


COMPONENT = "Story1:C1:1"


class _FakeSession:
    pass


@dataclass(frozen=True)
class _SourceIdentity:
    source_model_ref: str = "source-model-ref:public-a5"
    normalized_model_reference: str = r"C:\tmp\public-a5-source.edb"


class _FakeContext:
    def __init__(self, session):
        self.verified_session = session
        self.source_model_identity = _SourceIdentity()
        self.acquisition_context_ref = "acquisition-context:public-a5"
        self.session_provenance_ref = "session-provenance:public-a5"
        self.model_fingerprint = "model-fingerprint:public-a5"
        self.evidence_epoch_id = "evidence-epoch:public-a5"


class _FakeOwnedScratch:
    def __init__(self, source_identity, snapshot):
        self.source_model_identity = source_identity
        self.scratch_path = r"C:\tmp\public-a5-scratch.edb"
        self.active_model_path = self.scratch_path
        self.ownership_proof_ref = "owned-scratch:public-a5"
        self.source_pre = snapshot
        self.source_post = snapshot


@dataclass(frozen=True)
class _Column:
    component_id: str = COMPONENT
    unique_name: str = "1"
    column_label: str = "C1"
    story: str = "Story1"
    section: str = "C50x80"
    width_t2_m: float = 0.5
    depth_t3_m: float = 0.8
    object_length_m: float = 3.0
    coordinate_length_m: float = 3.0
    bottom_coord_m: tuple[float, float, float] = (0.0, 0.0, 0.0)
    top_coord_m: tuple[float, float, float] = (0.0, 0.0, 3.0)
    local_axis_angle_deg: float | None = 0.0
    local_axis_explicit: bool = True
    beams_at_bottom: tuple[object, ...] = ()
    beams_at_top: tuple[object, ...] = ()

    def as_dict(self):
        return {
            "component_id": self.component_id,
            "unique_name": self.unique_name,
            "section": self.section,
            "bottom_coord_m": self.bottom_coord_m,
            "top_coord_m": self.top_coord_m,
            "local_axis_angle_deg": self.local_axis_angle_deg,
            "local_axis_explicit": self.local_axis_explicit,
        }


@dataclass(frozen=True)
class _BaseFact:
    component_unique_name: str
    assigned_section_name: str
    material_name: str
    section_semantics: str
    t2_mm: Decimal
    t3_mm: Decimal
    concrete_fck_mpa: Decimal
    etabs_ec_mpa: Decimal
    source_model_ref: str
    ownership_proof_ref: str
    semantic_state_ref: str
    evidence_ref: str
    capture_event_ref: str
    source_refs: tuple[str, ...]


class _Topology:
    def __init__(self, column):
        self.columns = (column,)


def _force_rows(case_name="EX"):
    return (
        {
            "Story": "Story1", "Column": "C1", "UniqueName": "1",
            "OutputCase": case_name, "CaseType": "LinStatic", "StepType": "",
            "StepNumber": None, "Station": 0.0, "Element": "1", "ElemStation": 0.0,
            "P": -1000.0, "V2": 0.0, "V3": 0.0, "T": 0.0,
            "M2": 100.0, "M3": 80.0,
        },
        {
            "Story": "Story1", "Column": "C1", "UniqueName": "1",
            "OutputCase": case_name, "CaseType": "LinStatic", "StepType": "",
            "StepNumber": None, "Station": 3.0, "Element": "1", "ElemStation": 3.0,
            "P": -900.0, "V2": 0.0, "V3": 0.0, "T": 0.0,
            "M2": 70.0, "M3": 60.0,
        },
    )


def _slenderness():
    def axis(name, dimension):
        return ColumnSlendernessAxisEvidence(
            axis=name,
            section_dimension_mm=dimension,
            factual_clear_length_candidate_mm=3000.0,
            factual_clear_length_source_ref=f"topology:{name}:clear",
            factual_clear_length_authority=FACTUAL_CLEAR_LENGTH_CANDIDATE_AUTHORITY,
            regulatory_free_length_ln_mm=3000.0,
            regulatory_free_length_source_ref=f"reviewed:{name}:ln",
            regulatory_free_length_authority=REGULATORY_FREE_LENGTH_AUTHORITY,
            sway_classification=SWAY_PREVENTED,
            sway_source_ref=f"reviewed:{name}:sway",
            sway_authority=SWAY_CLASSIFICATION_AUTHORITY,
            effective_length_factor_k=None,
            effective_length_source_ref=None,
            effective_length_authority=None,
            moment_ratio_m1_over_m2=0.0,
            moment_ratio_source_ref=f"reviewed:{name}:ratio",
            moment_ratio_authority=MOMENT_RATIO_AUTHORITY,
            allow_conservative_braced_ratio=False,
        )
    return ColumnSlendernessEvidence(
        component_id=COMPONENT,
        m2=axis("M2", 800.0),
        m3=axis("M3", 500.0),
        source_refs=("slenderness:public-a5",),
    )


@pytest.fixture
def product_harness(monkeypatch):
    session = _FakeSession()
    context = _FakeContext(session)
    snapshot = PhysicalFileSnapshot(
        canonical_absolute_path="/tmp/public-a5-source.edb",
        exists=True,
        file_size_bytes=100,
        sha256_content_digest="a" * 64,
        mtime_ns=1,
    )
    owned = _FakeOwnedScratch(context.source_model_identity, snapshot)
    column = _Column()
    topology = _Topology(column)

    base = _BaseFact(
        component_unique_name="1",
        assigned_section_name="C50x80",
        material_name="C35",
        section_semantics="PRISMATIC_RECTANGULAR_RC_FRAME",
        t2_mm=Decimal("500"),
        t3_mm=Decimal("800"),
        concrete_fck_mpa=Decimal("35"),
        etabs_ec_mpa=Decimal("33000"),
        source_model_ref=context.source_model_identity.source_model_ref,
        ownership_proof_ref=owned.ownership_proof_ref,
        semantic_state_ref="frame-semantic:1",
        evidence_ref="frame-base-pre:1",
        capture_event_ref="frame-capture:pre",
        source_refs=("frame-base-row:1",),
    )
    post_base = _BaseFact(
        component_unique_name=base.component_unique_name,
        assigned_section_name=base.assigned_section_name,
        material_name=base.material_name,
        section_semantics=base.section_semantics,
        t2_mm=base.t2_mm,
        t3_mm=base.t3_mm,
        concrete_fck_mpa=base.concrete_fck_mpa,
        etabs_ec_mpa=base.etabs_ec_mpa,
        source_model_ref=base.source_model_ref,
        ownership_proof_ref=base.ownership_proof_ref,
        semantic_state_ref=base.semantic_state_ref,
        evidence_ref="frame-base-post:1",
        capture_event_ref="frame-capture:post",
        source_refs=base.source_refs,
    )

    section_initial = FrameModifierVector.from_sequence((0.41, 0.52, 0.63, 0.74, 0.85, 0.96, 1.2, 1.3))
    object_initial = FrameModifierVector.from_sequence((0.31, 0.42, 0.53, 0.64, 0.75, 0.86, 0.9, 0.8))
    modifier_values = {
        (FrameModifierSurface.FRAME_SECTION_PROPERTY.value, "C50x80"): section_initial,
        (FrameModifierSurface.FRAME_OBJECT.value, "1"): object_initial,
    }
    property_fact = FrameModifierReadFact(
        surface=FrameModifierSurface.FRAME_SECTION_PROPERTY,
        target_name="C50x80",
        modifiers=section_initial,
        return_code=0,
    )
    object_fact = FrameModifierReadFact(
        surface=FrameModifierSurface.FRAME_OBJECT,
        target_name="1",
        modifiers=object_initial,
        return_code=0,
    )
    frame_fact = SimpleNamespace(
        frame_name="1",
        member_role="COLUMN",
        base_fact=base,
        property_modifiers=property_fact,
        object_modifiers=object_fact,
        releases=SimpleNamespace(evidence_ref="release:1"),
        isotropic_material=SimpleNamespace(evidence_ref="isotropic:C35"),
        factual_ec_mpa=Decimal("33000"),
        factual_gc_mpa=Decimal("13200"),
        source_refs=(
            "frame-fact:1", base.evidence_ref, property_fact.evidence_ref,
            object_fact.evidence_ref, "release:1", "isotropic:C35",
        ),
        supported_end_condition=True,
    )
    frame_population = SimpleNamespace(
        expected_frame_names=("1",),
        rows=(frame_fact,),
        source_refs=("frame-population:1", base.evidence_ref),
    )
    area_population = SimpleNamespace(
        expected_area_names=(),
        rows=(),
        source_refs=("area-population:empty",),
    )

    # Public root + trusted context boundary.
    monkeypatch.setattr(project_execution, "EtabsVerifiedSession", _FakeSession)
    monkeypatch.setattr(project_execution, "create_trusted_live_acquisition_context", lambda verified_session: context)
    monkeypatch.setattr(a5, "TrustedLiveAcquisitionContext", _FakeContext)
    monkeypatch.setattr(a5, "create_owned_scratch_context", lambda _context: owned)
    monkeypatch.setattr(a5, "capture_etabs_strict_column_topology_from_session", lambda _session: topology)
    monkeypatch.setattr(a5, "capture_frame_eq713_factual_population", lambda *_args, **_kwargs: frame_population)
    monkeypatch.setattr(a5, "capture_area_contributor_population_from_session", lambda *_args, **_kwargs: area_population)

    selection = SimpleNamespace(
        capture_complete=True,
        rows=(SimpleNamespace(combo_name="ULS"),),
        names=("ULS",),
        source_refs=("selected-combos:ULS",),
    )
    combo = SimpleNamespace(
        name="ULS",
        combo_type="LINEAR_ADD",
        constituents=(SimpleNamespace(cname_type="LOAD_CASE", name="EX", scale_factor=1.0),),
        nested_combos=(),
    )
    monkeypatch.setattr(a5, "acquire_actual_concrete_design_combo_selection_from_session", lambda *_args, **_kwargs: selection)
    monkeypatch.setattr(a5, "capture_etabs_combo_definitions_from_session", lambda *_args, **_kwargs: (combo,))

    monkeypatch.setattr(
        a5,
        "capture_etabs_column_endpoint_restraints_from_session",
        lambda *_args, **_kwargs: SimpleNamespace(
            bottom=SimpleNamespace(dofs=(True,) * 6),
            top=SimpleNamespace(dofs=(False,) * 6),
            bottom_source_ref="restraint:bottom",
            top_source_ref="restraint:top",
        ),
    )
    monkeypatch.setattr(a5, "resolve_ts500_column_free_length", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("bounded test uses reviewed slenderness evidence")))
    monkeypatch.setattr(a5, "build_factual_slenderness_evidence_from_topology", lambda *_args, **_kwargs: _slenderness())
    monkeypatch.setattr(a5, "build_assigned_rc_frame_bending_modifier_evidence", lambda *_args, **_kwargs: ())

    # B4B exact mixed mutation with mocked OAPI boundary.
    for module in (b4b, revalidation, b5):
        monkeypatch.setattr(module, "TrustedLiveAcquisitionContext", _FakeContext)
        monkeypatch.setattr(module, "OwnedScratchContext", _FakeOwnedScratch)

    def identity(_session, *, timeout_seconds=30.0):
        return SimpleNamespace(model_full_path=owned.scratch_path, model_locked=False)

    monkeypatch.setattr(b4b, "reread_verified_session_identity", identity)
    monkeypatch.setattr(b4b, "capture_physical_file_snapshot", lambda _path: snapshot)
    monkeypatch.setattr(revalidation, "reread_verified_session_identity", identity)
    monkeypatch.setattr(revalidation, "capture_physical_file_snapshot", lambda _path: snapshot)
    monkeypatch.setattr(b5, "reread_verified_session_identity", identity)
    monkeypatch.setattr(b5, "capture_physical_file_snapshot", lambda _path: snapshot)

    mutation_calls = []

    def get_frame(_session, *, surface, target_name, timeout_seconds=30.0):
        vector = modifier_values[(surface.value, target_name)]
        return FrameModifierReadFact(surface=surface, target_name=target_name, modifiers=vector, return_code=0)

    def set_frame(_session, *, surface, target_name, modifiers, timeout_seconds=30.0):
        mutation_calls.append((surface.value, target_name, modifiers.as_tuple()))
        modifier_values[(surface.value, target_name)] = modifiers
        return FrameModifierSetFact(surface=surface, target_name=target_name, requested_modifiers=modifiers, return_code=0)

    monkeypatch.setattr(b4b, "get_frame_modifiers_from_session", get_frame)
    monkeypatch.setattr(b4b, "set_frame_modifiers_from_session", set_frame)

    # B5 canonical execution: one case, one exact RunAnalysis call.
    runtime = {
        "run_flags": {"EX": False},
        "statuses": {"EX": 4},
        "run_calls": 0,
        "delete_calls": 0,
    }
    monkeypatch.setattr(
        b5,
        "get_defined_analysis_cases_from_session",
        lambda *_args, **_kwargs: DefinedAnalysisCasePopulationFact(case_names=tuple(runtime["run_flags"]), return_code=0),
    )
    monkeypatch.setattr(
        b5,
        "get_etabs_runtime_version_fact_from_session",
        lambda *_args, **_kwargs: EtabsRuntimeVersionFact(program_version="23.2.0", internal_version_number=0.0, return_code=0),
    )
    monkeypatch.setattr(
        b5,
        "get_load_case_type_runtime_fact_from_session",
        lambda _session, *, case_name, timeout_seconds=30.0: LoadCaseTypeRuntimeFact(
            case_name=case_name,
            case_type=1,
            sub_type=0,
            design_type=1,
            design_type_option=0,
            runtime_auto_slot_value=0,
            return_code=0,
        ),
    )
    monkeypatch.setattr(
        b5,
        "get_run_case_flags_from_session",
        lambda *_args, **_kwargs: RunCaseFlagSnapshotFact(case_flags=tuple(runtime["run_flags"].items()), return_code=0),
    )

    def set_flag(_session, *, case_name, run, all_cases=False, timeout_seconds=30.0):
        if all_cases:
            for name in tuple(runtime["run_flags"]):
                runtime["run_flags"][name] = run
        else:
            runtime["run_flags"][case_name] = run
        return RunCaseFlagSetFact(case_name=case_name, run=run, all_cases=all_cases, return_code=0)

    def delete_results(_session, *, case_name, all_cases=False, timeout_seconds=30.0):
        runtime["delete_calls"] += 1
        if all_cases:
            for name in tuple(runtime["statuses"]):
                runtime["statuses"][name] = 1
        else:
            runtime["statuses"][case_name] = 1
        return DeleteAnalysisResultsFact(case_name=case_name, all_cases=all_cases, return_code=0)

    def run_analysis(_session, *, timeout_seconds=300.0):
        runtime["run_calls"] += 1
        for name, enabled in runtime["run_flags"].items():
            if enabled:
                runtime["statuses"][name] = 4
        return RunAnalysisFact(return_code=0)

    monkeypatch.setattr(b5, "set_run_case_flag_from_session", set_flag)
    monkeypatch.setattr(b5, "delete_analysis_results_from_session", delete_results)
    monkeypatch.setattr(
        b5,
        "get_case_status_population_from_session",
        lambda *_args, **_kwargs: CaseStatusPopulationFact(case_statuses=tuple(runtime["statuses"].items()), return_code=0),
    )
    monkeypatch.setattr(
        b5,
        "read_verified_analysis_readiness",
        lambda _session, case_name, *, timeout_seconds=30.0: SimpleNamespace(
            case_name=case_name,
            readiness={1: AnalysisReadiness.ANALYSIS_NOT_RUN, 4: AnalysisReadiness.ANALYSIS_FINISHED}[runtime["statuses"][case_name]],
            etabs_status_code=runtime["statuses"][case_name],
        ),
    )
    monkeypatch.setattr(b5, "run_analysis_from_session", run_analysis)
    expectation = ColumnForcePopulationExpectation(expected_unique_names=("1",), source_row_count=1)
    monkeypatch.setattr(b5, "capture_column_force_population_expectation_from_session", lambda *_args, **_kwargs: expectation)
    monkeypatch.setattr(
        b5,
        "capture_column_force_result_population_from_session",
        lambda _session, *, case_name, expectation, timeout_seconds=30.0: ColumnForceResultPopulationFact(
            case_name=case_name,
            expectation_ref=expectation.evidence_ref,
            expected_unique_names=expectation.expected_unique_names,
            observed_unique_names=expectation.expected_unique_names,
            rows=_force_rows(case_name),
        ),
    )

    # Existing POST continuity runs with the real helper against mocked factual recapture.
    monkeypatch.setattr(continuity, "TrustedLiveAcquisitionContext", _FakeContext)
    monkeypatch.setattr(continuity, "OwnedScratchContext", _FakeOwnedScratch)
    monkeypatch.setattr(continuity, "FrameFlexuralBaseFact", _BaseFact)
    monkeypatch.setattr(continuity, "capture_frame_flexural_base_fact", lambda **_kwargs: post_base)

    request = ProjectExecutionRequest(
        project_id="project:public-a5",
        report_id="report:public-a5",
        title="PUBLIC A5 product path",
        column=ColumnExecutionRequest(COMPONENT),
    )
    return SimpleNamespace(
        request=request,
        runtime=runtime,
        modifier_values=modifier_values,
        mutation_calls=mutation_calls,
        column=column,
        topology=topology,
        frame_population=frame_population,
        area_population=area_population,
        section_initial=section_initial,
        object_initial=object_initial,
    )


def test_execute_project_reaches_real_fnd2_and_preserves_non_target_frame_slots(product_harness):
    result = project_execution.execute_project(product_harness.request, verified_session=_FakeSession())

    assert result.column.fnd_col_2_execution is not None
    assert BLOCKER_LIVE_FND2_INPUT_LINEAGE not in result.column.blockers
    assert product_harness.runtime["run_calls"] == 1
    assert product_harness.runtime["delete_calls"] == 1

    section = product_harness.modifier_values[(FrameModifierSurface.FRAME_SECTION_PROPERTY.value, "C50x80")].as_tuple()
    obj = product_harness.modifier_values[(FrameModifierSurface.FRAME_OBJECT.value, "1")].as_tuple()
    assert section == (0.41, 1.0, 1.0, 0.74, 1.0, 1.0, 1.2, 1.3)
    assert obj == (0.31, 1.0, 1.0, 0.64, 1.0, 1.0, 0.9, 0.8)


def test_unresolved_required_frame_mode_fails_closed_before_b4b(product_harness, monkeypatch):
    bad_column = _Column(top_coord_m=(1.0, 0.0, 3.0), coordinate_length_m=(10.0 ** 0.5))
    bad_topology = _Topology(bad_column)
    monkeypatch.setattr(a5, "capture_etabs_strict_column_topology_from_session", lambda _session: bad_topology)

    result = project_execution.execute_project(product_harness.request, verified_session=_FakeSession())

    assert result.column.blockers == (a5.BLOCKER_A3_EQ713_POPULATION,)
    assert result.column.fnd_col_2_execution is None
    assert product_harness.runtime["run_calls"] == 0


def test_unproven_shell_thick_area_plate_and_transverse_modes_fail_closed(product_harness, monkeypatch):
    area = SimpleNamespace(
        area_name="A1",
        orientation=AreaDesignOrientation.FLOOR,
        property_name="Slab15",
        property_state=SimpleNamespace(
            family=AreaPropertyFamily.SLAB,
            shell_type_code=2,
            material_name="C35",
            thickness=0.15,
            property_modifiers=SimpleNamespace(modifiers=AreaModifierVector.from_sequence((0.25,) * 6 + (1.0,) * 4)),
        ),
        raw_material_overwrite_name="None",
        object_modifiers=SimpleNamespace(modifiers=AreaModifierVector.from_sequence((1.0,) * 10)),
        semi_rigid_diaphragm_assigned=True,
        wall_assignment_role=None,
        default_local_axes_assignment_proven=True,
        source_refs=("area:A1",),
    )
    area_population = SimpleNamespace(
        expected_area_names=("A1",),
        rows=(area,),
        source_refs=("area-population:A1",),
    )
    monkeypatch.setattr(a5, "capture_area_contributor_population_from_session", lambda *_args, **_kwargs: area_population)

    result = project_execution.execute_project(product_harness.request, verified_session=_FakeSession())

    assert result.column.blockers == (a5.BLOCKER_A3_EQ713_POPULATION,)
    assert result.column.fnd_col_2_execution is None
    assert product_harness.runtime["run_calls"] == 0
