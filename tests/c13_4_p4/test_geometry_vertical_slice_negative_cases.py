from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from tbdy_engine.checks.geometry_vertical_slice import run_geometry_vertical_slice_from_file
from tools.audit_legacy_boundary import build_report

ROOT = Path(__file__).resolve().parents[2]
FORBIDDEN_IMPORTS = (
    "tbdy_engine.design",
    "tbdy_engine.adapters.check_adapter",
    "tbdy_engine.engine.topology",
    "tbdy_engine.runtime",
    "tbdy_engine.runner_v2",
    "tbdy_engine.archx",
)


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _evidence(feature_name: str, value: float, unit: str = "mm") -> dict[str, object]:
    return {
        "actual_table_name": "ETABS Geometry Source",
        "evidence_status": "FULL",
        "normalized_value": value,
        "raw_value": value,
        "resolver": "c13_4_p4_fixture_resolver",
        "source_column": feature_name,
        "source_row": {"component": "fixture"},
        "source_table": "source_geometry_table",
        "unit": unit,
    }


def _feature(feature_name: str, value: float, *, unit: str = "mm") -> dict[str, object]:
    return {
        "evidence": [_evidence(feature_name, value, unit)],
        "semantic_role": "GEOMETRY",
        "status": "RESOLVED",
        "unit": unit,
        "value": value,
    }


def _write_payload(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_missing_beam_depth_writes_adapter_diagnostics_without_depth_or_ratio_results(tmp_path: Path):
    input_path = tmp_path / "missing_depth.json"
    _write_payload(
        input_path,
        {
            "component_id": "B1",
            "component_type": "beam",
            "features": {"beam_width_mm": _feature("beam_width_mm", 300.0)},
            "identity": {"ductility_class": "HIGH"},
        },
    )
    out_dir = tmp_path / "out"

    run_geometry_vertical_slice_from_file(feature_snapshot_path=input_path, output_dir=out_dir)

    check_results = _read_json(out_dir / "check_results.json")
    diagnostics = _read_json(out_dir / "adapter_diagnostics.json")
    summary = _read_json(out_dir / "run_summary.json")
    assert [item["check_id"] for item in check_results] == ["beam_geometry_min_width"]
    assert {item["check_id"] for item in diagnostics} == {"beam_geometry_min_depth", "beam_depth_width_ratio"}
    assert summary["adapter_diagnostic_count"] == 2
    assert summary["status"] == "OK"


def test_wrong_unit_cm_writes_adapter_diagnostics_and_does_not_convert(tmp_path: Path):
    input_path = tmp_path / "wrong_unit.json"
    _write_payload(
        input_path,
        {
            "component_id": "B1",
            "component_type": "beam",
            "features": {
                "beam_width_mm": _feature("beam_width_mm", 30.0, unit="cm"),
                "beam_depth_mm": _feature("beam_depth_mm", 600.0),
            },
            "identity": {"ductility_class": "HIGH"},
        },
    )
    out_dir = tmp_path / "out"

    run_geometry_vertical_slice_from_file(feature_snapshot_path=input_path, output_dir=out_dir)

    check_results = _read_json(out_dir / "check_results.json")
    diagnostics = _read_json(out_dir / "adapter_diagnostics.json")
    assert [item["check_id"] for item in check_results] == ["beam_geometry_min_depth"]
    assert {item["check_id"] for item in diagnostics} == {"beam_geometry_min_width", "beam_depth_width_ratio"}
    assert all("beam_width_mm" in item["invalid_features"] for item in diagnostics)
    assert all("cm" in item["reason"] for item in diagnostics)
    assert all(item["evidence_by_feature"]["beam_width_mm"][0]["raw_value"] == 30.0 for item in diagnostics)


def test_unsupported_component_type_writes_out_of_scope_diagnostic(tmp_path: Path):
    input_path = tmp_path / "wall.json"
    _write_payload(
        input_path,
        {
            "component_id": "W1",
            "component_type": "wall",
            "features": {"wall_thickness_mm": _feature("wall_thickness_mm", 300.0)},
            "identity": {"ductility_class": "HIGH"},
        },
    )
    out_dir = tmp_path / "out"

    run_geometry_vertical_slice_from_file(feature_snapshot_path=input_path, output_dir=out_dir)

    assert _read_json(out_dir / "check_results.json") == []
    diagnostics = _read_json(out_dir / "adapter_diagnostics.json")
    assert len(diagnostics) == 1
    assert diagnostics[0]["status"] == "OUT_OF_SCOPE"


def test_invalid_json_raises_clear_exception(tmp_path: Path):
    input_path = tmp_path / "invalid.json"
    input_path.write_text("{invalid", encoding="utf-8")

    with pytest.raises(json.JSONDecodeError):
        run_geometry_vertical_slice_from_file(feature_snapshot_path=input_path, output_dir=tmp_path / "out")


def test_missing_input_path_returns_nonzero_cli_result(tmp_path: Path):
    completed = subprocess.run(
        [
            sys.executable,
            "tools/run_geometry_vertical_slice.py",
            "--feature-snapshot",
            str(tmp_path / "missing.json"),
            "--out",
            str(tmp_path / "out"),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode != 0
    assert "Geometry vertical slice: ERROR" in completed.stderr


def test_adapter_diagnostics_artifact_contains_no_engine_decision_statuses(tmp_path: Path):
    input_path = tmp_path / "wall.json"
    _write_payload(
        input_path,
        {"component_id": "W1", "component_type": "wall", "features": {}, "identity": {"ductility_class": "HIGH"}},
    )
    out_dir = tmp_path / "out"

    run_geometry_vertical_slice_from_file(feature_snapshot_path=input_path, output_dir=out_dir)

    diagnostics = _read_json(out_dir / "adapter_diagnostics.json")
    engine_decisions = {"O" + "K", "FA" + "IL"}
    assert {item["status"] for item in diagnostics}.isdisjoint(engine_decisions)


def test_legacy_boundary_audit_scans_geometry_vertical_slice_module():
    report = build_report()

    assert "tbdy_engine/checks/geometry_vertical_slice.py" in report["checked_files"]
    runner_blockers = [
        blocker
        for blocker in report["blockers"]
        if blocker["file"] == "tbdy_engine/checks/geometry_vertical_slice.py"
    ]
    assert runner_blockers == []


def test_cli_script_does_not_import_forbidden_legacy_paths():
    script_text = (ROOT / "tools" / "run_geometry_vertical_slice.py").read_text(encoding="utf-8")

    for forbidden_import in FORBIDDEN_IMPORTS:
        assert forbidden_import not in script_text
