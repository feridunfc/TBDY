from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from tbdy_engine.features.etabs_com_attach import EtabsAttachAttempt, EtabsAttachResult
from tbdy_engine.features.live_etabs_geometry_probe import (
    AcceptedMappingGeometryRowProvider,
    create_live_etabs_geometry_provider,
    probe_geometry_feature_snapshots,
    read_live_frame_component_type_source,
)
from tbdy_engine.product.offline_acceptance import build_offline_acceptance_command_plan

ROOT = Path(__file__).resolve().parents[2]
ASSIGNMENT_FIXTURE = ROOT / "tests" / "fixtures" / "c13_5_p6" / "fake_assignment_rows.json"
PROPERTY_FIXTURE = ROOT / "tests" / "fixtures" / "c13_5_p6" / "fake_property_definition_rows.json"
COMPONENT_TYPE_FIXTURE = ROOT / "tests" / "fixtures" / "c13_5_p6" / "fake_component_type_rows.json"
LIVE_PROBE_PATH = ROOT / "tbdy_engine" / "features" / "live_etabs_geometry_probe.py"
CLI_PATH = ROOT / "tools" / "probe_live_etabs_geometry_snapshot.py"
ASSIGNMENT_TABLE = "Frame Assignments - Section Properties"
PROPERTY_TABLE = "Frame Section Property Definitions - Concrete Rectangular"
COMPONENT_TYPE_TABLE = "Frame Assignments - Summary"
ASSIGNMENT_COLUMNS = ["Story", "Label", "UniqueName", "Shape", "AutoSelect", "SectProp"]
PROPERTY_COLUMNS = ["Name", "t2", "t3", "unit"]
COMPONENT_TYPE_COLUMNS = ["UniqueName", "Design Type"]
COMPACT_COMPONENT_TYPE_COLUMNS = ["UniqueName", "DesignType"]


class _FakeDatabaseTables:
    def __init__(self, payloads):
        self.payloads = dict(payloads)

    def GetTableForDisplayArray(self, table_key, *_args):
        payload = self.payloads[table_key]
        if isinstance(payload, Exception):
            raise payload
        return payload


def _attached_result(database_tables: _FakeDatabaseTables) -> EtabsAttachResult:
    return EtabsAttachResult(
        status="ATTACHED",
        strategy="comtypes_get_active_object_etabs_api_object",
        etabs_object=object(),
        sap_model=SimpleNamespace(DatabaseTables=database_tables),
        attempts=(
            EtabsAttachAttempt(
                strategy="comtypes_get_active_object_etabs_api_object",
                status="SUCCESS",
                message="Attached fake ETABS for tests",
                prog_id="CSI.ETABS.API.ETABSObject",
            ),
        ),
    )


def _rows(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))["rows"]


def _fixture_provider(component_type_rows=None, source_column: str = "ObjectType") -> AcceptedMappingGeometryRowProvider:
    return AcceptedMappingGeometryRowProvider(
        assignment_rows=_rows(ASSIGNMENT_FIXTURE),
        property_rows=_rows(PROPERTY_FIXTURE),
        component_type_rows=_rows(COMPONENT_TYPE_FIXTURE) if component_type_rows is None else component_type_rows,
        component_type_source_table=COMPONENT_TYPE_TABLE,
        component_type_source_column=source_column,
        component_type_join_key_column="UniqueName",
    )


def _valid_assignment_display_array():
    return (
        0,
        ASSIGNMENT_COLUMNS,
        [
            "+14.5", "B1", "297", "Rectangular", "No", "B40x70",
            "+11.0", "C1", "301", "Rectangular", "No", "C50x60",
        ],
    )


def _valid_property_display_array():
    return (
        0,
        PROPERTY_COLUMNS,
        ["B40x70", 400.0, 700.0, "mm", "C50x60", 500.0, 600.0, "mm"],
    )


def _valid_component_type_display_array():
    return (
        0,
        COMPONENT_TYPE_COLUMNS,
        ["297", "Beam", "301", "Column"],
    )


def _compact_component_type_display_array():
    return (
        0,
        COMPACT_COMPONENT_TYPE_COLUMNS,
        ["297", "Beam", "301", "Column"],
    )


def _codes(result):
    return {diagnostic.code for diagnostic in result.iter_geometry_diagnostics()}


