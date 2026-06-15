"""C13.2-P1 Excel-guided source verification gate tests.

Offline tests only; no ETABS connection or real Excel workbook required.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import probe_excel_guided_live_contract_sources as probe


def write_inventory(tmp_path: Path, rows: list[dict]) -> Path:
    path = tmp_path / "inventory.json"
    path.write_text(json.dumps({"tables": rows}, ensure_ascii=False), encoding="utf-8")
    return path


def test_parse_only_never_produces_verified_live(tmp_path: Path):
    inventory = write_inventory(tmp_path, [
        {"table_name": "Frame Assignments - Summary", "headers": ["UniqueName", "Label", "Story", "Type", "Design Section"]},
        {"table_name": "Modal Participating Mass Ratios", "headers": ["Mode", "Period", "UX", "UY", "Sum UX", "Sum UY"]},
    ])
    out = tmp_path / "out"
    code = probe.run_probe(
        out=out,
        excel_inventory=None,
        inventory_json=inventory,
        live_etabs=False,
        probe_profile="verification_gate",
        max_candidate_tables_per_family=3,
        max_sample_rows=5,
        preferred_output_case=None,
    )
    assert code == 0
    recs = json.loads((out / "source_promotion_recommendation.json").read_text(encoding="utf-8"))
    assert recs
    assert all(r["recommended_status"] != "VERIFIED_LIVE" for r in recs)
    assert all(r["can_implement_check_now"] is False for r in recs)


def test_excel_table_names_classify_expected_families():
    assert probe.classify_table_family("Frame Assignments - Summary") == "frame_assignments_summary"
    assert probe.classify_table_family("Frame Sec Def - Conc Rect") == "concrete_rectangular_frame_sections"
    assert probe.classify_table_family("Modal Participating Mass Ratios") == "modal_participating_mass"
    assert probe.classify_table_family("Story Max Over Avg Drifts") == "story_max_over_avg_drifts"
    assert probe.classify_table_family("Mat Prop - Concrete Data") == "concrete_material_properties"
    assert probe.classify_table_family("Shear Wall Design Summary - TS 500-2000(R2018)") == "shear_wall_design_summary"


def test_design_output_tables_classify_as_semantic_review():
    for name in [
        "Concrete Beam Design Summary - TS 500-2000(R2018)",
        "Concrete Beam Flexure Envelope - TS 500-2000(R2018)",
        "Concrete Column Design Summary - TS 500-2000(R2018)",
        "Shear Wall Design Summary - TS 500-2000(R2018)",
    ]:
        family_id = probe.classify_table_family(name)
        rule = probe.family_rule(family_id)
        assert rule is not None
        assert rule.semantic_review is True


def test_header_validation_alias_aware():
    headers = ["Unique Name", "Object Label", "Story Name", "Design Type", "Design Section", "Analysis Section", "Width", "Depth", "Output Case", "Max Drift", "Avg Drift"]
    result = probe.validate_expected_headers(headers, ["UniqueName", "Label", "Story", "Type", "DesignSect", "AnalysisSect", "t2", "t3", "OutputCase", "MaxDrift", "AvgDrift"])
    assert result["passed"] is True
    assert result["missing_required"] == []
    assert result["alias_policy_used"] is True


def test_promotion_to_verified_live_requires_headers_and_rows():
    classification_rows = [{"family_id": "frame_assignments_summary", "excel_table_name": "Frame Assignments - Summary", "headers": ["UniqueName"], "row_count": 10}]
    match_rows = [{"family_id": "frame_assignments_summary", "live_table_name": "Frame Assignments - Summary", "match_basis": "exact"}]
    bad_headers = [{"family_id": "frame_assignments_summary", "live_table_name": "Frame Assignments - Summary", "live_headers": ["UniqueName"], "expected_header_validation": {"passed": False}, "live_sample_row_count": 5}]
    rows = probe.build_promotion_rows(classification_rows, match_rows, bad_headers, live_mode=True)
    assert rows[0]["recommended_status"] != "VERIFIED_LIVE"

    good_headers = [{"family_id": "frame_assignments_summary", "live_table_name": "Frame Assignments - Summary", "live_headers": ["UniqueName", "Label", "Story", "Type", "DesignSect"], "expected_header_validation": {"passed": True}, "live_sample_row_count": 3}]
    rows = probe.build_promotion_rows(classification_rows, match_rows, good_headers, live_mode=True)
    assert rows[0]["recommended_status"] == "VERIFIED_LIVE"
    assert rows[0]["can_implement_check_now"] is False


def test_semantic_review_never_verifies_even_with_live_proof():
    classification_rows = [{"family_id": "concrete_beam_design_summary", "excel_table_name": "Concrete Beam Design Summary - TS 500-2000(R2018)", "headers": ["Frame", "Station", "AsTop", "AsBottom"], "row_count": 10}]
    match_rows = [{"family_id": "concrete_beam_design_summary", "live_table_name": "Concrete Beam Design Summary - TS 500-2000(R2018)", "match_basis": "exact"}]
    header_rows = [{"family_id": "concrete_beam_design_summary", "live_table_name": "Concrete Beam Design Summary - TS 500-2000(R2018)", "live_headers": ["Frame", "Station", "AsTop", "AsBottom"], "expected_header_validation": {"passed": True}, "live_sample_row_count": 5}]
    rows = probe.build_promotion_rows(classification_rows, match_rows, header_rows, live_mode=True)
    assert rows[0]["recommended_status"] == "SEMANTIC_REVIEW"
    assert rows[0]["can_expand_contract_now"] is False
    assert rows[0]["can_implement_check_now"] is False


def test_column_geometry_gate_passes_only_when_column_designsect_matches_rectangular_name():
    fetched = {
        "Frame Assignments - Summary": {
            "rows": [
                {"Type": "Beam", "DesignSect": "B40x70"},
                {"Type": "Column", "DesignSect": "Column_80x80", "Label": "C1"},
                {"Type": "Brace", "DesignSect": "BR1"},
                {"Type": "Null", "DesignSect": "None"},
            ]
        },
        "Frame Section Property Definitions - Concrete Rectangular": {
            "rows": [{"Name": "Column_80x80", "t2": "800", "t3": "800"}]
        },
    }
    gate = probe.column_geometry_gate(fetched)
    assert gate["passed"] is True
    assert gate["status"] == "VERIFIED_LIVE_FOR_COLUMN_GEOMETRY_CONTRACT"
    assert gate["type_distribution"]["Brace"] == 1
    assert gate["type_distribution"]["Null"] == 1
    assert gate["missing_column_sections"] == []


def test_column_geometry_gate_fails_when_column_section_missing():
    fetched = {
        "Frame Assignments - Summary": {"rows": [{"Type": "Column", "DesignSect": "Column_80x80"}]},
        "Frame Section Property Definitions - Concrete Rectangular": {"rows": [{"Name": "B40x70"}]},
    }
    gate = probe.column_geometry_gate(fetched)
    assert gate["passed"] is False
    assert gate["status"] == "NEEDS_LIVE_PROBE"
    assert gate["missing_column_sections"] == ["Column_80x80"]


def test_full_expansion_decision_remains_false_if_incomplete():
    decision = probe.expansion_decision_report(
        {"table_count": 1},
        [{"family_id": "story_drifts", "recommended_status": "NEEDS_LIVE_PROBE"}],
        {"passed": False},
        live_mode=True,
    )
    assert decision["full_c13_2_contract_expansion_now"] is False
    assert decision["safe_to_implement_checks_now"] is False
    assert decision["current_safe_check_capacity"]["current_safe_check_count"] == 5


def test_output_artifacts_are_written(tmp_path: Path):
    inventory = write_inventory(tmp_path, [{"table_name": "Frame Assignments - Summary", "headers": ["UniqueName", "Label", "Story", "Type", "DesignSect"]}])
    out = tmp_path / "out"
    code = probe.run_probe(
        out=out,
        excel_inventory=None,
        inventory_json=inventory,
        live_etabs=False,
        probe_profile="current_product",
        max_candidate_tables_per_family=3,
        max_sample_rows=5,
        preferred_output_case=None,
    )
    assert code == 0
    for artifact in probe.ARTIFACT_NAMES:
        assert (out / artifact).exists(), artifact


def test_unknown_profile_returns_argparse_choice_or_value_error():
    try:
        probe.family_rules_for_profile("does_not_exist")
    except ValueError as exc:
        assert "Unknown probe profile" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected ValueError")


def test_verification_gate_only_creates_rows_for_excel_observed_families_by_default(tmp_path: Path):
    inventory = write_inventory(tmp_path, [
        {"table_name": "Frame Assignments - Summary", "headers": ["UniqueName", "Label", "Story", "Type", "DesignSect"]},
    ])
    out = tmp_path / "out_observed_only"
    code = probe.run_probe(
        out=out,
        excel_inventory=None,
        inventory_json=inventory,
        live_etabs=False,
        probe_profile="verification_gate",
        max_candidate_tables_per_family=3,
        max_sample_rows=5,
        preferred_output_case=None,
    )
    assert code == 0
    recs = json.loads((out / "source_promotion_recommendation.json").read_text(encoding="utf-8"))
    assert [r["family_id"] for r in recs] == ["frame_assignments_summary"]
    assert all(r["recommended_status"] != "PLANNED" for r in recs)


def test_include_planned_families_reports_but_does_not_fetch_absent_families(tmp_path: Path):
    inventory = write_inventory(tmp_path, [
        {"table_name": "Frame Assignments - Summary", "headers": ["UniqueName", "Label", "Story", "Type", "DesignSect"]},
    ])
    out = tmp_path / "out_planned"
    code = probe.run_probe(
        out=out,
        excel_inventory=None,
        inventory_json=inventory,
        live_etabs=False,
        probe_profile="current_product",
        max_candidate_tables_per_family=3,
        max_sample_rows=5,
        preferred_output_case=None,
        include_planned_families=True,
    )
    assert code == 0
    matches = json.loads((out / "excel_to_live_table_match_report.json").read_text(encoding="utf-8"))
    planned = [m for m in matches if m.get("planned_absent")]
    assert planned
    assert all(m["live_candidate_tables"] == [] for m in planned)
    assert all(m["planned_live_fetch_allowed"] is False for m in planned)
    recs = json.loads((out / "source_promotion_recommendation.json").read_text(encoding="utf-8"))
    planned_recs = [r for r in recs if r["recommended_status"] == "PLANNED"]
    assert planned_recs
    assert all(r["can_implement_check_now"] is False for r in planned_recs)


def test_connection_report_contains_architecture_guardrail(tmp_path: Path):
    inventory = write_inventory(tmp_path, [
        {"table_name": "Frame Assignments - Summary", "headers": ["UniqueName", "Label", "Story", "Type", "DesignSect"]},
    ])
    out = tmp_path / "out_guardrail"
    code = probe.run_probe(
        out=out,
        excel_inventory=None,
        inventory_json=inventory,
        live_etabs=False,
        probe_profile="verification_gate",
        max_candidate_tables_per_family=3,
        max_sample_rows=5,
        preferred_output_case=None,
    )
    assert code == 0
    report = json.loads((out / "connection_report.json").read_text(encoding="utf-8"))
    guardrail = report["architecture_guardrail"]
    assert guardrail["excel_role"] == "probe_target_inventory_only"
    assert guardrail["excel_is_production_input"] is False
    assert guardrail["catalog_schema_expansion_in_this_sprint"] is False
    assert guardrail["safe_to_implement_checks_now"] is False


def test_promotion_rows_include_excel_and_live_fetch_metadata():
    classification_rows = [{
        "family_id": "frame_assignments_summary",
        "excel_table_name": "Frame Assignments - Summary",
        "headers": ["UniqueName", "Label", "Story", "Type", "DesignSect"],
        "row_count": 10,
    }]
    match_rows = [{
        "family_id": "frame_assignments_summary",
        "live_table_name": None,
        "planned_absent": False,
        "planned_live_fetch_allowed": True,
        "match_basis": "parse_only",
    }]
    rows = probe.build_promotion_rows(classification_rows, match_rows, [], live_mode=False)
    assert set(["observed_in_excel", "planned_without_excel_evidence", "live_fetch_allowed"]) <= set(rows[0])
    assert rows[0]["observed_in_excel"] is True
    assert rows[0]["planned_without_excel_evidence"] is False
    assert rows[0]["live_fetch_allowed"] is True


def test_planned_absent_promotion_metadata_blocks_live_fetch():
    classification_rows = [{
        "family_id": "frame_assignments_summary",
        "excel_table_name": "Frame Assignments - Summary",
        "headers": ["UniqueName", "Label", "Story", "Type", "DesignSect"],
    }]
    match_rows = [{
        "family_id": "modal_participating_mass",
        "live_table_name": None,
        "planned_absent": True,
        "planned_live_fetch_allowed": False,
        "match_basis": "planned_absent",
    }]
    rows = probe.build_promotion_rows(classification_rows, match_rows, [], live_mode=False)
    assert rows[0]["recommended_status"] == "PLANNED"
    assert rows[0]["observed_in_excel"] is False
    assert rows[0]["planned_without_excel_evidence"] is True
    assert rows[0]["live_fetch_allowed"] is False


def test_default_verification_gate_observed_rows_have_metadata(tmp_path: Path):
    inventory = write_inventory(tmp_path, [
        {"table_name": "Frame Assignments - Summary", "headers": ["UniqueName", "Label", "Story", "Type", "DesignSect"]},
    ])
    out = tmp_path / "out_metadata"
    code = probe.run_probe(
        out=out,
        excel_inventory=None,
        inventory_json=inventory,
        live_etabs=False,
        probe_profile="verification_gate",
        max_candidate_tables_per_family=3,
        max_sample_rows=5,
        preferred_output_case=None,
    )
    assert code == 0
    recs = json.loads((out / "source_promotion_recommendation.json").read_text(encoding="utf-8"))
    assert recs
    assert all(r["observed_in_excel"] is True for r in recs)
    assert all(r["planned_without_excel_evidence"] is False for r in recs)
    assert all("live_fetch_allowed" in r for r in recs)


def test_material_properties_not_verified_by_material_list_by_story():
    classification_rows = [{
        "family_id": "material_properties",
        "excel_table_name": "Mat Prop - Basic Mech Props",
        "headers": ["Material", "E1", "G12", "U12"],
    }]
    match_rows = [{
        "family_id": "material_properties",
        "live_table_name": "Material List by Story",
        "planned_absent": False,
        "planned_live_fetch_allowed": True,
        "match_basis": "keyword_or_alias",
    }]
    header_rows = [{
        "family_id": "material_properties",
        "live_table_name": "Material List by Story",
        "live_headers": ["Story", "Material", "Object Type", "Weight"],
        "expected_header_validation": {"passed": True},  # even if a caller over-trusts generic headers
        "live_sample_row_count": 5,
    }]
    rows = probe.build_promotion_rows(classification_rows, match_rows, header_rows, live_mode=True)
    assert rows[0]["recommended_status"] == "NEEDS_LIVE_PROBE"
    assert rows[0]["match_quality"] == "KEYWORD_TABLE_HEADER_MATCH"
    assert any("not basic mechanical material properties" in b for b in rows[0]["blockers"])


def test_frame_section_material_assignments_not_verified_without_material_header():
    classification_rows = [{
        "family_id": "frame_section_material_assignments",
        "excel_table_name": "Frame Prop - Summary",
        "headers": ["Name", "Material", "Shape"],
    }]
    match_rows = [{
        "family_id": "frame_section_material_assignments",
        "live_table_name": "Frame Assignments - Section Properties",
        "planned_absent": False,
        "planned_live_fetch_allowed": True,
        "match_basis": "keyword_or_alias",
    }]
    header_rows = [{
        "family_id": "frame_section_material_assignments",
        "live_table_name": "Frame Assignments - Section Properties",
        "live_headers": ["Story", "Label", "UniqueName", "Shape", "AutoSelect", "SectProp"],
        "expected_header_validation": {"passed": True},  # semantic role still must reject it
        "live_sample_row_count": 5,
    }]
    rows = probe.build_promotion_rows(classification_rows, match_rows, header_rows, live_mode=True)
    assert rows[0]["recommended_status"] == "NEEDS_LIVE_PROBE"
    assert any("section assignment, not material assignment" in b for b in rows[0]["blockers"])
    assert any("missing Material header" in b for b in rows[0]["blockers"])


def test_keyword_table_header_match_alone_cannot_verify_without_header_proof():
    classification_rows = [{
        "family_id": "frame_assignments_summary",
        "excel_table_name": "Frame Assignments - Summary",
        "headers": ["UniqueName", "Label", "Story", "Type", "DesignSect"],
    }]
    match_rows = [{
        "family_id": "frame_assignments_summary",
        "live_table_name": "Some Frame Summary Keyword Match",
        "planned_absent": False,
        "planned_live_fetch_allowed": True,
        "match_basis": "keyword_or_alias",
    }]
    header_rows = [{
        "family_id": "frame_assignments_summary",
        "live_table_name": "Some Frame Summary Keyword Match",
        "live_headers": ["Story", "Label"],
        "expected_header_validation": {"passed": False},
        "live_sample_row_count": 5,
    }]
    rows = probe.build_promotion_rows(classification_rows, match_rows, header_rows, live_mode=True)
    assert rows[0]["match_quality"] == "KEYWORD_TABLE_HEADER_MATCH"
    assert rows[0]["recommended_status"] != "VERIFIED_LIVE"


def test_context_inventory_family_can_verify_but_never_unlock_checks():
    classification_rows = [{
        "family_id": "material_list_by_story",
        "excel_table_name": "Material List by Story",
        "headers": ["Story", "Material"],
    }]
    match_rows = [{
        "family_id": "material_list_by_story",
        "live_table_name": "Material List by Story",
        "planned_absent": False,
        "planned_live_fetch_allowed": True,
        "match_basis": "exact",
    }]
    header_rows = [{
        "family_id": "material_list_by_story",
        "live_table_name": "Material List by Story",
        "live_headers": ["Story", "Material", "Object Type", "Weight"],
        "expected_header_validation": {"passed": True},
        "live_sample_row_count": 5,
    }]
    rows = probe.build_promotion_rows(classification_rows, match_rows, header_rows, live_mode=True)
    assert rows[0]["recommended_status"] == "VERIFIED_LIVE"
    assert rows[0]["source_role"] == "quantity_or_inventory_context_only"
    assert rows[0]["check_unlock_allowed"] is False
    assert rows[0]["can_implement_check_now"] is False


def test_frame_section_material_assignments_absent_from_verified_decision_when_only_section_assignment_live():
    classification_rows = [
        {
            "family_id": "frame_section_material_assignments",
            "excel_table_name": "Frame Prop - Summary",
            "headers": ["Name", "Material", "Shape"],
        },
        {
            "family_id": "frame_section_assignments",
            "excel_table_name": "Frame Assignments - Section Properties",
            "headers": ["Story", "Label", "UniqueName", "SectProp"],
        },
    ]
    match_rows = [
        {
            "family_id": "frame_section_material_assignments",
            "live_table_name": "Frame Assignments - Section Properties",
            "planned_absent": False,
            "planned_live_fetch_allowed": True,
            "match_basis": "keyword_or_alias",
        },
        {
            "family_id": "frame_section_assignments",
            "live_table_name": "Frame Assignments - Section Properties",
            "planned_absent": False,
            "planned_live_fetch_allowed": True,
            "match_basis": "exact",
        },
    ]
    header_rows = [
        {
            "family_id": "frame_section_material_assignments",
            "live_table_name": "Frame Assignments - Section Properties",
            "live_headers": ["Story", "Label", "UniqueName", "Shape", "AutoSelect", "SectProp"],
            "expected_header_validation": {"passed": False},
            "live_sample_row_count": 5,
        },
        {
            "family_id": "frame_section_assignments",
            "live_table_name": "Frame Assignments - Section Properties",
            "live_headers": ["Story", "Label", "UniqueName", "Shape", "AutoSelect", "SectProp"],
            "expected_header_validation": {"passed": True},
            "live_sample_row_count": 5,
        },
    ]
    rows = probe.build_promotion_rows(classification_rows, match_rows, header_rows, live_mode=True)
    by_family = {r["family_id"]: r for r in rows}
    assert by_family["frame_section_material_assignments"]["recommended_status"] == "NEEDS_LIVE_PROBE"
    assert by_family["frame_section_material_assignments"]["can_expand_contract_now"] is False
    assert by_family["frame_section_assignments"]["recommended_status"] == "VERIFIED_LIVE"
    assert by_family["frame_section_assignments"]["source_role"] == "section_assignment_context_only"
    assert by_family["frame_section_assignments"]["check_unlock_allowed"] is False

    decision = probe.expansion_decision_report({"table_count": 2}, rows, {"passed": True}, live_mode=True)
    assert "frame_section_material_assignments" not in decision["verified_live_families"]
    assert "frame_section_material_assignments" in decision["needs_live_probe_families"]
    assert "frame_section_assignments" in decision["verified_live_families"]
    assert decision["safe_to_implement_checks_now"] is False
    assert decision["full_c13_2_contract_expansion_now"] is False


def test_frame_section_material_assignments_blocker_message_is_specific_for_section_assignment_table():
    validation = probe.semantic_source_role_validation(
        "frame_section_material_assignments",
        "Frame Assignments - Section Properties",
        ["Story", "Label", "UniqueName", "Shape", "AutoSelect", "SectProp"],
    )
    assert validation["passed"] is False
    assert "live table proves section assignment, not material assignment; Material header missing" in validation["blockers"]
