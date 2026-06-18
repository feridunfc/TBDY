from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from tools.audit_legacy_boundary import build_report

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests" / "fixtures" / "c13_4_p4" / "geometry_feature_snapshots.json"
PRODUCT_MODULE = ROOT / "tbdy_engine" / "product" / "geometry_product_smoke.py"
CLI_SCRIPT = ROOT / "tools" / "run_geometry_product_smoke.py"
FORBIDDEN_IMPORTS = (
    "tbdy_engine.design",
    "tbdy_engine.adapters.check_adapter",
    "tbdy_engine.engine.topology",
    "tbdy_engine.runtime",
    "tbdy_engine.runner_v2",
    "tbdy_engine.archx",
)
SUMMARY_FORBIDDEN_TEXT = (
    "final_building_compliance",
    "flexure",
    "shear",
    "rebar",
    "capacity",
    "PMM",
    "drift",
)


def test_missing_input_path_returns_nonzero_cli_result(tmp_path: Path):
    completed = subprocess.run(
        [
            sys.executable,
            "tools/run_geometry_product_smoke.py",
            "--feature-snapshot",
            str(tmp_path / "missing.json"),
            "--out",
            str(tmp_path / "out"),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode != 0
    assert "Geometry product smoke: ERROR" in completed.stderr


def test_invalid_input_json_returns_nonzero_cli_result(tmp_path: Path):
    input_path = tmp_path / "invalid.json"
    input_path.write_text("{invalid", encoding="utf-8")

    completed = subprocess.run(
        [
            sys.executable,
            "tools/run_geometry_product_smoke.py",
            "--feature-snapshot",
            str(input_path),
            "--out",
            str(tmp_path / "out"),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode != 0
    assert "Geometry product smoke: ERROR" in completed.stderr


def test_invalid_catalog_dir_propagates_p4_failure_as_nonzero_cli_result(tmp_path: Path):
    completed = subprocess.run(
        [
            sys.executable,
            "tools/run_geometry_product_smoke.py",
            "--feature-snapshot",
            str(FIXTURE),
            "--out",
            str(tmp_path / "out"),
            "--catalog-dir",
            str(tmp_path / "missing_catalogs"),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode != 0
    assert "Geometry product smoke: ERROR" in completed.stderr


def test_product_module_does_not_import_forbidden_legacy_paths():
    module_text = PRODUCT_MODULE.read_text(encoding="utf-8")

    for forbidden_import in FORBIDDEN_IMPORTS:
        assert forbidden_import not in module_text


def test_cli_script_does_not_import_forbidden_legacy_paths():
    script_text = CLI_SCRIPT.read_text(encoding="utf-8")

    for forbidden_import in FORBIDDEN_IMPORTS:
        assert forbidden_import not in script_text


def test_p6_module_does_not_import_engine_or_p3_adapter_directly():
    module_text = PRODUCT_MODULE.read_text(encoding="utf-8")

    assert "MinimalCheckEngine" not in module_text
    assert "build_geometry_check_inputs_from_feature_snapshot" not in module_text


def test_p6_module_imports_existing_p4_and_p5_apis():
    module_text = PRODUCT_MODULE.read_text(encoding="utf-8")

    assert "run_geometry_vertical_slice_from_file" in module_text
    assert "render_geometry_markdown_report_from_artifact_dir" in module_text


def test_legacy_boundary_audit_scans_product_module_without_product_blockers():
    report = build_report()

    assert "tbdy_engine/product/geometry_product_smoke.py" in report["checked_files"]
    product_blockers = [
        blocker
        for blocker in report["blockers"]
        if blocker["file"] == "tbdy_engine/product/geometry_product_smoke.py"
    ]
    assert product_blockers == []


def test_product_smoke_summary_does_not_emit_forbidden_engineering_verdict_terms(tmp_path: Path):
    out_dir = tmp_path / "product_smoke"

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
    summary_text = (out_dir / "product_smoke_summary.json").read_text(encoding="utf-8")
    for forbidden_text in SUMMARY_FORBIDDEN_TEXT:
        assert forbidden_text not in summary_text


def test_product_smoke_manifest_includes_forbidden_scope_list(tmp_path: Path):
    out_dir = tmp_path / "product_smoke"

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
    manifest = json.loads((out_dir / "product_smoke_manifest.json").read_text(encoding="utf-8"))
    assert "forbidden_scope" in manifest
    assert "beam_flexure" in manifest["forbidden_scope"]
    assert "capacity_design" in manifest["forbidden_scope"]
