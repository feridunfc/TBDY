from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from tbdy_engine.product.geometry_product_smoke import run_geometry_product_smoke

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests" / "fixtures" / "c13_4_p4" / "geometry_feature_snapshots.json"
REQUIRED_OUTPUTS = {
    "artifacts/coverage_rows.json",
    "artifacts/coverage_execution_trace.json",
    "artifacts/check_results.json",
    "artifacts/adapter_diagnostics.json",
    "artifacts/run_summary.json",
    "artifacts/run_manifest.json",
    "reports/geometry_report.md",
    "product_smoke_summary.json",
    "product_smoke_manifest.json",
}


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _collect_files(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): path.read_text(encoding="utf-8")
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_successful_product_smoke_creates_required_directory_structure(tmp_path: Path):
    out_dir = tmp_path / "product_smoke"

    result = run_geometry_product_smoke(feature_snapshot_path=FIXTURE, output_dir=out_dir)

    assert result.output_dir == out_dir
    assert result.artifact_dir == out_dir / "artifacts"
    assert result.report_path == out_dir / "reports" / "geometry_report.md"
    assert result.product_smoke_summary_path == out_dir / "product_smoke_summary.json"
    assert result.product_smoke_manifest_path == out_dir / "product_smoke_manifest.json"
    assert (out_dir / "artifacts").is_dir()
    assert (out_dir / "reports").is_dir()


def test_successful_product_smoke_writes_all_required_outputs(tmp_path: Path):
    out_dir = tmp_path / "product_smoke"

    run_geometry_product_smoke(feature_snapshot_path=FIXTURE, output_dir=out_dir)

    assert {path.relative_to(out_dir).as_posix() for path in out_dir.rglob("*") if path.is_file()} == REQUIRED_OUTPUTS


def test_summary_json_has_required_p4_and_p5_counts(tmp_path: Path):
    out_dir = tmp_path / "product_smoke"

    result = run_geometry_product_smoke(feature_snapshot_path=FIXTURE, output_dir=out_dir)
    summary = _read_json(out_dir / "product_smoke_summary.json")

    assert result.status == "OK"
    assert result.p4_check_result_count == 6
    assert result.p4_adapter_diagnostic_count == 0
    assert result.p4_coverage_execution_trace_count == 6
    assert result.p5_section_count == 9
    assert result.p5_table_count == 9
    assert summary["status"] == "OK"
    assert summary["scope"] == "GEOMETRY_ONLY_PRODUCT_SMOKE"
    assert summary["p4"]["check_result_count"] == 6
    assert summary["p4"]["adapter_diagnostic_count"] == 0
    assert summary["p4"]["check_result_status_counts"] == {"OK": 6}
    assert summary["p4"]["coverage_row_count"] == 6
    assert summary["p4"]["coverage_status_counts"] == {"RUNNABLE": 6}
    assert summary["p4"]["coverage_execution_trace_count"] == 6
    assert summary["p4"]["check_input_emitted_count"] == 6
    assert summary["p4"]["check_input_not_emitted_count"] == 0
    assert summary["p4"]["check_result_emitted_count"] == 6
    assert summary["p4"]["check_result_not_emitted_count"] == 0
    assert summary["p4"]["trace_adapter_status_counts"] == {"READY": 6}
    assert summary["p4"]["trace_result_status_counts"] == {"OK": 6}
    assert summary["outputs"]["coverage_rows_json"] == str(out_dir / "artifacts" / "coverage_rows.json")
    assert summary["outputs"]["coverage_execution_trace_json"] == str(
        out_dir / "artifacts" / "coverage_execution_trace.json"
    )
    assert summary["p5"]["section_count"] == 9
    assert summary["p5"]["table_count"] == 9
    assert summary["p5"]["table_names"] == [
        "executive_summary",
        "geometry_check_summary",
        "adapter_diagnostics",
        "beam_geometry_detail",
        "column_geometry_detail",
        "evidence_trace_detail",
        "artifact_manifest",
        "guardrails",
        "boundary_notes",
    ]


def test_manifest_json_has_required_guardrails_and_forbidden_scope(tmp_path: Path):
    out_dir = tmp_path / "product_smoke"

    run_geometry_product_smoke(feature_snapshot_path=FIXTURE, output_dir=out_dir)
    manifest = _read_json(out_dir / "product_smoke_manifest.json")

    assert manifest["runner"] == "C13.4-P6 Geometry Product Smoke"
    assert manifest["scope"] == "GEOMETRY_ONLY_PRODUCT_SMOKE"
    assert manifest["guardrails"]["geometry_only"] is True
    assert manifest["guardrails"]["orchestration_only"] is True
    assert manifest["guardrails"]["etabs_live_fetching_used"] is False
    assert manifest["guardrails"]["excel_production_path_used"] is False
    assert manifest["guardrails"]["legacy_runtime_used"] is False
    assert manifest["guardrails"]["final_building_compliance_verdict_emitted"] is False
    assert "beam_flexure" in manifest["forbidden_scope"]
    assert "modal_mass" in manifest["forbidden_scope"]
    assert "artifacts/coverage_execution_trace.json" in manifest["artifact_files"]


def test_report_file_starts_with_p5_title(tmp_path: Path):
    out_dir = tmp_path / "product_smoke"

    run_geometry_product_smoke(feature_snapshot_path=FIXTURE, output_dir=out_dir)

    assert (out_dir / "reports" / "geometry_report.md").read_text(encoding="utf-8").startswith(
        "# TBDY Geometry Vertical Slice Report — C13.4-P5\n"
    )


def test_cli_script_runs_from_repo_root_and_writes_all_outputs(tmp_path: Path):
    out_dir = tmp_path / "cli_product_smoke"

    completed = subprocess.run(
        [
            sys.executable,
            "tools/run_geometry_product_smoke.py",
            "--feature-snapshot",
            str(FIXTURE),
            "--out",
            str(out_dir),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert "Geometry product smoke: OK" in completed.stdout
    assert f"Artifacts: {out_dir / 'artifacts'}" in completed.stdout
    assert f"Report: {out_dir / 'reports' / 'geometry_report.md'}" in completed.stdout
    assert "CheckResults: 6" in completed.stdout
    assert "Adapter diagnostics: 0" in completed.stdout
    assert "Sections: 9" in completed.stdout
    assert "Tables: 9" in completed.stdout
    assert f"Summary: {out_dir / 'product_smoke_summary.json'}" in completed.stdout
    assert f"Manifest: {out_dir / 'product_smoke_manifest.json'}" in completed.stdout
    assert {path.relative_to(out_dir).as_posix() for path in out_dir.rglob("*") if path.is_file()} == REQUIRED_OUTPUTS


def test_output_is_deterministic_across_repeated_runs(tmp_path: Path):
    out_dir = tmp_path / "product_smoke"

    run_geometry_product_smoke(feature_snapshot_path=FIXTURE, output_dir=out_dir)
    first = _collect_files(out_dir)
    run_geometry_product_smoke(feature_snapshot_path=FIXTURE, output_dir=out_dir)
    second = _collect_files(out_dir)

    assert first == second
    assert all(content.endswith("\n") for content in first.values())
