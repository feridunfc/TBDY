from __future__ import annotations

import json
from pathlib import Path

from tbdy_engine.features import live_etabs_table_discovery as discovery
from tbdy_engine.features.etabs_com_attach import EtabsAttachAttempt, EtabsAttachFailure, EtabsAttachResult
from tbdy_engine.features.live_etabs_table_discovery import (
    EtabsTableDescriptor,
    MappingEtabsTableDiscoverySource,
    GEOMETRY_TABLE_KEYWORDS,
    load_mapping_table_discovery_source_from_json,
    run_live_geometry_table_discovery,
)
from tools import probe_live_etabs_geometry_tables as discovery_cli

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests" / "fixtures" / "c13_5_p4" / "fake_etabs_table_inventory.json"
REQUIRED_OUTPUTS = {
    "live_geometry_table_discovery_summary.json",
    "live_geometry_table_inventory.json",
    "live_geometry_table_candidates.json",
    "live_geometry_table_rejections.json",
    "live_geometry_table_discovery_diagnostics.json",
    "live_geometry_table_discovery_manifest.json",
}
ATTACH_FAILURE_OUTPUTS = {
    "live_geometry_table_discovery_summary.json",
    "live_geometry_table_discovery_diagnostics.json",
    "live_geometry_table_discovery_manifest.json",
}


def _load_fixture_source():
    return load_mapping_table_discovery_source_from_json(FIXTURE)


def _section_only_source() -> MappingEtabsTableDiscoverySource:
    descriptors = (
        EtabsTableDescriptor(
            table_key="Frame Assignments - Summary",
            display_name="Frame Assignments - Summary",
            import_type="READ_ONLY",
            is_empty=False,
            source="fake",
        ),
        EtabsTableDescriptor(
            table_key="Frame Section Assignments",
            display_name="Frame Section Assignments",
            import_type="READ_ONLY",
            is_empty=False,
            source="fake",
        ),
    )
    return MappingEtabsTableDiscoverySource(
        descriptors=descriptors,
        columns_by_table_key={
            "Frame Assignments - Summary": ("Story", "Label", "UniqueName", "Section"),
            "Frame Section Assignments": ("Frame", "Section"),
        },
    )


def _failed_attach_result() -> EtabsAttachResult:
    return EtabsAttachResult(
        status="FAILED",
        strategy=None,
        etabs_object=None,
        sap_model=None,
        attempts=(
            EtabsAttachAttempt(
                strategy="comtypes_get_active_object_etabs_api_object",
                prog_id="CSI.ETABS.API.ETABSObject",
                status="FAILED",
                message="No such interface supported",
                exception_type="COMError",
                hresult="-2147467262",
            ),
        ),
    )


def test_discovery_module_imports_without_etabs():
    assert discovery.GEOMETRY_TABLE_KEYWORDS == GEOMETRY_TABLE_KEYWORDS


def test_cli_refuses_without_live_etabs(tmp_path: Path, capsys):
    exit_code = discovery_cli.main(["--out", str(tmp_path)])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "explicit --live-etabs opt-in" in captured.err
    assert list(tmp_path.glob("*.json")) == []


def test_discovery_uses_existing_attach_boundary_and_has_no_direct_com_imports():
    module_source = (ROOT / "tbdy_engine" / "features" / "live_etabs_table_discovery.py").read_text(encoding="utf-8")
    cli_source = (ROOT / "tools" / "probe_live_etabs_geometry_tables.py").read_text(encoding="utf-8")

    assert "attach_to_running_etabs" in module_source
    assert "EtabsAttachFailure" in module_source
    assert "import comtypes" not in module_source
    assert "import win32com" not in module_source
    assert "import comtypes" not in cli_source
    assert "import win32com" not in cli_source


def test_candidate_strategy_list_is_bounded():
    assert GEOMETRY_TABLE_KEYWORDS == (
        "frame",
        "section",
        "property",
        "assignment",
        "assign",
        "column",
        "beam",
        "dimension",
        "object",
    )


