from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from tbdy_engine.product_reports.c13_1_report import PRODUCT_REPORT_KEYS, build_c13_1_product_report, write_c13_1_product_report
from tools.run_live_model_product_report import main as run_product_main

FIXTURE = Path("tests/fixtures/p2_0_c13_1_product_report_fixture.json")

REQUIRED_EXECUTIVE_FIELDS = {
    "product_slice_passed",
    "report_product_passed",
    "concrete_beam_section_type_count",
    "concrete_beam_object_count",
    "unsupported_beam_section_type_count",
    "unsupported_beam_object_count",
    "concrete_column_section_type_count",
    "concrete_column_object_count",
    "unsupported_column_section_type_count",
    "unsupported_column_object_count",
    "beam_fail_count",
    "column_fail_count",
    "modal_mass_table_rows",
    "modal_threshold",
    "modal_ux_status",
    "modal_uy_status",
    "total_fail_count",
}


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")


def _input_dir(tmp_path: Path, payload: dict | None = None) -> Path:
    root = tmp_path / "input"
    _write_json(root / "product_report_source_tables.json", payload or json.loads(FIXTURE.read_text(encoding="utf-8")))
    _write_json(root / "product_slice_manifest.json", {
        "product_slice_passed": True,
        "excel_production_path_used": False,
        "streamlit_ui_used": False,
        "legacy_runtime_used": False,
        "rebar_flexure_shear_capacity_unlocked": False,
    })
    return root


def _report(tmp_path: Path, payload: dict | None = None) -> dict:
    return build_c13_1_product_report(_input_dir(tmp_path, payload), tmp_path / "out")


def test_product_report_json_contains_all_required_c13_1_sections(tmp_path: Path):
    report = _report(tmp_path)
    for key in PRODUCT_REPORT_KEYS:
        assert key in report
    assert set(report["executive_summary"]) == REQUIRED_EXECUTIVE_FIELDS
    assert isinstance(report["concrete_beam_section_geometry_checks"], list)
    assert isinstance(report["concrete_column_section_geometry_checks"], list)
    assert isinstance(report["modal_mass_full_table"], list)
    assert isinstance(report["modal_mass_final_verdict"], list)
    assert isinstance(report["guardrails"], dict)
    assert isinstance(report["boundary_notes"], dict)


def test_executive_summary_counts_are_derived_from_input_rows_not_constants(tmp_path: Path):
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    rows = payload["tables"]["frame_assignments"]["rows"]
    rows.append({"Story": "+10.5", "Label": "B9", "UniqueName": "402", "Type": "Beam", "Length": "5.0", "AnalysisSect": "B60x70", "DesignSect": "B60x70"})
    rows.append({"Story": "+10.5", "Label": "C3", "UniqueName": "904", "Type": "Column", "Length": "4.5", "AnalysisSect": "C40x80", "DesignSect": "C40x80"})
    summary = _report(tmp_path, payload)["executive_summary"]
    assert summary["concrete_beam_section_type_count"] == 2
    assert summary["concrete_beam_object_count"] == 4
    assert summary["concrete_column_section_type_count"] == 1
    assert summary["concrete_column_object_count"] == 3
    assert summary["unsupported_beam_object_count"] == 1
    assert summary["unsupported_column_object_count"] == 1


def test_beam_geometry_checks_evaluate_width_depth_and_h_over_bw(tmp_path: Path):
    report = _report(tmp_path)
    beam_rows = {row["section"]: row for row in report["concrete_beam_section_geometry_checks"]}
    b40 = beam_rows["B40x70"]
    assert b40["assigned_beam_count"] == 2
    assert b40["width_value_mm"] == 400.0
    assert b40["width_limit_mm"] == 250.0
    assert b40["width_check_status"] == "OK"
    assert b40["depth_value_mm"] == 700.0
    assert b40["depth_limit_mm"] == 300.0
    assert b40["depth_check_status"] == "OK"
    assert b40["h_over_bw_value"] == 1.75
    assert b40["h_over_bw_limit"] == 3.5
    assert b40["h_over_bw_status"] == "OK"
    assert b40["evidence_table"] == "Frame Section Property Definitions - Concrete Rectangular"


