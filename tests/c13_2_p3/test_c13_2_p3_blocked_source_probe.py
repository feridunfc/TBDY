from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools" / "probe_c13_2_p3_blocked_sources.py"
sys.path.insert(0, str(ROOT))

from tools import probe_c13_2_p3_blocked_sources as p3


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def run_no_live(tmp_path: Path, *extra: str):
    out = tmp_path / "out"
    cmd = [sys.executable, str(SCRIPT), "--out", str(out), *extra]
    proc = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True)
    return proc, out


def test_no_live_mode_exits_2_and_writes_connection_report(tmp_path: Path):
    proc, out = run_no_live(tmp_path)
    assert proc.returncode == 2
    report = read_json(out / "connection_report.json")
    assert report["live_etabs_connected"] is False
    assert report["probe_passed"] is False


def test_no_live_mode_writes_summary_false_flags(tmp_path: Path):
    proc, out = run_no_live(tmp_path)
    assert proc.returncode == 2
    summary = read_json(out / "c13_2_p3_blocked_source_probe_summary.json")
    assert summary["live_etabs_connected"] is False
    assert summary["safe_to_implement_checks_now"] is False
    assert summary["probe_passed"] is False


@pytest.mark.parametrize("family", ["material_properties", "story_definitions", "pier_section_properties", "all"])
def test_target_family_choices_are_accepted(tmp_path: Path, family: str):
    proc, out = run_no_live(tmp_path, "--target-family", family)
    assert proc.returncode == 2
    summary = read_json(out / "c13_2_p3_blocked_source_probe_summary.json")
    if family == "all":
        assert set(summary["families"]) == set(p3.TARGET_FAMILIES)
    else:
        assert set(summary["families"]) == {family}


def test_exact_matches_are_preferred_over_fallback_keyword_candidates():
    family = p3.TARGET_FAMILIES["story_definitions"]
    available = ["Story Metadata Maybe", "Story Definitions", "Story Data From Other"]
    match = p3.match_target_tables(available, family, max_candidate_tables_per_family=5)
    assert match["match_strategy"] == "exact"
    assert match["selected_tables"] == ["Story Definitions"]
    assert match["fallback_candidates"] == []


def test_candidate_cap_is_applied_before_fetch():
    family = p3.TargetFamily(
        family_id="story_definitions",
        semantic_role="test",
        expected_table_names=("No Exact",),
        fallback_keywords=("Story Definitions",),
        required_columns=("Story", "Height", "Elevation"),
    )
    available = [f"Story Definitions Candidate {i}" for i in range(10)]
    match = p3.match_target_tables(available, family, max_candidate_tables_per_family=3)
    assert len(match["selected_tables"]) == 3
    assert match["candidate_count_before_cap"] == 10
    assert match["candidate_count_after_cap"] == 3
    assert match["candidate_truncation_applied"] is True


def test_target_table_matches_records_cap_fields():
    family = p3.TARGET_FAMILIES["material_properties"]
    available = ["Material Properties - Basic Mechanical Properties"]
    match = p3.match_target_tables(available, family, max_candidate_tables_per_family=5)
    assert "candidate_count_before_cap" in match
    assert "candidate_count_after_cap" in match
    assert "candidate_truncation_applied" in match


def test_material_properties_does_not_accept_material_list_by_story_as_direct_proof():
    family = p3.TARGET_FAMILIES["material_properties"]
    result = p3.evaluate_family_status(
        family,
        ["Material List by Story"],
        {"Material List by Story": ["Story", "Material", "Volume"]},
    )
    assert result["source_status"] == "PARTIAL_CONTEXT_ONLY"
    assert "E1" in result["required_columns_missing"]
    assert "Material List" in result["semantic_risks"][0]


def test_material_properties_accepts_basic_mechanical_headers_as_candidate():
    family = p3.TARGET_FAMILIES["material_properties"]
    result = p3.evaluate_family_status(
        family,
        ["Material Properties - Basic Mechanical Properties"],
        {"Material Properties - Basic Mechanical Properties": ["Material", "E1", "G12", "U12"]},
    )
    assert result["source_status"] == "VERIFIED_LIVE_CANDIDATE"