def test_default_candidate_fetch_cap_remains_5(tmp_path: Path):
    run_live_geometry_table_discovery(source=_load_fixture_source(), output_dir=tmp_path)
    summary = json.loads((tmp_path / "live_geometry_table_discovery_summary.json").read_text(encoding="utf-8"))

    assert summary["candidate_fetch_cap"] == 5
    assert summary["fetched_candidate_count"] == 5


def test_fake_table_inventory_writes_required_artifacts_and_mapping_when_t2_t3_present(tmp_path: Path):
    result = run_live_geometry_table_discovery(
        source=_load_fixture_source(),
        output_dir=tmp_path,
        candidate_fetch_cap=5,
    )

    outputs = {path.name for path in tmp_path.glob("*.json")}
    mapping = json.loads((tmp_path / "accepted_geometry_table_mapping.json").read_text(encoding="utf-8"))

    assert result.status == "OK"
    assert REQUIRED_OUTPUTS < outputs
    assert "accepted_geometry_table_mapping.json" in outputs
    assert mapping == {
        "depth_column": "t3",
        "mapping_basis": "explicit_columns_only",
        "table_key": "Frame Section Property Definitions - Concrete Rectangular",
        "width_column": "t2",
    }


def test_concrete_rectangular_table_is_fetched_with_default_cap_5(tmp_path: Path):
    run_live_geometry_table_discovery(source=_load_fixture_source(), output_dir=tmp_path)
    candidates = json.loads((tmp_path / "live_geometry_table_candidates.json").read_text(encoding="utf-8"))

    concrete = next(candidate for candidate in candidates if candidate["table_key"] == "Frame Section Property Definitions - Concrete Rectangular")
    assert concrete["fetch_status"] == "FETCHED"
    assert concrete["available_columns"] == ["Name", "t3", "t2"]
    assert concrete["missing_expected_columns"] == []


def test_candidate_scoring_is_deterministic_after_prefetch_hotfix(tmp_path: Path):
    run_live_geometry_table_discovery(source=_load_fixture_source(), output_dir=tmp_path, candidate_fetch_cap=5)
    candidates = json.loads((tmp_path / "live_geometry_table_candidates.json").read_text(encoding="utf-8"))

    assert [candidate["table_key"] for candidate in candidates] == [
        "Frame Section Property Definitions - Concrete Rectangular",
        "Beam Property Labels",
        "Frame Assignments - Summary",
        "Column Object Assignments",
        "Concrete Frame Reinforcing Data",
        "Frame Design Forces",
        "Frame Section Assignments",
        "Load Assignments - Frame",
    ]
    assert [candidate["score"] for candidate in candidates] == [73, 12, 4, 2, 2, 0, 0, 0]


def test_candidate_fetch_cap_is_enforced(tmp_path: Path):
    run_live_geometry_table_discovery(source=_load_fixture_source(), output_dir=tmp_path, candidate_fetch_cap=2)
    candidates = json.loads((tmp_path / "live_geometry_table_candidates.json").read_text(encoding="utf-8"))
    summary = json.loads((tmp_path / "live_geometry_table_discovery_summary.json").read_text(encoding="utf-8"))

    assert summary["candidate_fetch_cap"] == 2
    assert summary["fetched_candidate_count"] == 2
    assert sum(1 for candidate in candidates if candidate["fetch_status"] == "SKIPPED_BY_CAP") == 6


def test_rejected_tables_are_recorded(tmp_path: Path):
    run_live_geometry_table_discovery(source=_load_fixture_source(), output_dir=tmp_path, candidate_fetch_cap=5)
    rejections = json.loads((tmp_path / "live_geometry_table_rejections.json").read_text(encoding="utf-8"))

    assert [item["table_key"] for item in rejections] == ["Story Data", "Named Sets"]
    assert all(item["reasons"] == ["no bounded geometry keyword match"] for item in rejections)


