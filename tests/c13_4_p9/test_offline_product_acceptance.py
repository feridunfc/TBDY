from __future__ import annotations

from types import SimpleNamespace
import json
import subprocess
import sys
from pathlib import Path

from tbdy_engine.product import offline_acceptance
from tbdy_engine.product.offline_acceptance import build_offline_acceptance_command_plan, run_offline_product_acceptance
from tools import run_offline_product_acceptance as acceptance_cli

ROOT = Path(__file__).resolve().parents[2]
EXPECTED_NAMES = (
    "compileall",
    "contract_constitution",
    "legacy_boundary_audit",
    "pytest_c13_4_p1",
    "pytest_c13_4_p2",
    "pytest_c13_4_p3",
    "pytest_c13_4_p4",
    "pytest_c13_4_p5",
    "pytest_c13_4_p6",
    "pytest_c13_4_p7",
    "pytest_c13_4_p8",
    "pytest_c13_5_p1",
    "pytest_c13_5_p2",
    "p8_golden_regression",
)


def _completed(command: tuple[str, ...], *, returncode: int = 0, stdout: str = "", stderr: str = ""):
    return subprocess.CompletedProcess(args=command, returncode=returncode, stdout=stdout, stderr=stderr)


def test_command_plan_contains_exactly_14_commands_in_required_order(tmp_path: Path):
    plan = build_offline_acceptance_command_plan(output_dir=tmp_path, python_executable="PY")

    assert len(plan) == 14
    assert tuple(name for name, _command in plan) == EXPECTED_NAMES


def test_last_command_is_p8_golden_regression(tmp_path: Path):
    plan = build_offline_acceptance_command_plan(output_dir=tmp_path, python_executable="PY")
    name, command = plan[-1]

    assert name == "p8_golden_regression"
    assert command[:2] == ("PY", "tools/run_geometry_golden_regression.py")
    assert "--golden" in command
    assert "tests/fixtures/c13_4_p8/golden_geometry_product_fingerprint.json" in command
    assert command[-2:] == ("--out", str(tmp_path / "golden_regression"))


def test_c13_5_suites_run_before_p8_golden_regression(tmp_path: Path):
    plan = build_offline_acceptance_command_plan(output_dir=tmp_path, python_executable="PY")

    assert plan[-3] == ("pytest_c13_5_p1", ("PY", "-m", "pytest", "-q", "tests/c13_5_p1"))
    assert plan[-2] == ("pytest_c13_5_p2", ("PY", "-m", "pytest", "-q", "tests/c13_5_p2"))
    assert plan[-1][0] == "p8_golden_regression"


def test_pytest_commands_use_python_m_pytest(tmp_path: Path):
    plan = build_offline_acceptance_command_plan(output_dir=tmp_path, python_executable="PY")

    for name, command in plan:
        if name.startswith("pytest_"):
            assert command[:4] == ("PY", "-m", "pytest", "-q")


def test_compileall_command_uses_active_python_executable(tmp_path: Path):
    plan = build_offline_acceptance_command_plan(output_dir=tmp_path, python_executable=sys.executable)
    name, command = plan[0]

    assert name == "compileall"
    assert command == (sys.executable, "-m", "compileall", "-q", "tbdy_engine", "tools", "tests")


def test_successful_mocked_execution_returns_ok_and_writes_report(tmp_path: Path, monkeypatch):
    calls: list[tuple[str, ...]] = []

    def fake_run(command: tuple[str, ...], *, cwd: Path):
        assert cwd == ROOT
        calls.append(command)
        return _completed(command, returncode=0, stdout="ok\n", stderr="")

    monkeypatch.setattr(offline_acceptance, "_run_command", fake_run)

    result = run_offline_product_acceptance(output_dir=tmp_path, python_executable="PY")
    report = json.loads((tmp_path / "offline_product_acceptance_report.json").read_text(encoding="utf-8"))

    assert result.status == "OK"
    assert result.command_count == 14
    assert result.failed_command_count == 0
    assert len(calls) == 14
    assert result.report_path == tmp_path / "offline_product_acceptance_report.json"
    assert report["status"] == "OK"
    assert report["command_count"] == 14
    assert report["failed_command_count"] == 0
    assert report["commands"][0]["stdout_tail"] == ["ok"]


def test_report_json_is_deterministic_across_repeated_serialization(tmp_path: Path, monkeypatch):
    def fake_run(command: tuple[str, ...], *, cwd: Path):
        return _completed(command, returncode=0, stdout="stable\n", stderr="")

    monkeypatch.setattr(offline_acceptance, "_run_command", fake_run)

    run_offline_product_acceptance(output_dir=tmp_path, python_executable="PY")
    first = (tmp_path / "offline_product_acceptance_report.json").read_text(encoding="utf-8")
    run_offline_product_acceptance(output_dir=tmp_path, python_executable="PY")
    second = (tmp_path / "offline_product_acceptance_report.json").read_text(encoding="utf-8")

    assert first == second
    assert first.endswith("\n")


def test_stdout_and_stderr_tail_keep_only_last_40_non_empty_lines(tmp_path: Path, monkeypatch):
    stdout = "\n".join(f"out-{index}" for index in range(45)) + "\n\n"
    stderr = "\n".join(f"err-{index}" for index in range(45)) + "\n\n"

    def fake_run(command: tuple[str, ...], *, cwd: Path):
        return _completed(command, returncode=0, stdout=stdout, stderr=stderr)

    monkeypatch.setattr(offline_acceptance, "_run_command", fake_run)

    result = run_offline_product_acceptance(output_dir=tmp_path, python_executable="PY", stop_on_failure=True)

    assert len(result.commands[0].stdout_tail) == 40
    assert len(result.commands[0].stderr_tail) == 40
    assert result.commands[0].stdout_tail[0] == "out-5"
    assert result.commands[0].stdout_tail[-1] == "out-44"
    assert result.commands[0].stderr_tail[0] == "err-5"
    assert result.commands[0].stderr_tail[-1] == "err-44"


def test_guardrails_are_present_and_false_where_required(tmp_path: Path, monkeypatch):
    def fake_run(command: tuple[str, ...], *, cwd: Path):
        return _completed(command, returncode=0)

    monkeypatch.setattr(offline_acceptance, "_run_command", fake_run)

    run_offline_product_acceptance(output_dir=tmp_path, python_executable="PY")
    report = json.loads((tmp_path / "offline_product_acceptance_report.json").read_text(encoding="utf-8"))

    assert report["guardrails"] == {
        "etabs_required": False,
        "excel_production_path_used": False,
        "final_building_compliance_verdict_emitted": False,
        "live_provider_used": False,
        "new_engineering_checks_added": False,
        "streamlit_ui_used": False,
    }


def test_cli_prints_success_format_under_mocked_success(tmp_path: Path, monkeypatch, capsys):
    fake_result = SimpleNamespace(
        status="OK",
        output_dir=tmp_path,
        report_path=tmp_path / "offline_product_acceptance_report.json",
        command_count=14,
        failed_command_count=0,
    )
    monkeypatch.setattr(acceptance_cli, "run_offline_product_acceptance", lambda **_kwargs: fake_result)

    exit_code = acceptance_cli.main(["--out", str(tmp_path)])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "Offline product acceptance: OK" in captured.out
    assert f"Output: {tmp_path}" in captured.out
    assert f"Report: {tmp_path / 'offline_product_acceptance_report.json'}" in captured.out
    assert "Commands: 14" in captured.out
    assert "Failed: 0" in captured.out