def test_fake_rows_emit_beam_feature_snapshot_from_explicit_component_type_source(tmp_path: Path):
    result = probe_geometry_feature_snapshots(provider=_fixture_provider(), output_dir=tmp_path)
    payload = json.loads((tmp_path / "feature_snapshot.json").read_text(encoding="utf-8"))
    beam = next(snapshot for snapshot in payload["snapshots"] if snapshot["component_type"] == "beam")

    assert result.status == "OK"
    assert beam["component_id"] == "297"
    assert beam["features"]["beam_width_mm"]["value"] == 400.0
    assert beam["features"]["beam_depth_mm"]["value"] == 700.0


def test_fake_rows_emit_column_feature_snapshot_from_explicit_component_type_source(tmp_path: Path):
    result = probe_geometry_feature_snapshots(provider=_fixture_provider(), output_dir=tmp_path)
    payload = json.loads((tmp_path / "feature_snapshot.json").read_text(encoding="utf-8"))
    column = next(snapshot for snapshot in payload["snapshots"] if snapshot["component_type"] == "column")

    assert result.status == "OK"
    assert column["component_id"] == "301"
    assert column["features"]["column_width_mm"]["value"] == 500.0
    assert column["features"]["column_depth_mm"]["value"] == 600.0


def test_design_type_spaced_column_resolves_beam_to_beam(tmp_path: Path):
    provider = _fixture_provider(
        component_type_rows=(
            {"UniqueName": "297", "Design Type": " Beam "},
            {"UniqueName": "301", "Design Type": "Column"},
        ),
        source_column="Design Type",
    )

    result = probe_geometry_feature_snapshots(provider=provider, output_dir=tmp_path)
    payload = json.loads((tmp_path / "feature_snapshot.json").read_text(encoding="utf-8"))

    assert result.status == "OK"
    assert any(snapshot["component_type"] == "beam" and snapshot["component_id"] == "297" for snapshot in payload["snapshots"])


def test_design_type_spaced_column_resolves_column_to_column(tmp_path: Path):
    provider = _fixture_provider(
        component_type_rows=(
            {"UniqueName": "297", "Design Type": "Beam"},
            {"UniqueName": "301", "Design Type": " column "},
        ),
        source_column="Design Type",
    )

    result = probe_geometry_feature_snapshots(provider=provider, output_dir=tmp_path)
    payload = json.loads((tmp_path / "feature_snapshot.json").read_text(encoding="utf-8"))

    assert result.status == "OK"
    assert any(snapshot["component_type"] == "column" and snapshot["component_id"] == "301" for snapshot in payload["snapshots"])


def test_design_type_compact_alias_still_works(tmp_path: Path):
    provider = _fixture_provider(
        component_type_rows=(
            {"UniqueName": "297", "DesignType": "Beam"},
            {"UniqueName": "301", "DesignType": "Column"},
        ),
        source_column="DesignType",
    )

    result = probe_geometry_feature_snapshots(provider=provider, output_dir=tmp_path)

    assert result.status == "OK"
    assert result.snapshot_count == 2


def test_brace_does_not_emit_beam_or_column_feature_snapshot(tmp_path: Path):
    provider = _fixture_provider(
        component_type_rows=(
            {"UniqueName": "297", "Design Type": "Brace"},
        ),
        source_column="Design Type",
    )

    result = probe_geometry_feature_snapshots(provider=provider, output_dir=tmp_path)

    assert result.status == "FAIL"
    assert result.snapshot_count == 0
    assert "COMPONENT_TYPE_VALUE_UNSUPPORTED" in _codes(provider)


def test_null_does_not_emit_beam_or_column_feature_snapshot(tmp_path: Path):
    provider = _fixture_provider(
        component_type_rows=(
            {"UniqueName": "301", "Design Type": "Null"},
        ),
        source_column="Design Type",
    )

    result = probe_geometry_feature_snapshots(provider=provider, output_dir=tmp_path)

    assert result.status == "FAIL"
    assert result.snapshot_count == 0
    assert "COMPONENT_TYPE_VALUE_UNSUPPORTED" in _codes(provider)


