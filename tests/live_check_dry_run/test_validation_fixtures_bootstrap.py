from __future__ import annotations

import json
from pathlib import Path

from tools.bootstrap_validation_fixtures import bootstrap_validation_fixtures
from tbdy_engine.checks.dry_run import build_and_write_c11_outputs


def test_live_check_dry_run_fixtures_are_available_from_clean_zip():
    outputs = bootstrap_validation_fixtures()
    for path in outputs.values():
        assert Path(path).is_file(), path
    assert Path("local_out/c10_minimal_live_readiness/feature_snapshot_with_context.json").is_file()
    assert Path("local_out/c10_minimal_live_readiness/coverage_matrix.json").is_file()


def test_bootstrap_validation_fixtures_outputs_required_c10_files():
    bootstrap_validation_fixtures()
    required = {
        Path("local_out/c9_live_coverage_matrix/coverage_matrix.json"),
        Path("local_out/c10_minimal_live_readiness/feature_snapshot_with_context.json"),
        Path("local_out/c10_minimal_live_readiness/coverage_matrix.json"),
    }
    assert all(path.is_file() for path in required)


def test_bootstrapped_c11_boundary_report_count_is_3(tmp_path):
    bootstrap_validation_fixtures()
    out = tmp_path / "c11"
    build_and_write_c11_outputs(
        Path("local_out/c10_minimal_live_readiness/feature_snapshot_with_context.json"),
        Path("local_out/c10_minimal_live_readiness/coverage_matrix.json"),
        out,
    )
    boundary = json.loads((out / "c11_boundary_report.json").read_text(encoding="utf-8"))
    summary = json.loads((out / "check_results_summary.json").read_text(encoding="utf-8"))
    results = json.loads((out / "check_results.json").read_text(encoding="utf-8"))
    assert boundary["check_result_count"] == 3
    assert boundary["check_result_count"] == summary["check_result_count"] == len(results)
