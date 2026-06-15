"""C13.2-P0 probe hotfix tests.

These tests are offline and do not require live ETABS. They validate the safety
contract for the probe before it is used against a live model.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import Mock, patch

from tools import probe_live_contract_sources as probe


SAMPLE_TABLE_NAMES = [
    "Frame Assignments - Summary",
    "Frame Section Property Definitions - Concrete Rectangular",
    "Modal Participating Mass Ratios",
    "Story Drifts",
    "Story Max Over Avg Drifts",
    "Base Reactions",
    "Material List by Type",
    "Material Properties - Summary",
    "Some Summary Table",
    "Area Assigns - Summary",
    "Concrete Beam Design Summary - TS 500-2000(R2018)",
    "Concrete Beam Flexure Envelope - TS 500-2000(R2018)",
    "Concrete Beam Shear Envelope - TS 500-2000(R2018)",
    "Concrete Column Design Summary - TS 500-2000(R2018)",
    "Shear Wall Design Summary - TS 500-2000(R2018)",
    "Pier Section Properties",
]


def _family(family_id: str) -> probe.SourceFamily:
    return next(family for family in probe.TARGET_SOURCE_FAMILIES if family.family_id == family_id)


def test_script_path_and_default_profile_contract():
    assert probe.PROBE_PROFILES["current_product"]["families"] == [
        "frame_assignments_summary",
        "concrete_rectangular_frame_sections",
        "modal_participating_mass",
    ]


def test_all_profile_family_references_exist():
    known = {family.family_id for family in probe.TARGET_SOURCE_FAMILIES}
    for profile_name, profile in probe.PROBE_PROFILES.items():
        families = profile["families"]
        if families == "all":
            continue
        missing = [family_id for family_id in families if family_id not in known]
        assert not missing, f"{profile_name} references unknown families: {missing}"


def test_missing_required_profile_family_validates_before_etabs_connection(tmp_path: Path):
    probe.PROBE_PROFILES["bad_profile_for_test"] = {"families": ["missing_family"], "timeout_risk": "low"}
    try:
        with patch.object(probe, "ETABSConnection") as connection_cls:
            exit_code = probe.run_live_probe(out=tmp_path, probe_profile="bad_profile_for_test", live_etabs=True)
            assert exit_code == 2
            connection_cls.assert_not_called()
        report = json.loads((tmp_path / "connection_report.json").read_text(encoding="utf-8"))
        assert report["live_etabs_connected"] is False
        assert "unknown family IDs" in report["errors"][0]
    finally:
        probe.PROBE_PROFILES.pop("bad_profile_for_test", None)


def test_exact_only_does_not_keyword_fallback():
    family = probe.SourceFamily(
        "fake_exact_only",
        0,
        "test",
        "exact_only",
        ("Definitely Missing Exact Name",),
        ("Summary", "Material", "Area"),
    )
    match = probe.match_target_tables(SAMPLE_TABLE_NAMES, [family])[0]
    assert match["match_status"] == "NOT_FOUND"
    assert match["matched_tables"] == []
    assert match["candidate_count_before_cap"] == 0


def test_exact_only_when_requested_does_not_keyword_fallback():
    family = probe.SourceFamily(
        "fake_exact_only_when_requested",
        4,
        "test",
        "exact_only_when_requested",
        ("Definitely Missing Design Summary",),
        ("Beam Design", "Summary"),
        semantic_status="SEMANTIC_REVIEW",
    )
    match = probe.match_target_tables(SAMPLE_TABLE_NAMES, [family])[0]
    assert match["match_status"] == "NOT_FOUND"
    assert match["matched_tables"] == []


def test_candidate_cap_is_recorded_before_fetch():
    family = probe.SourceFamily(
        "fake_broad",
        3,
        "test",
        "capped_keyword",
        (),
        ("Material", "Summary"),
    )
    match = probe.match_target_tables(SAMPLE_TABLE_NAMES, [family], max_candidate_tables_per_family=1)[0]
    assert match["candidate_count_after_cap"] <= 1
    if match["candidate_count_before_cap"] > 1:
        assert match["candidate_truncation_applied"] is True


def test_weak_one_word_keyword_alone_does_not_create_fetch_candidate():
    evidence = probe._keyword_evidence("Some Summary Table", ("Summary",))
    assert evidence["is_fetch_candidate"] is False


def test_phrase_keyword_can_create_fetch_candidate():
    evidence = probe._keyword_evidence("Concrete Beam Design Summary", ("Beam Design",))
    assert evidence["is_fetch_candidate"] is True


def test_header_validation_is_alias_aware_for_frame_assignment_aliases():
    headers = ["UniqueName", "Label", "Story", "Design Type", "Design Section", "Analysis Section"]
    validation = probe.expected_header_validation(
        "frame_assignments_summary",
        headers,
        ("UniqueName", "Label", "Story", "Type", "DesignSect"),
        ("AnalysisSect",),
    )
    assert validation["passed"] is True
    assert set(validation["matched_required"]) == {"UniqueName", "Label", "Story", "Type", "DesignSect"}
    assert "AnalysisSect" in validation["matched_optional"]


def test_header_validation_is_alias_aware_for_geometry_aliases():
    validation = probe.expected_header_validation(
        "concrete_rectangular_frame_sections",
        ["Section Name", "Width", "Depth"],
        ("Name", "t2", "t3"),
        (),
    )
    assert validation["passed"] is True


def test_header_validation_is_alias_aware_for_output_case_and_drift_aliases():
    validation = probe.expected_header_validation(
        "story_max_over_avg_drifts",
        ["Story", "Output Case", "Direction", "Max Drift", "Avg Drift", "Ratio"],
        ("Story", "OutputCase", "Direction", "MaxDrift", "AvgDrift", "Ratio"),
        (),
    )
    assert validation["passed"] is True


def test_verified_live_requires_alias_aware_expected_headers():
    family = _family("frame_assignments_summary")
    match = {"family_id": family.family_id, "matched_tables": ["Frame Assignments - Summary"]}
    header_records = [
        {
            "family_id": family.family_id,
            "attempted_table_name": "Frame Assignments - Summary",
            "fetch_status": "FETCHED",
            "headers": ["UniqueName", "Label", "Story", "Design Type", "Design Section"],
        }
    ]
    sample_records = [{"family_id": family.family_id, "sample_row_count": 1}]
    result = probe.classify_source_readiness(family, match, header_records, sample_records)
    assert result["readiness_status"] == "VERIFIED_LIVE"


def test_missing_required_headers_prevents_verified_live():
    family = _family("frame_assignments_summary")
    match = {"family_id": family.family_id, "matched_tables": ["Frame Assignments - Summary"]}
    header_records = [
        {
            "family_id": family.family_id,
            "attempted_table_name": "Frame Assignments - Summary",
            "fetch_status": "FETCHED",
            "headers": ["UniqueName", "Label", "Story"],
        }
    ]
    sample_records = [{"family_id": family.family_id, "sample_row_count": 1}]
    result = probe.classify_source_readiness(family, match, header_records, sample_records)
    assert result["readiness_status"] == "PROBED_PARTIAL"
    assert any("expected header proof failed" in blocker for blocker in result["blockers"])


def test_semantic_review_overrides_verified_live():
    family = _family("concrete_beam_design_summary")
    match = {"family_id": family.family_id, "matched_tables": ["Concrete Beam Design Summary - TS 500-2000(R2018)"]}
    header_records = [
        {
            "family_id": family.family_id,
            "attempted_table_name": "Concrete Beam Design Summary - TS 500-2000(R2018)",
            "fetch_status": "FETCHED",
            "headers": ["Frame", "Station", "AsTop", "AsBottom"],
        }
    ]
    sample_records = [{"family_id": family.family_id, "sample_row_count": 5}]
    result = probe.classify_source_readiness(family, match, header_records, sample_records)
    assert result["readiness_status"] == "SEMANTIC_REVIEW"
    assert result["readiness_status"] != "VERIFIED_LIVE"


def test_missing_profile_families_are_defined_or_removed():
    known = {family.family_id for family in probe.TARGET_SOURCE_FAMILIES}
    assert "concrete_material_properties" in known
    assert "rebar_material_properties" in known
    assert "wall_section_properties" in known


def test_probe_summary_has_required_fields_and_never_allows_checks():
    readiness = [
        {"family_id": "frame_assignments_summary", "readiness_status": "VERIFIED_LIVE"},
        {"family_id": "concrete_beam_design_summary", "readiness_status": "SEMANTIC_REVIEW"},
        {"family_id": "story_drifts", "readiness_status": "PROBED_PARTIAL"},
        {"family_id": "wall_section_properties", "readiness_status": "NEEDS_LIVE_PROBE"},
        {"family_id": "pier_assignments", "readiness_status": "NOT_FOUND"},
    ]
    summary = probe.build_probe_summary(
        probe_profile="current_product",
        live_etabs_connected=True,
        available_table_count=99,
        readiness=readiness,
        recommendation_markdown="# test",
    )
    for field in [
        "probe_passed",
        "live_etabs_connected",
        "available_table_count",
        "verified_live_count",
        "probed_partial_count",
        "needs_live_probe_count",
        "not_found_count",
        "semantic_review_count",
        "recommended_next_sprint",
        "safe_to_expand_contract_now",
        "safe_to_implement_checks_now",
        "generated_artifacts",
    ]:
        assert field in summary
    assert summary["safe_to_implement_checks_now"] is False
    assert summary["verified_live_count"] == 1
    assert summary["probed_partial_count"] == 1
    assert summary["needs_live_probe_count"] == 1
    assert summary["not_found_count"] == 1
    assert summary["semantic_review_count"] == 1


def test_live_false_writes_connection_report_only(tmp_path: Path):
    exit_code = probe.run_live_probe(out=tmp_path, live_etabs=False, probe_profile="current_product")
    assert exit_code == 2
    report = json.loads((tmp_path / "connection_report.json").read_text(encoding="utf-8"))
    assert report["probe_profile"] == "current_product"
    assert report["live_etabs_connected"] is False
    assert "--live-etabs is required." in report["errors"]
    assert not (tmp_path / "available_tables.json").exists()


def test_current_product_profile_matches_only_three_exact_tables():
    ok, errors, families = probe.validate_probe_profile("current_product")
    assert ok, errors
    matches = probe.match_target_tables(SAMPLE_TABLE_NAMES, families, max_candidate_tables_per_family=5)
    attempted = [table for match in matches for table in match["matched_tables"]]
    assert attempted == [
        "Frame Assignments - Summary",
        "Frame Section Property Definitions - Concrete Rectangular",
        "Modal Participating Mass Ratios",
    ]
    assert all(match["fetch_policy"] == "exact_only" for match in matches)


def test_current_product_live_path_fetches_only_three_tables(tmp_path: Path):
    class DummySap:
        DatabaseTables = object()

    fake_conn = Mock()
    fake_conn.connect.return_value = (True, "connected")
    fake_conn.get_sap.return_value = DummySap()

    def fake_fetch(_database_tables, table_name, max_rows=20):
        parsed = Mock()
        parsed.rows = [{"dummy": table_name}]
        parsed.field_keys = {
            "Frame Assignments - Summary": ["UniqueName", "Label", "Story", "Design Type", "Design Section"],
            "Frame Section Property Definitions - Concrete Rectangular": ["Name", "Width", "Depth"],
            "Modal Participating Mass Ratios": ["Mode", "Period", "UX", "UY", "SumUX", "SumUY"],
        }[table_name]
        parsed.fetch_status = "FETCHED"
        parsed.return_code = 0
        parsed.debug = {}
        parsed.row_count_reported = 1
        result = Mock()
        result.parsed = parsed
        result.raw_response = []
        result.selected_signature = {}
        return result

    with patch.object(probe, "ETABSConnection", return_value=fake_conn), \
        patch.object(probe, "get_available_tables", return_value=SAMPLE_TABLE_NAMES), \
        patch.object(probe, "select_output_for_display", return_value={"display_selection_success": True}), \
        patch.object(probe, "fetch_display_table", side_effect=fake_fetch) as fetch_mock:
        exit_code = probe.run_live_probe(
            out=tmp_path,
            live_etabs=True,
            probe_profile="current_product",
            preferred_output_case="Crack_SeisY_UpSoil",
            max_sample_rows=20,
        )

    assert exit_code == 0
    fetched_tables = [call.args[1] for call in fetch_mock.call_args_list]
    assert fetched_tables == [
        "Frame Assignments - Summary",
        "Frame Section Property Definitions - Concrete Rectangular",
        "Modal Participating Mass Ratios",
    ]
    summary = json.loads((tmp_path / "probe_summary.json").read_text(encoding="utf-8"))
    assert summary["safe_to_implement_checks_now"] is False
    assert summary["available_table_count"] == len(SAMPLE_TABLE_NAMES)
