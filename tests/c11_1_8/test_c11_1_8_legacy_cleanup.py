import ast
import json
import subprocess
import sys
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator


def _read_json(path: str | Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _imports(path: str | Path):
    tree = ast.parse(Path(path).read_text(encoding="utf-8-sig"))
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return names


def test_no_archx_imports_in_active_runtime():
    for path in Path("tbdy_engine").rglob("*.py"):
        imports = _imports(path)
        assert not any(name == "tbdy_engine.archx" or name.startswith("tbdy_engine.archx.") for name in imports), path


def test_no_runner_v2_imports_in_active_runtime():
    assert not Path("tbdy_engine/runner_v2.py").exists()
    for path in Path("tbdy_engine").rglob("*.py"):
        imports = _imports(path)
        assert not any(name == "tbdy_engine.runner_v2" or name.startswith("tbdy_engine.runner_v2.") for name in imports), path


def test_no_old_runtime_imports_in_active_runtime():
    assert not Path("tbdy_engine/runtime").exists()
    for path in Path("tbdy_engine").rglob("*.py"):
        imports = _imports(path)
        assert not any(name == "tbdy_engine.runtime" or name.startswith("tbdy_engine.runtime.") for name in imports), path


def test_no_old_beam_check_result_imports():
    for root in ("tbdy_engine", "tests", "tools"):
        base = Path(root)
        if not base.exists():
            continue
        for path in base.rglob("*.py"):
            imports = _imports(path)
            assert not any("BeamCheckResult" in name for name in imports), path


def test_no_old_report_app_imports_in_engine():
    assert not Path("tbdy_engine/reports").exists()
    for path in Path("tbdy_engine").rglob("*.py"):
        imports = _imports(path)
        assert not any(name == "tbdy_engine.reports" or name.startswith("tbdy_engine.reports.") for name in imports), path


def test_no_streamlit_ui_imports_in_engine_runtime():
    for path in Path("tbdy_engine").rglob("*.py"):
        imports = _imports(path)
        assert not any(name == "streamlit" or name.startswith("streamlit.") for name in imports), path


def test_no_excel_production_input_path():
    for path in Path("tbdy_engine").rglob("*.py"):
        imports = _imports(path)
        assert not any(name == "pandas" or name.startswith("pandas.") or name == "openpyxl" or name.startswith("openpyxl.") for name in imports), path
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        assert ".read_excel(" not in text


def test_check_engine_still_reads_only_snapshot_coverage_catalog():
    imports = "\n".join(_imports("tbdy_engine/checks/engine.py") + _imports("tbdy_engine/checks/dry_run.py"))
    for forbidden in [
        "tbdy_engine.providers",
        "tbdy_engine.features.resolver",
        "tbdy_engine.etabs",
        "tbdy_engine.archx",
        "tbdy_engine.runtime",
        "tbdy_engine.runner_v2",
        "tbdy_engine.reports",
    ]:
        assert forbidden not in imports


def test_feature_resolver_still_does_not_emit_check_result():
    text = Path("tbdy_engine/features/resolver/live_smoke.py").read_text(encoding="utf-8")
    assert "CheckResult(" not in text
    assert "from tbdy_engine.checks.result" not in text


def test_feature_snapshot_schema_still_rejects_check_result_semantics():
    schema = _read_json("tbdy_engine/catalogs/schemas/feature_snapshot.schema.json")
    validator = Draft202012Validator(schema)
    payload = _read_json("tests/fixtures/feature_snapshot_c8_3_minimal_valid.json")
    validator.validate(payload)
    bad = json.loads(json.dumps(payload))
    first_snapshot = bad["snapshots"][0]
    first_key = next(iter(first_snapshot["features"]))
    first_snapshot["features"][first_key]["check_result"] = {"status": "OK"}
    errors = list(validator.iter_errors(bad))
    assert errors


def test_etabs_feature_source_contract_still_covers_current_resolved_features():
    contract = yaml.safe_load(Path("tbdy_engine/catalogs/etabs_feature_source_contract.yaml").read_text(encoding="utf-8"))
    entries = contract["sources"]
    feature_ids = {entry["feature_id"] for entry in entries}
    current = _read_json("tests/fixtures/feature_snapshot_c8_3_minimal_valid.json")
    resolved = {
        feature_id
        for snapshot in current["snapshots"]
        for feature_id, feature in snapshot["features"].items()
        if feature.get("status") == "RESOLVED"
    }
    assert len(feature_ids) == 28
    assert resolved.issubset(feature_ids)


def test_legacy_import_audit_report_clean(tmp_path):
    out = tmp_path / "audit"
    subprocess.run([sys.executable, "tools/audit_legacy_imports.py", "--out", str(out)], check=True)
    report = _read_json(out / "legacy_import_audit_report.json")
    assert report["forbidden_imports_found"] is False
    assert report["active_runtime_violations"] == []
    assert report["excel_production_path_violations"] == []
    assert report["blockers"] == []
    assert report["summary"]["legacy_import_audit_clean"] is True
    assert report["summary"]["archx_runtime_runner_v2_removed_or_quarantined"] is True


def test_c11_dry_run_still_emits_three_ok_results(tmp_path):
    out = tmp_path / "c11"
    subprocess.run([
        sys.executable,
        "tools/run_c11_minimal_check_dry_run.py",
        "--feature-snapshot",
        "local_out/c10_minimal_live_readiness/feature_snapshot_with_context.json",
        "--coverage-matrix",
        "local_out/c10_minimal_live_readiness/coverage_matrix.json",
        "--out",
        str(out),
    ], check=True)
    summary = _read_json(out / "check_results_summary.json")
    boundary = _read_json(out / "c11_boundary_report.json")
    results = _read_json(out / "check_results.json")
    assert summary["check_result_count"] == 3
    assert len(results) == 3
    assert summary["status_counts"]["OK"] == 3
    assert summary["status_counts"].get("FAIL", 0) == 0
    assert boundary["check_result_count"] == 3
    assert boundary["rebar_selection_executed"] is False
    assert boundary["beam_flexure_executed"] is False
    assert boundary["beam_shear_executed"] is False