def test_unsupported_non_target_values_do_not_block_supported_rows(tmp_path: Path):
    provider = _fixture_provider(
        component_type_rows=(
            {"UniqueName": "297", "Design Type": "Beam"},
            {"UniqueName": "301", "Design Type": "Column"},
            {"UniqueName": "BRACE_1", "Design Type": "Brace"},
            {"UniqueName": "NULL_1", "Design Type": "Null"},
        ),
        source_column="Design Type",
    )

    result = probe_geometry_feature_snapshots(provider=provider, output_dir=tmp_path)

    assert result.status == "PARTIAL"
    assert result.snapshot_count == 2
    assert "COMPONENT_TYPE_VALUE_UNSUPPORTED" in _codes(provider)


def test_summary_includes_component_type_source_status_and_counts(tmp_path: Path):
    probe_geometry_feature_snapshots(provider=_fixture_provider(), output_dir=tmp_path)
    summary = json.loads((tmp_path / "live_geometry_probe_summary.json").read_text(encoding="utf-8"))

    assert summary["component_type_source_table"] == COMPONENT_TYPE_TABLE
    assert summary["component_type_source_status"] == "FETCHED"
    assert summary["component_type_source_row_count"] == 2
    assert summary["component_type_resolved_row_count"] == 2
    assert summary["component_type_unresolved_row_count"] == 0
    assert summary["assignment_table_row_count"] == 2
    assert summary["property_table_row_count"] == 2
    assert summary["resolved_geometry_row_count"] == 2


def test_evidence_preserves_component_type_source_table_column_and_raw_row(tmp_path: Path):
    provider = _fixture_provider(
        component_type_rows=(
            {"UniqueName": "297", "Design Type": "Beam"},
            {"UniqueName": "301", "Design Type": "Column"},
        ),
        source_column="Design Type",
    )
    probe_geometry_feature_snapshots(provider=provider, output_dir=tmp_path)
    payload = json.loads((tmp_path / "feature_snapshot.json").read_text(encoding="utf-8"))
    beam = next(snapshot for snapshot in payload["snapshots"] if snapshot["component_type"] == "beam")
    evidence = beam["features"]["beam_width_mm"]["evidence"][0]
    source_row = evidence["source_row"]

    assert source_row["component_type_source_table"] == COMPONENT_TYPE_TABLE
    assert source_row["component_type_source_column"] == "Design Type"
    assert source_row["component_type_join_key_column"] == "UniqueName"
    assert source_row["component_type_source_row"] == {"Design Type": "Beam", "UniqueName": "297"}


def test_live_fake_database_component_type_source_consumes_spaced_design_type(tmp_path: Path):
    database_tables = _FakeDatabaseTables(
        {
            ASSIGNMENT_TABLE: _valid_assignment_display_array(),
            PROPERTY_TABLE: _valid_property_display_array(),
            COMPONENT_TYPE_TABLE: _valid_component_type_display_array(),
        }
    )
    provider = create_live_etabs_geometry_provider(attach_result=_attached_result(database_tables), max_candidate_tables=1)

    result = probe_geometry_feature_snapshots(provider=provider, output_dir=tmp_path)
    summary = json.loads((tmp_path / "live_geometry_probe_summary.json").read_text(encoding="utf-8"))

    assert result.status == "OK"
    assert result.snapshot_count == 2
    assert summary["component_type_source_status"] == "FETCHED"
    assert summary["component_type_source_row_count"] == 2


def test_live_fake_database_component_type_source_keeps_compact_design_type_alias(tmp_path: Path):
    database_tables = _FakeDatabaseTables(
        {
            ASSIGNMENT_TABLE: _valid_assignment_display_array(),
            PROPERTY_TABLE: _valid_property_display_array(),
            COMPONENT_TYPE_TABLE: _compact_component_type_display_array(),
        }
    )
    provider = create_live_etabs_geometry_provider(attach_result=_attached_result(database_tables), max_candidate_tables=1)

    result = probe_geometry_feature_snapshots(provider=provider, output_dir=tmp_path)

    assert result.status == "OK"
    assert result.snapshot_count == 2


def test_read_live_frame_component_type_source_reports_spaced_design_type_column():
    result = read_live_frame_component_type_source(
        _FakeDatabaseTables({COMPONENT_TYPE_TABLE: _valid_component_type_display_array()}),
        max_candidate_tables=1,
    )

    assert result.status == "FETCHED"
    assert result.source_table == COMPONENT_TYPE_TABLE
    assert result.source_column == "Design Type"
    assert result.row_count == 2
    assert result.evidence_by_unique_name["297"].component_type == "beam"
    assert result.evidence_by_unique_name["301"].component_type == "column"


