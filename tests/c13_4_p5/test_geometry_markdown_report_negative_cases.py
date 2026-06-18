from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tbdy_engine.reports.geometry_markdown_report import render_geometry_markdown_report_from_artifact_dir
from tools.audit_legacy_boundary import build_report

ROOT = Path(__file__).resolve().parents[2]
ARTIFACT_DIR = ROOT / "tests" / "fixtures" / "c13_4_p5" / "p4_artifacts"
FORBIDDEN_IMPORTS = (
    "tbdy_engine.design",
    "tbdy_engine.adapters.check_adapter",
    "tbdy_engine.engine.topology",
    "tbdy_engine.runtime",
    "tbdy_engine.runner_v2",
    "tbdy_engine.archx",
)


def _copy_artifacts(tmp_path: Path) -> Path:
    copied = tmp_path / "artifacts"
    shutil.copytree(ARTIFACT_DIR, copied)
    return copied


def test_adapter_diagnostics_with_engine_decision_status_raises_value_error(tmp_path: Path):
    artifact_dir = _copy_artifacts(tmp_path)
    diagnostics_path = artifact_dir / "adapter_diagnostics.json"
    diagnostics_path.write_text(
        json.dumps(
            [
                {
                    "check_id": "beam_geometry_min_width",
                    "component_id": "B1",
                    "component_type": "beam",
                    "evidence_by_feature": {},
                    "invalid_features": [],
                    "missing_features": [],
                    "reason": "invalid fixture status",
                    "status": "OK",
                }
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Adapter diagnostics"):
        render_geometry_markdown_report_from_artifact_dir(
            artifact_dir=artifact_dir,
            output_path=tmp_path / "geometry_report.md",
        )


def test_missing_required_artifact_file_raises_clear_exception(tmp_path: Path):
    artifact_dir = _copy_artifacts(tmp_path)
    (artifact_dir / "run_manifest.json").unlink()

    with pytest.raises(FileNotFoundError, match="Required P4 artifact missing"):
        render_geometry_markdown_report_from_artifact_dir(
            artifact_dir=artifact_dir,
            output_path=tmp_path / "geometry_report.md",
        )


def test_invalid_json_raises_clear_exception(tmp_path: Path):
    artifact_dir = _copy_artifacts(tmp_path)
    (artifact_dir / "run_summary.json").write_text("{invalid", encoding="utf-8")

    with pytest.raises(json.JSONDecodeError):
        render_geometry_markdown_report_from_artifact_dir(
            artifact_dir=artifact_dir,
            output_path=tmp_path / "geometry_report.md",
        )


def test_cli_missing_artifact_returns_nonzero(tmp_path: Path):
    artifact_dir = _copy_artifacts(tmp_path)
    (artifact_dir / "check_results.json").unlink()
    output_path = tmp_path / "geometry_report.md"

    completed = subprocess.run(
        [
            sys.executable,
            "tools/render_geometry_report.py",
            "--artifact-dir",
            str(artifact_dir),
            "--out",
            str(output_path),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode != 0
    assert "Geometry Markdown report: ERROR" in completed.stderr
    assert not output_path.exists()


def test_report_module_does_not_import_forbidden_legacy_paths():
    module_text = (ROOT / "tbdy_engine" / "reports" / "geometry_markdown_report.py").read_text(encoding="utf-8")

    for forbidden_import in FORBIDDEN_IMPORTS:
        assert forbidden_import not in module_text


def test_cli_script_does_not_import_forbidden_legacy_paths():
    script_text = (ROOT / "tools" / "render_geometry_report.py").read_text(encoding="utf-8")

    for forbidden_import in FORBIDDEN_IMPORTS:
        assert forbidden_import not in script_text


def test_legacy_boundary_audit_scans_report_module_without_report_blockers():
    report = build_report()

    assert "tbdy_engine/reports/geometry_markdown_report.py" in report["checked_files"]
    report_blockers = [
        blocker
        for blocker in report["blockers"]
        if blocker["file"] == "tbdy_engine/reports/geometry_markdown_report.py"
    ]
    assert report_blockers == []
