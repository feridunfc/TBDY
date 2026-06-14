from __future__ import annotations

import inspect
from pathlib import Path

from tbdy_engine.canonical_tables.table import CanonicalTable
from tbdy_engine.contracts.loader import load_contracts
from tbdy_engine.features.diagnostics import FeatureDiagnosticCode
from tbdy_engine.features.resolver.live_smoke import (
    C8LiveFeatureResolverSmoke,
    build_seed_identity_from_target,
)
from tbdy_engine.features.value import FeatureValueStatus
from tbdy_engine.providers import etabs_display_table_parser as parser
from tbdy_engine.providers.etabs_display_table_fetcher import select_output_for_display
from tbdy_engine.providers.etabs_display_table_parser import parse_etabs_display_table_result


def _unit_context() -> dict[str, object]:
    return {
        "source": "fixture_declared_units",
        "force_unit": "kN",
        "length_unit": "mm",
        "temperature_unit": "C",
        "unit_query_status": "RESOLVED",
        "unit_basis_confidence": "high",
        "unit_query_succeeded": True,
    }


def _table(table_key: str, actual_name: str, rows: list[dict[str, object]], *, raw: dict[str, object] | None = None) -> CanonicalTable:
    columns = list(rows[0].keys()) if rows else []
    return CanonicalTable(
        table_key=table_key,
        actual_table_name=actual_name,
        columns=columns,
        rows=rows,
        units={"raw_table_diagnostics": raw or {"parser_status": "FETCHED", "number_records": len(rows), "table_data_length": len(rows) * len(columns)}},
        source="C11_1_12_TEST_FIXTURE",
    )


def _frame_assignment_row() -> dict[str, object]:
    return {
        "Story": "+14.5",
        "Label": "B1",
        "UniqueName": "297",
        "Type": "Beam",
        "Length": "7000",
        "AnalysisSect": "B40x70",
        "DesignSect": "B40x70",
    }


def _design_summary_row() -> dict[str, object]:
    return {
        "Story": "+14.5",
        "Label": "B1",
        "UniqueName": "297",
        "AnalysisSect": "B40x70",
        "DesignSect": "B40x70",
        "AsTop": "572",
        "AsBot": "601",
        "VRebar": "38",
        "AsTopCombo": "Crack_SeisY_UpSoil",
        "AsBotCombo": "Crack_SeisY_UpSoil",
        "VCombo": "Crack_SeisY_UpSoil",
        "WarnMsg": "",
        "ErrMsg": "",
    }


def _resolver(*, include_design_summary: bool = False, include_frame_assignments: bool = True, direct_api: bool = False) -> C8LiveFeatureResolverSmoke:
    tables: list[CanonicalTable] = []
    if include_frame_assignments:
        tables.append(_table("frame_assignments", "Frame Assignments - Summary", [_frame_assignment_row()]))
    tables.append(_table("frame_section_properties", "Frame Section Property Definitions", [{"Name": "B40x70", "t2": "400", "t3": "700"}]))
    if include_design_summary:
        tables.append(_table("concrete_beam_design_summary", "Concrete Beam Design Summary - TS 500-2000(R2018)", [_design_summary_row()]))
    direct_payload = None
    if direct_api:
        direct_payload = {"frame": {"object_name": "297", "label": "B1", "story": "+14.5", "section": "B40x70"}}
    return C8LiveFeatureResolverSmoke(
        load_contracts(),
        tables,
        unit_context=_unit_context(),
        target_component="297",
        target_label="B1",
        target_story="+14.5",
        target_section="B40x70",
        preferred_output_case="Crack_SeisY_UpSoil",
        direct_api_geometry=direct_payload,
        table_extraction_debug={
            "concrete_beam_design_summary_availability": {
                "fetch_attempted": True,
                "aliases_attempted": ["Concrete Beam Design Summary - TS 500-2000(R2018)"],
                "display_selection_attempted": True,
                "display_selection_success": True,
                "display_selection_selected_method": "SetLoadCombinationsSelectedForDisplay",
                "preferred_output_case": "Crack_SeisY_UpSoil",
            }
        },
    )


def test_parser_has_single_sequence_shape_function_and_compact_helper():
    src = Path(parser.__file__).read_text(encoding="utf-8")
    assert src.count("def _extract_sequence_shape") == 1
    assert src.count("def _extract_compact_six_item_etabs_shape") == 1
    assert src.index("_extract_compact_six_item_etabs_shape(result)") < src.index("debug: dict[str, Any] = {\"sequence_length\"")


def test_parser_accepts_six_item_etabs_return_shape_with_tabledata_at_index_4():
    raw = [(), 1, ("Story", "OutputCase"), 2, ("+14.5", "CaseA", "+14.5", "CaseB"), 0]
    parsed = parse_etabs_display_table_result(raw, actual_table_name="Story Drifts", max_rows=None)
    assert parsed.fetch_status == "FETCHED"
    assert len(parsed.rows) == 2
    assert parsed.rows[0]["Story"] == "+14.5"
    assert parsed.rows[1]["OutputCase"] == "CaseB"
    assert parsed.debug["compact_six_item_shape_detected"] is True
    assert parsed.debug["compact_shape_slots"]["table_data_index"] == 4
    assert parsed.debug["number_fields_detected"] is None
    assert parsed.debug["number_fields_source"] == "compact_6_item_slot_1_ignored_as_ambiguous"