def test_component_type_source_table_missing_produces_diagnostic(tmp_path: Path):
    provider = create_live_etabs_geometry_provider(
        attach_result=_attached_result(
            _FakeDatabaseTables(
                {
                    ASSIGNMENT_TABLE: _valid_assignment_display_array(),
                    PROPERTY_TABLE: _valid_property_display_array(),
                }
            )
        ),
        max_candidate_tables=1,
    )

    result = probe_geometry_feature_snapshots(provider=provider, output_dir=tmp_path)

    assert result.status == "FAIL"
    assert result.snapshot_count == 0
    assert "COMPONENT_TYPE_SOURCE_TABLE_MISSING" in _codes(provider)


def test_component_type_source_column_missing_produces_diagnostic(tmp_path: Path):
    provider = _fixture_provider(component_type_rows=({"UniqueName": "297", "SomeOtherColumn": "Beam"},))

    result = probe_geometry_feature_snapshots(provider=provider, output_dir=tmp_path)

    assert result.status == "FAIL"
    assert "COMPONENT_TYPE_SOURCE_COLUMN_MISSING" in _codes(provider)


def test_configured_source_column_must_exist_exactly(tmp_path: Path):
    provider = _fixture_provider(
        component_type_rows=({"UniqueName": "297", "DesignType": "Beam"},),
        source_column="Design Type",
    )

    result = probe_geometry_feature_snapshots(provider=provider, output_dir=tmp_path)

    assert result.status == "FAIL"
    assert "COMPONENT_TYPE_SOURCE_COLUMN_MISSING" in _codes(provider)


def test_component_type_value_unsupported_produces_diagnostic(tmp_path: Path):
    provider = _fixture_provider(component_type_rows=({"UniqueName": "297", "ObjectType": "Wall"},))

    result = probe_geometry_feature_snapshots(provider=provider, output_dir=tmp_path)

    assert result.status == "FAIL"
    assert "COMPONENT_TYPE_VALUE_UNSUPPORTED" in _codes(provider)


def test_component_type_join_not_found_produces_diagnostic(tmp_path: Path):
    provider = _fixture_provider(component_type_rows=({"UniqueName": "NO_MATCH", "ObjectType": "Beam"},))

    result = probe_geometry_feature_snapshots(provider=provider, output_dir=tmp_path)

    assert result.status == "FAIL"
    assert result.snapshot_count == 0
    assert "COMPONENT_TYPE_JOIN_NOT_FOUND" in _codes(provider)


def test_label_prefix_is_not_used_to_resolve_component_type(tmp_path: Path):
    provider = _fixture_provider(component_type_rows=({"UniqueName": "NO_MATCH", "ObjectType": "Beam"},))

    result = probe_geometry_feature_snapshots(provider=provider, output_dir=tmp_path)

    assert result.status == "FAIL"
    assert result.snapshot_count == 0
    assert "COMPONENT_TYPE_JOIN_NOT_FOUND" in _codes(provider)


def test_section_name_is_not_parsed_and_b_c_prefix_is_not_used():
    source = LIVE_PROBE_PATH.read_text(encoding="utf-8")

    assert "B40x70" not in source
    assert "C50x60" not in source
    assert "parse_section" not in source
    assert ".split(" not in source
    assert "startswith" not in source


def test_no_unit_conversion_exists_in_live_probe():
    source = LIVE_PROBE_PATH.read_text(encoding="utf-8")

    assert "cm_to_mm" not in source
    assert "converted" not in source.casefold()


def test_no_checkengine_or_checkresult_in_live_probe():
    source = LIVE_PROBE_PATH.read_text(encoding="utf-8")

    assert "CheckResult" not in source
    assert "MinimalCheckEngine" not in source
    assert "tbdy_engine.checks.engine" not in source


def test_no_product_smoke_auto_run_in_live_probe_cli():
    source = CLI_PATH.read_text(encoding="utf-8")

    assert "run_geometry_product_smoke" not in source
    assert "product_smoke" not in source


def test_offline_acceptance_includes_c13_5_p6_and_command_count_remains_18(tmp_path: Path):
    plan = build_offline_acceptance_command_plan(output_dir=tmp_path, python_executable="PY")

    assert len(plan) == 18
    assert ("pytest_c13_5_p6", ("PY", "-m", "pytest", "-q", "tests/c13_5_p6")) in plan