def test_column_geometry_checks_evaluate_min_dimension_area_and_aspect_ratio(tmp_path: Path):
    column = _report(tmp_path)["concrete_column_section_geometry_checks"][0]
    assert column["section"] == "C40x80"
    assert column["assigned_column_count"] == 2
    assert column["min_dimension_value_mm"] == 400.0
    assert column["min_dimension_limit_mm"] == 300.0
    assert column["min_dimension_status"] == "OK"
    assert column["area_value_mm2"] == 320000.0
    assert column["area_limit_mm2"] == 75000.0
    assert column["area_status"] == "OK"
    assert column["aspect_ratio_value"] == 0.5
    assert column["aspect_ratio_limit"] == 0.4
    assert column["aspect_ratio_status"] == "OK"


def test_concrete_failures_change_report_pass_without_hard_coded_counts(tmp_path: Path):
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload["tables"]["frame_assignments"]["rows"].append(
        {"Story": "+1.00", "Label": "B_BAD", "UniqueName": "999", "Type": "Beam", "Length": "3.0", "AnalysisSect": "B20x90", "DesignSect": "B20x90"}
    )
    payload["tables"]["frame_section_properties"]["rows"].append({"Name": "B20x90", "t2": "0.2", "t3": "0.9"})
    report = _report(tmp_path, payload)
    bad = {row["section"]: row for row in report["concrete_beam_section_geometry_checks"]}["B20x90"]
    assert bad["width_check_status"] == "FAIL"
    assert bad["h_over_bw_status"] == "FAIL"
    assert report["executive_summary"]["beam_fail_count"] == 2
    assert report["executive_summary"]["report_product_passed"] is False


def test_unsupported_beam_and_column_sections_are_reported_not_counted_as_fail(tmp_path: Path):
    report = _report(tmp_path)
    unsupported_beams = {row["section"]: row for row in report["unsupported_beam_sections"]}
    unsupported_columns = {row["section"]: row for row in report["unsupported_column_sections"]}
    assert unsupported_beams["HE160A"]["assigned_beam_count"] == 1
    assert unsupported_beams["HE160A"]["product_pass_impact"] == "Not counted as FAIL"
    assert unsupported_columns["STEEL_COL"]["assigned_column_count"] == 1
    assert unsupported_columns["STEEL_COL"]["product_pass_impact"] == "Not counted as FAIL"
    assert report["executive_summary"]["beam_fail_count"] == 0
    assert report["executive_summary"]["column_fail_count"] == 0
    assert report["executive_summary"]["total_fail_count"] == 0


def test_modal_mass_final_verdict_selects_ux_uy_cumulative_values_against_095(tmp_path: Path):
    verdict = {row["direction"]: row for row in _report(tmp_path)["modal_mass_final_verdict"]}
    assert verdict["UX"] == {
        "direction": "UX",
        "value": 0.9999,
        "limit": 0.95,
        "comparison": "0.9999 >= 0.95",
        "status": "OK",
        "selected_mode": 2,
        "selected_row_index": 1,
        "rows_considered": 2,
        "source_column": "SumUX",
    }
    assert verdict["UY"]["value"] == 0.9999
    assert verdict["UY"]["status"] == "OK"
    assert verdict["UY"]["source_column"] == "SumUY"


def test_guardrails_are_present_and_false_and_boundary_notes_are_present(tmp_path: Path):
    report = _report(tmp_path)
    assert report["guardrails"] == {
        "excel_production_path_used": False,
        "streamlit_ui_used": False,
        "legacy_runtime_used": False,
        "rebar_flexure_shear_capacity_unlocked": False,
    }
    assert set(report["boundary_notes"]) == {"scope", "unsupported_sections", "excluded_engineering_checks"}


def test_product_report_is_deterministic_json_serializable(tmp_path: Path):
    first = _report(tmp_path / "a")
    second = deepcopy(first)
    assert json.dumps(first, sort_keys=True, ensure_ascii=False) == json.dumps(second, sort_keys=True, ensure_ascii=False)


def test_product_command_fixture_mode_writes_json_and_markdown(tmp_path: Path):
    out = tmp_path / "cmd_out"
    rc = run_product_main(["--input", str(FIXTURE), "--out", str(out)])
    assert rc == 0
    assert (out / "product_report.json").is_file()
    assert (out / "product_report.md").is_file()
    assert (out / "product_summary.json").is_file()
    saved = json.loads((out / "product_report.json").read_text(encoding="utf-8"))
    assert saved["executive_summary"]["report_product_passed"] is True
    assert saved["executive_summary"]["concrete_beam_object_count"] == 3
    assert saved["executive_summary"]["concrete_column_object_count"] == 2
    assert "Concrete Beam Section Geometry Checks" in (out / "product_report.md").read_text(encoding="utf-8")