def test_story_drifts_compact_shape_parses_rows():
    headers = ("Story", "OutputCase", "CaseType", "StepType", "Direction", "Drift", "Drift/", "Label", "X", "Y", "Z")
    row = ("+14.5", "Crack_SeisY_UpSoil", "LinStatic", None, "Y", "0.0012", "1/810", "37", "102", "51.8", "14.5")
    parsed = parse_etabs_display_table_result([(), 2, headers, 1, row, 0], actual_table_name="Story Drifts", max_rows=None)
    assert parsed.fetch_status == "FETCHED"
    assert len(parsed.rows) == 1
    assert parsed.rows[0]["Drift"] == "0.0012"


def test_story_max_over_avg_drifts_compact_shape_parses_rows():
    headers = ("Story", "OutputCase", "CaseType", "StepType", "Direction", "Max Drift", "Avg Drift", "Ratio")
    row = ("+14.5", "Crack_SeisY_UpSoil", "LinStatic", None, "Y", "0.0068", "0.0063", "1.076")
    parsed = parse_etabs_display_table_result([(), 1, headers, 1, row, 0], actual_table_name="Story Max Over Avg Drifts", max_rows=None)
    assert parsed.fetch_status == "FETCHED"
    assert parsed.rows[0]["Ratio"] == "1.076"


def test_base_reactions_compact_shape_parses_rows():
    headers = ("OutputCase", "CaseType", "StepType", "FX", "FY", "FZ", "MX", "MY", "MZ", "X", "Y", "Z")
    row = ("Crack_SeisY_UpSoil", "LinStatic", None, "-11424.4", "-828.7", "0", "0", "0", "0", "0", "0", "-5.15")
    parsed = parse_etabs_display_table_result([(), 1, headers, 1, row, 0], actual_table_name="Base Reactions", max_rows=None)
    assert parsed.fetch_status == "FETCHED"
    assert parsed.rows[0]["FX"] == "-11424.4"


def test_existing_mapping_and_fixture_parser_still_passes():
    parsed = parse_etabs_display_table_result(
        {"headers": ["A", "B"], "rows": [{"A": "x", "B": "y"}], "number_records": 1, "return_code": 0},
        actual_table_name="Fixture Table",
        max_rows=None,
    )
    assert parsed.fetch_status == "FETCHED"
    assert parsed.rows[0]["B"] == "y"


def test_malformed_compact_shape_flat_length_mismatch_still_reports_partial():
    raw = [(), 1, ("Story", "OutputCase"), 2, ("+14.5", "CaseA"), 0]
    parsed = parse_etabs_display_table_result(raw, actual_table_name="Story Drifts", max_rows=None)
    assert parsed.fetch_status == "ROW_PARSE_PARTIAL"
    assert parsed.debug["mismatch_reason"] == "flat_length_mismatch:2!=4"


def test_display_selection_contract_uses_list_only_combo_first_and_skips_case_on_success():
    class FakeDatabaseTables:
        def __init__(self) -> None:
            self.calls: list[tuple[str, tuple[object, ...]]] = []

        def SetLoadCombinationsSelectedForDisplay(self, *args):
            self.calls.append(("combo", args))
            return [args[0], 0]

        def SetLoadCasesSelectedForDisplay(self, *args):
            self.calls.append(("case", args))
            return [args[0], 0]

    fake = FakeDatabaseTables()
    report = select_output_for_display(fake, "Crack_SeisY_UpSoil")
    assert fake.calls == [("combo", (["Crack_SeisY_UpSoil"],))]
    assert report["display_selection_success"] is True
    assert report["display_selection_selected_method"] == "SetLoadCombinationsSelectedForDisplay"
    assert report["skipped_case_selection_because_combo_succeeded"] is True
    assert report["display_selection_attempts"][0]["args_shape"] == ["list"]


def test_build_seed_identity_from_target_args():
    assert build_seed_identity_from_target("297", "B1", "+14.5", "B40x70") == {
        "UniqueName": "297",
        "Label": "B1",
        "Story": "+14.5",
        "DesignSect": "B40x70",
        "AnalysisSect": "B40x70",
    }


def test_frame_assignment_matching_uses_non_null_seed_keys_and_finds_target_row():
    report = _resolver().build_all().identity_resolution_report
    assert report["identity_seeded"] is True
    assert report["seed_identity"]["UniqueName"] == "297"
    assert report["identity_confirmed_by_frame_assignments"] is True
    first = report["frame_assignment_matching_attempts"][0]
    assert first["matched"] is True
    assert first["attempted_keys"] == {"UniqueName": "297", "Label": "B1", "Story": "+14.5", "DesignSect": "B40x70"}
    assert all(value is not None for value in first["attempted_keys"].values())


