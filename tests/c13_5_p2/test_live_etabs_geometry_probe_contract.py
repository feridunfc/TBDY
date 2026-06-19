from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import tbdy_engine.features.live_etabs_geometry_probe as probe_module
from tbdy_engine.features.live_etabs_geometry_probe import (
    load_mapping_provider_from_json,
    probe_geometry_feature_snapshots,
)
from tbdy_engine.product.geometry_product_smoke import run_geometry_product_smoke
from tbdy_engine.product.offline_acceptance import build_offline_acceptance_command_plan

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests" / "fixtures" / "c13_5_p2" / "fake_live_etabs_geometry_tables.json"
MODULE_PATH = ROOT / "tbdy_engine" / "features" / "live_etabs_geometry_probe.py"
CLI_PATH = ROOT / "tools" / "probe_live_etabs_geometry_snapshot.py"


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _probe_good_rows(tmp_path: Path):
    return probe_geometry_feature_snapshots(
        provider=load_mapping_provider_from_json(FIXTURE),
        output_dir=tmp_path,
        target_story="+14.5",
        max_rows=2,
    )


def test_cli_refuses_live_probe_without_explicit_live_etabs_flag(tmp_path: Path):
    completed = subprocess.run(
        [
            sys.executable,
            "tools/probe_live_etabs_geometry_snapshot.py",
            "--out",
            str(tmp_path / "probe"),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 2
    assert "requires explicit --live-etabs opt-in" in completed.stderr
    assert not (tmp_path / "probe").exists()


def test_module_imports_without_etabs():
    assert probe_module.__name__ == "tbdy_engine.features.live_etabs_geometry_probe"


def test_fake_provider_produces_beam_and_column_feature_snapshots(tmp_path: Path):
    result = _probe_good_rows(tmp_path)
    payload = _read_json(result.feature_snapshot_path)
    snapshots = {item["component_id"]: item for item in payload["snapshots"]}

    assert result.status == "OK"
    assert result.snapshot_count == 2
    assert set(snapshots) == {"B1", "C1"}
    assert set(snapshots["B1"]["features"]) == {"beam_width_mm", "beam_depth_mm"}
    assert set(snapshots["C1"]["features"]) == {"column_width_mm", "column_depth_mm"}


def test_feature_values_use_feature_statuses_not_decision_statuses(tmp_path: Path):
    result = _probe_good_rows(tmp_path)
    payload = _read_json(result.feature_snapshot_path)
    statuses = {
        feature_payload["status"]
        for snapshot in payload["snapshots"]
        for feature_payload in snapshot["features"].values()
    }

    assert statuses == {"RESOLVED"}
    assert statuses.isdisjoint({"OK", "FAIL"})


def test_evidence_contains_required_provenance_fields(tmp_path: Path):
    result = _probe_good_rows(tmp_path)
    payload = _read_json(result.feature_snapshot_path)
    required_fields = {
        "source_table",
        "actual_table_name",
        "source_column",
        "source_row",
        "raw_value",
        "normalized_value",
        "unit",
        "resolver",
        "evidence_status",
    }

    for snapshot in payload["snapshots"]:
        for feature_payload in snapshot["features"].values():
            evidence = feature_payload["evidence"]
            assert len(evidence) == 1
            assert required_fields.issubset(evidence[0])
            assert evidence[0]["evidence_status"] == "FULL"
            assert evidence[0]["unit"] == "mm"


def test_output_files_are_written_with_expected_contract(tmp_path: Path):
    result = _probe_good_rows(tmp_path)

    assert result.feature_snapshot_path == tmp_path / "feature_snapshot.json"
    assert result.summary_path == tmp_path / "live_geometry_probe_summary.json"
    assert result.diagnostics_path == tmp_path / "live_geometry_probe_diagnostics.json"
    assert result.manifest_path == tmp_path / "live_geometry_probe_manifest.json"
    assert {path.name for path in tmp_path.iterdir()} == {
        "feature_snapshot.json",
        "live_geometry_probe_summary.json",
        "live_geometry_probe_diagnostics.json",
        "live_geometry_probe_manifest.json",
    }


def test_output_files_are_deterministic(tmp_path: Path):
    _probe_good_rows(tmp_path)
    first = {path.name: path.read_text(encoding="utf-8") for path in sorted(tmp_path.iterdir())}
    _probe_good_rows(tmp_path)
    second = {path.name: path.read_text(encoding="utf-8") for path in sorted(tmp_path.iterdir())}

    assert first == second
    assert all(content.endswith("\n") for content in first.values())


def test_cli_can_use_fake_provider_fixture_for_ci_without_real_etabs(tmp_path: Path):
    out_dir = tmp_path / "probe"

    completed = subprocess.run(
        [
            sys.executable,
            "tools/probe_live_etabs_geometry_snapshot.py",
            "--live-etabs",
            "--fake-provider-fixture",
            str(FIXTURE),
            "--out",
            str(out_dir),
            "--max-rows",
            "2",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert "Live geometry probe: OK" in completed.stdout
    assert "Snapshots: 2" in completed.stdout
    assert (out_dir / "feature_snapshot.json").is_file()


def test_fake_feature_snapshot_can_feed_existing_product_smoke_and_produce_six_results(tmp_path: Path):
    probe_out = tmp_path / "probe"
    product_out = tmp_path / "product"

    probe_geometry_feature_snapshots(
        provider=load_mapping_provider_from_json(FIXTURE),
        output_dir=probe_out,
        target_story="+14.5",
        max_rows=2,
    )
    product = run_geometry_product_smoke(
        feature_snapshot_path=probe_out / "feature_snapshot.json",
        output_dir=product_out,
    )

    assert product.status == "OK"
    assert product.p4_check_result_count == 6
    check_results = _read_json(product_out / "artifacts" / "check_results.json")
    assert len(check_results) == 6
    assert {item["status"] for item in check_results} == {"OK"}


def test_p9_offline_acceptance_includes_c13_5_p2_before_golden_regression(tmp_path: Path):
    plan = build_offline_acceptance_command_plan(output_dir=tmp_path, python_executable="PY")

    assert len(plan) == 14
    assert plan[-3] == ("pytest_c13_5_p1", ("PY", "-m", "pytest", "-q", "tests/c13_5_p1"))
    assert plan[-2] == ("pytest_c13_5_p2", ("PY", "-m", "pytest", "-q", "tests/c13_5_p2"))
    assert plan[-1][0] == "p8_golden_regression"


def test_p10_workflow_still_delegates_to_p9_cli_only():
    workflow = (ROOT / ".github" / "workflows" / "c13_4_offline_acceptance.yml").read_text(encoding="utf-8")

    assert "python tools/run_offline_product_acceptance.py --out local_out/c13_4_ci_offline_acceptance" in workflow
    assert "tests/c13_5_p2" not in workflow
    assert "tools/probe_live_etabs_geometry_snapshot.py" not in workflow


def test_probe_module_does_not_import_check_engine_or_create_check_results():
    module_text = MODULE_PATH.read_text(encoding="utf-8")
    cli_text = CLI_PATH.read_text(encoding="utf-8")

    assert "MinimalCheckEngine" not in module_text
    assert "tbdy_engine.checks.engine" not in module_text
    assert "CheckResult" not in module_text
    assert "MinimalCheckEngine" not in cli_text
    assert "tbdy_engine.checks.engine" not in cli_text
    assert "CheckResult" not in cli_text
