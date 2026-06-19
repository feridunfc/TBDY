from __future__ import annotations

from types import SimpleNamespace
import subprocess
from pathlib import Path

from tbdy_engine.product import offline_acceptance
from tbdy_engine.product.offline_acceptance import run_offline_product_acceptance
from tools import run_offline_product_acceptance as acceptance_cli
from tools.audit_legacy_boundary import build_report

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "tbdy_engine" / "product" / "offline_acceptance.py"
CLI_PATH = ROOT / "tools" / "run_offline_product_acceptance.py"
FORBIDDEN_IMPORT_PATHS = (
    "tbdy_engine.design",
    "tbdy_engine.adapters.check_adapter",
    "tbdy_engine.engine.topology",
    "tbdy_engine.runtime",
    "tbdy_engine.runner_v2",
    "tbdy_engine.archx",
)
FORBIDDEN_DIRECT_IMPORT_SNIPPETS = (
    "from tbdy_engine.checks.geometry_vertical_slice import",
    "from tbdy_engine.reports.geometry_markdown_report import",
    "from tbdy_engine.product.geometry_product_smoke import",
    "from tbdy_engine.product.bundle_validator import",
    "from tbdy_engine.product.golden_regression import",
    "MinimalCheckEngine",
    "build_geometry_check_inputs_from_feature_snapshot",
)


def _completed(command: tuple[str, ...], *, returncode: int = 0, stdout: str = "", stderr: str = ""):
    return subprocess.CompletedProcess(args=command, returncode=returncode, stdout=stdout, stderr=stderr)


def test_failed_mocked_command_returns_fail(tmp_path: Path, monkeypatch):
    def fake_run(command: tuple[str, ...], *, cwd: Path):
        if command[1:] == ("tools/audit_legacy_boundary.py",):
            return _completed(command, returncode=1, stdout="", stderr="audit failed\n")
        return _completed(command, returncode=0)

    monkeypatch.setattr(offline_acceptance, "_run_command", fake_run)

    result = run_offline_product_acceptance(output_dir=tmp_path, python_executable="PY")

    assert result.status == "FAIL"
    assert result.command_count == 14
    assert result.failed_command_count == 1
    assert result.commands[2].name == "legacy_boundary_audit"
    assert result.commands[2].status == "FAIL"
    assert result.commands[2].stderr_tail == ("audit failed",)


def test_stop_on_failure_true_stops_after_first_failure(tmp_path: Path, monkeypatch):
    calls: list[tuple[str, ...]] = []

    def fake_run(command: tuple[str, ...], *, cwd: Path):
        calls.append(command)
        return _completed(command, returncode=1, stderr="first fail\n")

    monkeypatch.setattr(offline_acceptance, "_run_command", fake_run)

    result = run_offline_product_acceptance(output_dir=tmp_path, python_executable="PY", stop_on_failure=True)

    assert result.status == "FAIL"
    assert result.command_count == 1
    assert result.failed_command_count == 1
    assert len(calls) == 1


def test_stop_on_failure_false_runs_all_commands(tmp_path: Path, monkeypatch):
    calls: list[tuple[str, ...]] = []

    def fake_run(command: tuple[str, ...], *, cwd: Path):
        calls.append(command)
        return _completed(command, returncode=1, stderr="fail\n")

    monkeypatch.setattr(offline_acceptance, "_run_command", fake_run)

    result = run_offline_product_acceptance(output_dir=tmp_path, python_executable="PY", stop_on_failure=False)

    assert result.status == "FAIL"
    assert result.command_count == 14
    assert result.failed_command_count == 14
    assert len(calls) == 14


def test_cli_returns_nonzero_under_mocked_failure(tmp_path: Path, monkeypatch, capsys):
    fake_result = SimpleNamespace(
        status="FAIL",
        output_dir=tmp_path,
        report_path=tmp_path / "offline_product_acceptance_report.json",
        command_count=3,
        failed_command_count=1,
    )
    monkeypatch.setattr(acceptance_cli, "run_offline_product_acceptance", lambda **_kwargs: fake_result)

    exit_code = acceptance_cli.main(["--out", str(tmp_path), "--stop-on-failure"])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "Offline product acceptance: FAIL" in captured.out
    assert "Commands: 3" in captured.out
    assert "Failed: 1" in captured.out


def test_p9_module_does_not_import_forbidden_legacy_paths():
    module_text = MODULE_PATH.read_text(encoding="utf-8")

    for forbidden_import in FORBIDDEN_IMPORT_PATHS:
        assert forbidden_import not in module_text


def test_p9_cli_does_not_import_forbidden_legacy_paths():
    cli_text = CLI_PATH.read_text(encoding="utf-8")

    for forbidden_import in FORBIDDEN_IMPORT_PATHS:
        assert forbidden_import not in cli_text


def test_p9_module_does_not_import_lower_pipeline_apis_directly():
    module_text = MODULE_PATH.read_text(encoding="utf-8")

    for forbidden_snippet in FORBIDDEN_DIRECT_IMPORT_SNIPPETS:
        assert forbidden_snippet not in module_text


def test_p9_invokes_p8_through_cli_command_only():
    module_text = MODULE_PATH.read_text(encoding="utf-8")

    assert "tools/run_geometry_golden_regression.py" in module_text
    assert "from tbdy_engine.product.golden_regression import" not in module_text


def test_legacy_boundary_audit_scans_offline_acceptance_module():
    report = build_report()

    assert "tbdy_engine/product/offline_acceptance.py" in report["checked_files"]
    blockers = [
        blocker
        for blocker in report["blockers"]
        if blocker["file"] == "tbdy_engine/product/offline_acceptance.py"
    ]
    assert blockers == []
