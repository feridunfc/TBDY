from __future__ import annotations

import json

import pytest

from tbdy_engine.features.population_audit import (
    BLOCKED_COMPONENT_TYPE_AMBIGUOUS,
    BLOCKED_COMPONENT_TYPE_MISSING,
    BLOCKED_SECTION_ASSIGNMENT_MISSING,
    BLOCKED_SECTION_DEFINITION_READ_FAILURE,
    BLOCKED_SUPPORTED_SECTION_GEOMETRY_UNRESOLVED,
    IN_SCOPE_CONCRETE_RECTANGULAR_BEAM,
    IN_SCOPE_CONCRETE_RECTANGULAR_COLUMN,
    OUT_OF_SCOPE_BRACE,
    OUT_OF_SCOPE_NULL_FRAME,
    OUT_OF_SCOPE_STEEL_SECTION,
    OUT_OF_SCOPE_UNSUPPORTED_SECTION_FAMILY,
    PopulationAudit,
    PopulationAuditRow,
    PopulationDisposition,
    build_population_audit,
    canonical_population_audit_json,
)


def _source_row(
    component_id: str,
    component_type: str | None,
    *,
    label: str | None = None,
    story: str | None = "+14.5",
    analysis_section: str | None = None,
    design_section: str | None = None,
) -> dict[str, object]:
    row: dict[str, object] = {
        "UniqueName": component_id,
        "AnalysisSect": analysis_section,
        "DesignSect": design_section,
    }
    if label is not None:
        row["Label"] = label
    if story is not None:
        row["Story"] = story
    if component_type is not None:
        row["Type"] = component_type
    return row


def _assignment(
    component_id: str,
    section: str,
    shape: str | None,
    *,
    label: str | None = None,
    story: str = "+14.5",
) -> dict[str, object]:
    return {
        "UniqueName": component_id,
        "Story": story,
        "Label": label or component_id,
        "SectProp": section,
        "Shape": shape,
    }


def _property(section: str, width: object = 400.0, depth: object = 700.0) -> dict[str, object]:
    return {"Name": section, "t2": width, "t3": depth, "unit": "mm"}


def _audit(source_rows, *, assignments=(), properties=()) -> PopulationAudit:
    return build_population_audit(
        source_rows=source_rows,
        assignment_rows=assignments,
        property_rows=properties,
    )


def test_summary_shape_is_not_required_and_assignment_evidence_is_joined_by_unique_name():
    summary = _source_row(
        "297",
        "Beam",
        label=None,
        story=None,
        analysis_section="B40x70",
        design_section="B40x70",
    )
    assignment = _assignment(
        "297",
        "B40x70",
        "Rectangular",
        label="B1",
        story="+14.5",
    )

    assert "Shape" not in summary
    audit = _audit([summary], assignments=[assignment], properties=[_property("B40x70")])
    row = audit.rows[0]

    assert row.disposition is PopulationDisposition.IN_SCOPE
    assert row.reason_code == IN_SCOPE_CONCRETE_RECTANGULAR_BEAM
    assert row.assigned_section == "B40x70"
    assert row.section_shape == "Rectangular"
    assert row.story == "+14.5"
    assert row.label == "B1"
    assert row.analysis_section == "B40x70"
    assert row.design_section == "B40x70"


def test_concrete_column_joins_assignment_and_accepts_concrete_rectangular_shape():
    summary = _source_row("301", "Column", analysis_section="C50x60", design_section="C50x60")
    assignment = _assignment("301", "C50x60", "Concrete Rectangular")

    audit = _audit([summary], assignments=[assignment], properties=[_property("C50x60", 500.0, 600.0)])

    assert "Shape" not in summary
    assert audit.rows[0].disposition is PopulationDisposition.IN_SCOPE
    assert audit.rows[0].reason_code == IN_SCOPE_CONCRETE_RECTANGULAR_COLUMN
    assert audit.rows[0].section_shape == "Concrete Rectangular"


