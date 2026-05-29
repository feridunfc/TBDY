from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pandas as pd

from tbdy_engine.archx import build_snapshot_from_etabs_workbook, run_archx_checks
from tbdy_engine.archx.providers.etabs_workbook import get_last_provider_diagnostics


ROOT = Path(__file__).resolve().parents[1]
ARCHX_ROOT = ROOT / "tbdy_engine" / "archx"
SECTION_TABLE_NAME = "Frame Section Property Definitions - Concrete Rectangular"


def _write_manifest(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "tables": [
                    {"table_name": "Story Definitions", "sheet_name": "Story Definitions"},
                    {"table_name": SECTION_TABLE_NAME, "sheet_name": "Frame Sec Rect"},
                    {"table_name": "Beam Object Connectivity", "sheet_name": "Beam Connectivity"},
                    {"table_name": "Column Object Connectivity", "sheet_name": "Column Connectivity"},
                    {"table_name": "Frame Assignments - Section Properties", "sheet_name": "Frame Assign Sections"},
                    {"table_name": "Story Drifts", "sheet_name": "Story Drifts"},
                ]
            }
        ),
        encoding="utf-8",
    )


def _write_minimal_workbook(path: Path, *, include_drifts: bool = False) -> None:
    with pd.ExcelWriter(path) as writer:
        pd.DataFrame([{"Story": "5", "Height": 3000}]).to_excel(writer, sheet_name="Story Definitions", index=False)
        pd.DataFrame([
            {"Name": "S_BEAM_OK", "t2": 300, "t3": 500},
            {"Name": "S_COLUMN_FAIL", "t2": 250, "t3": 1000},
        ]).to_excel(writer, sheet_name="Frame Sec Rect", index=False)
        pd.DataFrame([
            {"UniqueName": "B101", "Label": "B101", "Story": "5"},
        ]).to_excel(writer, sheet_name="Beam Connectivity", index=False)
        pd.DataFrame([
            {"UniqueName": "C101", "Label": "C101", "Story": "5"},
        ]).to_excel(writer, sheet_name="Column Connectivity", index=False)
        pd.DataFrame([
            {"UniqueName": "B101", "AnalysisSect": "S_BEAM_OK", "Story": "5", "ObjectType": "Beam"},
            {"UniqueName": "C101", "AnalysisSect": "S_COLUMN_FAIL", "Story": "5", "ObjectType": "Column"},
        ]).to_excel(writer, sheet_name="Frame Assign Sections", index=False)
        if include_drifts:
            pd.DataFrame([{"Story": "5", "DriftRatio": 0.025}]).to_excel(writer, sheet_name="Story Drifts", index=False)


def _write_short_candidate_workbook(path: Path) -> None:
    with pd.ExcelWriter(path) as writer:
        pd.DataFrame([{"Story": "5", "Height": 3000}]).to_excel(writer, sheet_name="Story Definitions", index=False)
        pd.DataFrame([{"Name": "S_BEAM_OK", "t2": 300, "t3": 500}]).to_excel(writer, sheet_name="Frame Sec Rect", index=False)
        pd.DataFrame([{"UniqueName": "B101", "Label": "B101", "Story": "5"}]).to_excel(writer, sheet_name="Beam Connectivity", index=False)
        pd.DataFrame([{"UniqueName": "B101", "AnalysisSect": "S_BEAM_OK", "Story": "5", "ObjectType": "Beam"}]).to_excel(writer, sheet_name="Frame Assign Sections", index=False)


def test_provider_builds_snapshot_from_minimal_workbook(tmp_path):
    workbook = tmp_path / "minimal.xlsx"
    manifest = tmp_path / "manifest.json"
    _write_minimal_workbook(workbook)
    _write_manifest(manifest)

    snapshot = build_snapshot_from_etabs_workbook(workbook, manifest_path=manifest)

    assert "B101" in snapshot.beams
    assert "C101" in snapshot.columns
    assert "S_BEAM_OK" in snapshot.sections
    assert "S_COLUMN_FAIL" in snapshot.sections
    assert "5" in snapshot.stories


def test_workbook_snapshot_runs_existing_archx_checks(tmp_path):
    workbook = tmp_path / "minimal.xlsx"
    manifest = tmp_path / "manifest.json"
    _write_minimal_workbook(workbook)
    _write_manifest(manifest)

    result = run_archx_checks(build_snapshot_from_etabs_workbook(workbook, manifest_path=manifest), run_id="workbook-run")
    statuses = {check.check_id: check.status for check in result.check_results}

    assert statuses["beam_geometry"] == "OK"
    assert statuses["column_geometry"] == "FAIL"


def test_story_drift_no_data_without_drift_limit(tmp_path):
    workbook = tmp_path / "minimal.xlsx"
    manifest = tmp_path / "manifest.json"
    _write_minimal_workbook(workbook, include_drifts=True)
    _write_manifest(manifest)

    result = run_archx_checks(
        build_snapshot_from_etabs_workbook(workbook, manifest_path=manifest),
        check_ids=["story_drift"],
        run_id="drift-no-data",
    )

    assert result.check_results[0].check_id == "story_drift"
    assert result.check_results[0].status == "NO_DATA"


