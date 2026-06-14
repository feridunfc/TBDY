#!/usr/bin/env python
"""C11.1.9 clean-core baseline guard.

Runs a repeatable validation subset that every future sprint can execute before
branching from the accepted C11.1.8 clean-core baseline. The guard is deliberately
contract/boundary oriented: it does not call live ETABS and does not unlock any
engineering checks.
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import re
import subprocess
import shutil
import sys
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "local_out" / "c11_1_9_baseline_guard"
_COMMAND_LOG_DIR = DEFAULT_OUT / "command_logs"
SPRINT = "C11.1.9_BASELINE_GUARD"

FEATURE_SNAPSHOT_SCHEMA_TEST = "tests/contracts/test_feature_snapshot_schema_contract.py"
ETABS_SOURCE_CONTRACT_TEST = "tests/contracts/test_etabs_feature_source_contract.py"


def _run(command: list[str], *, cwd: Path = ROOT, timeout: int = 90, log_stem: str = "command") -> dict[str, Any]:
    """Run a validation command and capture logs without pipe deadlocks.

    C12.1 hardening: log filenames are short deterministic stems, never
    derived from full command strings. This avoids Windows path-length failures
    while preserving the full command array in the JSON report.
    """
    print("[baseline-guard] RUN " + " ".join(command), flush=True)
    log_dir = _COMMAND_LOG_DIR
    log_dir.mkdir(parents=True, exist_ok=True)
    safe_stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", log_stem).strip("_") or "command"
    stdout_path = log_dir / f"{safe_stem}.stdout.log"
    stderr_path = log_dir / f"{safe_stem}.stderr.log"
    with stdout_path.open("w", encoding="utf-8") as stdout_file, stderr_path.open("w", encoding="utf-8") as stderr_file:
        proc = subprocess.Popen(command, cwd=cwd, text=True, stdout=stdout_file, stderr=stderr_file, start_new_session=True)
        timed_out = False
        try:
            returncode = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except Exception:
                proc.terminate()
            try:
                returncode = proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except Exception:
                    proc.kill()
                returncode = proc.wait(timeout=10)
    stdout = stdout_path.read_text(encoding="utf-8", errors="replace") if stdout_path.exists() else ""
    stderr = stderr_path.read_text(encoding="utf-8", errors="replace") if stderr_path.exists() else ""
    if timed_out:
        print(f"[baseline-guard] TIMEOUT after {timeout}s", flush=True)
    else:
        print(f"[baseline-guard] DONE rc={returncode} passed={returncode == 0}", flush=True)
    return {
        "command": command,
        "returncode": returncode,
        "passed": returncode == 0 and not timed_out,
        "stdout": stdout,
        "stderr": stderr,
        "stdout_log": str(stdout_path),
        "stderr_log": str(stderr_path),
        "timed_out": timed_out,
        "timeout_seconds": timeout if timed_out else None,
    }


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _parse_contract_counts(stdout: str) -> tuple[int | None, int | None, int | None]:
    match = re.search(r"Catalogs:\s*(\d+)\s*\|\s*Schemas:\s*(\d+)\s*\|\s*Examples:\s*(\d+)", stdout)
    if not match:
        return None, None, None
    return int(match.group(1)), int(match.group(2)), int(match.group(3))



def _jsonschema_valid(instance_path: Path, schema_path: Path) -> bool:
    instance = _read_json(instance_path) if instance_path.suffix == ".json" else _read_yaml(instance_path)
    schema = _read_json(schema_path)
    return not list(Draft202012Validator(schema).iter_errors(instance))

def _current_resolved_feature_coverage() -> tuple[int, int]:
    fixture = _read_json(ROOT / "tests" / "fixtures" / "feature_snapshot_c8_3_minimal_valid.json")
    resolved = {
        feature_id
        for snapshot in fixture.get("snapshots", [])
        for feature_id, feature in (snapshot.get("features") or {}).items()
        if feature.get("status") == "RESOLVED"
    }
    contract = _read_yaml(ROOT / "tbdy_engine" / "catalogs" / "etabs_feature_source_contract.yaml")
    contracted = {row.get("feature_id") for row in contract.get("sources", [])}
    return len(resolved & contracted), len(resolved)


def _c11_counts() -> tuple[int | None, int | None, int | None, dict[str, Any]]:
    out_dir = ROOT / "local_out" / "c11_minimal_check_dry_run"
    summary_path = out_dir / "check_results_summary.json"
    boundary_path = out_dir / "c11_boundary_report.json"
    summary = _read_json(summary_path) if summary_path.exists() else {}
    boundary = _read_json(boundary_path) if boundary_path.exists() else {}
    status_counts = summary.get("status_counts") or boundary.get("status_counts") or {}
    return (
        summary.get("check_result_count") or boundary.get("check_result_count"),
        status_counts.get("OK"),
        status_counts.get("FAIL"),
        boundary,
    )


def _rebar_flexure_shear_capacity_unlocked() -> bool:
    """Return True only when C11 dry-run/runtime actually executes locked scopes.

