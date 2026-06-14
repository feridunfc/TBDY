#!/usr/bin/env python
"""C12.0 minimal live product slice orchestrator.

Runs the accepted contract-first vertical slice from ETABS/fixture feature
resolution to the minimal C11 CheckResult JSON outputs. This command only
orchestrates existing accepted tools/modules. It does not add engineering checks,
call legacy runtime paths, use Excel production input/output, or start any UI.
"""
from __future__ import annotations

import argparse
import json
import contextlib
import io
import importlib
import os
import re
import shutil
import signal
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
SPRINT = "C12.0_MINIMAL_LIVE_PRODUCT_SLICE"
DEFAULT_PREFERRED_OUTPUT_CASE = "Crack_SeisY_UpSoil"
C8_FIXTURE_INPUT = ROOT / "tests" / "fixtures" / "c8_table_headers_fixture.json"
DEFAULT_FIXTURE_DESIGN_CONTEXT = ROOT / "tests" / "fixtures" / "c10_design_context_fixture.json"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tbdy_engine.coverage.live_readiness import validate_design_context_path


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def _slug(command: list[str]) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", "_".join(command))[:140]


def _run(command: list[str], *, out_dir: Path, log_dir: Path, timeout: int = 300, log_stem: str = "command") -> dict[str, Any]:
    del out_dir  # retained for call-site compatibility and future report context
    log_dir.mkdir(parents=True, exist_ok=True)
    safe_stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", log_stem).strip("_") or "command"
    stdout_path = log_dir / f"{safe_stem}.stdout.log"
    stderr_path = log_dir / f"{safe_stem}.stderr.log"
    timed_out = False
    try:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            start_new_session=True,
        )
        returncode = int(completed.returncode)
        stdout = completed.stdout or ""
        stderr = completed.stderr or ""
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        returncode = -1
        stdout = exc.stdout if isinstance(exc.stdout, str) else (exc.stdout or b"").decode("utf-8", errors="replace")
        stderr = exc.stderr if isinstance(exc.stderr, str) else (exc.stderr or b"").decode("utf-8", errors="replace")
        stderr += f"\nTIMEOUT after {timeout}s"
    stdout_path.write_text(stdout, encoding="utf-8")
    stderr_path.write_text(stderr, encoding="utf-8")
    return {
        "command": command,
        "returncode": returncode,
        "passed": returncode == 0 and not timed_out,
        "timed_out": timed_out,
        "stdout_log": str(stdout_path),
        "stderr_log": str(stderr_path),
        "stdout_tail": stdout[-4000:],
        "stderr_tail": stderr[-4000:],
    }


def _run_callable(
    command: list[str],
    *,
    log_dir: Path,
    log_stem: str,
    func: Any,
) -> dict[str, Any]:
    """Run a known fixture-safe stage in-process while preserving command-style logs."""
    log_dir.mkdir(parents=True, exist_ok=True)
    safe_stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", log_stem).strip("_") or "command"
    stdout_path = log_dir / f"{safe_stem}.stdout.log"
    stderr_path = log_dir / f"{safe_stem}.stderr.log"
    stdout_buffer = io.StringIO()
    stderr_buffer = io.StringIO()
    returncode = 0
    try:
        with contextlib.redirect_stdout(stdout_buffer), contextlib.redirect_stderr(stderr_buffer):
            result = func()
        if isinstance(result, int):
            returncode = int(result)
        elif isinstance(result, Mapping) and result.get("baseline_guard_passed") is False:
            returncode = 1
    except Exception as exc:  # pragma: no cover - defensive orchestration boundary
        returncode = 1
        stderr_buffer.write(str(exc))
    stdout = stdout_buffer.getvalue()
    stderr = stderr_buffer.getvalue()
    stdout_path.write_text(stdout, encoding="utf-8")
    stderr_path.write_text(stderr, encoding="utf-8")
    return {
        "command": command,
        "returncode": returncode,
        "passed": returncode == 0,
        "timed_out": False,
        "stdout_log": str(stdout_path),
        "stderr_log": str(stderr_path),
        "stdout_tail": stdout[-4000:],
        "stderr_tail": stderr[-4000:],
        "execution_mode": "in_process_fixture_safe",
    }


class StageExecutionError(RuntimeError):
    def __init__(self, message: str, *, stage: str, blocker: str, commands: list[dict[str, Any]]):
        super().__init__(message)
        self.stage = stage
        self.blocker = blocker
        self.commands = commands


