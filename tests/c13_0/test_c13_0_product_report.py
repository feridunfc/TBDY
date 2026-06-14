from __future__ import annotations

import json
from pathlib import Path

from tools.render_product_report import MODAL_THRESHOLD, render_product_report
from tools.smoke_live_feature_resolver import FULL_ROW_CAPTURE_TABLES


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _product_input(tmp_path: Path) -> Path:
    root = tmp_path / "c13_product"
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
                    {"Story": "+14.5", "Label": "B1", "UniqueName": "297", "Type": "Beam", "Length": "7", "AnalysisSect": "B40x70", "DesignSect": "B40x70"},
                    {"Story": "+14.5", "Label": "B4", "UniqueName": "300", "Type": "Beam", "Length": "3.6", "AnalysisSect": "B40x70", "DesignSect": "B40x70"},
                    {"Story": "+10.5", "Label": "B8", "UniqueName": "401", "Type": "Beam", "Length": "5", "AnalysisSect": "B60x70", "DesignSect": "B60x70"},
                    {"Story": "+4.50", "Label": "B290", "UniqueName": "760", "Type": "Beam", "Length": "3.7", "AnalysisSect": "HE160A", "DesignSect": "HE160A"},
                    {"Story": "+4.50", "Label": "B291", "UniqueName": "761", "Type": "Beam", "Length": "3.7", "AnalysisSect": "HE160A", "DesignSect": "HE160A"},
                    {"Story": "+10.5", "Label": "C1", "UniqueName": "900", "Type": "Column", "Length": "3", "AnalysisSect": "C40x40", "DesignSect": "C40x40"},
                ],
            },
            "frame_section_properties": {
                "actual_table_name": "Frame Section Property Definitions - Concrete Rectangular",
                "columns": ["Name", "t2", "t3"],
                "rows": [
                    {"Name": "B40x70", "t2": "0.4", "t3": "0.7"},
                    {"Name": "B60x70", "t2": "0.6", "t3": "0.7"},
                    {"Name": "C40x40", "t2": "0.4", "t3": "0.4"},
                ],
            },
            "modal_participating_mass": {
                "actual_table_name": "Modal Participating Mass Ratios",
                "columns": ["Mode", "Period", "UX", "UY", "SumUX", "SumUY", "RZ", "SumRZ", "OutputCase"],
                "rows": [
                    {"Mode": 1, "Period": 1.1, "UX": 0.1, "UY": 0.2, "SumUX": 0.1, "SumUY": 0.2, "RZ": 0.01, "SumRZ": 0.01, "OutputCase": "Modal"},
                    {"Mode": 2, "Period": 0.9, "UX": 0.4, "UY": 0.3, "SumUX": 0.5, "SumUY": 0.5, "RZ": 0.02, "SumRZ": 0.03, "OutputCase": "Modal"},
                    {"Mode": 3, "Period": 0.7, "UX": 0.4999, "UY": 0.4999, "SumUX": 0.9999, "SumUY": 0.9999, "RZ": 0.03, "SumRZ": 0.06, "OutputCase": "Modal"},
                ],
            },
        },
    })
    return root


def test_c13_product_report_outputs_all_required_files(tmp_path: Path):
    product_input = _product_input(tmp_path)
    out = product_input / "report"
    summary = render_product_report(product_input, out)
    assert (out / "product_report.html").is_file()
    assert (out / "product_report.md").is_file()
    assert (out / "product_summary.json").is_file()
    assert summary["product_slice_passed"] is True
    assert summary["report_product_passed"] is True


def test_c13_concrete_rectangular_beam_sections_are_checked(tmp_path: Path):
    summary = render_product_report(_product_input(tmp_path), tmp_path / "report")
    assert summary["assigned_beam_section_type_count"] == 3
    assert summary["total_beam_count"] == 5
    assert summary["concrete_beam_section_type_count"] == 2
    assert summary["concrete_beam_object_count"] == 3
    sections = {row["section_name"]: row for row in summary["beam_section_type_results"]}
    assert sections["B40x70"]["assigned_beam_count"] == 2
    assert sections["B60x70"]["assigned_beam_count"] == 1
    assert "HE160A" not in sections


