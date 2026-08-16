from __future__ import annotations

import json
from pathlib import Path

from tools.render_product_report import MODAL_THRESHOLD, TABLE_COLUMNS, render_product_report


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _canonical_result(
    *,
    check_id: str,
    component: str,
    component_type: str,
    section: str,
    status: str,
    value: float,
    limit: float,
    ratio: float,
    unit: str,
) -> dict:
    return {
        "check_id": check_id,
        "component": component,
        "component_type": component_type,
        "story": "S1",
        "section": section,
        "status": status,
        "value": value,
        "limit": limit,
        "ratio": ratio,
        "ratio_type": "value_over_maximum" if check_id == "beam_depth_width_ratio" else "actual_over_minimum",
        "pass_rule": "canonical-fixture",
        "unit": unit,
        "evaluation_level": "DESIGN_LEVEL",
        "evidence": [{"source": "canonical-fixture"}],
        "messages": ["canonical fixture"],
        "code_ref": "fixture",
        "diagnostics": [],
    }


def _product_input(tmp_path: Path, *, column_status: str = "OK", include_results: bool = True) -> Path:
    root = tmp_path / "c13_1_product"
    _write_json(root / "product_slice_manifest.json", {
        "product_slice_passed": True,
        "excel_production_path_used": False,
        "streamlit_ui_used": False,
        "legacy_runtime_used": False,
        "rebar_flexure_shear_capacity_unlocked": False,
    })
    _write_json(root / "product_report_source_tables.json", {
        "metadata": {"artifact": "product_report_source_tables"},
        "tables": {
            "frame_assignments": {
                "actual_table_name": "Frame Assignments - Summary",
                "columns": ["Story", "Label", "UniqueName", "Type", "Length", "AnalysisSect", "DesignSect"],
                "rows": [
                    {"Story": "S1", "Label": "B1", "UniqueName": "297", "Type": "Beam", "Length": "7", "AnalysisSect": "B40x70", "DesignSect": "B40x70"},
                    {"Story": "S1", "Label": "B290", "UniqueName": "760", "Type": "Beam", "Length": "3.7", "AnalysisSect": "HE160A", "DesignSect": "HE160A"},
                    {"Story": "S1", "Label": "C1", "UniqueName": "901", "Type": "Column", "Length": "4.5", "AnalysisSect": "C40x80", "DesignSect": "C40x80"},
                    {"Story": "S1", "Label": "C2", "UniqueName": "902", "Type": "Column", "Length": "4.5", "AnalysisSect": "C40x80", "DesignSect": "C40x80"},
                    {"Story": "S1", "Label": "SC1", "UniqueName": "903", "Type": "Column", "Length": "4.5", "AnalysisSect": "STEEL_COL", "DesignSect": "STEEL_COL"},
                ],
            },
            # Raw geometry is compatibility/source evidence only.  B1 reporter must not evaluate it.
            "frame_section_properties": {
                "actual_table_name": "Frame Section Property Definitions - Concrete Rectangular",
                "columns": ["Name", "t2", "t3"],
                "rows": [
                    {"Name": "B40x70", "t2": "0.4", "t3": "0.7"},
                    {"Name": "C40x80", "t2": "0.4", "t3": "0.8"},
                ],
            },
            # Historical C13.1 modal key must continue to work unchanged.
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
    if include_results:
        column_value = 300 if column_status == "OK" else 299
        results = [
            _canonical_result(check_id="beam_geometry_min_width", component="B1", component_type="beam", section="B40x70", status="OK", value=400, limit=250, ratio=1.6, unit="mm"),
            _canonical_result(check_id="beam_geometry_min_depth", component="B1", component_type="beam", section="B40x70", status="OK", value=700, limit=300, ratio=700 / 300, unit="mm"),
            _canonical_result(check_id="beam_depth_width_ratio", component="B1", component_type="beam", section="B40x70", status="OK", value=1.75, limit=3.5, ratio=0.5, unit=""),
            _canonical_result(check_id="column_geometry_min_dimension", component="C1", component_type="column", section="C40x80", status=column_status, value=column_value, limit=300, ratio=column_value / 300, unit="mm"),
            _canonical_result(check_id="column_geometry_min_dimension", component="C2", component_type="column", section="C40x80", status=column_status, value=column_value, limit=300, ratio=column_value / 300, unit="mm"),
        ]
        _write_json(root / "canonical_member_check_results.json", results)
    return root


def test_c13_1_member_rows_are_canonical_projections_not_raw_geometry_calculations(tmp_path: Path):
    summary = render_product_report(_product_input(tmp_path), tmp_path / "report")
    assert summary["concrete_column_section_type_count"] == 1
    assert summary["concrete_column_object_count"] == 2
    section = summary["concrete_column_section_geometry_checks"][0]
    assert section["section"] == "C40x80"
    assert section["assigned_column_count"] == 2
    assert section["canonical_statuses"] == ["OK", "OK"]
    assert "area_value_mm2" not in section
    assert "aspect_ratio_value" not in section
    assert all(row["check_id"] == "column_geometry_min_dimension" for row in summary["column_section_detail_rows"])


def test_c13_1_canonical_fail_is_preserved_without_reporter_recalculation(tmp_path: Path):
    summary = render_product_report(_product_input(tmp_path, column_status="FAIL"), tmp_path / "report")
    assert {row["status"] for row in summary["column_section_detail_rows"]} == {"FAIL"}
    assert summary["column_fail_count"] == 2
    assert summary["report_product_passed"] is None


def test_c13_1_missing_canonical_member_results_produces_no_member_verdict(tmp_path: Path):
    summary = render_product_report(_product_input(tmp_path, include_results=False), tmp_path / "report")
    assert summary["beam_section_detail_rows"] == []
    assert summary["column_section_detail_rows"] == []
    assert summary["beam_fail_count"] == 0
    assert summary["column_fail_count"] == 0
    assert summary["report_product_passed"] is None
    assert all("no member PASS/FAIL" in row["product_pass_impact"] for row in summary["unsupported_sections"])


def test_c13_1_unassessed_sections_preserve_scope_counts_without_engineering_verdict(tmp_path: Path):
    summary = render_product_report(_product_input(tmp_path), tmp_path / "report")
    unsupported_beam = {row["section"]: row for row in summary["unsupported_beam_sections"]}
    unsupported_column = {row["section"]: row for row in summary["unsupported_column_sections"]}
    assert unsupported_beam["HE160A"]["assigned_beam_count"] == 1
    assert unsupported_column["STEEL_COL"]["assigned_column_count"] == 1
    assert summary["unsupported_beam_object_count"] == 1
    assert summary["unsupported_column_object_count"] == 1


def test_c13_1_existing_modal_behavior_is_preserved(tmp_path: Path):
    summary = render_product_report(_product_input(tmp_path), tmp_path / "report")
    assert summary["modal_threshold"] == MODAL_THRESHOLD == 0.95
    assert summary["modal_ux_status"] == "OK"
    assert summary["modal_uy_status"] == "OK"
    assert summary["modal_mass_table_rows"] == 2
    assert summary["modal_mass_final_verdict_rows"] == [
        {
            "direction": "UX", "value": 0.9999, "limit": 0.95,
            "comparison": "0.9999 >= 0.95", "status": "OK", "selected_mode": 2,
            "selected_row_index": 1, "rows_considered": 2, "source_column": "SumUX",
        },
        {
            "direction": "UY", "value": 0.9999, "limit": 0.95,
            "comparison": "0.9999 >= 0.95", "status": "OK", "selected_mode": 2,
            "selected_row_index": 1, "rows_considered": 2, "source_column": "SumUY",
        },
    ]


def test_c13_1_json_markdown_html_follow_new_canonical_table_contract(tmp_path: Path):
    product_input = _product_input(tmp_path)
    out = tmp_path / "report"
    render_product_report(product_input, out)
    saved = json.loads((out / "product_summary.json").read_text(encoding="utf-8"))
    md = (out / "product_report.md").read_text(encoding="utf-8")
    html = (out / "product_report.html").read_text(encoding="utf-8")
    for key, columns in TABLE_COLUMNS.items():
        assert key in saved
        if saved[key]:
            assert list(saved[key][0]) == columns
    assert "canonical_beam_check_results" in md
    assert "canonical_column_check_results" in md
    assert "<caption>canonical_beam_check_results</caption>" in html
    assert "<caption>modal_mass_final_verdict</caption>" in html
    text = json.dumps(saved, sort_keys=True)
    assert "area_value_mm2" not in text
    assert "aspect_ratio_value" not in text


def test_c13_1_manifest_guardrails_are_preserved_and_b1_member_guardrails_are_false(tmp_path: Path):
    summary = render_product_report(_product_input(tmp_path), tmp_path / "report")
    assert summary["guardrails"]["excel_production_path_used"] is False
    assert summary["guardrails"]["streamlit_ui_used"] is False
    assert summary["guardrails"]["legacy_runtime_used"] is False
    assert summary["guardrails"]["rebar_flexure_shear_capacity_unlocked"] is False
    assert summary["guardrails"]["member_engineering_calculation_in_reporter"] is False
    assert summary["guardrails"]["member_limit_authority_in_reporter"] is False
    assert summary["guardrails"]["member_unit_inference_in_reporter"] is False
    assert summary["guardrails"]["retired_legacy_member_criteria_formalized"] is False
