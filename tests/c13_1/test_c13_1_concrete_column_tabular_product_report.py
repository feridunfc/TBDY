from __future__ import annotations

import json
from pathlib import Path

from tools.render_product_report import MODAL_THRESHOLD, render_product_report


REQUIRED_TABLE_ARRAYS = {
    "executive_summary_rows": ["metric", "value"],
    "concrete_beam_section_geometry_checks": [
        "section", "assigned_beam_count", "stories", "width_mm", "depth_mm",
        "width_check_status", "width_value_mm", "width_limit_mm",
        "depth_check_status", "depth_value_mm", "depth_limit_mm",
        "h_over_bw_value", "h_over_bw_limit", "h_over_bw_status",
        "overall_status", "evidence_table",
    ],
    "unsupported_beam_sections": ["section", "assigned_beam_count", "stories", "sample_labels", "reason", "product_pass_impact"],
    "concrete_column_section_geometry_checks": [
        "section", "assigned_column_count", "stories", "width_mm", "depth_mm",
        "min_dimension_value_mm", "min_dimension_limit_mm", "min_dimension_status",
        "area_value_mm2", "area_limit_mm2", "area_status",
        "aspect_ratio_value", "aspect_ratio_limit", "aspect_ratio_status",
        "overall_status", "evidence_table",
    ],
    "unsupported_column_sections": ["section", "assigned_column_count", "stories", "sample_labels", "reason", "product_pass_impact"],
    "beam_section_detail_rows": [
        "element_type", "section", "check_id", "check_title", "value", "limit", "unit",
        "comparison", "status", "ratio", "evidence_table", "evidence_columns", "raw_values", "normalized_values",
    ],
    "column_section_detail_rows": [
        "element_type", "section", "check_id", "check_title", "value", "limit", "unit",
        "comparison", "status", "ratio", "evidence_table", "evidence_columns", "raw_values", "normalized_values",
    ],
    "modal_mass_final_verdict_rows": [
        "direction", "value", "limit", "comparison", "status", "selected_mode",
        "selected_row_index", "rows_considered", "source_column",
    ],
    "guardrail_rows": ["guardrail", "value"],
    "boundary_note_rows": ["item", "statement"],
}


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _product_input(tmp_path: Path, *, failing_column: bool = False) -> Path:
    root = tmp_path / ("c13_1_failing" if failing_column else "c13_1_product")
    _write_json(root / "product_slice_manifest.json", {
        "product_slice_passed": True,
        "excel_production_path_used": False,
        "streamlit_ui_used": False,
        "legacy_runtime_used": False,
        "rebar_flexure_shear_capacity_unlocked": False,
    })
    column_section = "C20x80" if failing_column else "C40x80"
    column_row = {"Name": "C20x80", "t2": "0.2", "t3": "0.8"} if failing_column else {"Name": "C40x80", "t2": "0.4", "t3": "0.8"}
    _write_json(root / "product_report_source_tables.json", {
        "metadata": {"artifact": "product_report_source_tables"},
        "tables": {
            "frame_assignments": {
                "actual_table_name": "Frame Assignments - Summary",
                "columns": ["Story", "Label", "UniqueName", "Type", "Length", "AnalysisSect", "DesignSect"],
                "rows": [
                    {"Story": "+14.5", "Label": "B1", "UniqueName": "297", "Type": "Beam", "Length": "7", "AnalysisSect": "B40x70", "DesignSect": "B40x70"},
                    {"Story": "+4.50", "Label": "B290", "UniqueName": "760", "Type": "Beam", "Length": "3.7", "AnalysisSect": "HE160A", "DesignSect": "HE160A"},
                    {"Story": "+0.00", "Label": "C1", "UniqueName": "901", "Type": "Column", "Length": "4.5", "AnalysisSect": column_section, "DesignSect": column_section},
                    {"Story": "+4.50", "Label": "C2", "UniqueName": "902", "Type": "Column", "Length": "4.5", "AnalysisSect": column_section, "DesignSect": column_section},
                    {"Story": "+9.00", "Label": "SC1", "UniqueName": "903", "Type": "Column", "Length": "4.5", "AnalysisSect": "STEEL_COL", "DesignSect": "STEEL_COL"},
                ],
            },
            "frame_section_properties": {
                "actual_table_name": "Frame Section Property Definitions - Concrete Rectangular",
                "columns": ["Name", "t2", "t3"],
                "rows": [
                    {"Name": "B40x70", "t2": "0.4", "t3": "0.7"},
                    column_row,
                ],
            },
            "modal_participating_mass": {
                "actual_table_name": "Modal Participating Mass Ratios",
                "columns": ["Case", "Mode", "Period", "UX", "UY", "SumUX", "SumUY", "SumRZ"],
                "rows": [
                    {"Case": "Modal", "Mode": 1, "Period": 1.1, "UX": 0.2, "UY": 0.3, "SumUX": 0.2, "SumUY": 0.3, "SumRZ": 0.1},
                    {"Case": "Modal", "Mode": 2, "Period": 0.7, "UX": 0.7999, "UY": 0.6999, "SumUX": 0.9999, "SumUY": 0.9999, "SumRZ": 0.2},
                ],
            },
        },
    })
    return root


