from __future__ import annotations

from pathlib import Path

import tbdy_engine.features.live_etabs_geometry_probe as live_geometry_probe
from tbdy_engine.features.live_etabs_geometry_probe import (
    DEFAULT_ACCEPTED_GEOMETRY_MAPPING,
    AcceptedMappingGeometryRowProvider,
    probe_geometry_feature_snapshots,
    read_live_etabs_table_for_geometry,
    resolve_geometry_rows_from_accepted_mapping,
)
from tbdy_engine.product.offline_acceptance import build_offline_acceptance_command_plan

ROOT = Path(__file__).resolve().parents[2]
LIVE_PROBE_PATH = ROOT / "tbdy_engine" / "features" / "live_etabs_geometry_probe.py"
CLI_PATH = ROOT / "tools" / "probe_live_etabs_geometry_snapshot.py"
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "c13_4_offline_acceptance.yml"
P4_NEGATIVE_TEST_PATH = ROOT / "tests" / "c13_5_p4" / "test_live_etabs_table_discovery_negative_cases.py"
ASSIGNMENT_TABLE = "Frame Assignments - Section Properties"
PROPERTY_TABLE = "Frame Section Property Definitions - Concrete Rectangular"
COMPONENT_TYPE_TABLE = "Frame Assignments - Summary"
ASSIGNMENT_COLUMNS = ["Story", "Label", "UniqueName", "Shape", "AutoSelect", "SectProp", "ComponentType"]
PROPERTY_COLUMNS = ["Name", "t2", "t3", "unit"]
COMPONENT_TYPE_COLUMNS = ["UniqueName", "ObjectType"]


class _FakeDatabaseTables:
    def __init__(self, payloads):
        self.payloads = dict(payloads)

    def GetTableForDisplayArray(self, table_key, *_args):
        payload = self.payloads[table_key]
        if isinstance(payload, Exception):
            raise payload
        return payload


def _valid_assignment_rows():
    return (
        {
            "Story": "+14.5",
            "Label": "B1",
            "UniqueName": "297",
            "SectProp": "B40x70",
            "ComponentType": "beam",
        },
    )


def _valid_property_rows():
    return (
        {"Name": "B40x70", "t2": 400.0, "t3": 700.0, "unit": "mm"},
    )


def _valid_assignment_display_array():
    return (
        0,
        ASSIGNMENT_COLUMNS,
        ["+14.5", "B1", "297", "Rectangular", "No", "B40x70", "beam"],
    )


def _valid_property_display_array():
    return (
        0,
        PROPERTY_COLUMNS,
        ["B40x70", 400.0, 700.0, "mm"],
    )


def _valid_component_type_display_array():
    return (
        0,
        COMPONENT_TYPE_COLUMNS,
        ["297", "Beam"],
    )


def _live_payloads(**overrides):
    payloads = {
        ASSIGNMENT_TABLE: _valid_assignment_display_array(),
        PROPERTY_TABLE: _valid_property_display_array(),
        COMPONENT_TYPE_TABLE: _valid_component_type_display_array(),
    }
    payloads.update(overrides)
    return payloads


def _codes(diagnostics):
    return {diagnostic.code for diagnostic in diagnostics}


def _table_diagnostics(*, role: str, table_key: str, payload):
    result = read_live_etabs_table_for_geometry(
        _FakeDatabaseTables({table_key: payload}),
        table_key,
    )
    return result, live_geometry_probe._table_read_diagnostics(
        table_role=role,
        result=result,
    )


def test_table_read_decodes_string_flat_data_rows():
    result = read_live_etabs_table_for_geometry(
        _FakeDatabaseTables({ASSIGNMENT_TABLE: _valid_assignment_display_array()}),
        ASSIGNMENT_TABLE,
    )

    assert result.status == "FETCHED"
    assert result.row_count == 1
    assert result.columns == tuple(ASSIGNMENT_COLUMNS)
    assert result.rows[0]["SectProp"] == "B40x70"


