from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from tbdy_engine.checks.geometry_vertical_slice import run_geometry_vertical_slice_from_file

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests" / "fixtures" / "c13_4_p4" / "geometry_feature_snapshots.json"
ARTIFACT_FILES = {
    "check_results.json",
    "adapter_diagnostics.json",
    "run_summary.json",
    "run_manifest.json",
}


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _evidence(feature_name: str, value: float) -> dict[str, object]:
    return {
        "actual_table_name": "ETABS Geometry Source",
        "evidence_status": "FULL",
        "normalized_value": value,
        "raw_value": value,
        "resolver": "c13_4_p4_fixture_resolver",
        "source_column": feature_name,
        "source_row": {"component": "fixture"},
        "source_table": "source_geometry_table",
        "unit": "mm",
    }


def _feature(feature_name: str, value: float, *, unit: str = "mm") -> dict[str, object]:
    return {
        "evidence": [_evidence(feature_name, value)],
        "semantic_role": "GEOMETRY",
        "status": "RESOLVED",
        "unit": unit,
        "value": value,
    }


def test_valid_fixture_writes_all_four_artifacts(tmp_path: Path):
    out_dir = tmp_path / "out"

    result = run_geometry_vertical_slice_from_file(feature_snapshot_path=FIXTURE, output_dir=out_dir)

    assert {path.name for path in out_dir.iterdir()} == ARTIFACT_FILES
    assert len(result.check_results) == 4
    assert result.adapter_diagnostics == ()


def test_valid_fixture_counts_and_geometry_check_ids(tmp_path: Path):
    out_dir = tmp_path / "out"

    run_geometry_vertical_slice_from_file(feature_snapshot_path=FIXTURE, output_dir=out_dir)
    summary = _read_json(out_dir / "run_summary.json")

    assert summary["status"] == "OK"
    assert summary["snapshot_count"] == 2
    assert summary["executable_input_count"] == 4
    assert summary["check_result_count"] == 4
    assert summary["adapter_diagnostic_count"] == 0
    assert summary["check_result_status_counts"] == {"OK": 4}
    assert summary["check_id_counts"] == {
        "beam_depth_width_ratio": 1,
        "beam_geometry_min_depth": 1,
        "beam_geometry_min_width": 1,
        "column_geometry_min_dimension": 1,
    }
    assert summary["component_type_counts"] == {"beam": 3, "column": 1}


def test_input_json_evidence_appears_in_check_results_artifact(tmp_path: Path):
    out_dir = tmp_path / "out"

    run_geometry_vertical_slice_from_file(feature_snapshot_path=FIXTURE, output_dir=out_dir)
    check_results = _read_json(out_dir / "check_results.json")
    evidence_items = [evidence for result in check_results for evidence in result["evidence"]]

    assert evidence_items
    assert {item["source_table"] for item in evidence_items} == {"source_geometry_table"}
    assert {item["actual_table_name"] for item in evidence_items} == {"ETABS Geometry Source"}
    assert {item["resolver"] for item in evidence_items} == {"c13_4_p4_fixture_resolver"}
    assert {item["unit"] for item in evidence_items} == {"mm"}
    assert {item["source_column"] for item in evidence_items} >= {
        "beam_width_mm",
        "beam_depth_mm",
        "column_width_mm",
        "column_depth_mm",
    }
    assert {item["raw_value"] for item in evidence_items} >= {300.0, 600.0, 400.0, 500.0}
    assert {item["normalized_value"] for item in evidence_items} >= {300.0, 600.0, 400.0, 500.0}


def test_single_snapshot_input_shape_is_supported(tmp_path: Path):
    input_path = tmp_path / "single.json"
    input_path.write_text(
        json.dumps(
            {
                "component_id": "B1",
                "component_type": "beam",
                "features": {
                    "beam_width_mm": _feature("beam_width_mm", 300.0),
                    "beam_depth_mm": _feature("beam_depth_mm", 600.0),
                },
                "identity": {},
            }
        ),
        encoding="utf-8",
    )
    out_dir = tmp_path / "out"

    run_geometry_vertical_slice_from_file(feature_snapshot_path=input_path, output_dir=out_dir)

    assert _read_json(out_dir / "run_summary.json")["check_result_count"] == 3


def test_snapshot_list_input_shape_is_supported(tmp_path: Path):
    input_path = tmp_path / "list.json"
    input_path.write_text(
        json.dumps(
            [
                {
                    "component_id": "C1",
                    "component_type": "column",
                    "features": {
                        "column_width_mm": _feature("column_width_mm", 400.0),
                        "column_depth_mm": _feature("column_depth_mm", 500.0),
                    },
                    "identity": {},
                }
            ]
        ),
        encoding="utf-8",
    )
    out_dir = tmp_path / "out"

    run_geometry_vertical_slice_from_file(feature_snapshot_path=input_path, output_dir=out_dir)

    assert _read_json(out_dir / "run_summary.json")["check_result_count"] == 1


def test_output_is_deterministic_across_repeated_runs_to_same_directory(tmp_path: Path):
    out_dir = tmp_path / "out"

    run_geometry_vertical_slice_from_file(feature_snapshot_path=FIXTURE, output_dir=out_dir)
    first = {name: (out_dir / name).read_text(encoding="utf-8") for name in ARTIFACT_FILES}
    run_geometry_vertical_slice_from_file(feature_snapshot_path=FIXTURE, output_dir=out_dir)
    second = {name: (out_dir / name).read_text(encoding="utf-8") for name in ARTIFACT_FILES}

    assert first == second


def test_cli_script_runs_from_repo_root_and_writes_artifacts(tmp_path: Path):
    out_dir = tmp_path / "cli_out"

    completed = subprocess.run(
        [
            sys.executable,
            "tools/run_geometry_vertical_slice.py",
            "--feature-snapshot",
            str(FIXTURE),
            "--out",
            str(out_dir),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert "Geometry vertical slice: OK" in completed.stdout
    assert "Snapshots: 2" in completed.stdout
    assert "CheckResults: 4" in completed.stdout
    assert {path.name for path in out_dir.iterdir()} == ARTIFACT_FILES
