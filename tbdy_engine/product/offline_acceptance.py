"""C13.4-P9 offline product acceptance gate.

The gate models a real user/CI invocation by running shell-level commands. It
must not import or call lower product pipeline APIs directly.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import subprocess
import sys

_SCOPE = "C13_4_OFFLINE_PRODUCT_ACCEPTANCE"
_TAIL_LIMIT = 40
_REPORT_NAME = "offline_product_acceptance_report.json"
_GUARDRAILS = {
    "etabs_required": False,
    "excel_production_path_used": False,
    "final_building_compliance_verdict_emitted": False,
    "live_provider_used": False,
    "new_engineering_checks_added": False,
    "streamlit_ui_used": False,
}


@dataclass(frozen=True, slots=True)
class OfflineAcceptanceCommandResult:
    name: str
    command: tuple[str, ...]
    returncode: int
    status: str
    stdout_tail: tuple[str, ...]
    stderr_tail: tuple[str, ...]

    def __post_init__(self) -> None:
        expected_status = "OK" if self.returncode == 0 else "FAIL"
        if self.status != expected_status:
            raise ValueError("OfflineAcceptanceCommandResult.status must match returncode")
        object.__setattr__(self, "command", tuple(str(item) for item in self.command))
        object.__setattr__(self, "stdout_tail", tuple(str(item) for item in self.stdout_tail))
        object.__setattr__(self, "stderr_tail", tuple(str(item) for item in self.stderr_tail))


@dataclass(frozen=True, slots=True)
class OfflineProductAcceptanceResult:
    status: str
    output_dir: Path
    report_path: Path
    command_count: int
    failed_command_count: int
    commands: tuple[OfflineAcceptanceCommandResult, ...]

    def __post_init__(self) -> None:
        expected_status = "OK" if self.failed_command_count == 0 else "FAIL"
        if self.status != expected_status:
            raise ValueError("OfflineProductAcceptanceResult.status must match failed_command_count")
        object.__setattr__(self, "output_dir", Path(self.output_dir))
        object.__setattr__(self, "report_path", Path(self.report_path))
        object.__setattr__(self, "commands", tuple(self.commands))


def run_offline_product_acceptance(
    *,
    output_dir: Path,
    python_executable: str | None = None,
    stop_on_failure: bool = False,
) -> OfflineProductAcceptanceResult:
    root = _repo_root()
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / _REPORT_NAME
    executable = python_executable or sys.executable
    command_plan = build_offline_acceptance_command_plan(
        output_dir=out_dir,
        python_executable=executable,
    )

    command_results: list[OfflineAcceptanceCommandResult] = []
    for name, command in command_plan:
        completed = _run_command(command, cwd=root)
        result = OfflineAcceptanceCommandResult(
            name=name,
            command=command,
            returncode=int(completed.returncode),
            status="OK" if completed.returncode == 0 else "FAIL",
            stdout_tail=_tail_lines(completed.stdout),
            stderr_tail=_tail_lines(completed.stderr),
        )
        command_results.append(result)
        if stop_on_failure and result.status == "FAIL":
            break

    failed_count = sum(1 for result in command_results if result.status == "FAIL")
    status = "OK" if failed_count == 0 else "FAIL"
    payload = _serialize_report(
        status=status,
        output_dir=out_dir,
        command_results=tuple(command_results),
        failed_command_count=failed_count,
    )
    _write_json(report_path, payload)

    return OfflineProductAcceptanceResult(
        status=status,
        output_dir=out_dir,
        report_path=report_path,
        command_count=len(command_results),
        failed_command_count=failed_count,
        commands=tuple(command_results),
    )


def build_offline_acceptance_command_plan(
    *,
    output_dir: Path,
    python_executable: str,
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    py = str(python_executable)
    golden_out = Path(output_dir) / "golden_regression"
    commands: list[tuple[str, tuple[str, ...]]] = [
        ("compileall", (py, "-m", "compileall", "-q", "tbdy_engine", "tools", "tests")),
        ("contract_constitution", (py, "tbdy_engine/tools/validate_contract_constitution.py")),
        ("legacy_boundary_audit", (py, "tools/audit_legacy_boundary.py")),
    ]
    for sprint in range(1, 9):
        commands.append((f"pytest_c13_4_p{sprint}", (py, "-m", "pytest", "-q", f"tests/c13_4_p{sprint}")))
    commands.append(("pytest_c13_5_p1", (py, "-m", "pytest", "-q", "tests/c13_5_p1")))
    commands.append(("pytest_c13_5_p2", (py, "-m", "pytest", "-q", "tests/c13_5_p2")))
    commands.append(
        (
            "p8_golden_regression",
            (
                py,
                "tools/run_geometry_golden_regression.py",
                "--feature-snapshot",
                "tests/fixtures/c13_4_p4/geometry_feature_snapshots.json",
                "--golden",
                "tests/fixtures/c13_4_p8/golden_geometry_product_fingerprint.json",
                "--out",
                str(golden_out),
            ),
        )
    )
    return tuple(commands)


def _run_command(command: tuple[str, ...], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )


def _tail_lines(text: str | None) -> tuple[str, ...]:
    if not text:
        return ()
    non_empty = [line for line in text.splitlines() if line.strip()]
    return tuple(non_empty[-_TAIL_LIMIT:])


def _serialize_report(
    *,
    status: str,
    output_dir: Path,
    command_results: tuple[OfflineAcceptanceCommandResult, ...],
    failed_command_count: int,
) -> dict[str, object]:
    return {
        "command_count": len(command_results),
        "commands": [
            {
                "command": list(result.command),
                "name": result.name,
                "returncode": result.returncode,
                "status": result.status,
                "stderr_tail": list(result.stderr_tail),
                "stdout_tail": list(result.stdout_tail),
            }
            for result in command_results
        ],
        "failed_command_count": failed_command_count,
        "guardrails": dict(_GUARDRAILS),
        "output_dir": str(output_dir),
        "scope": _SCOPE,
        "status": status,
    }


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


__all__ = [
    "OfflineAcceptanceCommandResult",
    "OfflineProductAcceptanceResult",
    "build_offline_acceptance_command_plan",
    "run_offline_product_acceptance",
]