def test_table_fetch_failure_returns_structured_result():
    result = read_live_etabs_table_for_geometry(
        _FakeDatabaseTables({ASSIGNMENT_TABLE: RuntimeError("boom")}),
        ASSIGNMENT_TABLE,
    )

    assert result.status == "FAILED"
    assert result.row_count == 0
    assert result.rows == ()
    assert result.message == "boom"


def test_table_fetched_with_columns_but_zero_rows_returns_empty():
    result = read_live_etabs_table_for_geometry(
        _FakeDatabaseTables({ASSIGNMENT_TABLE: (0, ASSIGNMENT_COLUMNS, [])}),
        ASSIGNMENT_TABLE,
    )

    assert result.status == "EMPTY"
    assert result.columns == tuple(ASSIGNMENT_COLUMNS)
    assert result.row_count == 0


def test_raw_display_array_parse_empty_returns_diagnostic_status():
    result = read_live_etabs_table_for_geometry(
        _FakeDatabaseTables({ASSIGNMENT_TABLE: (1, ASSIGNMENT_COLUMNS, ["orphan-value"])}),
        ASSIGNMENT_TABLE,
    )

    assert result.status == "PARSE_EMPTY"
    assert result.row_count == 0
    assert "divisible" in str(result.message)


def test_assignment_table_fetch_failure_diagnostic():
    result, diagnostics = _table_diagnostics(
        role="ASSIGNMENT",
        table_key=ASSIGNMENT_TABLE,
        payload=RuntimeError("assignment fetch failed"),
    )

    assert result.status == "FAILED"
    assert _codes(diagnostics) == {"ASSIGNMENT_TABLE_FETCH_FAILED"}


def test_assignment_table_fetched_zero_rows_diagnostic():
    result, diagnostics = _table_diagnostics(
        role="ASSIGNMENT",
        table_key=ASSIGNMENT_TABLE,
        payload=(0, ASSIGNMENT_COLUMNS, []),
    )

    assert result.status == "EMPTY"
    assert _codes(diagnostics) == {"ASSIGNMENT_TABLE_FETCHED_ZERO_ROWS"}


def test_assignment_table_parse_empty_diagnostic():
    result, diagnostics = _table_diagnostics(
        role="ASSIGNMENT",
        table_key=ASSIGNMENT_TABLE,
        payload=(1, ASSIGNMENT_COLUMNS, ["orphan-value"]),
    )

    assert result.status == "PARSE_EMPTY"
    assert _codes(diagnostics) == {"ASSIGNMENT_TABLE_PARSE_EMPTY"}


def test_property_table_fetch_failure_diagnostic():
    result, diagnostics = _table_diagnostics(
        role="PROPERTY",
        table_key=PROPERTY_TABLE,
        payload=RuntimeError("property fetch failed"),
    )

    assert result.status == "FAILED"
    assert _codes(diagnostics) == {"PROPERTY_TABLE_FETCH_FAILED"}


def test_summary_counts_for_live_table_read_results(tmp_path: Path):
    database_tables = _FakeDatabaseTables(_live_payloads())
    assignment_result = read_live_etabs_table_for_geometry(database_tables, ASSIGNMENT_TABLE)
    property_result = read_live_etabs_table_for_geometry(database_tables, PROPERTY_TABLE)
    component_result = read_live_etabs_table_for_geometry(database_tables, COMPONENT_TYPE_TABLE)
    provider = AcceptedMappingGeometryRowProvider(
        assignment_rows=assignment_result.rows,
        property_rows=property_result.rows,
        component_type_rows=component_result.rows,
        component_type_source_table=COMPONENT_TYPE_TABLE,
        component_type_source_column="ObjectType",
        component_type_join_key_column="UniqueName",
    )

    result = probe_geometry_feature_snapshots(provider=provider, output_dir=tmp_path)
    summary_text = (tmp_path / "live_geometry_probe_summary.json").read_text(encoding="utf-8")

    assert result.status == "OK"
    assert '"assignment_table_row_count": 1' in summary_text
    assert '"property_table_row_count": 1' in summary_text
    assert '"resolved_geometry_row_count": 1' in summary_text


