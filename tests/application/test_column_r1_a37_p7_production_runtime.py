from __future__ import annotations

from dataclasses import fields
from types import SimpleNamespace

import pytest

import tbdy_engine.application.column_p7_runtime as subject
from tbdy_engine.application.contracts import ColumnExecutionRequest, ProjectExecutionRequest
from tbdy_engine.design.columns.section_capacity import ColumnSectionMaterial
from tbdy_engine.features.column_shear_demand_evidence import (
    build_column_shear_demand_evidence,
    column_shear_source_identity,
)
from tbdy_engine.regulatory.contracts import AvailabilityState
from tbdy_engine.regulatory.units import UNIT_KN, UNIT_M
from tbdy_engine.regulatory.vs6_column_shear_p7_integration import ReviewedDAmplifiedShearAuthority

COMPONENT = "S1:C1:101"


def _row(case="COMB1"):
    return {
        "Story": "S1", "Column": "C1", "UniqueName": "101",
        "OutputCase": case, "CaseType": "Combination", "StepType": "",
        "StepNumber": None, "Station": 0.0, "Element": "501", "ElemStation": 0.0,
        "P": -500.0, "V2": -80.0, "V3": 30.0, "T": 0.0, "M2": 20.0, "M3": 50.0,
    }


def _d(direction):
    return ReviewedDAmplifiedShearAuthority(
        component_id=COMPONENT,
        direction=direction,
        availability=AvailabilityState.BLOCKED,
        candidate_kn=None,
        authority_ref="REVIEWED:D:BLOCKED",
        review_refs=("REVIEW:D",),
    )


def _not_short():
    return subject.ReviewedColumnShortColumnContext(
        component_id=COMPONENT,
        short_column_applies=False,
        short_free_length_mm=None,
        infill_fully_adjacent=None,
        story_height_mm=None,
        review_refs=("REVIEW:NOT_SHORT",),
    )


def _short():
    return subject.ReviewedColumnShortColumnContext(
        component_id=COMPONENT,
        short_column_applies=True,
        short_free_length_mm=900.0,
        infill_fully_adjacent=False,
        story_height_mm=None,
        review_refs=("REVIEW:SHORT:7.3.8",),
    )


def _context():
    identity = column_shear_source_identity(_row())
    return subject.ReviewedColumnP7RuntimeContext(
        component_id=COMPONENT,
        directions=tuple(
            subject.ReviewedColumnP7DirectionPlan(
                component_id=COMPONENT,
                direction=direction,
                tbdy_vd_source_identity=identity,
                ts500_vd_source_identity=identity,
                bottom_state_id="STATE:BOTTOM",
                top_state_id="STATE:TOP",
                response_spectrum_concurrency_proven=False,
                d_amplified_authority=_d(direction),
                review_refs=(f"REVIEW:{direction}",),
            )
            for direction in ("V2", "V3")
        ),
        review_refs=("REVIEW:P7",),
    )


def test_b5_population_is_projected_without_second_result_table_read(monkeypatch):
    population = SimpleNamespace(case_name="COMB1", rows=(_row(),), evidence_ref="B5:POP:COMB1")
    result_identity = SimpleNamespace(identity_ref="ANALYSIS_RESULT:1")
    qualification = SimpleNamespace(qualified=True, require_qualified_result=lambda: result_identity)
    analysis = SimpleNamespace(
        qualification=qualification,
        analysis_result_identity=result_identity,
        execution_proof_ref="B5:EXECUTION:1",
        manifest=SimpleNamespace(
            scope=SimpleNamespace(case_names=("COMB1",)),
            result_populations=(population,),
        ),
    )
    monkeypatch.setattr(subject, "AnalysisExecutionResult", type(analysis))
    context = SimpleNamespace(verified_session=object())
    monkeypatch.setattr(subject, "TrustedLiveAcquisitionContext", type(context))
    monkeypatch.setattr(
        subject,
        "read_verified_unit_snapshot",
        lambda _session: SimpleNamespace(
            present_units_api="GetPresentUnits_2",
            present_force_unit=4,
            present_length_unit=6,
        ),
    )
    bundle = subject.build_b5_bound_column_shear_evidence(
        model_fingerprint="model:a37",
        acquisition_context=context,
        analysis_execution=analysis,
    )
    assert bundle.output_names == ("COMB1",)
    assert len(bundle.rows) == 1
    assert dict(bundle.rows[0])["V2"] == pytest.approx(-80.0)
    assert bundle.force_unit == UNIT_KN
    assert bundle.length_unit == UNIT_M
    assert "B5:POP:COMB1" in bundle.unit_provenance_refs
    assert "B5:EXECUTION:1" in bundle.unit_provenance_refs


