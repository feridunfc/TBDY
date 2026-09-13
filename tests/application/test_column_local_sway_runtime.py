from types import SimpleNamespace

import tbdy_engine.application.column_local_sway_runtime as runtime
from tbdy_engine.design.columns.local_axis_sway_binding import LOCAL_SWAY_PREVENTED
from tbdy_engine.design.columns.sway_stability import (
    LOAD_BASIS_AUTHORITY,
    STORY_STABILITY_INPUT_AUTHORITY,
    TS500_LOAD_GQE,
    TS500_LOAD_GQW,
    UNCRACKED_SECTION_BASIS_AUTHORITY,
    StoryStabilityIndexEvidence,
)


class _Topology:
    def __init__(self, columns):
        self.columns = tuple(columns)


def _column(angle=30.0):
    return SimpleNamespace(
        component_id="S1:C1:U1",
        story="S1",
        unique_name="U1",
        local_axis_angle_deg=angle,
    )


def _evidence(direction, load_basis, *, drift_mm, source_ref):
    return StoryStabilityIndexEvidence(
        story="S1",
        direction=direction,
        load_basis=load_basis,
        story_height_mm=3000.0,
        relative_story_displacement_mm=drift_mm,
        story_shear_n=100000.0,
        sum_column_axial_design_force_n=500000.0,
        input_authority=STORY_STABILITY_INPUT_AUTHORITY,
        load_basis_authority=LOAD_BASIS_AUTHORITY,
        stiffness_basis="UNCRACKED",
        stiffness_basis_authority=UNCRACKED_SECTION_BASIS_AUTHORITY,
        source_refs=(source_ref,),
    )


def _candidate(direction, evidence):
    return SimpleNamespace(
        story="S1",
        global_direction=direction,
        stability_evidence=evidence,
    )


def test_a17_resolves_unfavorable_load_bases_then_binds_global_xy_to_local_m2_m3(monkeypatch):
    monkeypatch.setattr(runtime, "StrictColumnTopologyBundle", _Topology)
    topology = _Topology((_column(angle=30.0),))
    candidates = (
        _candidate("X", _evidence("X", TS500_LOAD_GQE, drift_mm=5.0, source_ref="x:gqe")),
        _candidate("X", _evidence("X", TS500_LOAD_GQW, drift_mm=6.0, source_ref="x:gqw")),
        _candidate("Y", _evidence("Y", TS500_LOAD_GQE, drift_mm=4.0, source_ref="y:gqe")),
        _candidate("Y", _evidence("Y", TS500_LOAD_GQW, drift_mm=5.5, source_ref="y:gqw")),
    )

    result = runtime.compose_column_local_axis_sway_runtime(
        topology=topology,
        component_id="S1:C1:U1",
        story="S1",
        candidate_runtimes=candidates,
    )

    assert result.status == runtime.STATUS_READY
    assert result.ready_for_fnd2
    assert result.global_x.governing_load_basis == TS500_LOAD_GQW
    assert result.global_y.governing_load_basis == TS500_LOAD_GQW
    assert result.local_binding.m2.status == LOCAL_SWAY_PREVENTED
    assert result.local_binding.m3.status == LOCAL_SWAY_PREVENTED
    assert set(result.local_binding.m2.contributing_global_directions) == {"X", "Y"}
    assert set(result.local_binding.m3.contributing_global_directions) == {"X", "Y"}


def test_a17_does_not_promote_failed_eq713_route_to_sway_permitted(monkeypatch):
    monkeypatch.setattr(runtime, "StrictColumnTopologyBundle", _Topology)
    topology = _Topology((_column(angle=30.0),))
    candidates = (
        _candidate("X", _evidence("X", TS500_LOAD_GQE, drift_mm=5.0, source_ref="x:gqe")),
        _candidate("X", _evidence("X", TS500_LOAD_GQW, drift_mm=25.0, source_ref="x:gqw")),
        _candidate("Y", _evidence("Y", TS500_LOAD_GQE, drift_mm=4.0, source_ref="y:gqe")),
        _candidate("Y", _evidence("Y", TS500_LOAD_GQW, drift_mm=5.5, source_ref="y:gqw")),
    )

    result = runtime.compose_column_local_axis_sway_runtime(
        topology=topology,
        component_id="S1:C1:U1",
        story="S1",
        candidate_runtimes=candidates,
    )

    assert result.status == runtime.STATUS_UNRESOLVED
    assert not result.ready_for_fnd2
    assert result.global_x.status == "NOT_PROVEN_SWAY_PREVENTED_BY_TS500_STABILITY_INDEX"
    assert result.local_binding.m2.sway_classification is None
    assert result.local_binding.m3.sway_classification is None
    assert "SWAY_PERMITTED" not in result.local_binding.m2.status
    assert "SWAY_PERMITTED" not in result.local_binding.m3.status
