from __future__ import annotations

import json
from pathlib import Path

from tools.render_product_report import build_product_summary
from tbdy_engine.product_reports.check_results import (
    RETIRED_LEGACY_CHECK_IDS,
    build_check_limit_contract,
    build_formal_check_artifacts,
)


def _write_input(tmp_path: Path, canonical_results: list[dict]) -> Path:
    source = {
        "tables": {
            "frame_assignments": {
                "actual_table_name": "Frame Assignments - Summary",
                "columns": ["Story", "Label", "Type", "DesignSect"],
                "rows": [
                    {"Story": "S1", "Label": "B1", "Type": "Beam", "DesignSect": "BSEC"},
                    {"Story": "S1", "Label": "C1", "Type": "Column", "DesignSect": "CSEC"},
                ],
            },
            # These raw section values deliberately contradict some canonical results.
            # B1 reporter must never evaluate or unit-convert them.
            "frame_section_properties": {
                "actual_table_name": "Frame Section Property Definitions - Concrete Rectangular",
                "columns": ["Section", "t2", "t3"],
                "rows": [
                    {"Section": "BSEC", "t2": 9999, "t3": 9999},
                    {"Section": "CSEC", "t2": 1, "t3": 1},
                ],
            },
            "modal_mass_ratios": {"actual_table_name": "Modal Participating Mass Ratios", "columns": [], "rows": []},
        }
    }
    (tmp_path / "product_report_source_tables.json").write_text(json.dumps(source), encoding="utf-8")
    (tmp_path / "canonical_member_check_results.json").write_text(json.dumps(canonical_results), encoding="utf-8")
    return tmp_path


def _result(
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
        "ratio_type": "actual_over_minimum" if check_id != "beam_depth_width_ratio" else "value_over_maximum",
        "pass_rule": "fixture-canonical",
        "unit": unit,
        "evaluation_level": "DESIGN_LEVEL",
        "evidence": [{"canonical": True}],
        "messages": ["canonical fixture"],
        "code_ref": "fixture",
        "diagnostics": [],
    }


def test_canonical_fail_remains_fail_even_when_raw_geometry_would_have_passed_legacy_logic(tmp_path: Path) -> None:
    input_dir = _write_input(tmp_path, [
        _result(
            check_id="beam_geometry_min_width", component="B1", component_type="beam",
            section="BSEC", status="FAIL", value=249, limit=250, ratio=0.996, unit="mm",
        )
    ])
    summary = build_product_summary(input_dir)
    row = summary["beam_section_detail_rows"][0]
    assert row["status"] == "FAIL"
    assert row["value"] == 249
    assert row["limit"] == 250
    assert row["ratio"] == 0.996


def test_canonical_ok_remains_ok_even_when_raw_geometry_would_have_failed_legacy_logic(tmp_path: Path) -> None:
    input_dir = _write_input(tmp_path, [
        _result(
            check_id="column_geometry_min_dimension", component="C1", component_type="column",
            section="CSEC", status="OK", value=300, limit=300, ratio=1.0, unit="mm",
        )
    ])
    summary = build_product_summary(input_dir)
    assert summary["column_section_detail_rows"][0]["status"] == "OK"


def test_reporter_does_not_recalculate_beam_h_over_bw_status(tmp_path: Path) -> None:
    input_dir = _write_input(tmp_path, [
        _result(
            check_id="beam_depth_width_ratio", component="B1", component_type="beam",
            section="BSEC", status="OK", value=99.0, limit=3.5, ratio=28.285714, unit="",
        )
    ])
    summary = build_product_summary(input_dir)
    row = summary["beam_section_detail_rows"][0]
    assert row["status"] == "OK"
    assert row["value"] == 99.0
    assert row["ratio"] == 28.285714


def test_retired_area_and_aspect_have_metadata_only_no_formal_limit_or_verdict(tmp_path: Path) -> None:
    input_dir = _write_input(tmp_path, [])
    summary = build_product_summary(input_dir)
    assert tuple(summary["retired_legacy_check_ids"]) == RETIRED_LEGACY_CHECK_IDS
    assert not any(row.get("check_id") in RETIRED_LEGACY_CHECK_IDS for row in summary["column_section_detail_rows"])

    limit_contract = build_check_limit_contract()
    text = json.dumps(limit_contract, sort_keys=True)
    assert "75000" not in text
    assert "min_area_mm2" not in text
    assert "min_aspect_ratio" not in text
    for retired in RETIRED_LEGACY_CHECK_IDS:
        assert retired in limit_contract["retired_legacy_check_ids"]


def test_product_check_result_projection_preserves_canonical_member_status_and_fields(tmp_path: Path) -> None:
    input_dir = _write_input(tmp_path, [
        _result(
            check_id="beam_geometry_min_width", component="B1", component_type="beam",
            section="BSEC", status="FAIL", value=249, limit=250, ratio=0.996, unit="mm",
        ),
        _result(
            check_id="column_geometry_min_dimension", component="C1", component_type="column",
            section="CSEC", status="OK", value=300, limit=300, ratio=1.0, unit="mm",
        ),
    ])
    summary = build_product_summary(input_dir)
    report = {
        "beam_section_detail": summary["beam_section_detail_rows"],
        "column_section_detail": summary["column_section_detail_rows"],
        "modal_mass_final_verdict": summary["modal_mass_final_verdict_rows"],
    }
    artifacts = build_formal_check_artifacts(
        report=report,
        object_scope_ledger=(),
        material_evidence_rows=(),
        product_summary={},
        source_tables={},
    )
    beam = artifacts["check_results_concrete_beam_min_geometry.json"]["results"][0]
    column = artifacts["check_results_concrete_column_min_geometry.json"]["results"][0]
    assert (beam["status"], beam["value"], beam["limit"], beam["ratio"]) == ("FAIL", 249, 250, 0.996)
    assert (column["status"], column["value"], column["limit"], column["ratio"]) == ("OK", 300, 300, 1.0)


def test_member_reporter_source_has_no_magnitude_unit_heuristic_or_legacy_member_threshold_authority() -> None:
    reporter_source = Path("tools/render_product_report.py").read_text(encoding="utf-8")
    product_source = Path("tbdy_engine/product_reports/check_results.py").read_text(encoding="utf-8")
    assert "_length_to_mm" not in reporter_source
    assert "abs(number) <= 30" not in reporter_source
    assert "COLUMN_MIN_AREA_MM2" not in reporter_source
    assert "COLUMN_ASPECT_RATIO_LIMIT" not in reporter_source
    assert "BEAM_HBW_LIMIT" not in reporter_source
    assert "75000.0" not in product_source
    assert "min_area_mm2" not in product_source
    assert "min_aspect_ratio" not in product_source
