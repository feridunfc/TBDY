from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


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