def test_runtime_binds_reviewed_identities_to_runtime_epoch_and_canonical_material(monkeypatch):
    bundle = build_column_shear_demand_evidence(
        model_fingerprint="model:a37",
        rows=(_row(),),
        output_names=("COMB1",),
        force_unit=UNIT_KN,
        length_unit=UNIT_M,
        unit_provenance_refs=("UNIT:PROOF",),
    )
    monkeypatch.setattr(subject, "build_b5_bound_column_shear_evidence", lambda **_kwargs: bundle)
    calls = []
    monkeypatch.setattr(
        subject,
        "run_vs6_p7_from_production_evidence",
        lambda **kwargs: calls.append(kwargs) or SimpleNamespace(
            component_id=COMPONENT,
            direction=kwargs["capacity_state_selection"].direction,
        ),
    )
    monkeypatch.setattr(
        subject,
        "build_vs6_p7_column_shear_run",
        lambda *, component_id, directions: SimpleNamespace(
            component_id=component_id,
            directions=tuple(directions),
        ),
    )
    material = ColumnSectionMaterial(fck_mpa=30.0, fcd_mpa=20.0, fyd_mpa=365.0)
    material_context = SimpleNamespace(
        component_id=COMPONENT,
        model_fingerprint="model:a37",
        material=material,
        section_material_binding_ref="MAT:BIND",
        binding_ref="MAT:CTX",
        concrete_strength_source_refs=("MAT:FCK",),
        concrete_design_strength_review_refs=("MAT:FCD",),
        steel_design_strength_review_refs=("MAT:FYD",),
    )
    runtime = SimpleNamespace(
        component_id=COMPONENT,
        target_topology=SimpleNamespace(component_id=COMPONENT, unique_name="101"),
        selection=SimpleNamespace(selected=True, selected_rebar=object()),
        bound_design_basis=SimpleNamespace(
            material_context=material_context,
            source_refs=("BASIS:1",),
            high_ductility_applies=True,
        ),
    )
    monkeypatch.setattr(subject, "ColumnLongitudinalRuntimeComposition", type(runtime))
    state_type = type("FakeState", (), {})
    states = (state_type(), state_type())
    for item in states:
        item.component_id = COMPONENT
    monkeypatch.setattr(subject, "ColumnDemandState", state_type)
    free_type = type("FakeFree", (), {})
    free = free_type()
    free.component_id = COMPONENT
    monkeypatch.setattr(subject, "ColumnFreeLengthResolution", free_type)

    result = subject.compose_column_p7_runtime(
        component_id=COMPONENT,
        model_fingerprint="model:a37",
        acquisition_context=object(),
        analysis_execution=object(),
        free_length=free,
        demand_states=states,
        longitudinal_runtime=runtime,
        reviewed_context=_context(),
        short_column_context=_not_short(),
    )
    assert result.component_id == COMPONENT
    assert len(calls) == 2
    assert {item["capacity_state_selection"].direction for item in calls} == {"V2", "V3"}
    assert all(item["section_material"] is material for item in calls)
    assert all("rebar_inputs" not in item for item in calls)
    assert all(
        item["tbdy_vd_selection"].evidence_epoch_id == bundle.evidence_epoch_id
        for item in calls
    )
    assert all(item["demand_states"] == states for item in calls)


def test_a37_reviewed_context_is_not_added_to_request_dtos():
    forbidden = {
        "reviewed_column_p7_context", "p7_context", "p7_demand_selection", "d_amplified_authority"
    }
    assert forbidden.isdisjoint({item.name for item in fields(ColumnExecutionRequest)})
    assert forbidden.isdisjoint({item.name for item in fields(ProjectExecutionRequest)})



