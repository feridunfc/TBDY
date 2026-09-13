import pytest

from tbdy_engine.design.columns.local_axis_sway_binding import (
    BLOCKED_SWAY,
    GlobalSwayDirectionEvidence,
    LOCAL_SWAY_NOT_PROVEN,
    LOCAL_SWAY_PREVENTED,
    NOT_PROVEN_SWAY_PREVENTED,
    PROVEN_SWAY_PREVENTED,
    bind_global_sway_to_column_local_axes,
)


def _g(direction, status=PROVEN_SWAY_PREVENTED):
    return GlobalSwayDirectionEvidence(
        direction=direction,
        status=status,
        source_refs=(f"story:{direction}:{status}",),
    )


def test_zero_angle_does_not_assume_x_is_m2():
    result = bind_global_sway_to_column_local_axes(
        component_id="S1:C1:1",
        local_axis_angle_deg=0.0,
        local_axis_source_refs=("ETABS:FrameLocalAxes:C1:0deg",),
        global_x=_g("X"),
        global_y=_g("Y"),
    )
    assert result.m3.contributing_global_directions == ("X",)
    assert result.m2.contributing_global_directions == ("Y",)
    assert result.m2.status == LOCAL_SWAY_PREVENTED
    assert result.m3.status == LOCAL_SWAY_PREVENTED


def test_ninety_degree_angle_swaps_global_contributors():
    result = bind_global_sway_to_column_local_axes(
        component_id="S1:C1:1",
        local_axis_angle_deg=90.0,
        local_axis_source_refs=("ETABS:FrameLocalAxes:C1:90deg",),
        global_x=_g("X"),
        global_y=_g("Y"),
    )
    assert result.m3.contributing_global_directions == ("Y",)
    assert result.m2.contributing_global_directions == ("X",)


def test_rotated_axis_requires_both_global_proofs_when_both_project():
    result = bind_global_sway_to_column_local_axes(
        component_id="S1:C1:1",
        local_axis_angle_deg=30.0,
        local_axis_source_refs=("ETABS:FrameLocalAxes:C1:30deg",),
        global_x=_g("X"),
        global_y=_g("Y", NOT_PROVEN_SWAY_PREVENTED),
    )
    assert result.m2.contributing_global_directions == ("X", "Y")
    assert result.m3.contributing_global_directions == ("X", "Y")
    assert result.m2.status == LOCAL_SWAY_NOT_PROVEN
    assert result.m3.status == LOCAL_SWAY_NOT_PROVEN
    assert result.m2.sway_classification is None
    assert result.m3.sway_classification is None


def test_blocked_global_direction_cannot_be_promoted_to_local_sway_prevented():
    result = bind_global_sway_to_column_local_axes(
        component_id="S1:C1:1",
        local_axis_angle_deg=0.0,
        local_axis_source_refs=("ETABS:FrameLocalAxes:C1:0deg",),
        global_x=_g("X", BLOCKED_SWAY),
        global_y=_g("Y"),
    )
    assert result.m3.status == LOCAL_SWAY_NOT_PROVEN
    assert result.m3.sway_classification is None
    assert result.m2.status == LOCAL_SWAY_PREVENTED


def test_source_refs_retain_local_axis_and_global_evidence():
    result = bind_global_sway_to_column_local_axes(
        component_id="S1:C1:1",
        local_axis_angle_deg=0.0,
        local_axis_source_refs=("ETABS:FrameLocalAxes:C1", "CSI:FRAME_AXIS_CONVENTION"),
        global_x=_g("X"),
        global_y=_g("Y"),
    )
    assert "ETABS:FrameLocalAxes:C1" in result.source_refs
    assert "CSI:FRAME_AXIS_CONVENTION" in result.source_refs
    assert "story:X:PROVEN_SWAY_PREVENTED_BY_TS500_STABILITY_INDEX" in result.m3.source_refs
    assert "story:Y:PROVEN_SWAY_PREVENTED_BY_TS500_STABILITY_INDEX" in result.m2.source_refs
