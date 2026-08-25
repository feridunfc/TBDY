import math

import pytest

from tbdy_engine.features.column_shear_topology import (
    ColumnShearTopologyError,
    build_strict_column_topology,
)


def _base_rows():
    points = [
        {"UniqueName": "P0", "Story": "Base", "X": "0", "Y": "0", "Z": "0"},
        {"UniqueName": "P1", "Story": "L1", "X": "0", "Y": "0", "Z": "3"},
        {"UniqueName": "PX+", "Story": "L1", "X": "4", "Y": "0", "Z": "3"},
        {"UniqueName": "PX-", "Story": "L1", "X": "-4", "Y": "0", "Z": "3"},
        {"UniqueName": "PB", "Story": "Base", "X": "3", "Y": "0", "Z": "0"},
    ]
    columns = [
        {
            "UniqueName": "CUID",
            "Story": "L1",
            "ColumnBay": "C1",
            "UniquePtI": "P0",
            "UniquePtJ": "P1",
            "Length": "3",
        }
    ]
    beams = [
        {
            "UniqueName": "BPOS",
            "Story": "L1",
            "BeamBay": "B1",
            "UniquePtI": "P1",
            "UniquePtJ": "PX+",
            "Length": "4",
        },
        {
            "UniqueName": "BNEG",
            "Story": "L1",
            "BeamBay": "B2",
            "UniquePtI": "PX-",
            "UniquePtJ": "P1",
            "Length": "4",
        },
        {
            "UniqueName": "BBOT",
            "Story": "Base",
            "BeamBay": "B3",
            "UniquePtI": "P0",
            "UniquePtJ": "PB",
            "Length": "3",
        },
    ]
    assignments = [
        {"UniqueName": "CUID", "Story": "L1", "Label": "C1", "Shape": "Concrete Rectangular", "SectProp": "C80"},
        {"UniqueName": "BPOS", "Story": "L1", "Label": "B1", "Shape": "Concrete Rectangular", "SectProp": "B40"},
        {"UniqueName": "BNEG", "Story": "L1", "Label": "B2", "Shape": "Concrete Rectangular", "SectProp": "B40"},
        {"UniqueName": "BBOT", "Story": "Base", "Label": "B3", "Shape": "Concrete Rectangular", "SectProp": "B40"},
    ]
    offsets = [
        {"UniqueName": "CUID", "Story": "L1", "Label": "C1", "OffsetI": "0.2", "OffsetJ": "0.3"},
        {"UniqueName": "BPOS", "Story": "L1", "Label": "B1", "OffsetI": "0", "OffsetJ": "0"},
        {"UniqueName": "BNEG", "Story": "L1", "Label": "B2", "OffsetI": "0", "OffsetJ": "0"},
        {"UniqueName": "BBOT", "Story": "Base", "Label": "B3", "OffsetI": "0", "OffsetJ": "0"},
    ]
    sections = [
        {"Name": "C80", "DesignType": "Column", "t2": "0.8", "t3": "0.8"},
        {"Name": "B40", "DesignType": "Beam", "t2": "0.4", "t3": "0.7"},
    ]
    return points, columns, beams, assignments, offsets, sections


def test_builds_exact_top_bottom_joint_and_beam_end_mapping():
    points, columns, beams, assignments, offsets, sections = _base_rows()

    bundle = build_strict_column_topology(
        point_rows=points,
        column_rows=columns,
        beam_rows=beams,
        section_assignment_rows=assignments,
        end_offset_rows=offsets,
        local_axis_rows=[{"UniqueName": "CUID", "Story": "L1", "Label": "C1", "Angle": "90"}],
        rectangular_section_rows=sections,
        reviewed_length_unit="m",
    )

    col = bundle.column("CUID")
    assert col.joint_bottom == "P0"
    assert col.joint_top == "P1"
    assert col.offset_bottom_m == 0.2
    assert col.offset_top_m == 0.3
    assert col.analysis_clear_length_candidate_m == pytest.approx(2.5)
    assert col.local_axis_angle_deg == 90.0
    assert col.local_axis_explicit is True

    top = {item.beam_unique_name: item for item in col.beams_at_top}
    assert set(top) == {"BPOS", "BNEG"}
    assert top["BPOS"].connected_end == "I"
    assert top["BNEG"].connected_end == "J"
    assert top["BPOS"].horizontal_azimuth_deg == pytest.approx(0.0)
    assert top["BNEG"].horizontal_azimuth_deg == pytest.approx(180.0)

    bottom = {item.beam_unique_name: item for item in col.beams_at_bottom}
    assert set(bottom) == {"BBOT"}
    assert bottom["BBOT"].connected_end == "I"


def test_reversed_column_i_j_maps_offsets_to_physical_bottom_top():
    points, columns, beams, assignments, offsets, sections = _base_rows()
    columns[0]["UniquePtI"] = "P1"
    columns[0]["UniquePtJ"] = "P0"

    bundle = build_strict_column_topology(
        point_rows=points,
        column_rows=columns,
        beam_rows=beams,
        section_assignment_rows=assignments,
        end_offset_rows=offsets,
        local_axis_rows=[],
        rectangular_section_rows=sections,
        reviewed_length_unit="m",
    )

    col = bundle.column("CUID")
    assert col.joint_bottom == "P0"
    assert col.joint_top == "P1"
    assert col.offset_bottom_m == 0.3
    assert col.offset_top_m == 0.2
    assert col.local_axis_angle_deg is None
    assert col.local_axis_explicit is False


def test_missing_exact_endpoint_fails_closed_without_coordinate_fallback():
    points, columns, beams, assignments, offsets, sections = _base_rows()
    points[:] = [row for row in points if row["UniqueName"] != "P1"]

    with pytest.raises(ColumnShearTopologyError, match="endpoint point missing"):
        build_strict_column_topology(
            point_rows=points,
            column_rows=columns,
            beam_rows=beams,
            section_assignment_rows=assignments,
            end_offset_rows=offsets,
            local_axis_rows=[],
            rectangular_section_rows=sections,
            reviewed_length_unit="m",
        )


def test_section_name_is_never_used_as_dimension_authority():
    points, columns, beams, assignments, offsets, sections = _base_rows()
    assignments[0]["SectProp"] = "C80x80"
    sections[:] = [row for row in sections if row["DesignType"] != "Column"]

    with pytest.raises(ColumnShearTopologyError, match="missing rectangular section definition C80x80"):
        build_strict_column_topology(
            point_rows=points,
            column_rows=columns,
            beam_rows=beams,
            section_assignment_rows=assignments,
            end_offset_rows=offsets,
            local_axis_rows=[],
            rectangular_section_rows=sections,
            reviewed_length_unit="m",
        )


def test_object_coordinate_length_mismatch_fails_closed():
    points, columns, beams, assignments, offsets, sections = _base_rows()
    beams[0]["Length"] = "4.5"

    with pytest.raises(ColumnShearTopologyError, match="object/coordinate length mismatch"):
        build_strict_column_topology(
            point_rows=points,
            column_rows=columns,
            beam_rows=beams,
            section_assignment_rows=assignments,
            end_offset_rows=offsets,
            local_axis_rows=[],
            rectangular_section_rows=sections,
            reviewed_length_unit="m",
        )