def test_missing_accepted_mapping_produces_blocked_diagnostic():
    rows, diagnostics = resolve_geometry_rows_from_accepted_mapping(
        assignment_rows=_valid_assignment_rows(),
        property_rows=_valid_property_rows(),
        mapping=None,
    )

    assert rows == ()
    assert _codes(diagnostics) == {"ACCEPTED_GEOMETRY_MAPPING_MISSING"}
    assert diagnostics[0].status == "BLOCKED"


def test_missing_assignment_table_produces_diagnostic_without_guessing():
    rows, diagnostics = resolve_geometry_rows_from_accepted_mapping(
        assignment_rows=(),
        property_rows=_valid_property_rows(),
        mapping=DEFAULT_ACCEPTED_GEOMETRY_MAPPING,
    )

    assert rows == ()
    assert _codes(diagnostics) == {"ASSIGNMENT_TABLE_MISSING_OR_EMPTY"}


def test_missing_property_table_produces_diagnostic_without_guessing():
    rows, diagnostics = resolve_geometry_rows_from_accepted_mapping(
        assignment_rows=_valid_assignment_rows(),
        property_rows=(),
        mapping=DEFAULT_ACCEPTED_GEOMETRY_MAPPING,
    )

    assert rows == ()
    assert _codes(diagnostics) == {"PROPERTY_TABLE_MISSING_OR_EMPTY"}


def test_missing_sectprop_join_column_produces_diagnostic():
    assignment_rows = ({"Story": "+14.5", "Label": "B1", "UniqueName": "297", "ComponentType": "beam"},)

    rows, diagnostics = resolve_geometry_rows_from_accepted_mapping(
        assignment_rows=assignment_rows,
        property_rows=_valid_property_rows(),
        mapping=DEFAULT_ACCEPTED_GEOMETRY_MAPPING,
    )

    assert rows == ()
    assert _codes(diagnostics) == {"ASSIGNMENT_TABLE_REQUIRED_COLUMN_MISSING"}


def test_missing_name_join_column_produces_diagnostic():
    property_rows = ({"SectionName": "B40x70", "t2": 400.0, "t3": 700.0, "unit": "mm"},)

    rows, diagnostics = resolve_geometry_rows_from_accepted_mapping(
        assignment_rows=_valid_assignment_rows(),
        property_rows=property_rows,
        mapping=DEFAULT_ACCEPTED_GEOMETRY_MAPPING,
    )

    assert rows == ()
    assert _codes(diagnostics) == {"PROPERTY_TABLE_REQUIRED_COLUMN_MISSING"}


def test_unmatched_section_property_produces_diagnostic():
    assignment_rows = ({"Story": "+14.5", "Label": "B1", "UniqueName": "297", "SectProp": "NOT_FOUND", "ComponentType": "beam"},)

    rows, diagnostics = resolve_geometry_rows_from_accepted_mapping(
        assignment_rows=assignment_rows,
        property_rows=_valid_property_rows(),
        mapping=DEFAULT_ACCEPTED_GEOMETRY_MAPPING,
    )

    assert rows == ()
    assert _codes(diagnostics) == {"SECTION_PROPERTY_NOT_FOUND"}


def test_missing_t2_or_t3_produces_diagnostic():
    property_rows = ({"Name": "B40x70", "t2": 400.0, "unit": "mm"},)

    rows, diagnostics = resolve_geometry_rows_from_accepted_mapping(
        assignment_rows=_valid_assignment_rows(),
        property_rows=property_rows,
        mapping=DEFAULT_ACCEPTED_GEOMETRY_MAPPING,
    )

    assert rows == ()
    assert _codes(diagnostics) == {"PROPERTY_TABLE_REQUIRED_COLUMN_MISSING"}


def test_non_numeric_t2_t3_produces_diagnostic():
    property_rows = ({"Name": "B40x70", "t2": "400", "t3": 700.0, "unit": "mm"},)

    rows, diagnostics = resolve_geometry_rows_from_accepted_mapping(
        assignment_rows=_valid_assignment_rows(),
        property_rows=property_rows,
        mapping=DEFAULT_ACCEPTED_GEOMETRY_MAPPING,
    )

    assert rows == ()
    assert _codes(diagnostics) == {"GEOMETRY_DIMENSION_VALUE_NOT_NUMERIC"}


