import importlib

from tbdy_engine.audit.etabs_table_fit import EtabsTableFitAuditor
from tbdy_engine.audit.models import AuditStatus
from tbdy_engine.canonical_tables.table import CanonicalTable
from tbdy_engine.contracts.loader import load_contracts
from tools.probe_etabs_table_headers import parse_etabs_display_table_result


def test_flat_table_data_reconstructs_rows_using_header_count_not_number_fields():
    parsed = parse_etabs_display_table_result(
        {
            "return_code": 0,
            "field_keys": ["Story", "Label", "UniqueName", "DesignSect"],
            "number_fields": 1,  # ETABS metadata can be unreliable
            "number_records": 2,
            "table_data": ["S1", "B1", "101", "B40x70", "S1", "B2", "102", "B30x60"],
        },
        actual_table_name="Frame Assignments - Summary",
        max_rows=3,
    )
    assert parsed.fetch_status == "FETCHED"
    assert parsed.debug["header_count"] == 4
    assert parsed.debug["expected_flat_length"] == 8
    assert parsed.rows[0] == {"Story": "S1", "Label": "B1", "UniqueName": "101", "DesignSect": "B40x70"}


def test_table_data_length_mismatch_returns_row_parse_partial_no_fake_rows():
    parsed = parse_etabs_display_table_result(
        {
            "return_code": 0,
            "field_keys": ["Story", "Label", "UniqueName", "DesignSect"],
            "number_fields": 1,
            "number_records": 2,
            "table_data": ["S1", "B1", "101"],
        },
        actual_table_name="Frame Assignments - Summary",
    )
    assert parsed.fetch_status == "ROW_PARSE_PARTIAL"
    assert parsed.rows == ()
    assert parsed.debug["row_parse_status"] == "ROW_PARSE_PARTIAL"
    assert parsed.debug["mismatch_reason"]
    assert any(d["code"] == "ROW_PARSE_PARTIAL" for d in parsed.diagnostics)


def test_zero_data_with_positive_records_is_empty_and_no_fake_rows():
    parsed = parse_etabs_display_table_result(
        {
            "return_code": 0,
            "field_keys": ["Story", "Label", "UniqueName", "DesignSect"],
            "number_fields": 1,
            "number_records": 998,
            "table_data": [],
        },
        actual_table_name="Frame Assignments - Summary",
    )
    assert parsed.fetch_status == "EMPTY"
    assert parsed.rows == ()
    assert parsed.debug["mismatch_reason"] == "no_table_data_with_reported_records"


def test_t2_t3_designsect_and_rebar_aliases_satisfy_contract_fit():
    bundle = load_contracts()
    tables = (
        CanonicalTable(
            table_key="frame_section_properties",
            actual_table_name="Frame Section Property Definitions - Concrete Rectangular",
            columns=("Name", "t3", "t2"),
            rows=({"Name": "B40x70", "t3": 700, "t2": 400},),
            units={},
            source="TEST",
        ),
        CanonicalTable(
            table_key="frame_assignments",
            actual_table_name="Frame Assignments - Summary",
            columns=("Story", "Label", "UniqueName", "DesignSect"),
            rows=({"Story": "S1", "Label": "B1", "UniqueName": "101", "DesignSect": "B40x70"},),
            units={},
            source="TEST",
        ),
        CanonicalTable(
            table_key="concrete_beam_design_summary",
            actual_table_name="Concrete Beam Design Summary - TS 500-2000(R2018)",
            columns=("Story", "Label", "UniqueName", "Station", "AsTop", "AsBot", "VRebar"),
            rows=({"Story": "S1", "Label": "B1", "UniqueName": "101", "Station": 0, "AsTop": 100, "AsBot": 120, "VRebar": 5},),
            units={},
            source="TEST",
        ),
    )
    auditor = EtabsTableFitAuditor(bundle, tables)
    table_reports = {r.table_key: r for r in auditor.table_contract_fit()}
    assert table_reports["frame_section_properties"].status == AuditStatus.MATCHED
    assert {"t3", "t2"}.issubset(set(table_reports["frame_section_properties"].matched_columns))
    assert table_reports["frame_assignments"].status == AuditStatus.MATCHED
    feature_reports = {r.feature_name: r for r in auditor.feature_source_fit()}
    assert feature_reports["beam_width_mm"].matched_column == "t2"
    assert feature_reports["beam_depth_mm"].matched_column == "t3"
    assert feature_reports["beam_As_top_etabs_required_mm2"].matched_column == "AsTop"
    assert feature_reports["beam_As_bottom_etabs_required_mm2"].matched_column == "AsBot"
    identity = {r.element_type: r for r in auditor.element_identity_fit()}
    assert identity["beam"].identity_mapping["section"] == "DesignSect"


def test_analysissect_identity_fallback_with_diagnostic_available_as_partial_context():
    bundle = load_contracts()
    tables = (
        CanonicalTable(
            table_key="frame_assignments",
            actual_table_name="Frame Assignments - Summary",
            columns=("Story", "Label", "UniqueName", "AnalysisSect"),
            rows=({"Story": "S1", "Label": "B1", "UniqueName": "101", "AnalysisSect": "B40x70"},),
            units={},
            source="TEST",
        ),
    )
    identity = {r.element_type: r for r in EtabsTableFitAuditor(bundle, tables).element_identity_fit()}
    assert identity["beam"].identity_mapping["section"] == "AnalysisSect"


def test_combo_probe_ignores_case_type_step_type_numeric_and_matches_crack_review():
    bundle = load_contracts()
    table = CanonicalTable(
        table_key="story_drifts",
        actual_table_name="Story Drifts",
        columns=("OutputCase", "CaseType", "StepType", "Drift"),
        rows=(
            {"OutputCase": "Crack_SeisY_UpSoil", "CaseType": "Combination", "StepType": "Max", "Drift": "0.000534"},
        ),
        units={},
        source="TEST",
    )
    reports = EtabsTableFitAuditor(bundle, (table,)).combo_family_fit()
    assert len(reports) == 1
    assert reports[0].raw_combo_name == "Crack_SeisY_UpSoil"
    assert reports[0].matched_combo_family in {"DUCTILE_Y", "SOIL"}
    assert reports[0].status == AuditStatus.MATCHED
    assert any(d.code == "COMBO_NEEDS_ENGINEERING_REVIEW" for d in reports[0].diagnostics)


def test_no_forbidden_imports_for_c56_paths():
    before = set(importlib.sys.modules)
    importlib.import_module("tbdy_engine.audit.etabs_table_fit")
    importlib.import_module("tools.probe_etabs_table_headers")
    after = set(importlib.sys.modules) - before
    forbidden = {"tbdy_engine.runner_v2", "tbdy_engine.runtime", "tbdy_engine.archx"}
    assert not (after & forbidden)
