from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from tbdy_engine.archx import (
    archx_run_result_to_dict,
    build_demo_snapshot,
    render_archx_markdown_report,
    run_archx_checks,
    write_archx_markdown_report,
)


ROOT = Path(__file__).resolve().parents[1]
ARCHX_ROOT = ROOT / "tbdy_engine" / "archx"


def _demo_payload() -> dict:
    return archx_run_result_to_dict(run_archx_checks(build_demo_snapshot(), run_id="demo-run"))


def test_render_demo_markdown_contains_core_sections():
    markdown = render_archx_markdown_report(_demo_payload())

    for text in [
        "# ARCH-X Run Report",
        "Run Metadata",
        "Executive Summary",
        "Status by Check",
        "Failing Checks",
        "Formula Trace",
        "Evidence Summary",
        "Diagnostics",
        "Workbench Index",
    ]:
        assert text in markdown


def test_render_demo_markdown_contains_expected_summary():
    markdown = render_archx_markdown_report(_demo_payload())

    assert "Total checks" in markdown
    assert "| Total checks | 3 |" in markdown
    assert "| OK | 1 |" in markdown
    assert "| FAIL | 2 |" in markdown


def test_render_demo_markdown_contains_check_rows():
    markdown = render_archx_markdown_report(_demo_payload())

    for text in ["beam_geometry", "B101", "column_geometry", "C101", "story_drift", "S1"]:
        assert text in markdown


def test_render_demo_markdown_contains_failed_subchecks():
    markdown = render_archx_markdown_report(_demo_payload())

    assert "column_min_edge" in markdown
    assert "column_aspect_ratio" in markdown
    assert "story_drift_ratio" in markdown


def test_render_demo_markdown_contains_formula_traces():
    markdown = render_archx_markdown_report(_demo_payload())

    assert "b_w >= 250 mm" in markdown
    assert "h >= 300 mm" in markdown
    assert "min(b, h) >= 300 mm" in markdown
    assert "A_c >= 75000 mm2" in markdown
    assert "Delta_i / h_i <= 0.02" in markdown


def test_write_markdown_report_creates_file(tmp_path):
    output_path = write_archx_markdown_report(_demo_payload(), tmp_path / "report.md")

    assert output_path.exists()
    assert "# ARCH-X Run Report" in output_path.read_text(encoding="utf-8")


def test_report_cli_reads_json_and_writes_markdown(tmp_path):
    payload = _demo_payload()
    input_path = tmp_path / "run.json"
    output_path = tmp_path / "report.md"
    input_path.write_text(json.dumps(payload), encoding="utf-8")

    completed = subprocess.run(
        [sys.executable, "-m", "tbdy_engine.archx.report_cli", "--input", str(input_path), "--out", str(output_path)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0
    assert output_path.exists()
    assert str(output_path) in completed.stdout
    assert "ARCH-X Run Report" in output_path.read_text(encoding="utf-8")


def test_invalid_artifact_type_raises():
    payload = _demo_payload()
    payload["artifact_type"] = "INVALID"

    with pytest.raises(ValueError):
        render_archx_markdown_report(payload)


def test_missing_required_key_raises():
    payload = _demo_payload()
    del payload["check_results"]

    with pytest.raises(ValueError, match="check_results"):
        render_archx_markdown_report(payload)


def test_no_forbidden_imports():
    source = "\n".join(
        (ARCHX_ROOT / filename).read_text(encoding="utf-8")
        for filename in ["report_markdown.py", "report_cli.py"]
    )
    forbidden = (
        "tbdy_engine.etabs",
        "tbdy_engine.table_engine",
        "tbdy_engine.runner_v2",
        "tbdy_engine.adapters",
        "tbdy_engine.reports",
        "tbdy_engine.contracts",
        "win32com",
    )

    for item in forbidden:
        assert item not in source
    assert "ev" + "al(" not in source
    assert "ex" + "ec(" not in source


def test_no_silent_exception_pass():
    source = "\n".join(
        (ARCHX_ROOT / filename).read_text(encoding="utf-8")
        for filename in ["report_markdown.py", "report_cli.py"]
    )

    assert "except Exception:\n        pass" not in source
    assert "except Exception as exc:\n        pass" not in source
    assert "except Exception as e:\n        pass" not in source
