from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pandas as pd

from tbdy_engine.archx import build_snapshot_from_etabs_workbook, run_archx_checks
from tbdy_engine.archx.providers.etabs_workbook import get_last_provider_diagnostics, read_etabs_export_sheet


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


def _write_etabs_sheet(writer, sheet_name: str, table_name: str, headers: list[str], units: list[object], rows: list[list[object]]) -> None:
    width = max(len(headers), 1)
    table_row = [f"TABLE: {table_name}"] + [None] * (width - 1)
    pd.DataFrame([table_row, headers, units, *rows]).to_excel(writer, sheet_name=sheet_name, index=False, header=False)


def _write_etabs_style_workbook(path: Path) -> None:
    with pd.ExcelWriter(path) as writer:
        _write_etabs_sheet(
            writer,
            "Story Definitions",
            "Story Definitions",
            ["Tower", "Name", "Height", "Master Story"],
            [None, None, "m", None],
            [["Tower 1", 14.5, 5.5, "Yes"]],
        )
        _write_etabs_sheet(
            writer,
            "Frame Sec Def - Conc Rect",
            SECTION_TABLE_NAME,
            ["Name", "Material", "Depth", "Width", "Design Type"],
            [None, None, "m", "m", None],
            [["B30x60", "C35/45", 0.6, 0.3, "Beam"], ["C40x40", "C35/45", 0.4, 0.4, "Column"]],
        )
        _write_etabs_sheet(
            writer,
            "Frame Assigns - Sect Prop",
            "Frame Assignments - Section Properties",
            ["Story", "Label", "UniqueName", "Shape", "Section Property"],
            [None, None, None, None, None],
            [[14.5, "B1", 297, "Line", "B30x60"], [14.5, "C1", 36, "Line", "C40x40"]],
        )
        _write_etabs_sheet(
            writer,
            "Beam Object Connectivity",
            "Beam Object Connectivity",
            ["Unique Name", "Story", "BeamBay", "UniquePtI", "UniquePtJ", "Length"],
            [None, None, None, None, None, "m"],
            [[297, 14.5, "B1", 1001, 1002, 5.2]],
        )
        _write_etabs_sheet(
            writer,
            "Column Object Connectivity",
            "Column Object Connectivity",
            ["Unique Name", "Story", "ColumnBay", "UniquePtI", "UniquePtJ", "Length"],
            [None, None, None, None, None, "m"],
            [[36, 14.5, "C1", 2001, 2002, 5.5]],
        )
        _write_etabs_sheet(
            writer,
            "Story Drifts",
            "Story Drifts",
            ["Story", "Output Case", "Case Type", "Step Type", "Step Number", "Direction", "Drift", "Drift/", "Label"],
            [None, None, None, None, None, None, None, None, None],
            [[14.5, "EQX", "LinStatic", "Max", 1, "X", 0.00108, "1/926", "D1"]],
        )


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


def test_missing_mapped_optional_story_drifts_sheet_does_not_crash(tmp_path):
    workbook = tmp_path / "minimal.xlsx"
    manifest = tmp_path / "manifest.json"
    _write_minimal_workbook(workbook, include_drifts=False)
    _write_manifest(manifest)

    snapshot = build_snapshot_from_etabs_workbook(workbook, manifest_path=manifest)
    result = run_archx_checks(snapshot, run_id="missing-story-drifts")
    diagnostics = get_last_provider_diagnostics()

    assert "B101" in snapshot.beams
    assert "C101" in snapshot.columns
    assert "S_BEAM_OK" in snapshot.sections
    assert "S_COLUMN_FAIL" in snapshot.sections
    assert "5" in snapshot.stories
    assert {check.check_id for check in result.check_results}.issuperset({"beam_geometry", "column_geometry"})
    assert any("Mapped sheet not found for story_drifts: Story Drifts" in item for item in diagnostics)


def test_read_etabs_export_sheet_normalizes_table_header(tmp_path):
    workbook = tmp_path / "etabs_header.xlsx"
    with pd.ExcelWriter(workbook) as writer:
        _write_etabs_sheet(
            writer,
            "Frame Sec Def - Conc Rect",
            SECTION_TABLE_NAME,
            ["Name", "Depth", "Width", "Design Type"],
            [None, "m", "m", None],
            [["B30x60", 0.6, 0.3, "Beam"]],
        )

    excel = pd.ExcelFile(workbook)
    df = read_etabs_export_sheet(excel, "Frame Sec Def - Conc Rect")

    assert list(df.columns) == ["Name", "Depth", "Width", "Design Type"]
    assert df.iloc[0]["Name"] == "B30x60"
    assert df.iloc[0]["Depth"] == 0.6
    assert df.iloc[0]["Width"] == 0.3


def test_provider_builds_snapshot_from_etabs_style_workbook(tmp_path):
    workbook = tmp_path / "etabs_style.xlsx"
    _write_etabs_style_workbook(workbook)

    snapshot = build_snapshot_from_etabs_workbook(workbook, drift_limit=0.02)

    assert "B30x60" in snapshot.sections
    assert snapshot.sections["B30x60"].depth_mm == 600
    assert snapshot.sections["B30x60"].width_mm == 300
    assert "297" in snapshot.beams
    assert snapshot.beams["297"].label == "B1"
    assert snapshot.beams["297"].story_id == "14.5"
    assert snapshot.beams["297"].section_id == "B30x60"
    assert "36" in snapshot.columns
    assert snapshot.columns["36"].label == "C1"
    assert snapshot.columns["36"].section_id == "C40x40"
    assert "14.5" in snapshot.stories
    assert snapshot.stories["14.5"].height_mm == 5500


def test_realistic_etabs_workbook_runs_geometry_checks(tmp_path):
    workbook = tmp_path / "etabs_style.xlsx"
    _write_etabs_style_workbook(workbook)

    snapshot = build_snapshot_from_etabs_workbook(workbook, drift_limit=0.02)
    result = run_archx_checks(snapshot, run_id="etabs-style")
    check_ids = {check.check_id for check in result.check_results}

    assert "beam_geometry" in check_ids
    assert "column_geometry" in check_ids
    assert len(result.check_results) > 0


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