def _design_context_preflight(design_context: Path) -> dict[str, Any]:
    detail = validate_design_context_path(design_context)
    status = detail.get("status")
    passed = status == "DESIGN_CONTEXT_OK"
    return {
        "sprint": SPRINT,
        "stage": "preflight",
        "preflight_passed": passed,
        "blocker": None if passed else status,
        "design_context": detail,
        "path": str(design_context),
        "user_action": None if passed else detail.get("user_action"),
    }


def _failed_manifest(
    *,
    out_dir: Path,
    live_etabs: bool,
    fixture_mode: bool,
    target_component: str | None,
    target_label: str | None,
    target_story: str | None,
    target_section: str | None,
    preferred_output_case: str,
    design_context: Path,
    stage: str,
    blocker: str,
    message: str,
    commands: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    manifest = {
        "sprint": SPRINT,
        "stage": stage,
        "blocker": blocker,
        "message": message,
        "live_etabs_requested": live_etabs,
        "fixture_mode": fixture_mode,
        "target_component": target_component,
        "target_label": target_label,
        "target_story": target_story,
        "target_section": target_section,
        "preferred_output_case": preferred_output_case,
        "design_context_path": str(design_context),
        "product_slice_passed": False,
        "check_result_count": 0,
        "ok_count": 0,
        "fail_count": 0,
        "excel_production_path_used": False,
        "streamlit_ui_used": False,
        "legacy_runtime_used": False,
        "rebar_flexure_shear_capacity_unlocked": False,
    }
    _write_json(out_dir / "product_slice_manifest.json", manifest)
    _write_json(out_dir / "command_log.json", {
        "sprint": SPRINT,
        "live_etabs_requested": live_etabs,
        "fixture_mode": fixture_mode,
        "commands": commands or [],
        "all_commands_passed": False,
        "failure_stage": stage,
        "blocker": blocker,
    })
    _write_json(out_dir / "acceptance_summary.json", {
        "product_slice_passed": False,
        "failure_stage": stage,
        "blocker": blocker,
        "c11_dry_run_still_3_OK": False,
        "no_new_engineering_unlocked": True,
    })
    return manifest

def _copy_required(src: Path, dst: Path) -> None:
    if not src.is_file():
        raise FileNotFoundError(f"Required product slice artifact missing: {src}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def _status_counts_from_results(results_path: Path) -> dict[str, int]:
    results = _read_json(results_path)
    counts = {"OK": 0, "FAIL": 0, "WARNING": 0, "NO_DATA": 0}
    if isinstance(results, list):
        for row in results:
            status = str((row or {}).get("status") or "")
            if status in counts:
                counts[status] += 1
    return counts


def _rebar_flexure_shear_capacity_unlocked(c11_boundary: Mapping[str, Any], check_results: list[Mapping[str, Any]]) -> bool:
    if c11_boundary.get("rebar_selection_executed") or c11_boundary.get("beam_flexure_executed") or c11_boundary.get("beam_shear_executed"):
        return True
    locked_terms = ("rebar", "flexure", "shear", "capacity")
    return any(any(term in str(row.get("check_id", "")).casefold() for term in locked_terms) for row in check_results)


def _load_baseline_guard(out_dir: Path) -> dict[str, Any]:
    return _read_json(out_dir / "baseline_guard_report.json")


def _run_stage_commands(
    *,
    out_dir: Path,
    live_etabs: bool,
    fixture_mode: bool,
    target_component: str | None,
    target_label: str | None,
    target_story: str | None,
    target_section: str | None,
    preferred_output_case: str,
    design_context: Path,
) -> tuple[list[dict[str, Any]], dict[str, Path]]:
    stage_root = out_dir / "_pipeline"
    log_dir = out_dir / "command_logs"
    if stage_root.exists():
        shutil.rmtree(stage_root)
    stage_root.mkdir(parents=True, exist_ok=True)
    commands: list[dict[str, Any]] = []

    baseline_out = out_dir / "baseline_guard"
    baseline_command = [sys.executable, "tools/validate_clean_core_baseline.py", "--out", str(baseline_out)]
    def _baseline_guard_callable() -> Any:
        module = importlib.import_module("tools.validate_clean_core_baseline")
        return module.build_baseline_guard_report(baseline_out)

    commands.append(_run_callable(baseline_command, log_dir=log_dir, log_stem="01_baseline_guard", func=_baseline_guard_callable))
    if not commands[-1]["passed"]:
        raise StageExecutionError("Baseline guard failed; C12 product slice is blocked before any pipeline stage.", stage="preflight", blocker="BASELINE_GUARD_FAILED", commands=commands)

    c8_out = stage_root / "c8_live_feature_resolver"
    c9_out = stage_root / "c9_live_coverage_matrix"
    c10_out = stage_root / "c10_minimal_live_readiness"
    c11_out = stage_root / "c11_minimal_check_dry_run"

    c8_cmd = [sys.executable, "tools/smoke_live_feature_resolver.py", "--out", str(c8_out), "--preferred-output-case", preferred_output_case]
    if live_etabs:
        c8_cmd.append("--live-etabs")
        for flag, value in (
            ("--target-component", target_component),
            ("--target-label", target_label),
            ("--target-story", target_story),
            ("--target-section", target_section),
        ):
            if value is not None:
                c8_cmd.extend([flag, str(value)])
    elif fixture_mode:
        c8_cmd.extend(["--input", str(C8_FIXTURE_INPUT)])
        # Keep the accepted live target identity in fixture mode while avoiding
        # any live ETABS call.
        c8_cmd.extend([
            "--target-component", str(target_component or "297"),
            "--target-label", str(target_label or "B1"),
            "--target-story", str(target_story or "+14.5"),
            "--target-section", str(target_section or "B40x70"),
        ])
    else:  # defensive; argparse should prevent this.
        raise ValueError("Either --live-etabs or --fixture-mode is required")
    if fixture_mode:
        def _c8_callable() -> int:
            return importlib.import_module("tools.smoke_live_feature_resolver").main(c8_cmd[2:])
        commands.append(_run_callable(c8_cmd, log_dir=log_dir, log_stem="02_c8_feature_resolver", func=_c8_callable))
    else:
        commands.append(_run(c8_cmd, out_dir=out_dir, log_dir=log_dir, timeout=300, log_stem="02_c8_feature_resolver"))
    if not commands[-1]["passed"]:
        raise StageExecutionError("C8 live/fixture FeatureResolver stage failed", stage="C8", blocker="C8_FEATURE_RESOLVER_FAILED", commands=commands)

    c9_cmd = [
        sys.executable,
        "tools/build_live_coverage_matrix.py",
        "--feature-snapshot",
        str(c8_out / "feature_snapshot.json"),
        "--out",
        str(c9_out),
    ]
    if fixture_mode:
        def _c9_callable() -> int:
            return importlib.import_module("tools.build_live_coverage_matrix").main(c9_cmd[2:])
        commands.append(_run_callable(c9_cmd, log_dir=log_dir, log_stem="03_c9_coverage_matrix", func=_c9_callable))
    else:
        commands.append(_run(c9_cmd, out_dir=out_dir, log_dir=log_dir, timeout=180, log_stem="03_c9_coverage_matrix"))
    if not commands[-1]["passed"]:
        raise StageExecutionError("C9 coverage matrix stage failed", stage="C9", blocker="C9_COVERAGE_MATRIX_FAILED", commands=commands)

    c10_cmd = [
        sys.executable,
        "tools/build_minimal_live_readiness_slice.py",
        "--feature-snapshot",
        str(c8_out / "feature_snapshot.json"),
        "--coverage-input",
        str(c9_out / "coverage_matrix.json"),
        "--design-context",
        str(design_context),
        "--out",
        str(c10_out),
    ]
    if fixture_mode:
        def _c10_callable() -> int:
            return importlib.import_module("tools.build_minimal_live_readiness_slice").main(c10_cmd[2:])
        commands.append(_run_callable(c10_cmd, log_dir=log_dir, log_stem="04_c10_minimal_readiness", func=_c10_callable))
    else:
        commands.append(_run(c10_cmd, out_dir=out_dir, log_dir=log_dir, timeout=180, log_stem="04_c10_minimal_readiness"))
    if not commands[-1]["passed"]:
        raise StageExecutionError("C10 minimal readiness stage failed", stage="C10", blocker="C10_MINIMAL_READINESS_FAILED", commands=commands)

    c11_cmd = [
        sys.executable,
        "tools/run_c11_minimal_check_dry_run.py",
        "--feature-snapshot",
        str(c10_out / "feature_snapshot_with_context.json"),
        "--coverage-matrix",
        str(c10_out / "coverage_matrix.json"),
        "--out",
        str(c11_out),
    ]
    if fixture_mode:
        def _c11_callable() -> int:
            return importlib.import_module("tools.run_c11_minimal_check_dry_run").main(c11_cmd[2:])
        commands.append(_run_callable(c11_cmd, log_dir=log_dir, log_stem="05_c11_minimal_check_dry_run", func=_c11_callable))
    else:
        commands.append(_run(c11_cmd, out_dir=out_dir, log_dir=log_dir, timeout=180, log_stem="05_c11_minimal_check_dry_run"))
    if not commands[-1]["passed"]:
        raise StageExecutionError("C11 minimal check dry-run stage failed", stage="C11", blocker="C11_MINIMAL_CHECK_DRY_RUN_FAILED", commands=commands)

    return commands, {
        "baseline": baseline_out,
        "c8": c8_out,
        "c9": c9_out,
        "c10": c10_out,
        "c11": c11_out,
    }


def build_product_slice(
    *,
    out_dir: Path,
    live_etabs: bool,
    fixture_mode: bool,
    target_component: str | None,
    target_label: str | None,
    target_story: str | None,
    target_section: str | None,
    preferred_output_case: str,
    design_context: Path,
) -> dict[str, Any]:
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    preflight = _design_context_preflight(design_context)
    _write_json(out_dir / "preflight_report.json", preflight)
    if not preflight.get("preflight_passed"):
        return _failed_manifest(
            out_dir=out_dir,
            live_etabs=live_etabs,
            fixture_mode=fixture_mode,
            target_component=target_component,
            target_label=target_label,
            target_story=target_story,
            target_section=target_section,
            preferred_output_case=preferred_output_case,
            design_context=design_context,
            stage="preflight",
            blocker=str(preflight.get("blocker")),
            message=str((preflight.get("design_context") or {}).get("message") or "Design context preflight failed"),
        )
    try:
        commands, paths = _run_stage_commands(
            out_dir=out_dir,
            live_etabs=live_etabs,
            fixture_mode=fixture_mode,
            target_component=target_component,
            target_label=target_label,
            target_story=target_story,
            target_section=target_section,
            preferred_output_case=preferred_output_case,
            design_context=design_context,
        )
    except StageExecutionError as exc:
        return _failed_manifest(
            out_dir=out_dir,
            live_etabs=live_etabs,
            fixture_mode=fixture_mode,
            target_component=target_component,
            target_label=target_label,
            target_story=target_story,
            target_section=target_section,
            preferred_output_case=preferred_output_case,
            design_context=design_context,
            stage=exc.stage,
            blocker=exc.blocker,
            message=str(exc),
            commands=exc.commands,
        )

    _copy_required(paths["baseline"] / "baseline_guard_report.json", out_dir / "baseline_guard_report.json")
    _copy_required(paths["c8"] / "feature_snapshot.json", out_dir / "feature_snapshot.json")
    _copy_required(paths["c9"] / "coverage_matrix.json", out_dir / "coverage_matrix.json")
    _copy_required(paths["c10"] / "feature_snapshot_with_context.json", out_dir / "feature_snapshot_with_context.json")
    _copy_required(paths["c11"] / "check_results.json", out_dir / "check_results.json")
    _copy_required(paths["c11"] / "c11_boundary_report.json", out_dir / "c11_boundary_report.json")
    _copy_required(paths["c11"] / "check_results_summary.json", out_dir / "check_results_summary.json")
    _copy_required(paths["c9"] / "coverage_summary.json", out_dir / "c9_coverage_summary.json")
    _copy_required(paths["c10"] / "coverage_summary.json", out_dir / "c10_coverage_summary.json")

    baseline = _read_json(out_dir / "baseline_guard_report.json")
    feature_snapshot = _read_json(out_dir / "feature_snapshot.json")
    c10_summary = _read_json(out_dir / "c10_coverage_summary.json")
    check_results = _read_json(out_dir / "check_results.json")
    c11_boundary = _read_json(out_dir / "c11_boundary_report.json")
    c11_summary = _read_json(out_dir / "check_results_summary.json")
    status_counts = dict(c11_summary.get("status_counts") or _status_counts_from_results(out_dir / "check_results.json"))
    check_result_count = int(c11_summary.get("check_result_count") or len(check_results))
    ok_count = int(status_counts.get("OK", 0))
    fail_count = int(status_counts.get("FAIL", 0))
    warning_count = int(status_counts.get("WARNING", 0))
    no_data_count = int(status_counts.get("NO_DATA", 0))
    feature_counts = dict(feature_snapshot.get("feature_status_counts") or {})
    coverage_counts = dict(c10_summary.get("coverage_status_counts") or {})
    locked_unlocked = _rebar_flexure_shear_capacity_unlocked(c11_boundary, check_results if isinstance(check_results, list) else [])

    command_log = {
        "sprint": SPRINT,
        "live_etabs_requested": live_etabs,
        "fixture_mode": fixture_mode,
        "commands": commands,
        "all_commands_passed": all(item.get("passed") for item in commands),
    }
    _write_json(out_dir / "command_log.json", command_log)

    product_slice_passed = bool(
        baseline.get("baseline_guard_passed") is True
        and all(item.get("passed") for item in commands)
        and feature_counts.get("RESOLVED") == 28
        and check_result_count == 3
        and ok_count == 3
        and fail_count == 0
        and locked_unlocked is False
        and baseline.get("legacy_import_audit_clean") is True
        and baseline.get("feature_snapshot_schema_valid") is True
        and baseline.get("etabs_feature_source_contract_valid") is True
    )
    manifest = {
        "sprint": SPRINT,
        "live_etabs_requested": live_etabs,
        "fixture_mode": fixture_mode,
        "target_component": target_component,
        "target_label": target_label,
        "target_story": target_story,
        "target_section": target_section,
        "preferred_output_case": preferred_output_case,
        "design_context_path": str(design_context),
        "baseline_guard_passed": bool(baseline.get("baseline_guard_passed")),
        "feature_snapshot_path": str(out_dir / "feature_snapshot.json"),
        "coverage_matrix_path": str(out_dir / "coverage_matrix.json"),
        "check_results_path": str(out_dir / "check_results.json"),
        "check_result_count": check_result_count,
        "ok_count": ok_count,
        "fail_count": fail_count,
        "no_data_count": no_data_count,
        "warning_count": warning_count,
        "live_feature_status_counts": feature_counts,
        "coverage_status_counts": coverage_counts,
        "c11_boundary": c11_boundary,
        "rebar_flexure_shear_capacity_unlocked": locked_unlocked,
        "excel_production_path_used": False,
        "streamlit_ui_used": False,
        "legacy_runtime_used": False,
        "product_slice_passed": product_slice_passed,
    }
    _write_json(out_dir / "product_slice_manifest.json", manifest)

    acceptance = {
        "baseline_guard_passed": bool(baseline.get("baseline_guard_passed")),
        "feature_snapshot_all_resolved": feature_counts.get("RESOLVED") == 28 and not any(feature_counts.get(name, 0) for name in ("PARTIAL", "MISSING")),
        "current_resolved_features_covered": f"{baseline.get('current_resolved_features_covered_count')}/{baseline.get('current_resolved_features_count')}",
        "c11_dry_run_still_3_OK": check_result_count == 3 and ok_count == 3 and fail_count == 0,
        "check_result_count": check_result_count,
        "ok_count": ok_count,
        "fail_count": fail_count,
        "legacy_import_audit_clean": bool(baseline.get("legacy_import_audit_clean")),
        "feature_snapshot_schema_valid": bool(baseline.get("feature_snapshot_schema_valid")),
        "etabs_feature_source_contract_valid": bool(baseline.get("etabs_feature_source_contract_valid")),
        "no_new_engineering_unlocked": locked_unlocked is False,
        "product_slice_passed": product_slice_passed,
    }
    _write_json(out_dir / "acceptance_summary.json", acceptance)
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run C12.0 minimal live/fixture product slice from FeatureResolver to CheckResult JSON.")
    parser.add_argument("--out", required=True, help="Output directory")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--live-etabs", action="store_true", help="Attach to an already open local ETABS model")
    mode.add_argument("--fixture-mode", action="store_true", help="Use committed fixtures only; never calls live ETABS")
    parser.add_argument("--target-component", default=None)
    parser.add_argument("--target-label", default=None)
    parser.add_argument("--target-story", default=None)
    parser.add_argument("--target-section", default=None)
    parser.add_argument("--preferred-output-case", default=DEFAULT_PREFERRED_OUTPUT_CASE)
    parser.add_argument("--design-context", default=str(DEFAULT_FIXTURE_DESIGN_CONTEXT))
    args = parser.parse_args(argv)
    try:
        manifest = build_product_slice(
            out_dir=Path(args.out),
            live_etabs=bool(args.live_etabs),
            fixture_mode=bool(args.fixture_mode),
            target_component=args.target_component,
            target_label=args.target_label,
            target_story=args.target_story,
            target_section=args.target_section,
            preferred_output_case=args.preferred_output_case,
            design_context=Path(args.design_context),
        )
        print(f"Wrote C12.0 minimal product slice outputs to {args.out}")
        print(json.dumps({"product_slice_passed": manifest.get("product_slice_passed"), "check_result_count": manifest.get("check_result_count"), "ok_count": manifest.get("ok_count"), "fail_count": manifest.get("fail_count")}, indent=2, ensure_ascii=False))
        return 0 if manifest.get("product_slice_passed") else 1
    except Exception as exc:
        print(f"C12.0 minimal product slice failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
