from __future__ import annotations

from dataclasses import fields
from types import SimpleNamespace

import pytest

import tbdy_engine.application.column_limited_shear_runtime as subject
from tbdy_engine.application.contracts import (
    ColumnExecutionRequest,
    ProjectExecutionRequest,
)
from tbdy_engine.features.column_shear_demand_evidence import (
    build_column_shear_demand_evidence,
    column_shear_source_identity,
)
from tbdy_engine.regulatory.units import UNIT_KN, UNIT_M


COMPONENT = "S1:C1:101"


def _row():
    return {
        "Story": "S1",
        "Column": "C1",
        "UniqueName": "101",
        "OutputCase": "LD_D_COMB",
        "CaseType": "Combination",
        "StepType": "",
        "StepNumber": None,
        "Station": 0.0,
        "Element": "501",
        "ElemStation": 0.0,
        "P": -300.0,
        "V2": 120.0,
        "V3": -140.0,
        "T": 0.0,
        "M2": 0.0,
        "M3": 0.0,
    }


def _context():
    identity = column_shear_source_identity(_row())
    return subject.ReviewedLimitedColumnShearRuntimeContext(
        component_id=COMPONENT,
        directions=tuple(
            subject.ReviewedLimitedColumnShearDirectionPlan(
                component_id=COMPONENT,
                direction=direction,
                vd_source_identity=identity,
                d_amplified_vertical_plus_earthquake_proven=True,
                authority_ref=(
                    f"REVIEW:LD:D_AMPLIFIED:{direction}"
                ),
                review_refs=(f"REVIEW:{direction}",),
            )
            for direction in ("V2", "V3")
        ),
        review_refs=("REVIEW:LD",),
    )


def test_limited_runtime_binds_exact_b5_row_and_never_calls_high_p7_formula(
    monkeypatch,
):
    bundle = build_column_shear_demand_evidence(
        model_fingerprint="model:a37",
        rows=(_row(),),
        output_names=("LD_D_COMB",),
        force_unit=UNIT_KN,
        length_unit=UNIT_M,
        unit_provenance_refs=("UNIT:PROOF",),
    )
    monkeypatch.setattr(
        subject,
        "build_b5_bound_column_shear_evidence",
        lambda **_kwargs: bundle,
    )

    depth_calls = []
    def depth(**kwargs):
        depth_calls.append(kwargs)
        return SimpleNamespace(
            resolved=True,
            component_id=COMPONENT,
            direction=kwargs["direction"],
            effective_depth_d_mm=450.0,
            web_width_bw_mm=600.0,
            source_refs=(f"D:{kwargs['direction']}",),
        )
    monkeypatch.setattr(
        subject,
        "resolve_selected_rebar_effective_depth",
        depth,
    )

    direction_calls = []
    monkeypatch.setattr(
        subject,
        "run_limited_column_shear_direction",
        lambda **kwargs: direction_calls.append(kwargs)
        or SimpleNamespace(
            component_id=COMPONENT,
            direction=kwargs["direction"],
        ),
    )
    monkeypatch.setattr(
        subject,
        "build_limited_column_shear_run",
        lambda *, component_id, directions: SimpleNamespace(
            component_id=component_id,
            directions=tuple(directions),
        ),
    )

    basis = SimpleNamespace(
        high_ductility_applies=False,
        limited_ductility_applies=True,
        material_context=SimpleNamespace(
            component_id=COMPONENT,
            model_fingerprint="model:a37",
            material=SimpleNamespace(
                fck_mpa=30.0,
                fcd_mpa=20.0,
            ),
            section_material_binding_ref="MAT:BIND",
            binding_ref="MAT:CTX",
            concrete_strength_source_refs=("MAT:FCK",),
            concrete_design_strength_review_refs=("MAT:FCD",),
        ),
        source_refs=("BASIS:LD",),
    )
    runtime = SimpleNamespace(
        component_id=COMPONENT,
        selection=SimpleNamespace(
            selected=True,
            selected_rebar=object(),
        ),
        bound_design_basis=basis,
        target_topology=SimpleNamespace(
            component_id=COMPONENT,
            unique_name="101",
            section="C1",
            story="S1",
            width_t2_m=0.5,
            depth_t3_m=0.6,
        ),
    )
    monkeypatch.setattr(
        subject,
        "ColumnLongitudinalRuntimeComposition",
        type(runtime),
    )

    result = subject.compose_column_limited_shear_runtime(
        component_id=COMPONENT,
        model_fingerprint="model:a37",
        acquisition_context=object(),
        analysis_execution=object(),
        longitudinal_runtime=runtime,
        reviewed_context=_context(),
    )

    assert result.component_id == COMPONENT
    assert len(depth_calls) == 2
    assert len(direction_calls) == 2
    assert {
        call["vd"].demand_kn
        for call in direction_calls
    } == {120.0, 140.0}
    assert all(
        call[
            "d_amplified_vertical_plus_earthquake_proven"
        ] is True
        for call in direction_calls
    )


def test_limited_context_is_not_added_to_request_dtos():
    forbidden = {
        "reviewed_column_limited_shear_context",
        "vd_source_identity",
        "d_amplified_vertical_plus_earthquake_proven",
    }
    assert forbidden.isdisjoint(
        {
            item.name
            for item in fields(ColumnExecutionRequest)
        }
    )
    assert forbidden.isdisjoint(
        {
            item.name
            for item in fields(ProjectExecutionRequest)
        }
    )
