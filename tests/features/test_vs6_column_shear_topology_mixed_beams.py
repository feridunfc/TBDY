from tbdy_engine.features.column_shear_topology import build_strict_column_topology


def test_non_rc_beam_is_preserved_without_blocking_rc_column_topology():
    points = [
        {"UniqueName": "P0", "Story": "Base", "X": "0", "Y": "0", "Z": "0"},
        {"UniqueName": "P1", "Story": "L1", "X": "0", "Y": "0", "Z": "3"},
        {"UniqueName": "PRC", "Story": "L1", "X": "4", "Y": "0", "Z": "3"},
        {"UniqueName": "PST", "Story": "L1", "X": "0", "Y": "4", "Z": "3"},
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
            "UniqueName": "BRC",
            "Story": "L1",
            "BeamBay": "B1",
            "UniquePtI": "P1",
            "UniquePtJ": "PRC",
            "Length": "4",
        },
        {
            "UniqueName": "BST",
            "Story": "L1",
            "BeamBay": "B2",
            "UniquePtI": "P1",
            "UniquePtJ": "PST",
            "Length": "4",
        },
    ]
    assignments = [
        {"UniqueName": "CUID", "Story": "L1", "Label": "C1", "Shape": "Concrete Rectangular", "SectProp": "C80"},
        {"UniqueName": "BRC", "Story": "L1", "Label": "B1", "Shape": "Concrete Rectangular", "SectProp": "B40"},
        {"UniqueName": "BST", "Story": "L1", "Label": "B2", "Shape": "Steel I/Wide Flange", "SectProp": "IPE200"},
    ]
    offsets = [
        {"UniqueName": "CUID", "Story": "L1", "Label": "C1", "OffsetI": "0", "OffsetJ": "0"},
        {"UniqueName": "BRC", "Story": "L1", "Label": "B1", "OffsetI": "0", "OffsetJ": "0"},
        {"UniqueName": "BST", "Story": "L1", "Label": "B2", "OffsetI": "0", "OffsetJ": "0"},
    ]
    sections = [
        {"Name": "C80", "DesignType": "Column", "t2": "0.8", "t3": "0.8"},
        {"Name": "B40", "DesignType": "Beam", "t2": "0.4", "t3": "0.7"},
    ]

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

    summary = bundle.summary()
    assert summary["beam_count"] == 2
    assert summary["supported_rc_beam_count"] == 1
    assert summary["unsupported_beam_count"] == 1
    assert summary["columns_with_unsupported_beam_attachments"] == 1
    assert summary["rc_beam_capacity_attachment_status"] == "REQUIRES_SCOPE_CLASSIFICATION"

    col = bundle.column("CUID")
    top = {item.beam_unique_name: item for item in col.beams_at_top}
    assert set(top) == {"BRC", "BST"}
    assert top["BRC"].is_supported_rc_beam is True
    assert top["BRC"].width_t2_m == 0.4
    assert top["BST"].is_supported_rc_beam is False
    assert top["BST"].shape == "Steel I/Wide Flange"
    assert top["BST"].section == "IPE200"
    assert top["BST"].width_t2_m is None
    assert top["BST"].depth_t3_m is None
    assert col.as_dict()["rc_beam_capacity_attachment_status"] == "REQUIRES_SCOPE_CLASSIFICATION"