def test_steel_beam_shape_comes_from_assignment_and_is_out_of_scope():
    summary = _source_row("ST-1", "Beam", analysis_section="HE160A", design_section="HE160A")
    assignment = _assignment("ST-1", "HE160A", "Steel I/Wide Flange")

    audit = _audit([summary], assignments=[assignment])

    assert "Shape" not in summary
    assert audit.rows[0].disposition is PopulationDisposition.OUT_OF_SCOPE
    assert audit.rows[0].reason_code == OUT_OF_SCOPE_STEEL_SECTION
    assert audit.rows[0].assigned_section == "HE160A"
    assert audit.rows[0].section_shape == "Steel I/Wide Flange"


def test_other_explicit_steel_shape_marker_is_out_of_scope():
    audit = _audit(
        [_source_row("ST-PIPE", "Column")],
        assignments=[_assignment("ST-PIPE", "PIPE-1", "Steel Pipe")],
    )

    assert audit.rows[0].reason_code == OUT_OF_SCOPE_STEEL_SECTION


def test_null_and_brace_need_no_assignment_or_shape():
    audit = _audit(
        [
            _source_row("NULL-1", "Null"),
            _source_row("BR-1", "Brace", analysis_section="DN40", design_section="DN40"),
        ]
    )
    rows = {row.component_id: row for row in audit.rows}

    assert rows["NULL-1"].reason_code == OUT_OF_SCOPE_NULL_FRAME
    assert rows["BR-1"].reason_code == OUT_OF_SCOPE_BRACE
    assert audit.out_of_scope_row_count == 2
    assert audit.blocked_row_count == 0


def test_explicit_non_concrete_non_steel_shape_is_unsupported_out_of_scope():
    audit = _audit(
        [_source_row("AL-1", "Beam")],
        assignments=[_assignment("AL-1", "AL-BOX", "Aluminum Box")],
    )

    assert audit.rows[0].reason_code == OUT_OF_SCOPE_UNSUPPORTED_SECTION_FAMILY


def test_supported_concrete_row_with_missing_assignment_is_blocked():
    audit = _audit([_source_row("297", "Beam")], properties=[_property("B40x70")])

    assert audit.rows[0].disposition is PopulationDisposition.BLOCKED
    assert audit.rows[0].reason_code == BLOCKED_SECTION_ASSIGNMENT_MISSING


def test_property_definition_read_failure_blocks_possible_concrete_candidate():
    audit = build_population_audit(
        source_rows=[_source_row("297", "Beam")],
        assignment_rows=[_assignment("297", "B40x70", "Rectangular")],
        property_rows=(),
        property_definition_read_failed=True,
    )

    assert audit.rows[0].reason_code == BLOCKED_SECTION_DEFINITION_READ_FAILURE


def test_supported_concrete_row_with_unresolved_property_is_blocked():
    audit = _audit(
        [_source_row("297", "Beam")],
        assignments=[_assignment("297", "B40x70", "Concrete Rectangular")],
        properties=[_property("OTHER")],
    )

    assert audit.rows[0].reason_code == BLOCKED_SUPPORTED_SECTION_GEOMETRY_UNRESOLVED


def test_resolved_component_id_controls_final_supported_geometry_disposition():
    source = [_source_row("297", "Beam")]
    assignments = [_assignment("297", "B40x70", "Rectangular")]
    properties = [_property("B40x70")]

    resolved = build_population_audit(
        source_rows=source,
        assignment_rows=assignments,
        property_rows=properties,
        resolved_geometry_component_ids=frozenset({"297"}),
    )
    unresolved = build_population_audit(
        source_rows=source,
        assignment_rows=assignments,
        property_rows=properties,
        resolved_geometry_component_ids=frozenset(),
    )

    assert resolved.rows[0].reason_code == IN_SCOPE_CONCRETE_RECTANGULAR_BEAM
    assert unresolved.rows[0].reason_code == BLOCKED_SUPPORTED_SECTION_GEOMETRY_UNRESOLVED