def test_c13_1_concrete_rectangular_columns_are_checked(tmp_path: Path):
    summary = render_product_report(_product_input(tmp_path), tmp_path / "report")
    assert summary["concrete_column_section_type_count"] == 1
    assert summary["concrete_column_object_count"] == 2
    column = summary["concrete_column_section_geometry_checks"][0]
    assert column["section"] == "C40x80"
    assert column["min_dimension_value_mm"] == 400.0
    assert column["area_value_mm2"] == 320000.0
    assert column["aspect_ratio_value"] == 0.5
    assert column["min_dimension_status"] == "OK"
    assert column["area_status"] == "OK"
    assert column["aspect_ratio_status"] == "OK"
    assert column["overall_status"] == "OK"


def test_c13_1_unsupported_non_concrete_columns_do_not_fail(tmp_path: Path):
    summary = render_product_report(_product_input(tmp_path), tmp_path / "report")
    unsupported = {row["section"]: row for row in summary["unsupported_column_sections"]}
    assert "STEEL_COL" in unsupported
    assert unsupported["STEEL_COL"]["assigned_column_count"] == 1
    assert unsupported["STEEL_COL"]["product_pass_impact"] == "Not counted as FAIL"
    assert summary["unsupported_column_section_type_count"] == 1
    assert summary["unsupported_column_object_count"] == 1
    assert summary["column_fail_count"] == 0
    assert summary["report_product_passed"] is True


def test_c13_1_failing_concrete_column_geometry_affects_report_pass(tmp_path: Path):
    summary = render_product_report(_product_input(tmp_path, failing_column=True), tmp_path / "report")
    column = summary["concrete_column_section_geometry_checks"][0]
    assert column["section"] == "C20x80"
    assert column["min_dimension_status"] == "FAIL"
    assert column["aspect_ratio_status"] == "FAIL"
    assert summary["column_fail_count"] > 0
    assert summary["report_product_passed"] is False


def test_c13_1_existing_beam_and_modal_behavior_is_preserved(tmp_path: Path):
    summary = render_product_report(_product_input(tmp_path), tmp_path / "report")
    beam = summary["concrete_beam_section_geometry_checks"][0]
    assert beam["section"] == "B40x70"
    assert beam["width_check_status"] == "OK"
    assert beam["depth_check_status"] == "OK"
    assert beam["h_over_bw_status"] == "OK"
    assert summary["unsupported_beam_sections"][0]["section"] == "HE160A"
    assert summary["unsupported_beam_sections"][0]["product_pass_impact"] == "Not counted as FAIL"
    assert summary["modal_threshold"] == MODAL_THRESHOLD == 0.95
    assert summary["modal_ux_status"] == "OK"
    assert summary["modal_uy_status"] == "OK"


def test_c13_1_html_markdown_and_json_expose_strict_table_contract(tmp_path: Path):
    product_input = _product_input(tmp_path)
    out = product_input / "report"
    summary = render_product_report(product_input, out)
    md = (out / "product_report.md").read_text(encoding="utf-8")
    html = (out / "product_report.html").read_text(encoding="utf-8")
    saved = json.loads((out / "product_summary.json").read_text(encoding="utf-8"))

    for key, columns in REQUIRED_TABLE_ARRAYS.items():
        assert key in saved
        assert isinstance(saved[key], list)
        if saved[key]:
            assert list(saved[key][0].keys()) == columns
    assert "modal_mass_full_table_rows" in saved
    assert len(saved["modal_mass_full_table_rows"]) == 2
    assert saved["modal_mass_table_rows"] == 2
    assert saved["modal_mass_summary"]["modal_mass_table_rows"] == 2
    assert len(saved["modal_mass_full_table_rows"]) == saved["modal_mass_table_rows"]
    assert [r for r in saved["executive_summary_rows"] if r.get("metric") == "modal_mass_table_rows"] == [
        {"metric": "modal_mass_table_rows", "value": 2}
    ]
    assert "Table name: `concrete_column_section_geometry_checks`" in md
    assert "Table name: `column_section_detail`" in md
    assert "Table name: `modal_mass_full_table`" in md
    assert "<caption>concrete_column_section_geometry_checks</caption>" in html
    assert "<caption>modal_mass_final_verdict</caption>" in html
    assert "STEEL_COL" in md
    assert "Not counted as FAIL" in md
    assert summary["modal_mass_final_verdict_rows"] == [
        {
            "direction": "UX",
            "value": 0.9999,
            "limit": 0.95,
            "comparison": "0.9999 >= 0.95",
            "status": "OK",
            "selected_mode": 2,
            "selected_row_index": 1,
            "rows_considered": 2,
            "source_column": "SumUX",
        },
        {
            "direction": "UY",
            "value": 0.9999,
            "limit": 0.95,
            "comparison": "0.9999 >= 0.95",
            "status": "OK",
            "selected_mode": 2,
            "selected_row_index": 1,
            "rows_considered": 2,
            "source_column": "SumUY",
        },
    ]


def test_c13_1_guardrails_remain_false(tmp_path: Path):
    summary = render_product_report(_product_input(tmp_path), tmp_path / "report")
    assert summary["guardrail_rows"] == [
        {"guardrail": "excel_production_path_used", "value": False},
        {"guardrail": "streamlit_ui_used", "value": False},
        {"guardrail": "legacy_runtime_used", "value": False},
        {"guardrail": "rebar_flexure_shear_capacity_unlocked", "value": False},
    ]
