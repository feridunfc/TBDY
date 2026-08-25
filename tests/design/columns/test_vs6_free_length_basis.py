import pytest

from tbdy_engine.design.columns.free_length_basis import (
    FREE_LENGTH_BLOCKED,
    FREE_LENGTH_PROVEN,
    POINT_XY_RESTRAINT,
    RC_BEAM_NETWORK,
    resolve_ts500_column_free_length,
)
from tbdy_engine.features.column_shear_topology import build_strict_column_topology


def _column(*, two_top_directions: bool = True):
    points = [
        {"UniqueName": "P0", "Story": "Base", "X": "0", "Y": "0", "Z": "0"},
        {"UniqueName": "P1", "Story": "L1", "X": "0", "Y": "0", "Z": "3"},
        {"UniqueName": "PX", "Story": "L1", "X": "4", "Y": "0", "Z": "3"},
        {"UniqueName": "PY", "Story": "L1", "X": "0", "Y": "4", "Z": "3"},
    ]
    columns = [{
        "UniqueName": "C1", "Story": "L1", "ColumnBay": "C1",
        "UniquePtI": "P0", "UniquePtJ": "P1", "Length": "3",
    }]
    beams = [{
        "UniqueName": "BX", "Story": "L1", "BeamBay": "B1",
        "UniquePtI": "P1", "UniquePtJ": "PX", "Length": "4",
    }]
    if two_top_directions:
        beams.append({
            "UniqueName": "BY", "Story": "L1", "BeamBay": "B2",
            "UniquePtI": "P1", "UniquePtJ": "PY", "Length": "4",
        })
    assignments = [
        {"UniqueName": "C1", "Story": "L1", "Label": "C1", "Shape": "Concrete Rectangular", "SectProp": "C80"},
        {"UniqueName": "BX", "Story": "L1", "Label": "B1", "Shape": "Concrete Rectangular", "SectProp": "B40"},
    ]
    if two_top_directions:
        assignments.append(
            {"UniqueName": "BY", "Story": "L1", "Label": "B2", "Shape": "Concrete Rectangular", "SectProp": "B40"}
        )
    offsets = [
        {"UniqueName": "C1", "Story": "L1", "Label": "C1", "OffsetI": "0.2", "OffsetJ": "0.3"},
        {"UniqueName": "BX", "Story": "L1", "Label": "B1", "OffsetI": "0", "OffsetJ": "0"},
    ]
    if two_top_directions:
        offsets.append({"UniqueName": "BY", "Story": "L1", "Label": "B2", "OffsetI": "0", "OffsetJ": "0"})
    sections = [
        {"Name": "C80", "DesignType": "Column", "t2": "0.8", "t3": "0.8"},
        {"Name": "B40", "DesignType": "Beam", "t2": "0.4", "t3": "0.7"},
    ]
    return build_strict_column_topology(
        point_rows=points,
        column_rows=columns,
        beam_rows=beams,
        section_assignment_rows=assignments,
        end_offset_rows=offsets,
        local_axis_rows=[],
        rectangular_section_rows=sections,
        reviewed_length_unit="m",
    ).column("C1")


def test_promotes_clear_length_when_bottom_xy_restraint_and_top_rc_beams_span_xy():
    column = _column(two_top_directions=True)
    result = resolve_ts500_column_free_length(
        column,
        bottom_restraint_dofs=(True, True, False, False, False, False),
        top_restraint_dofs=(False, False, False, False, False, False),
        bottom_restraint_source_ref="ETABS:GetRestraint:P0",
        top_restraint_source_ref="ETABS:GetRestraint:P1",
    )

    assert result.status == FREE_LENGTH_PROVEN
    assert result.free_length_ln_mm == pytest.approx(2500.0)
    assert result.factual_candidate_mm == pytest.approx(2500.0)
    assert POINT_XY_RESTRAINT in result.bottom_support.proof_methods
    assert RC_BEAM_NETWORK in result.top_support.proof_methods
    assert result.bottom_support.proven is True
    assert result.top_support.proven is True


def test_does_not_promote_when_top_has_only_one_beam_direction_and_no_restraint():
    column = _column(two_top_directions=False)
    result = resolve_ts500_column_free_length(
        column,
        bottom_restraint_dofs=(True, True, False, False, False, False),
        top_restraint_dofs=(False, False, False, False, False, False),
        bottom_restraint_source_ref="ETABS:GetRestraint:P0",
        top_restraint_source_ref="ETABS:GetRestraint:P1",
    )

    assert result.status == FREE_LENGTH_BLOCKED
    assert result.free_length_ln_mm is None
    assert result.bottom_support.proven is True
    assert result.top_support.proven is False