def test_story_drift_runs_with_drift_limit(tmp_path):
    workbook = tmp_path / "minimal.xlsx"
    manifest = tmp_path / "manifest.json"
    _write_minimal_workbook(workbook, include_drifts=True)
    _write_manifest(manifest)

    snapshot = build_snapshot_from_etabs_workbook(workbook, manifest_path=manifest, drift_limit=0.02)
    result = run_archx_checks(snapshot, check_ids=["story_drift"], run_id="drift-fail")

    assert result.check_results[0].check_id == "story_drift"
    assert result.check_results[0].status == "FAIL"


def test_cli_etabs_workbook_writes_json(tmp_path):
    workbook = tmp_path / "minimal.xlsx"
    manifest = tmp_path / "manifest.json"
    output = tmp_path / "run.json"
    _write_minimal_workbook(workbook, include_drifts=True)
    _write_manifest(manifest)

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "tbdy_engine.archx.cli",
            "--etabs-workbook",
            str(workbook),
            "--manifest",
            str(manifest),
            "--drift-limit",
            "0.02",
            "--out",
            str(output),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["artifact_type"] == "ARCH-X_RUN_RESULT"
    check_ids = {check["check_id"] for check in payload["check_results"]}
    assert {"beam_geometry", "column_geometry", "story_drift"}.issubset(check_ids)


def test_cli_rejects_demo_and_etabs_workbook_together(tmp_path):
    workbook = tmp_path / "minimal.xlsx"
    output = tmp_path / "run.json"
    _write_minimal_workbook(workbook)

    completed = subprocess.run(
        [sys.executable, "-m", "tbdy_engine.archx.cli", "--demo", "--etabs-workbook", str(workbook), "--out", str(output)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode != 0
    assert "exactly one input source" in completed.stderr


def test_cli_rejects_missing_workbook(tmp_path):
    output = tmp_path / "run.json"
    missing = tmp_path / "missing.xlsx"

    completed = subprocess.run(
        [sys.executable, "-m", "tbdy_engine.archx.cli", "--etabs-workbook", str(missing), "--out", str(output)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode != 0
    assert "ETABS workbook not found" in completed.stderr


def test_missing_tables_do_not_crash(tmp_path):
    workbook = tmp_path / "sections_only.xlsx"
    with pd.ExcelWriter(workbook) as writer:
        pd.DataFrame([{"Name": "S1", "t2": 300, "t3": 500}]).to_excel(writer, sheet_name="Frame Sec Rect", index=False)

    snapshot = build_snapshot_from_etabs_workbook(workbook)
    result = run_archx_checks(snapshot, run_id="missing-tables")

    assert snapshot.sections
    assert result.check_results == []
    assert any("Missing table" in item or "missing" in item.lower() for item in get_last_provider_diagnostics())


def test_manifest_mapping_if_present(tmp_path):
    workbook = tmp_path / "manifest.xlsx"
    manifest = tmp_path / "manifest.json"
    with pd.ExcelWriter(workbook) as writer:
        pd.DataFrame([{"Story": "5", "Height": 3000}]).to_excel(writer, sheet_name="Sheet_ABCD", index=False)
    manifest.write_text(json.dumps({"tables": [{"table_name": "Story Definitions", "sheet_name": "Sheet_ABCD"}]}), encoding="utf-8")

    snapshot = build_snapshot_from_etabs_workbook(workbook, manifest_path=manifest)

    assert "5" in snapshot.stories


def test_manifest_maps_long_concrete_rectangular_table_to_short_sheet(tmp_path):
    workbook = tmp_path / "manifest_sections.xlsx"
    manifest = tmp_path / "manifest_sections.json"
    with pd.ExcelWriter(workbook) as writer:
        pd.DataFrame([{"Name": "S_BEAM_OK", "t2": 300, "t3": 500}]).to_excel(writer, sheet_name="Frame Sec Rect", index=False)
    manifest.write_text(
        json.dumps({"tables": [{"table_name": SECTION_TABLE_NAME, "sheet_name": "Frame Sec Rect"}]}),
        encoding="utf-8",
    )

    snapshot = build_snapshot_from_etabs_workbook(workbook, manifest_path=manifest)

    assert "S_BEAM_OK" in snapshot.sections
    assert snapshot.sections["S_BEAM_OK"].width_mm == 300
    assert snapshot.sections["S_BEAM_OK"].depth_mm == 500


def test_missing_manifest_works_with_short_candidate_sheet_names(tmp_path):
    workbook = tmp_path / "short_candidates.xlsx"
    _write_short_candidate_workbook(workbook)

    snapshot = build_snapshot_from_etabs_workbook(workbook)

    assert "S_BEAM_OK" in snapshot.sections
    assert "B101" in snapshot.beams
    assert "5" in snapshot.stories


def test_no_forbidden_imports():
    source = "\n".join(
        (ARCHX_ROOT / filename).read_text(encoding="utf-8")
        for filename in ["providers/etabs_workbook.py", "cli.py"]
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
        for filename in ["providers/etabs_workbook.py", "cli.py"]
    )

    assert "except Exception:\n        pass" not in source
    assert "except Exception as exc:\n        pass" not in source
    assert "except Exception as e:\n        pass" not in source