def test_pier_assignments_alone_is_partial_context_only():
    family = p3.TARGET_FAMILIES["pier_section_properties"]
    result = p3.evaluate_family_status(
        family,
        ["Pier Assignments"],
        {"Pier Assignments": ["Story", "Pier", "Label"]},
    )
    assert result["source_status"] == "PARTIAL_CONTEXT_ONLY"
    assert result["promotion_recommendation"].startswith("Do not promote")


def test_pier_section_properties_direct_section_and_geometry_proof_is_candidate():
    family = p3.TARGET_FAMILIES["pier_section_properties"]
    result = p3.evaluate_family_status(
        family,
        ["Pier Section Properties"],
        {"Pier Section Properties": ["Story", "Pier", "Section", "Width Bottom", "Thickness Bottom", "Material"]},
    )
    assert result["source_status"] == "VERIFIED_LIVE_CANDIDATE"
    assert result["direct_section_geometry_present"] is True
    assert result["section_name_column_present"] is True


def test_story_definitions_requires_story_height_elevation_for_candidate():
    family = p3.TARGET_FAMILIES["story_definitions"]
    result = p3.evaluate_family_status(
        family,
        ["Story Definitions"],
        {"Story Definitions": ["Story", "Height", "Elevation"]},
    )
    assert result["source_status"] == "VERIFIED_LIVE_CANDIDATE"


def test_story_definitions_missing_elevation_stays_needs_live_probe():
    family = p3.TARGET_FAMILIES["story_definitions"]
    result = p3.evaluate_family_status(
        family,
        ["Story Definitions"],
        {"Story Definitions": ["Story", "Height"]},
    )
    assert result["source_status"] == "NEEDS_LIVE_PROBE"
    assert "Elevation" in result["required_columns_missing"]


def test_summary_never_sets_check_unlock_allowed_true():
    matches = {"story_definitions": {"selected_tables": ["Story Definitions"]}}
    summary = p3.build_summary(
        live_etabs_connected=True,
        probe_passed=True,
        family_ids=["story_definitions"],
        matches=matches,
        headers_by_table={"Story Definitions": ["Story", "Height", "Elevation"]},
    )
    assert summary["families"]["story_definitions"]["check_unlock_allowed"] is False


def test_summary_never_sets_safe_to_implement_checks_now_true():
    matches = {"story_definitions": {"selected_tables": ["Story Definitions"]}}
    summary = p3.build_summary(
        live_etabs_connected=True,
        probe_passed=True,
        family_ids=["story_definitions"],
        matches=matches,
        headers_by_table={"Story Definitions": ["Story", "Height", "Elevation"]},
    )
    assert summary["safe_to_implement_checks_now"] is False


def test_promotion_recommendations_never_promote_now():
    matches = {"story_definitions": {"selected_tables": ["Story Definitions"]}}
    summary = p3.build_summary(
        live_etabs_connected=True,
        probe_passed=True,
        family_ids=["story_definitions"],
        matches=matches,
        headers_by_table={"Story Definitions": ["Story", "Height", "Elevation"]},
    )
    recommendations = p3.build_promotion_recommendations(summary)
    assert recommendations["promote_now"] is False
    assert recommendations["safe_to_implement_checks_now"] is False


def test_script_compiles():
    proc = subprocess.run([sys.executable, "-m", "py_compile", str(SCRIPT)], cwd=ROOT)
    assert proc.returncode == 0


def test_story_definitions_expected_tables_include_tower_and_base_story_definition():
    family = p3.TARGET_FAMILIES["story_definitions"]
    assert "Tower and Base Story Definition" in family.expected_table_names


def test_story_definitions_combined_story_height_and_bselev_is_candidate():
    family = p3.TARGET_FAMILIES["story_definitions"]
    result = p3.evaluate_family_status(
        family,
        ["Story Definitions", "Tower and Base Story Definition"],
        {
            "Story Definitions": ["Name", "Height", "MasterStory"],
            "Tower and Base Story Definition": ["Tower", "BSElev"],
        },
    )
    assert result["source_status"] == "VERIFIED_LIVE_CANDIDATE"
    assert result["derived_elevation_supported"] is True
    assert result["elevation_is_direct_column"] is False
    assert result["required_columns_missing"] == []