def test_missing_unit_produces_diagnostic_and_no_feature_rows():
    property_rows = ({"Name": "B40x70", "t2": 400.0, "t3": 700.0},)

    rows, diagnostics = resolve_geometry_rows_from_accepted_mapping(
        assignment_rows=_valid_assignment_rows(),
        property_rows=property_rows,
        mapping=DEFAULT_ACCEPTED_GEOMETRY_MAPPING,
    )

    assert rows == ()
    assert _codes(diagnostics) == {"GEOMETRY_UNIT_NOT_PROVEN_MM"}


def test_missing_component_type_produces_diagnostic_no_label_guessing():
    assignment_rows = ({"Story": "+14.5", "Label": "B1", "UniqueName": "297", "SectProp": "B40x70"},)

    rows, diagnostics = resolve_geometry_rows_from_accepted_mapping(
        assignment_rows=assignment_rows,
        property_rows=_valid_property_rows(),
        mapping=DEFAULT_ACCEPTED_GEOMETRY_MAPPING,
    )

    assert rows == ()
    assert _codes(diagnostics) == {"COMPONENT_TYPE_NOT_EXPLICIT"}


def test_probe_writes_diagnostics_when_mapping_provider_has_no_rows(tmp_path: Path):
    provider = AcceptedMappingGeometryRowProvider(
        assignment_rows=(),
        property_rows=_valid_property_rows(),
        mapping=DEFAULT_ACCEPTED_GEOMETRY_MAPPING,
    )

    result = probe_geometry_feature_snapshots(provider=provider, output_dir=tmp_path)

    assert result.status == "FAIL"
    assert result.snapshot_count == 0
    assert result.diagnostic_count == 1


def test_no_section_name_parsing_exists_in_live_probe_path():
    source = LIVE_PROBE_PATH.read_text(encoding="utf-8")

    assert "B40x70" not in source
    assert "C40x50" not in source
    assert "parse_section" not in source
    assert ".split(" not in source


def test_no_unit_conversion_exists_in_live_probe_path():
    source = LIVE_PROBE_PATH.read_text(encoding="utf-8")

    assert "cm_to_mm" not in source
    assert "converted" not in source.casefold()


def test_no_checkresult_or_checkengine_appears_in_live_probe_path():
    source = LIVE_PROBE_PATH.read_text(encoding="utf-8")

    assert "CheckResult" not in source
    assert "MinimalCheckEngine" not in source
    assert "tbdy_engine.checks.engine" not in source


def test_no_product_smoke_call_from_live_probe_cli():
    source = CLI_PATH.read_text(encoding="utf-8")

    assert "run_geometry_product_smoke" not in source
    assert "product_smoke" not in source


def test_no_forbidden_engineering_logic_added_to_live_probe_path():
    source = LIVE_PROBE_PATH.read_text(encoding="utf-8")

    for forbidden in ("rebar_extraction", "capacity_design_shear", "PMM_design", "SCWB_design", "drift_extraction", "modal_mass_extraction"):
        assert forbidden not in source


def test_offline_acceptance_includes_c13_5_p5_and_command_count_is_18(tmp_path: Path):
    plan = build_offline_acceptance_command_plan(output_dir=tmp_path, python_executable="PY")

    assert len(plan) == 18
    assert ("pytest_c13_5_p5", ("PY", "-m", "pytest", "-q", "tests/c13_5_p5")) in plan


def test_p10_workflow_still_delegates_to_p9_cli_only():
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")

    assert "python tools/run_offline_product_acceptance.py" in workflow
    assert "pytest -q" not in workflow
    assert "tests/c13_5_p5" not in workflow


def test_stale_c13_5_p4_tests_remain_future_safe():
    source = P4_NEGATIVE_TEST_PATH.read_text(encoding="utf-8")
    lines = source.splitlines()

    real_stale_assertions = [line for line in lines if line.strip() == "assert len(plan) == 16"]

    assert real_stale_assertions == []
    assert "tests/c13_5_p4" in source
    assert "tests/c13_5_p5" not in source
