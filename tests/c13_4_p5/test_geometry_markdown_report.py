from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from tbdy_engine.reports.geometry_markdown_report import render_geometry_markdown_report_from_artifact_dir

ROOT = Path(__file__).resolve().parents[2]
ARTIFACT_DIR = ROOT / "tests" / "fixtures" / "c13_4_p5" / "p4_artifacts"
EXPECTED_HEADINGS = (
    "## 1. Executive Summary",
    "## 2. Geometry Check Summary",
    "## 3. Adapter Diagnostics",
    "## 4. Beam Geometry Detail",
    "## 5. Column Geometry Detail",
    "## 6. Evidence Trace Detail",
    "## 7. Artifact Manifest",
    "## 8. Guardrails",
    "## 9. Boundary Notes",
)
EXPECTED_TABLE_NAMES = (
    "Table name: executive_summary",
    "Table name: geometry_check_summary",
    "Table name: adapter_diagnostics",
    "Table name: beam_geometry_detail",
    "Table name: column_geometry_detail",
    "Table name: evidence_trace_detail",
    "Table name: artifact_manifest",
    "Table name: guardrails",
    "Table name: boundary_notes",
)


def _render(tmp_path: Path) -> str:
    output_path = tmp_path / "geometry_report.md"
    render_geometry_markdown_report_from_artifact_dir(artifact_dir=ARTIFACT_DIR, output_path=output_path)
    return output_path.read_text(encoding="utf-8")


def _section(report: str, heading: str, next_heading: str | None = None) -> str:
    start = report.index(heading)
    if next_heading is None:
        return report[start:]
    end = report.index(next_heading)
    return report[start:end]


def test_report_renders_from_valid_p4_artifact_fixture(tmp_path: Path):
    output_path = tmp_path / "geometry_report.md"

    result = render_geometry_markdown_report_from_artifact_dir(artifact_dir=ARTIFACT_DIR, output_path=output_path)

    assert output_path.is_file()
    assert result.report_path == output_path
    assert result.section_count == 9
    assert result.table_names == tuple(item.removeprefix("Table name: ") for item in EXPECTED_TABLE_NAMES)
    assert result.source_artifacts == (
        "check_results.json",
        "adapter_diagnostics.json",
        "run_summary.json",
        "run_manifest.json",
    )


def test_report_starts_with_required_title(tmp_path: Path):
    report = _render(tmp_path)

    assert report.startswith("# TBDY Geometry Vertical Slice Report — C13.4-P5\n")


def test_report_includes_required_section_headings_in_exact_order(tmp_path: Path):
    report = _render(tmp_path)

    positions = [report.index(heading) for heading in EXPECTED_HEADINGS]
    assert positions == sorted(positions)


def test_each_section_includes_correct_table_name(tmp_path: Path):
    report = _render(tmp_path)

    for table_name in EXPECTED_TABLE_NAMES:
        assert table_name in report


def test_executive_summary_contains_required_metrics(tmp_path: Path):
    report = _render(tmp_path)
    executive = _section(report, EXPECTED_HEADINGS[0], EXPECTED_HEADINGS[1])

    for metric in (
        "report_product_passed",
        "snapshot_count",
        "check_result_count",
        "adapter_diagnostic_count",
        "total_ok_count",
        "total_fail_count",
        "artifact_scope",
    ):
        assert metric in executive
    assert "| total_ok_count | 4 |" in executive
    assert "| total_fail_count | 0 |" in executive
    assert "| artifact_scope | GEOMETRY_ONLY |" in executive


def test_beam_detail_includes_existing_beam_geometry_rows_only(tmp_path: Path):
    report = _render(tmp_path)
    beam_detail = _section(report, EXPECTED_HEADINGS[3], EXPECTED_HEADINGS[4])

    assert "beam_geometry_min_width" in beam_detail
    assert "beam_geometry_min_depth" in beam_detail
    assert "beam_depth_width_ratio" in beam_detail
    assert "column_geometry_min_dimension" not in beam_detail
    assert "column_geometry_min_area" not in beam_detail
    assert "column_geometry_aspect_ratio" not in beam_detail


def test_column_detail_includes_existing_column_geometry_rows_only(tmp_path: Path):
    report = _render(tmp_path)
    column_detail = _section(report, EXPECTED_HEADINGS[4], EXPECTED_HEADINGS[5])

    assert "column_geometry_min_dimension" in column_detail
    assert "beam_geometry_min_width" not in column_detail
    assert "column_geometry_min_area" not in column_detail
    assert "column_geometry_aspect_ratio" not in column_detail


def test_evidence_trace_detail_preserves_required_evidence_fields(tmp_path: Path):
    report = _render(tmp_path)
    evidence = _section(report, EXPECTED_HEADINGS[5], EXPECTED_HEADINGS[6])

    for text in (
        "source_geometry_table",
        "ETABS Geometry Source",
        "beam_width_mm",
        "beam_depth_mm",
        "column_width_mm",
        "column_depth_mm",
        "300.0",
        "600.0",
        "400.0",
        "500.0",
        "mm",
        "c13_4_p4_fixture_resolver",
    ):
        assert text in evidence


def test_adapter_diagnostics_section_handles_empty_diagnostics_deterministically(tmp_path: Path):
    report = _render(tmp_path)
    diagnostics = _section(report, EXPECTED_HEADINGS[2], EXPECTED_HEADINGS[3])

    assert "| - | - | - | NONE |  |  | No adapter diagnostics |" in diagnostics


def test_guardrails_include_forbidden_scope_as_false(tmp_path: Path):
    report = _render(tmp_path)
    guardrails = _section(report, EXPECTED_HEADINGS[7], EXPECTED_HEADINGS[8])

    for guardrail in (
        "etabs_live_fetching_used",
        "excel_production_path_used",
        "streamlit_ui_used",
        "legacy_runtime_used",
        "rebar_flexure_shear_capacity_unlocked",
        "modal_mass_unlocked",
    ):
        assert f"| {guardrail} | False |" in guardrails
    assert "| report_only_no_check_execution | True |" in guardrails
    assert "| no_new_engineering_logic | True |" in guardrails


def test_output_is_deterministic_across_repeated_runs(tmp_path: Path):
    output_path = tmp_path / "geometry_report.md"

    render_geometry_markdown_report_from_artifact_dir(artifact_dir=ARTIFACT_DIR, output_path=output_path)
    first = output_path.read_text(encoding="utf-8")
    render_geometry_markdown_report_from_artifact_dir(artifact_dir=ARTIFACT_DIR, output_path=output_path)
    second = output_path.read_text(encoding="utf-8")

    assert first == second
    assert first.endswith("\n")


def test_cli_script_runs_from_repo_root_and_writes_report(tmp_path: Path):
    output_path = tmp_path / "report" / "geometry_report.md"

    completed = subprocess.run(
        [
            sys.executable,
            "tools/render_geometry_report.py",
            "--artifact-dir",
            str(ARTIFACT_DIR),
            "--out",
            str(output_path),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert "Geometry Markdown report: OK" in completed.stdout
    assert "Sections: 9" in completed.stdout
    assert "Tables: 9" in completed.stdout
    assert output_path.is_file()
