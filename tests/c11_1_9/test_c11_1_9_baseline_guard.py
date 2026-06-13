from __future__ import annotations

import importlib.util
import json
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "validate_clean_core_baseline.py"


def _load_tool():
    spec = importlib.util.spec_from_file_location("validate_clean_core_baseline", TOOL)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@lru_cache(maxsize=1)
def _report() -> dict:
    # Required validation runs tools/validate_clean_core_baseline.py before this
    # suite. Reading the emitted report keeps these tests fast and avoids nesting
    # pytest subprocesses inside pytest.
    report_path = ROOT / "local_out" / "c11_1_9_baseline_guard" / "baseline_guard_report.json"
    assert report_path.is_file(), "run `python tools/validate_clean_core_baseline.py` before tests/c11_1_9"
    return json.loads(report_path.read_text(encoding="utf-8"))


def test_baseline_guard_tool_exists():
    assert TOOL.is_file()


def test_baseline_guard_report_schema():
    report = _report()
    required = {
        "sprint",
        "compileall_passed",
        "contract_validator_ok",
        "catalog_count",
        "schema_count",
        "example_count",
        "bootstrap_validation_fixtures_passed",
        "legacy_import_audit_clean",
        "forbidden_imports_found",
        "active_runtime_violations",
        "excel_production_path_violations",
        "feature_snapshot_schema_valid",
        "etabs_feature_source_contract_valid",
        "current_resolved_features_covered_count",
        "current_resolved_features_count",
        "c11_check_result_count",
        "c11_ok_count",
        "c11_fail_count",
        "rebar_flexure_shear_capacity_unlocked",
        "baseline_guard_passed",
    }
    assert required.issubset(report)
    assert report["sprint"] == "C11.1.9_BASELINE_GUARD"


def test_baseline_guard_contract_validator_ok():
    report = _report()
    assert report["contract_validator_ok"] is True
    assert report["catalog_count"] == 13
    assert report["schema_count"] == 18
    assert report["example_count"] == 11


def test_baseline_guard_legacy_import_audit_clean():
    report = _report()
    assert report["legacy_import_audit_clean"] is True
    assert report["forbidden_imports_found"] is False
    assert report["active_runtime_violations"] == 0
    assert report["excel_production_path_violations"] == 0


def test_baseline_guard_feature_snapshot_schema_valid():
    report = _report()
    assert report["feature_snapshot_schema_valid"] is True


def test_baseline_guard_etabs_source_contract_valid():
    report = _report()
    assert report["etabs_feature_source_contract_valid"] is True
    assert report["current_resolved_features_covered_count"] == report["current_resolved_features_count"] == 28


def test_baseline_guard_c11_dry_run_still_3_ok():
    report = _report()
    assert report["c11_check_result_count"] == 3
    assert report["c11_ok_count"] == 3
    assert report["c11_fail_count"] == 0


def test_baseline_guard_rebar_flexure_shear_capacity_locked():
    report = _report()
    assert report["rebar_flexure_shear_capacity_unlocked"] is False
    assert report["baseline_guard_passed"] is True
