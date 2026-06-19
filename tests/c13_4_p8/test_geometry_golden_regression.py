from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from tbdy_engine.product.golden_regression import run_geometry_golden_regression

ROOT = Path(__file__).resolve().parents[2]
FEATURE_SNAPSHOT = ROOT / "tests" / "fixtures" / "c13_4_p4" / "geometry_feature_snapshots.json"
GOLDEN = ROOT / "tests" / "fixtures" / "c13_4_p8" / "golden_geometry_product_fingerprint.json"
EXPECTED_TABLE_NAMES = [
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


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_golden_regression_passes_using_canonical_fixture_and_committed_golden(tmp_path: Path):
    out_dir = tmp_path / "golden_regression"

    result = run_geometry_golden_regression(
        feature_snapshot_path=FEATURE_SNAPSHOT,
        output_dir=out_dir,
        golden_fingerprint_path=GOLDEN,
    )

    assert result.status == "OK"
    assert result.difference_count == 0
    assert result.error_count == 0
    assert result.actual_fingerprint == result.expected_fingerprint


def test_cli_passes_using_canonical_fixture_and_committed_golden(tmp_path: Path):
    out_dir = tmp_path / "cli_golden_regression"

    completed = subprocess.run(
        [
            sys.executable,
            "tools/run_geometry_golden_regression.py",
            "--feature-snapshot",
            str(FEATURE_SNAPSHOT),
            "--golden",
            str(GOLDEN),
            "--out",
            str(out_dir),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert "Geometry golden regression: OK" in completed.stdout
    assert f"Output: {out_dir}" in completed.stdout
    assert f"Bundle: {out_dir / 'product_smoke'}" in completed.stdout
    assert f"Validation: {out_dir / 'product_smoke' / 'geometry_product_bundle_validation.json'}" in completed.stdout
    assert f"Golden: {GOLDEN}" in completed.stdout
    assert f"Report: {out_dir / 'geometry_golden_regression_report.json'}" in completed.stdout
    assert "Differences: 0" in completed.stdout
    assert "Errors: 0" in completed.stdout


def test_output_directory_contains_required_regression_bundle_files(tmp_path: Path):
    out_dir = tmp_path / "golden_regression"

    run_geometry_golden_regression(
        feature_snapshot_path=FEATURE_SNAPSHOT,
        output_dir=out_dir,
        golden_fingerprint_path=GOLDEN,
    )

    assert (out_dir / "product_smoke").is_dir()
    assert (out_dir / "product_smoke" / "artifacts" / "check_results.json").is_file()
    assert (out_dir / "product_smoke" / "reports" / "geometry_report.md").is_file()
    assert (out_dir / "product_smoke" / "product_smoke_summary.json").is_file()
    assert (out_dir / "product_smoke" / "product_smoke_manifest.json").is_file()
    assert (out_dir / "product_smoke" / "geometry_product_bundle_validation.json").is_file()
    assert (out_dir / "geometry_golden_regression_report.json").is_file()


def test_regression_report_status_counts_and_fingerprints(tmp_path: Path):
    out_dir = tmp_path / "golden_regression"

    run_geometry_golden_regression(
        feature_snapshot_path=FEATURE_SNAPSHOT,
        output_dir=out_dir,
        golden_fingerprint_path=GOLDEN,
    )
    report = _read_json(out_dir / "geometry_golden_regression_report.json")

    assert report["status"] == "OK"
    assert report["counts"] == {"difference_count": 0, "error_count": 0}
    assert report["actual_fingerprint"] == report["expected_fingerprint"]


def test_actual_fingerprint_is_path_normalized(tmp_path: Path):
    out_dir = tmp_path / "golden_regression"

    result = run_geometry_golden_regression(
        feature_snapshot_path=FEATURE_SNAPSHOT,
        output_dir=out_dir,
        golden_fingerprint_path=GOLDEN,
    )
    fingerprint_text = json.dumps(result.actual_fingerprint, sort_keys=True)

    assert "local_out" not in fingerprint_text
    assert str(out_dir) not in fingerprint_text
    assert str(FEATURE_SNAPSHOT) not in fingerprint_text
    assert str(GOLDEN) not in fingerprint_text


def test_actual_fingerprint_has_expected_semantic_shape(tmp_path: Path):
    out_dir = tmp_path / "golden_regression"

    result = run_geometry_golden_regression(
        feature_snapshot_path=FEATURE_SNAPSHOT,
        output_dir=out_dir,
        golden_fingerprint_path=GOLDEN,
    )
    actual = result.actual_fingerprint

    assert len(actual["checks"]) == 6
    assert actual["report"]["table_names"] == EXPECTED_TABLE_NAMES
    assert len(actual["report"]["table_names"]) == 9
    assert actual["p6"]["check_result_count"] == 6
    assert actual["p7"]["report_table_count"] == 9
    assert actual["guardrails"]["geometry_only"] is True


def test_regression_json_is_deterministic_across_repeated_runs(tmp_path: Path):
    out_dir = tmp_path / "golden_regression"
    report_path = out_dir / "geometry_golden_regression_report.json"

    run_geometry_golden_regression(
        feature_snapshot_path=FEATURE_SNAPSHOT,
        output_dir=out_dir,
        golden_fingerprint_path=GOLDEN,
    )
    first = report_path.read_text(encoding="utf-8")
    run_geometry_golden_regression(
        feature_snapshot_path=FEATURE_SNAPSHOT,
        output_dir=out_dir,
        golden_fingerprint_path=GOLDEN,
    )
    second = report_path.read_text(encoding="utf-8")

    assert first == second
    assert first.endswith("\n")
