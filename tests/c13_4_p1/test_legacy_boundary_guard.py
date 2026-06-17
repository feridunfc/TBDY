from __future__ import annotations

import ast
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _load_audit_module():
    module_path = ROOT / "tools/audit_legacy_boundary.py"
    spec = importlib.util.spec_from_file_location("audit_legacy_boundary_under_test", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_legacy_boundary_audit_runs_successfully(tmp_path):
    out = tmp_path / "legacy_boundary_audit_report.json"
    result = subprocess.run(
        [sys.executable, "tools/audit_legacy_boundary.py", "--out", str(out)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["status"] == "OK"
    assert report["blockers"] == []
    assert "tbdy_engine/checks/engine.py" in report["checked_files"]


def test_new_pipeline_does_not_import_legacy_paths():
    production_files = [
        ROOT / "tbdy_engine/checks/engine.py",
        ROOT / "tbdy_engine/checks/result.py",
    ]
    forbidden = (
        "tbdy_engine.design",
        "tbdy_engine.adapters.check_adapter",
        "tbdy_engine.engine.topology",
        "tbdy_engine.contracts.runtime_catalog",
        "tbdy_engine.contracts.generated",
        "tbdy_engine.contracts.legacy",
        "tbdy_engine.archx",
        "tbdy_engine.runtime",
        "tbdy_engine.runner_v2",
    )
    for path in production_files:
        text = path.read_text(encoding="utf-8")
        assert not any(token in text for token in forbidden)


def test_legacy_beam_module_can_exist_but_is_reference_only():
    legacy_path = ROOT / "tbdy_engine/design/beams/beam_module.py"
    assert legacy_path.exists()
    audit = subprocess.run(
        [sys.executable, "tools/audit_legacy_boundary.py"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert audit.returncode == 0, audit.stdout + audit.stderr
    report = json.loads(audit.stdout)
    assert all(blocker["file"] != "tbdy_engine/design/beams/beam_module.py" for blocker in report["blockers"])


def test_importfrom_legacy_forms_are_flagged(monkeypatch, tmp_path):
    audit = _load_audit_module()
    prod_dir = tmp_path / "tbdy_engine" / "checks"
    prod_dir.mkdir(parents=True)
    probe = prod_dir / "probe.py"
    root_pkg = "tbdy" + "_engine"
    module = ast.Module(
        body=[
            ast.ImportFrom(module=root_pkg, names=[ast.alias(name="design")], level=0),
            ast.ImportFrom(module=f"{root_pkg}.adapters", names=[ast.alias(name="check_adapter")], level=0),
            ast.ImportFrom(module=f"{root_pkg}.design.beams", names=[ast.alias(name="beam_module")], level=0),
            ast.ImportFrom(module=f"{root_pkg}.engine", names=[ast.alias(name="topology")], level=0),
            ast.ImportFrom(module=f"{root_pkg}.contracts", names=[ast.alias(name="runtime_catalog")], level=0),
        ],
        type_ignores=[],
    )
    ast.fix_missing_locations(module)
    probe.write_text(ast.unparse(module), encoding="utf-8")
    monkeypatch.setattr(audit, "ROOT", tmp_path)
    monkeypatch.setattr(audit, "PRODUCTION_GLOBS", ("tbdy_engine/checks/*.py",))
    report = audit.build_report()
    names = {blocker["name"] for blocker in report["blockers"]}
    assert report["status"] == "BLOCKED"
    assert f"{root_pkg}.design" in names
    assert f"{root_pkg}.adapters.check_adapter" in names
    assert f"{root_pkg}.design.beams.beam_module" in names
    assert f"{root_pkg}.engine.topology" in names
    assert f"{root_pkg}.contracts.runtime_catalog" in names
