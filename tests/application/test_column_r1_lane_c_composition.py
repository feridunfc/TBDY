from __future__ import annotations

from types import SimpleNamespace

import pytest

import tbdy_engine.application.column_execution as subject
from tbdy_engine.regulatory.column_transverse_confinement import (
    ColumnTransverseConfinementInput,
    TransverseDirectionFacts,
)
from tbdy_engine.regulatory.vs6_column_shear_p7_program import VS6P7ColumnShearRun


def _column(component_id="Story1:C1:10"):
    return subject.ColumnDomainArtifact(
        component_id=component_id,
        model_fingerprint="model:test",
        evidence_epoch_id="epoch:test",
        status=subject.STATUS_SELECTED,
        blockers=(),
        longitudinal_selection=SimpleNamespace(selected_rebar=None),
    )


def _transverse(component_id="Story1:C1:10"):
    return ColumnTransverseConfinementInput(
        component_id=component_id,
        story="Story1",
        section="C50x80",
        high_ductility_applies=True,
        cantilever_column=False,
        clear_height_mm=3000.0,
        width_mm=500.0,
        depth_mm=800.0,
        gross_area_ac_mm2=400000.0,
        confined_core_area_ack_mm2=300000.0,
        fck_mpa=30.0,
        fywk_mpa=420.0,
        axial_design_force_nd_n=1000000.0,
        transverse_diameter_mm=8.0,
        confinement_spacing_mm=100.0,
        middle_spacing_mm=150.0,
        provided_confinement_region_length_mm=1200.0,
        directions=(
            TransverseDirectionFacts("DIR2", 420.0, 1000.0, 200.0, ("D2",)),
            TransverseDirectionFacts("DIR3", 720.0, 1000.0, 200.0, ("D3",)),
        ),
        arrangement=None,
        source_refs=("FACT:exact",),
    )


def _shear(component_id="Story1:C1:10", directions=("V2", "V3")):
    return VS6P7ColumnShearRun(
        component_id=component_id,
        directions=tuple(
            SimpleNamespace(component_id=component_id, direction=direction)
            for direction in directions
        ),
    )


def test_lane_c_composes_existing_shear_artifact_without_recomputing(monkeypatch):
    transverse_result = SimpleNamespace(
        component_id="Story1:C1:10",
        blockers=(),
    )
    calls = []

    def evaluate(request, *, selected_rebar):
        calls.append((request.component_id, selected_rebar))
        return transverse_result

    monkeypatch.setattr(subject, "evaluate_column_transverse_confinement", evaluate)
    shear = _shear()
    result = subject._compose_lane_c_outputs(
        _column(), transverse_input=_transverse(), column_shear=shear
    )

    assert calls == [("Story1:C1:10", None)]
    assert result.transverse_confinement is transverse_result
    assert result.column_shear is shear
    assert result.status == subject.STATUS_SELECTED
    assert result.blockers == ()


def test_missing_shear_fails_closed_without_inventing_result(monkeypatch):
    monkeypatch.setattr(
        subject,
        "evaluate_column_transverse_confinement",
        lambda *_args, **_kwargs: SimpleNamespace(blockers=()),
    )
    result = subject._compose_lane_c_outputs(
        _column(), transverse_input=_transverse(), column_shear=None
    )
    assert result.column_shear is None
    assert result.status == subject.STATUS_APPLICATION_BLOCKED
    assert result.blockers == (subject.BLOCKER_LANE_C_SHEAR,)


def test_foreign_component_binding_is_rejected_before_composition():
    with pytest.raises(subject.ColumnExecutionContractError, match="transverse component"):
        subject._compose_lane_c_outputs(
            _column(), transverse_input=_transverse("Story1:C2:20"), column_shear=_shear()
        )


def test_foreign_shear_component_is_rejected(monkeypatch):
    monkeypatch.setattr(
        subject,
        "evaluate_column_transverse_confinement",
        lambda *_args, **_kwargs: SimpleNamespace(blockers=()),
    )
    with pytest.raises(subject.ColumnExecutionContractError, match="shear component"):
        subject._compose_lane_c_outputs(
            _column(), transverse_input=_transverse(), column_shear=_shear("Story1:C2:20")
        )


def test_partial_or_duplicate_direction_population_cannot_enter_column_artifact(monkeypatch):
    monkeypatch.setattr(
        subject,
        "evaluate_column_transverse_confinement",
        lambda *_args, **_kwargs: SimpleNamespace(blockers=()),
    )
    with pytest.raises(subject.ColumnExecutionContractError, match="exact V2/V3"):
        subject._compose_lane_c_outputs(
            _column(), transverse_input=_transverse(), column_shear=_shear(directions=("V2",))
        )


def test_production_request_dto_still_has_no_lane_c_engineering_authority():
    from dataclasses import fields
    from tbdy_engine.application.contracts import ColumnExecutionRequest

    assert tuple(item.name for item in fields(ColumnExecutionRequest)) == ("component_id",)
    source = __import__("pathlib").Path(subject.__file__).read_text(encoding="utf-8")
    assert "SapModel" not in source
    assert "StartDesign" not in source