def test_p7_runtime_rejects_limited_ductility_basis(monkeypatch):
    runtime = SimpleNamespace(
        component_id=COMPONENT,
        target_topology=SimpleNamespace(
            component_id=COMPONENT,
            unique_name="101",
        ),
        selection=SimpleNamespace(
            selected=True,
            selected_rebar=object(),
        ),
        bound_design_basis=SimpleNamespace(
            high_ductility_applies=False,
            limited_ductility_applies=True,
            material_context=SimpleNamespace(
                component_id=COMPONENT,
                model_fingerprint="model:a37",
            ),
        ),
    )
    monkeypatch.setattr(
        subject,
        "ColumnLongitudinalRuntimeComposition",
        type(runtime),
    )

    state_type = type("FakeState", (), {})
    state = state_type()
    state.component_id = COMPONENT
    monkeypatch.setattr(
        subject,
        "ColumnDemandState",
        state_type,
    )

    free_type = type("FakeFree", (), {})
    free = free_type()
    free.component_id = COMPONENT
    monkeypatch.setattr(
        subject,
        "ColumnFreeLengthResolution",
        free_type,
    )

    with pytest.raises(
        ValueError,
        match="only to proven HIGH",
    ):
        subject.compose_column_p7_runtime(
            component_id=COMPONENT,
            model_fingerprint="model:a37",
            acquisition_context=object(),
            analysis_execution=object(),
            free_length=free,
            demand_states=(state,),
            longitudinal_runtime=runtime,
            reviewed_context=_context(),
        short_column_context=_not_short(),
        )

def test_short_runtime_passes_actual_short_length_into_existing_p7_integration(
    monkeypatch,
):
    bundle = build_column_shear_demand_evidence(
        model_fingerprint="model:a37",
        rows=(_row(),),
        output_names=("COMB1",),
        force_unit=UNIT_KN,
        length_unit=UNIT_M,
        unit_provenance_refs=("UNIT:PROOF",),
    )
    monkeypatch.setattr(
        subject,
        "build_b5_bound_column_shear_evidence",
        lambda **_kwargs: bundle,
    )
    calls = []
    monkeypatch.setattr(
        subject,
        "run_vs6_p7_from_production_evidence",
        lambda **kwargs: calls.append(kwargs)
        or SimpleNamespace(
            component_id=COMPONENT,
            direction=kwargs["capacity_state_selection"].direction,
        ),
    )
    monkeypatch.setattr(
        subject,
        "build_vs6_p7_column_shear_run",
        lambda *, component_id, directions: SimpleNamespace(
            component_id=component_id,
            directions=tuple(directions),
        ),
    )

    material = ColumnSectionMaterial(
        fck_mpa=30.0,
        fcd_mpa=20.0,
        fyd_mpa=365.0,
    )
    material_context = SimpleNamespace(
        component_id=COMPONENT,
        model_fingerprint="model:a37",
        material=material,
        section_material_binding_ref="MAT:BIND",
        binding_ref="MAT:CTX",
        concrete_strength_source_refs=("MAT:FCK",),
        concrete_design_strength_review_refs=("MAT:FCD",),
        steel_design_strength_review_refs=("MAT:FYD",),
    )
    runtime = SimpleNamespace(
        component_id=COMPONENT,
        target_topology=SimpleNamespace(
            component_id=COMPONENT,
            unique_name="101",
        ),
        selection=SimpleNamespace(
            selected=True,
            selected_rebar=object(),
        ),
        bound_design_basis=SimpleNamespace(
            material_context=material_context,
            source_refs=("BASIS:1",),
            high_ductility_applies=False,
            limited_ductility_applies=True,
        ),
    )
    monkeypatch.setattr(
        subject,
        "ColumnLongitudinalRuntimeComposition",
        type(runtime),
    )
    state_type = type("FakeState", (), {})
    states = (state_type(), state_type())
    for item in states:
        item.component_id = COMPONENT
    monkeypatch.setattr(subject, "ColumnDemandState", state_type)
    free_type = type("FakeFree", (), {})
    free = free_type()
    free.component_id = COMPONENT
    monkeypatch.setattr(subject, "ColumnFreeLengthResolution", free_type)

    subject.compose_column_p7_runtime(
        component_id=COMPONENT,
        model_fingerprint="model:a37",
        acquisition_context=object(),
        analysis_execution=object(),
        free_length=free,
        demand_states=states,
        longitudinal_runtime=runtime,
        reviewed_context=_context(),
        short_column_context=_short(),
    )

    assert len(calls) == 2
    assert all(item["short_column_applies"] is True for item in calls)
    assert all(
        item["short_free_length_mm"] == pytest.approx(900.0)
        for item in calls
    )
    assert all(
        item["short_basis_refs"] == ("REVIEW:SHORT:7.3.8",)
        for item in calls
    )


def test_short_context_is_not_added_to_request_dtos():
    forbidden = {
        "reviewed_column_short_column_context",
        "short_free_length_mm",
        "short_column_applies",
    }
    assert forbidden.isdisjoint(
        {item.name for item in fields(ColumnExecutionRequest)}
    )
    assert forbidden.isdisjoint(
        {item.name for item in fields(ProjectExecutionRequest)}
    )