def test_table_fetch_failure_is_diagnostic_not_crash(tmp_path: Path):
    source = MappingEtabsTableDiscoverySource(
        descriptors=(
            EtabsTableDescriptor(
                table_key="Frame Assignments - Summary",
                display_name="Frame Assignments - Summary",
                import_type="READ_ONLY",
                is_empty=False,
                source="fake",
            ),
        ),
        columns_by_table_key={},
        failed_table_keys=("Frame Assignments - Summary",),
    )

    result = run_live_geometry_table_discovery(source=source, output_dir=tmp_path, candidate_fetch_cap=1)
    diagnostics = json.loads((tmp_path / "live_geometry_table_discovery_diagnostics.json").read_text(encoding="utf-8"))

    assert result.status == "PARTIAL"
    assert result.candidates[0].fetch_status == "FAILED"
    assert any(item["code"] == "CANDIDATE_TABLE_FETCH_FAILED" for item in diagnostics)


def test_no_accepted_mapping_written_when_only_section_names_exist(tmp_path: Path):
    run_live_geometry_table_discovery(source=_section_only_source(), output_dir=tmp_path, candidate_fetch_cap=5)
    summary = json.loads((tmp_path / "live_geometry_table_discovery_summary.json").read_text(encoding="utf-8"))
    diagnostics = json.loads((tmp_path / "live_geometry_table_discovery_diagnostics.json").read_text(encoding="utf-8"))

    assert summary["accepted_mapping_written"] is False
    assert not (tmp_path / "accepted_geometry_table_mapping.json").exists()
    assert any(item["code"] == "NO_ACCEPTED_GEOMETRY_TABLE_MAPPING" for item in diagnostics)


def test_cli_with_fake_inventory_writes_required_outputs(tmp_path: Path, capsys):
    exit_code = discovery_cli.main(
        [
            "--live-etabs",
            "--out",
            str(tmp_path),
            "--fake-table-inventory",
            str(FIXTURE),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Live geometry table discovery: OK" in captured.out
    assert REQUIRED_OUTPUTS < {path.name for path in tmp_path.glob("*.json")}


def test_cli_attach_failure_writes_summary_diagnostics_manifest_only(tmp_path: Path, monkeypatch, capsys):
    stale_mapping = tmp_path / "accepted_geometry_table_mapping.json"
    stale_mapping.write_text("{}", encoding="utf-8")

    def fail_to_create_source(**_kwargs):
        raise EtabsAttachFailure(_failed_attach_result())

    monkeypatch.setattr(discovery_cli, "create_live_etabs_table_discovery_source", fail_to_create_source)

    exit_code = discovery_cli.main(["--live-etabs", "--out", str(tmp_path)])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Live geometry table discovery: FAIL" in captured.out
    assert ATTACH_FAILURE_OUTPUTS == {path.name for path in tmp_path.glob("*.json")}
    assert not stale_mapping.exists()


def test_fixture_discovery_does_not_emit_no_mapping_diagnostic_when_t2_t3_exist(tmp_path: Path):
    run_live_geometry_table_discovery(source=_load_fixture_source(), output_dir=tmp_path, candidate_fetch_cap=5)
    diagnostics = json.loads((tmp_path / "live_geometry_table_discovery_diagnostics.json").read_text(encoding="utf-8"))

    assert all(item["code"] != "NO_ACCEPTED_GEOMETRY_TABLE_MAPPING" for item in diagnostics)


def test_section_only_discovery_explains_why_c13_5_p3_snapshot_count_may_be_zero(tmp_path: Path):
    run_live_geometry_table_discovery(source=_section_only_source(), output_dir=tmp_path, candidate_fetch_cap=5)
    diagnostics = json.loads((tmp_path / "live_geometry_table_discovery_diagnostics.json").read_text(encoding="utf-8"))

    diagnostic = next(item for item in diagnostics if item["code"] == "NO_ACCEPTED_GEOMETRY_TABLE_MAPPING")
    assert "zero snapshots" in diagnostic["message"]
