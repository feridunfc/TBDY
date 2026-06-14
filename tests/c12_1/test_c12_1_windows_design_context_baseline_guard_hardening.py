from __future__ import annotations

import json
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

from tbdy_engine.coverage.live_readiness import load_design_context, validate_design_context_path
from tools import run_live_minimal_product_slice as c12_tool

ROOT = Path(__file__).resolve().parents[2]
BASELINE_GUARD = ROOT / "tools" / "validate_clean_core_baseline.py"
PRODUCT_SLICE = ROOT / "tools" / "run_live_minimal_product_slice.py"


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


@lru_cache(maxsize=1)
def _run_baseline_guard_long_path() -> Path:
    out = ROOT / "local_out" / "c12_1_baseline_guard_long_path_pytest" / ("nested_" + "x" * 40)
    result = subprocess.run(
        [sys.executable, str(BASELINE_GUARD), "--out", str(out)],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=240,
    )
    assert result.returncode == 0, result.stdout + "\n" + result.stderr
    return out


def test_baseline_guard_uses_short_deterministic_log_names_on_long_out_path():
    out = _run_baseline_guard_long_path()
    log_names = {p.name for p in (out / "command_logs").glob("*.log")}
    expected = {
        "01_compileall.stdout.log",
        "01_compileall.stderr.log",
        "02_contract_validator.stdout.log",
        "02_contract_validator.stderr.log",
        "03_bootstrap_validation_fixtures.stdout.log",
        "03_bootstrap_validation_fixtures.stderr.log",
        "04_legacy_import_audit.stdout.log",
        "04_legacy_import_audit.stderr.log",
    }
    assert expected.issubset(log_names)
    assert not any("C_Users" in name or "PycharmProjects" in name for name in log_names)
    assert max(len(name) for name in log_names) < 80


def test_baseline_guard_report_preserves_full_command_arrays_and_log_paths():
    report = _read_json(_run_baseline_guard_long_path() / "baseline_guard_report.json")
    for key in ["compileall", "contract_validator", "bootstrap_validation_fixtures", "legacy_import_audit"]:
        command_report = report["command_results"][key]
        assert isinstance(command_report["command"], list)
        assert command_report["command"]
        assert command_report["stdout_log"].endswith(".stdout.log")
        assert command_report["stderr_log"].endswith(".stderr.log")
    assert report["command_results"]["legacy_import_audit"]["command"][-2:] == ["--out", str(_run_baseline_guard_long_path())]


def test_design_context_bom_free_json_passes(tmp_path: Path):
    path = tmp_path / "design_context.json"
    path.write_text('{"ductility_class":"HIGH","source":"pytest"}', encoding="utf-8")
    report = validate_design_context_path(path)
    assert report["status"] == "DESIGN_CONTEXT_OK"
    assert report["has_utf8_bom"] is False
    values, provenance = load_design_context(path)
    assert values["ductility_class"] == "HIGH"
    assert provenance["has_utf8_bom"] is False


def test_design_context_utf8_bom_json_passes(tmp_path: Path):
    path = tmp_path / "design_context_bom.json"
    path.write_bytes(b"\xef\xbb\xbf" + b'{"ductility_class":"HIGH","source":"powershell"}')
    report = validate_design_context_path(path)
    assert report["status"] == "DESIGN_CONTEXT_OK"
    assert report["has_utf8_bom"] is True
    values, provenance = load_design_context(path)
    assert values["ductility_class"] == "HIGH"
    assert provenance["has_utf8_bom"] is True


def test_design_context_malformed_json_reports_clear_diagnostic(tmp_path: Path):
    path = tmp_path / "bad.json"
    path.write_text('{"ductility_class":', encoding="utf-8")
    report = validate_design_context_path(path)
    assert report["status"] == "DESIGN_CONTEXT_INVALID_JSON"
    assert report["parse_error"]
    assert "ductility_class" in report["user_action"]


def test_design_context_missing_file_reports_clear_diagnostic(tmp_path: Path):
    path = tmp_path / "missing.json"
    report = validate_design_context_path(path)
    assert report["status"] == "DESIGN_CONTEXT_MISSING"
    assert report["path"] == str(path)
    assert "ductility_class" in report["message"]


def test_design_context_missing_ductility_class_reports_incomplete(tmp_path: Path):
    path = tmp_path / "incomplete.json"
    path.write_text('{"source":"pytest"}', encoding="utf-8")
    report = validate_design_context_path(path)
    assert report["status"] == "DESIGN_CONTEXT_INCOMPLETE"
    assert report["missing_keys"] == ["ductility_class"]


def test_c12_missing_design_context_blocks_in_preflight_before_c10(tmp_path: Path):
    out = tmp_path / "missing_context_slice"
    missing = tmp_path / "no_such_design_context.json"
    result = subprocess.run(
        [sys.executable, str(PRODUCT_SLICE), "--out", str(out), "--fixture-mode", "--design-context", str(missing)],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=120,
    )
    assert result.returncode == 1
    manifest = _read_json(out / "product_slice_manifest.json")
    preflight = _read_json(out / "preflight_report.json")
    assert manifest["stage"] == "preflight"
    assert manifest["blocker"] == "DESIGN_CONTEXT_MISSING"
    assert preflight["design_context"]["status"] == "DESIGN_CONTEXT_MISSING"
    assert not (out / "_pipeline" / "c10_minimal_live_readiness").exists()
    assert "C10 minimal readiness stage failed" not in result.stderr


def test_c12_bom_design_context_passes_c12_preflight(tmp_path: Path):
    bom_context = tmp_path / "design_context_bom.json"
    bom_context.write_bytes(b"\xef\xbb\xbf" + b'{"ductility_class":"HIGH","source":"pytest_bom"}')
    preflight = c12_tool._design_context_preflight(bom_context)  # noqa: SLF001 - C12.1 hardening contract
    assert preflight["preflight_passed"] is True
    assert preflight["blocker"] is None
    assert preflight["design_context"]["status"] == "DESIGN_CONTEXT_OK"
    assert preflight["design_context"]["has_utf8_bom"] is True


def test_c12_command_logs_are_short_deterministic(tmp_path: Path):
    log_dir = tmp_path / "command_logs"
    result = c12_tool._run(  # noqa: SLF001 - C12.1 hardening contract
        [sys.executable, "-c", "print('ok')"],
        out_dir=tmp_path,
        log_dir=log_dir,
        timeout=30,
        log_stem="02_c8_feature_resolver",
    )
    assert result["passed"] is True
    log_names = {p.name for p in log_dir.glob("*.log")}
    assert log_names == {"02_c8_feature_resolver.stdout.log", "02_c8_feature_resolver.stderr.log"}
    assert result["command"] == [sys.executable, "-c", "print('ok')"]
    assert max(len(name) for name in log_names) < 80