def test_c13_b40x70_geometry_checks_are_ok(tmp_path: Path):
    summary = render_product_report(_product_input(tmp_path), tmp_path / "report")
    b40 = next(row for row in summary["beam_section_type_results"] if row["section_name"] == "B40x70")
    checks = {check["check_id"]: check for check in b40["checks"]}
    assert b40["classification"] == "CONCRETE_RECTANGULAR_BEAM_CHECKED"
    assert b40["width_mm"] == 400.0
    assert b40["depth_mm"] == 700.0
    assert checks["beam_geometry_min_width"]["status"] == "OK"
    assert checks["beam_geometry_min_width"]["ratio"] == 1.6
    assert checks["beam_geometry_min_depth"]["status"] == "OK"
    assert checks["beam_depth_width_ratio"]["value"] == 1.75
    assert checks["beam_depth_width_ratio"]["status"] == "OK"


def test_c13_unsupported_steel_or_non_concrete_beam_section_is_not_fail(tmp_path: Path):
    summary = render_product_report(_product_input(tmp_path), tmp_path / "report")
    unsupported = {row["section_name"]: row for row in summary["unsupported_sections"]}
    assert "HE160A" in unsupported
    assert unsupported["HE160A"]["status"] == "OUT_OF_SCOPE"
    assert unsupported["HE160A"]["classification"] == "UNSUPPORTED_OR_NON_CONCRETE_BEAM_SECTION"
    assert unsupported["HE160A"]["assigned_beam_count"] == 2
    assert summary["unsupported_beam_section_type_count"] == 1
    assert summary["unsupported_beam_object_count"] == 2
    assert summary["fail_count"] == 0
    assert summary["report_product_passed"] is True


def test_c13_modal_full_table_and_final_095_verdict(tmp_path: Path):
    summary = render_product_report(_product_input(tmp_path), tmp_path / "report")
    modal = summary["modal_mass_summary"]
    assert summary["modal_threshold"] == MODAL_THRESHOLD == 0.95
    assert modal["modal_mass_table_rows"] == 3
    assert modal["modal_mass_participation_ux"]["value"] == 0.9999
    assert modal["modal_mass_participation_uy"]["value"] == 0.9999
    assert summary["modal_ux_status"] == "OK"
    assert summary["modal_uy_status"] == "OK"
    assert "SumUX" in modal["columns"]


def test_c13_report_includes_unsupported_section_table(tmp_path: Path):
    product_input = _product_input(tmp_path)
    out = product_input / "report"
    render_product_report(product_input, out)
    md = (out / "product_report.md").read_text(encoding="utf-8")
    html = (out / "product_report.html").read_text(encoding="utf-8")
    assert "Unsupported / Out-of-Scope Beam Sections" in md
    assert "HE160A" in md
    assert "Not counted as FAIL" in md
    assert "Unsupported" in html


def test_c13_guardrails_remain_locked(tmp_path: Path):
    summary = render_product_report(_product_input(tmp_path), tmp_path / "report")
    assert summary["guardrails"] == {
        "excel_production_path_used": False,
        "streamlit_ui_used": False,
        "legacy_runtime_used": False,
        "rebar_flexure_shear_capacity_unlocked": False,
    }


def test_c13_live_smoke_captures_full_rows_for_report_tables():
    assert "Frame Assignments - Summary" in FULL_ROW_CAPTURE_TABLES
    assert "Frame Section Property Definitions - Concrete Rectangular" in FULL_ROW_CAPTURE_TABLES
    assert "Modal Participating Mass Ratios" in FULL_ROW_CAPTURE_TABLES
