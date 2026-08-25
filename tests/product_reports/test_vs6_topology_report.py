from tbdy_engine.features.column_shear_topology import build_strict_column_topology
from tbdy_engine.product_reports.vs6_topology_report import (
    build_vs6_topology_report_contribution,
)


def _bundle():
    points = [
        {"UniqueName": "P0", "Story": "Base", "X": "0", "Y": "0", "Z": "0"},
        {"UniqueName": "P1", "Story": "L1", "X": "0", "Y": "0", "Z": "3"},
        {"UniqueName": "PX", "Story": "L1", "X": "4", "Y": "0", "Z": "3"},
        {"UniqueName": "PS", "Story": "L1", "X": "0", "Y": "4", "Z": "3"},
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
            "UniquePtJ": "PX",
            "Length": "4",
        },
        {
            "UniqueName": "BST",
            "Story": "L1",
            "BeamBay": "S1",
            "UniquePtI": "P1",
            "UniquePtJ": "PS",
            "Length": "4",
        },
    ]
    assignments = [
        {"UniqueName": "CUID", "Story": "L1", "Label": "C1", "Shape": "Concrete Rectangular", "SectProp": "C80"},
        {"UniqueName": "BRC", "Story": "L1", "Label": "B1", "Shape": "Concrete Rectangular", "SectProp": "B40"},
        {"UniqueName": "BST", "Story": "L1", "Label": "S1", "Shape": "Steel I/Wide Flange", "SectProp": "IPE300"},
    ]
    offsets = [
        {"UniqueName": "CUID", "Story": "L1", "Label": "C1", "OffsetI": "0.2", "OffsetJ": "0.3"},
        {"UniqueName": "BRC", "Story": "L1", "Label": "B1", "OffsetI": "0", "OffsetJ": "0"},
        {"UniqueName": "BST", "Story": "L1", "Label": "S1", "OffsetI": "0", "OffsetJ": "0"},
    ]
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
    )


def test_vs6_topology_report_is_projection_only_and_preserves_ln_boundary():
    contribution = build_vs6_topology_report_contribution(_bundle())
    payload = contribution.as_dict()

    assert payload["contribution_kind"] == "FACTUAL"
    assert payload["status"] == "PROVEN"
    assert payload["calculations"] == []
    assert payload["presentation_contract"]["engineering_recalculation_allowed"] is False

    summary = {item["key"]: item["value"] for item in payload["summary_fields"]}
    assert summary["column_count"] == 1
    assert summary["beam_count"] == 2
    assert summary["supported_rc_beam_count"] == 1
    assert summary["unsupported_beam_count"] == 1
    assert summary["regulatory_ln_status"] == "NOT_PROMOTED_FROM_FACTUAL_CANDIDATE"

    column_row = payload["tables"][0]["rows"][0]
    assert column_row["analysis_clear_length_candidate_m"] == 2.5
    assert column_row["regulatory_ln_status"] == "NOT_PROMOTED_FROM_FACTUAL_CANDIDATE"


def test_vs6_topology_report_preserves_unsupported_attachment_for_later_scope_decision():
    contribution = build_vs6_topology_report_contribution(_bundle())
    payload = contribution.as_dict()

    attachments = payload["tables"][1]["rows"]
    assert len(attachments) == 2
    supported = {row["beam_unique_name"]: row["supported_rc_beam"] for row in attachments}
    assert supported == {"BRC": True, "BST": False}
    assert payload["warnings"]