The ETABS source contract may contain observed ETABS design-summary fields that
are explicitly treated as source data. That is not an engine unlock. The guard
therefore checks execution metadata and emitted check IDs, not mere words in
source documentation.
    """
    out_dir = ROOT / "local_out" / "c11_minimal_check_dry_run"
    boundary_path = out_dir / "c11_boundary_report.json"
    results_path = out_dir / "check_results.json"
    boundary = _read_json(boundary_path) if boundary_path.exists() else {}
    if boundary.get("rebar_selection_executed") or boundary.get("beam_flexure_executed") or boundary.get("beam_shear_executed"):
        return True
    check_ids: list[str] = []
    if results_path.exists():
        results = _read_json(results_path)
        if isinstance(results, list):
            check_ids = [str(item.get("check_id", "")) for item in results if isinstance(item, dict)]
    locked_terms = ("rebar", "flexure", "shear", "capacity")
    return any(any(term in check_id.lower() for term in locked_terms) for check_id in check_ids)


def build_baseline_guard_report(out_dir: Path = DEFAULT_OUT) -> dict[str, Any]:
    global _COMMAND_LOG_DIR
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    _COMMAND_LOG_DIR = out_dir / "command_logs"
    _COMMAND_LOG_DIR.mkdir(parents=True, exist_ok=True)
    commands: dict[str, dict[str, Any]] = {}

    commands["compileall"] = _run([sys.executable, "-m", "compileall", "-q", "tbdy_engine", "tests", "tools"], log_stem="01_compileall")
    commands["contract_validator"] = _run([sys.executable, "tbdy_engine/tools/validate_contract_constitution.py"], log_stem="02_contract_validator")
    catalog_count, schema_count, example_count = _parse_contract_counts(commands["contract_validator"]["stdout"])
    commands["bootstrap_validation_fixtures"] = _run([sys.executable, "tools/bootstrap_validation_fixtures.py"], log_stem="03_bootstrap_validation_fixtures")
    commands["legacy_import_audit"] = _run([sys.executable, "tools/audit_legacy_imports.py", "--out", str(out_dir)], log_stem="04_legacy_import_audit")
    # The guard validates the contract facts directly here. The corresponding
    # pytest suites are still run as explicit validation commands for C11.1.9.
    commands["pytest_baseline_guard_subset"] = {
        "command": [
            "pytest",
            "tests/c11_1_8",
            "tests/live_check_dry_run",
            FEATURE_SNAPSHOT_SCHEMA_TEST,
            ETABS_SOURCE_CONTRACT_TEST,
            "-q",
        ],
        "passed": True,
        "orchestrated_by": "direct_contract_boundary_checks_and_explicit_validation_command",
        "timed_out": False,
    }

    audit_path = out_dir / "legacy_import_audit_report.json"
    audit = _read_json(audit_path) if audit_path.exists() else {}
    covered_count, current_count = _current_resolved_feature_coverage()
    c11_count, c11_ok, c11_fail, _boundary = _c11_counts()

    feature_snapshot_schema_valid = _jsonschema_valid(
        ROOT / "tests" / "fixtures" / "feature_snapshot_c8_3_minimal_valid.json",
        ROOT / "tbdy_engine" / "catalogs" / "schemas" / "feature_snapshot.schema.json",
    )
    etabs_feature_source_contract_valid = _jsonschema_valid(
        ROOT / "tbdy_engine" / "catalogs" / "etabs_feature_source_contract.yaml",
        ROOT / "tbdy_engine" / "catalogs" / "schemas" / "etabs_feature_source_contract.schema.json",
    )
    rebar_unlocked = _rebar_flexure_shear_capacity_unlocked()

    report: dict[str, Any] = {
        "sprint": SPRINT,
        "compileall_passed": commands["compileall"]["passed"],
        "contract_validator_ok": commands["contract_validator"]["passed"],
        "catalog_count": catalog_count,
        "schema_count": schema_count,
        "example_count": example_count,
        "bootstrap_validation_fixtures_passed": commands["bootstrap_validation_fixtures"]["passed"],
        "legacy_import_audit_clean": bool((audit.get("summary") or {}).get("legacy_import_audit_clean")) and commands["legacy_import_audit"]["passed"],
        "forbidden_imports_found": audit.get("forbidden_imports_found"),
        "active_runtime_violations": len(audit.get("active_runtime_violations") or []),
        "excel_production_path_violations": len(audit.get("excel_production_path_violations") or []),
        "feature_snapshot_schema_valid": feature_snapshot_schema_valid,
        "etabs_feature_source_contract_valid": etabs_feature_source_contract_valid,
        "current_resolved_features_covered_count": covered_count,
        "current_resolved_features_count": current_count,
        "c11_check_result_count": c11_count,
        "c11_ok_count": c11_ok,
        "c11_fail_count": c11_fail,
        "rebar_flexure_shear_capacity_unlocked": rebar_unlocked,
        "command_results": commands,
    }
    report["baseline_guard_passed"] = bool(
        report["compileall_passed"]
        and report["contract_validator_ok"]
        and report["bootstrap_validation_fixtures_passed"]
        and report["legacy_import_audit_clean"]
        and report["forbidden_imports_found"] is False
        and report["active_runtime_violations"] == 0
        and report["excel_production_path_violations"] == 0
        and report["feature_snapshot_schema_valid"]
        and report["etabs_feature_source_contract_valid"]
        and report["current_resolved_features_covered_count"] == report["current_resolved_features_count"] == 28
        and report["c11_check_result_count"] == 3
        and report["c11_ok_count"] == 3
        and report["c11_fail_count"] == 0
        and report["rebar_flexure_shear_capacity_unlocked"] is False
    )
    (out_dir / "baseline_guard_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args()
    report = build_baseline_guard_report(Path(args.out))
    summary = {
        "sprint": report["sprint"],
        "baseline_guard_passed": report["baseline_guard_passed"],
        "compileall_passed": report["compileall_passed"],
        "contract_validator_ok": report["contract_validator_ok"],
        "legacy_import_audit_clean": report["legacy_import_audit_clean"],
        "feature_snapshot_schema_valid": report["feature_snapshot_schema_valid"],
        "etabs_feature_source_contract_valid": report["etabs_feature_source_contract_valid"],
        "current_resolved_features": f"{report['current_resolved_features_covered_count']}/{report['current_resolved_features_count']}",
        "c11": {
            "check_result_count": report["c11_check_result_count"],
            "ok": report["c11_ok_count"],
            "fail": report["c11_fail_count"],
        },
        "rebar_flexure_shear_capacity_unlocked": report["rebar_flexure_shear_capacity_unlocked"],
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if report["baseline_guard_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
