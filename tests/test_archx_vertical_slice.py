from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from tbdy_engine.archx import (
    Beam,
    CanonicalSnapshot,
    Column,
    DesignBasis,
    Section,
    Story,
    archx_run_result_to_dict,
    build_demo_snapshot,
    run_archx_checks,
    write_archx_run_json,
)


ROOT = Path(__file__).resolve().parents[1]
ARCHX_ROOT = ROOT / "tbdy_engine" / "archx"


def _statuses_by_check(result):
    return {item.check_id: item.status for item in result.check_results}


def test_demo_runner_produces_expected_product_slice():
    result = run_archx_checks(build_demo_snapshot(), run_id="demo-run")

    assert result.run_id == "demo-run"
    assert len(result.evaluation_packages) == 3
    assert len(result.check_results) == 3
    assert len(result.workbench_cells) == 3
    assert result.workbench_bundle
    assert result.summary["total_check_results"] == 3
    assert result.summary["by_status"]["OK"] == 1
    assert result.summary["by_status"]["FAIL"] == 2
    assert result.summary["by_status"]["NO_DATA"] == 0
    assert _statuses_by_check(result) == {
        "beam_geometry": "OK",
        "column_geometry": "FAIL",
        "story_drift": "FAIL",
    }


def test_demo_runner_contains_evaluation_packages():
    result = run_archx_checks(build_demo_snapshot(), run_id="demo-run")
    packages = {package.evaluation_id: package for package in result.evaluation_packages}

    assert set(packages) == {"beam_geometry", "column_geometry", "story_drift"}
    for package in packages.values():
        assert package.evaluation_id
        assert package.status
        assert package.outputs
        assert package.summary


def test_check_id_filter_runs_only_beam():
    result = run_archx_checks(build_demo_snapshot(), check_ids=["beam_geometry"], run_id="beam-only")

    assert len(result.evaluation_packages) == 1
    assert len(result.check_results) == 1
    assert result.check_results[0].check_id == "beam_geometry"
    assert "column_geometry" not in result.summary["by_check_id"]
    assert "story_drift" not in result.summary["by_check_id"]


def test_unsupported_check_id_adds_diagnostic():
    result = run_archx_checks(build_demo_snapshot(), check_ids=["beam_geometry", "unknown_check"], run_id="diag")

    assert [item.check_id for item in result.check_results] == ["beam_geometry"]
    assert "Unsupported ARCH-X check_id: unknown_check" in result.diagnostics


def test_deterministic_ordering():
    snapshot = CanonicalSnapshot(
        sections={
            "BSEC": Section(section_id="BSEC", width_mm=300, depth_mm=500),
            "CSEC": Section(section_id="CSEC", width_mm=400, depth_mm=400),
        },
        beams={
            "B200": Beam(element_id="B200", label="B200", story_id="5", section_id="BSEC"),
            "B100": Beam(element_id="B100", label="B100", story_id="5", section_id="BSEC"),
        },
        columns={
            "C200": Column(element_id="C200", label="C200", story_id="5", section_id="CSEC"),
            "C100": Column(element_id="C100", label="C100", story_id="5", section_id="CSEC"),
        },
        stories={
            "S2": Story(story_id="S2", height_mm=3000, drift_max_mm=30),
            "S1": Story(story_id="S1", height_mm=3000, drift_max_mm=30),
        },
        design_basis=DesignBasis(drift_limit=0.02),
    )

    first = run_archx_checks(snapshot, run_id="order")
    second = run_archx_checks(snapshot, run_id="order")
    expected = [
        ("beam_geometry", "B100"),
        ("beam_geometry", "B200"),
        ("column_geometry", "C100"),
        ("column_geometry", "C200"),
        ("story_drift", "S1"),
        ("story_drift", "S2"),
    ]

    assert [(item.check_id, item.element_label) for item in first.check_results] == expected
    assert [(item.check_id, item.element_label) for item in second.check_results] == expected


def test_no_data_does_not_crash():
    snapshot = CanonicalSnapshot(
        sections={},
        beams={"B101": Beam(element_id="B101", label="B101", story_id="5", section_id="MISSING")},
        columns={},
        stories={"S1": Story(story_id="S1", height_mm=3000, drift_max_mm=30)},
        design_basis=None,
    )

    result = run_archx_checks(snapshot, run_id="no-data")

    assert any(check.status == "NO_DATA" for check in result.check_results)
    assert any("Missing required input" in diagnostic or "NO_DATA" in diagnostic for diagnostic in result.diagnostics)


def test_json_serializer_outputs_required_top_level_keys():
    result = run_archx_checks(build_demo_snapshot(), run_id="demo-run")

    payload = archx_run_result_to_dict(result)

    assert set(payload) == {
        "artifact_type",
        "artifact_version",
        "run_id",
        "summary",
        "diagnostics",
        "evaluation_packages",
        "check_results",
        "workbench_bundle",
    }
    json.dumps(payload)


def test_write_archx_run_json_creates_file(tmp_path):
    result = run_archx_checks(build_demo_snapshot(), run_id="demo-run")

    output_path = write_archx_run_json(result, tmp_path / "archx_run.json")

    assert output_path.exists()
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["artifact_type"] == "ARCH-X_RUN_RESULT"
    assert payload["summary"]["total_check_results"] == 3


def test_cli_demo_writes_json(tmp_path):
    output_path = tmp_path / "archx_demo_run.json"

    completed = subprocess.run(
        [sys.executable, "-m", "tbdy_engine.archx.cli", "--demo", "--out", str(output_path)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0
    assert output_path.exists()
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["summary"]["total_check_results"] == 3
    assert payload["summary"]["by_status"]["OK"] == 1
    assert payload["summary"]["by_status"]["FAIL"] == 2
    assert str(output_path) in completed.stdout


def test_workbench_bundle_json_serializable():
    result = run_archx_checks(build_demo_snapshot(), run_id="demo-run")
    payload = archx_run_result_to_dict(result)

    json.dumps(payload["workbench_bundle"])


def test_no_forbidden_imports():
    source = "\n".join(
        (ARCHX_ROOT / filename).read_text(encoding="utf-8")
        for filename in ["runner.py", "serialization.py", "demo.py", "cli.py"]
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
        for filename in ["runner.py", "serialization.py", "demo.py", "cli.py"]
    )

    assert "except Exception:\n        pass" not in source
    assert "except Exception as exc:\n        pass" not in source
    assert "except Exception as e:\n        pass" not in source