def test_identity_resolution_report_records_seed_identity():
    report = _resolver().build_all().identity_resolution_report
    assert report["identity_source"] == "frame_assignments"
    assert report["identity_confidence"] == "high"
    assert report["resolved_identity"] == {"component": "297", "label": "B1", "story": "+14.5", "section": "B40x70"}


def test_identity_features_can_resolve_from_frame_assignments_when_design_summary_unavailable():
    beam = _resolver(include_design_summary=False).build_beam_snapshot("297")
    expected = {
        "beam_unique_name": "297",
        "beam_label": "B1",
        "beam_story": "+14.5",
        "beam_section_name": "B40x70",
    }
    for name, value in expected.items():
        feature = beam.features[name]
        assert feature.status == FeatureValueStatus.RESOLVED
        assert feature.value == value
        assert feature.evidence[0].source_table == "frame_assignments"


def test_identity_features_can_resolve_from_direct_api_evidence():
    beam = _resolver(include_frame_assignments=False, include_design_summary=False, direct_api=True).build_beam_snapshot("297")
    expected = {
        "beam_unique_name": "297",
        "beam_label": "B1",
        "beam_story": "+14.5",
        "beam_section_name": "B40x70",
    }
    for name, value in expected.items():
        feature = beam.features[name]
        assert feature.status == FeatureValueStatus.RESOLVED
        assert feature.value == value
        assert feature.evidence[0].source_table == "live_etabs_direct_api"


def test_concrete_design_summary_fetch_attempted_and_aliases_are_reported_when_unavailable():
    report = _resolver(include_design_summary=False).build_all().identity_resolution_report
    assert report["concrete_beam_design_summary_fetch_attempted"] is True
    assert report["concrete_beam_design_summary_aliases_attempted"]
    assert report["concrete_beam_design_summary_available"] is False
    assert report["concrete_beam_design_summary"]["diagnostic"] == "TABLE_UNAVAILABLE"


def test_concrete_design_matching_uses_seeded_identity_when_table_available():
    outputs = _resolver(include_design_summary=True).build_all()
    report = outputs.identity_resolution_report
    assert report["concrete_beam_design_summary_available"] is True
    assert report["concrete_beam_design_summary_row_matching_uses_seeded_identity"] is True
    assert report["concrete_beam_design_summary_row_matched"] is True
    attempt = report["concrete_beam_design_summary_matching_attempts"][0]
    assert attempt["matched"] is True
    assert attempt["attempted_keys"]["UniqueName"] == "297"


def test_design_result_features_do_not_resolve_without_real_design_summary_row():
    beam = _resolver(include_design_summary=False).build_beam_snapshot("297")
    for name in (
        "beam_As_top_etabs_required_mm2",
        "beam_As_bottom_etabs_required_mm2",
        "beam_shear_rebar_etabs_required_mm2",
        "beam_As_top_combo",
        "beam_As_bottom_combo",
        "beam_V_combo",
        "beam_design_warn_msg",
        "beam_design_err_msg",
    ):
        feature = beam.features[name]
        assert feature.status == FeatureValueStatus.MISSING
        assert any(d.code == FeatureDiagnosticCode.TABLE_UNAVAILABLE for d in feature.diagnostics)


def test_design_result_features_resolve_only_from_matched_design_summary_row():
    beam = _resolver(include_design_summary=True).build_beam_snapshot("297")
    assert beam.features["beam_As_top_etabs_required_mm2"].status == FeatureValueStatus.RESOLVED
    assert beam.features["beam_As_top_etabs_required_mm2"].value == 572.0
    assert beam.features["beam_As_top_etabs_required_mm2"].evidence[0].source_table == "concrete_beam_design_summary"
    assert beam.features["beam_As_top_combo"].value == "Crack_SeisY_UpSoil"


def test_row_missing_report_contains_non_null_attempted_keys_after_seed():
    wrong = _design_summary_row() | {"UniqueName": "999", "Label": "B99", "Story": "+12.0", "DesignSect": "B30x50", "AnalysisSect": "B30x50"}
    resolver = C8LiveFeatureResolverSmoke(
        load_contracts(),
        [
            _table("frame_assignments", "Frame Assignments - Summary", [_frame_assignment_row()]),
            _table("frame_section_properties", "Frame Section Property Definitions", [{"Name": "B40x70", "t2": "400", "t3": "700"}]),
            _table("concrete_beam_design_summary", "Concrete Beam Design Summary - TS 500-2000(R2018)", [wrong]),
        ],
        unit_context=_unit_context(),
        target_component="297",
        target_label="B1",
        target_story="+14.5",
        target_section="B40x70",
    )
    report = resolver.build_all().identity_resolution_report
    assert report["concrete_beam_design_summary_available"] is True
    assert report["concrete_beam_design_summary_row_matched"] is False
    attempts = report["concrete_beam_design_summary_matching_attempts"]
    assert attempts
    assert attempts[0]["attempted_keys"]["UniqueName"] == "297"
    assert all(value is not None for value in attempts[0]["attempted_keys"].values())