def test_missing_and_unknown_types_remain_blocked():
    audit = _audit(
        [
            _source_row("MISSING-TYPE", None),
            _source_row("W1", "Wall"),
        ]
    )
    rows = {row.component_id: row for row in audit.rows}

    assert rows["MISSING-TYPE"].reason_code == BLOCKED_COMPONENT_TYPE_MISSING
    assert rows["W1"].reason_code == BLOCKED_COMPONENT_TYPE_AMBIGUOUS


def test_population_counts_reconcile_exactly():
    audit = _audit(
        [
            _source_row("297", "Beam"),
            _source_row("NULL-1", "Null"),
            _source_row("UNKNOWN-1", "Unknown"),
        ],
        assignments=[_assignment("297", "B40x70", "Rectangular")],
        properties=[_property("B40x70")],
    )

    assert audit.source_row_count == 3
    assert audit.in_scope_row_count == 1
    assert audit.out_of_scope_row_count == 1
    assert audit.blocked_row_count == 1
    assert audit.source_row_count == (
        audit.in_scope_row_count + audit.out_of_scope_row_count + audit.blocked_row_count
    )
    assert sum(audit.disposition_counts.values()) == audit.source_row_count
    assert sum(audit.reason_counts.values()) == audit.source_row_count


def test_conflicting_assignment_evidence_fails_closed_as_missing_assignment():
    audit = _audit(
        [_source_row("297", "Beam")],
        assignments=[
            _assignment("297", "B40x70", "Rectangular"),
            _assignment("297", "B50x80", "Rectangular"),
        ],
        properties=[_property("B40x70"), _property("B50x80", 500.0, 800.0)],
    )

    assert audit.rows[0].reason_code == BLOCKED_SECTION_ASSIGNMENT_MISSING


def test_duplicate_non_empty_component_ids_fail_closed():
    rows = (
        PopulationAuditRow(
            component_id="297",
            label="B1",
            story="+14.5",
            raw_component_type="Beam",
            assigned_section="B40x70",
            analysis_section="B40x70",
            design_section="B40x70",
            section_shape="Rectangular",
            disposition=PopulationDisposition.IN_SCOPE,
            reason_code=IN_SCOPE_CONCRETE_RECTANGULAR_BEAM,
            source_table="Frame Assignments - Summary",
        ),
        PopulationAuditRow(
            component_id="297",
            label="B2",
            story="+11.0",
            raw_component_type="Beam",
            assigned_section="B40x70",
            analysis_section="B40x70",
            design_section="B40x70",
            section_shape="Rectangular",
            disposition=PopulationDisposition.IN_SCOPE,
            reason_code=IN_SCOPE_CONCRETE_RECTANGULAR_BEAM,
            source_table="Frame Assignments - Summary",
        ),
    )

    with pytest.raises(ValueError, match="Duplicate non-empty population component IDs"):
        PopulationAudit(rows)


def test_json_serialization_is_deterministic_and_contains_no_engineering_verdict_fields():
    source_rows = [
        _source_row("B", "Beam"),
        _source_row("A", "Null"),
    ]
    assignments = [_assignment("B", "B40x70", "Rectangular")]
    properties = [_property("B40x70")]
    audit_a = _audit(source_rows, assignments=assignments, properties=properties)
    audit_b = _audit(list(reversed(source_rows)), assignments=assignments, properties=properties)

    first = canonical_population_audit_json(audit_a)
    second = canonical_population_audit_json(audit_b)
    assert first == second
    assert first.endswith("\n")
    payload = json.loads(first)
    assert [row["component_id"] for row in payload["rows"]] == ["A", "B"]
    forbidden = {"CheckResult", "ratio", "limit", "formula", "pass_rule", "PASS", "FAIL"}
    assert forbidden.isdisjoint(first.split('"'))