def test_story_definitions_summary_records_combined_elevation_flags():
    matches = {"story_definitions": {"selected_tables": ["Story Definitions", "Tower and Base Story Definition"]}}
    summary = p3.build_summary(
        live_etabs_connected=True,
        probe_passed=True,
        family_ids=["story_definitions"],
        matches=matches,
        headers_by_table={
            "Story Definitions": ["Story", "Height"],
            "Tower and Base Story Definition": ["BSElev"],
        },
    )
    story = summary["families"]["story_definitions"]
    assert story["source_status"] == "VERIFIED_LIVE_CANDIDATE"
    assert story["derived_elevation_supported"] is True
    assert story["elevation_is_direct_column"] is False
    assert story["check_unlock_allowed"] is False
    assert summary["safe_to_implement_checks_now"] is False


def test_pier_section_properties_direct_geometry_without_section_column_is_candidate():
    family = p3.TARGET_FAMILIES["pier_section_properties"]
    result = p3.evaluate_family_status(
        family,
        ["Pier Section Properties"],
        {"Pier Section Properties": ["Story", "Pier", "Width Bottom", "Thickness Bottom", "Material"]},
    )
    assert result["source_status"] == "VERIFIED_LIVE_CANDIDATE"
    assert result["direct_section_geometry_present"] is True
    assert result["section_name_column_present"] is False
    assert result["material_present"] is True
    assert result["required_columns_missing"] == []


def test_wall_object_connectivity_alone_is_partial_context_only():
    family = p3.TARGET_FAMILIES["pier_section_properties"]
    result = p3.evaluate_family_status(
        family,
        ["Wall Object Connectivity"],
        {"Wall Object Connectivity": ["Story", "Pier", "Wall", "Point1", "Point2"]},
    )
    assert result["source_status"] == "PARTIAL_CONTEXT_ONLY"
    assert result["direct_section_geometry_present"] is False
    assert result["promotion_recommendation"].startswith("Do not promote")


def test_area_pier_and_section_assigns_without_direct_pier_geometry_stay_partial():
    family = p3.TARGET_FAMILIES["pier_section_properties"]
    result = p3.evaluate_family_status(
        family,
        ["Area Assigns - Pier Labels", "Area Assigns - Sect Prop"],
        {
            "Area Assigns - Pier Labels": ["Story", "Pier", "Area"],
            "Area Assigns - Sect Prop": ["Story", "Area", "Section"],
        },
    )
    assert result["source_status"] == "PARTIAL_CONTEXT_ONLY"
    assert result["direct_section_geometry_present"] is False
    assert result["direct_pier_section_table"] is None


def test_area_context_plus_direct_pier_geometry_becomes_candidate():
    family = p3.TARGET_FAMILIES["pier_section_properties"]
    result = p3.evaluate_family_status(
        family,
        ["Area Assigns - Pier Labels", "Area Assigns - Sect Prop", "Pier Section Properties"],
        {
            "Area Assigns - Pier Labels": ["Story", "Pier", "Area"],
            "Area Assigns - Sect Prop": ["Story", "Area", "Section"],
            "Pier Section Properties": ["Story", "Pier", "Width Top", "Thickness Top"],
        },
    )
    assert result["source_status"] == "VERIFIED_LIVE_CANDIDATE"
    assert result["direct_section_geometry_present"] is True
    assert result["material_present"] is False


def test_pier_supporting_exact_table_names_are_bounded_targets():
    family = p3.TARGET_FAMILIES["pier_section_properties"]
    for table_name in (
        "Wall Bays",
        "Wall Object Connectivity",
        "Area Assigns - Pier Labels",
        "Area Assigns - Sect Prop",
        "Wall Property Def - Specified",
        "Area Section Props - Summary",
    ):
        assert table_name in family.expected_table_names


def test_pier_summary_records_direct_geometry_flags_and_keeps_unlock_false():
    matches = {"pier_section_properties": {"selected_tables": ["Pier Section Properties"]}}
    summary = p3.build_summary(
        live_etabs_connected=True,
        probe_passed=True,
        family_ids=["pier_section_properties"],
        matches=matches,
        headers_by_table={"Pier Section Properties": ["Story", "Pier", "Width Bottom", "Thickness Bottom", "Material"]},
    )
    pier = summary["families"]["pier_section_properties"]
    assert pier["source_status"] == "VERIFIED_LIVE_CANDIDATE"
    assert pier["direct_section_geometry_present"] is True
    assert pier["section_name_column_present"] is False
    assert pier["material_present"] is True
    assert pier["check_unlock_allowed"] is False
    assert summary["safe_to_implement_checks_now"] is False
