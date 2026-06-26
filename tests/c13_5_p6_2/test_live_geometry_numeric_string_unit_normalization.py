from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from tbdy_engine.features.etabs_com_attach import EtabsAttachAttempt, EtabsAttachResult
from tbdy_engine.features.live_etabs_geometry_probe import (
    AcceptedMappingGeometryRowProvider,
    LENGTH_TO_MM_FACTOR,
    LENGTH_UNITS,
    LiveEtabsLengthUnitEvidence,
    MappingGeometryRowProvider,
    create_live_etabs_geometry_provider,
    probe_geometry_feature_snapshots,
    resolve_geometry_rows_from_accepted_mapping,
    write_com_attach_failure_probe_outputs,
)

ASSIGNMENT_TABLE = "Frame Assignments - Section Properties"
PROPERTY_TABLE = "Frame Section Property Definitions - Concrete Rectangular"
COMPONENT_TYPE_TABLE = "Frame Assignments - Summary"
ASSIGNMENT_COLUMNS = ["Story", "Label", "UniqueName", "Shape", "AutoSelect", "SectProp"]
PROPERTY_COLUMNS = ["Name", "t2", "t3", "DesignType"]
COMPONENT_TYPE_COLUMNS = ["Story", "Label", "UniqueName", "Type"]


def _assignment_rows(section_name: str = "SEC"):
    return ({"Story": "+14.5", "Label": "B1", "UniqueName": "297", "SectProp": section_name, "ComponentType": "beam"},)


def _component_type_rows():
    return ({"UniqueName": "297", "Type": "Beam"},)


def _property_rows(*, width: object = "0.4", depth: object = "0.7", section_name: str = "SEC"):
    return ({"Name": section_name, "t2": width, "t3": depth, "DesignType": "Beam"},)


def _unit_evidence(source_unit: str) -> LiveEtabsLengthUnitEvidence:
    enum = next(key for key, value in LENGTH_UNITS.items() if value == source_unit)
    raw = (4, enum, 2, 0)
    return LiveEtabsLengthUnitEvidence(
        present_force_unit="kN",
        present_length_unit=source_unit,
        present_temperature_unit="C",
        database_force_unit="kN",
        database_length_unit=source_unit,
        database_temperature_unit="C",
        present_units_raw=raw,
        database_units_raw=raw,
    )


def _codes(diagnostics):
    return {diagnostic.code for diagnostic in diagnostics}


@pytest.mark.parametrize(
    ("source_unit", "raw_value", "expected_mm"),
    [
        ("um", "400000", 400.0),
        ("mm", "400", 400.0),
        ("cm", "40", 400.0),
        ("m", "0.4", 400.0),
        ("in", "15.7480314961", pytest.approx(400.0)),
        ("ft", "1.312335958", pytest.approx(400.0)),
    ],
)
def test_supported_runtime_length_units_normalize_numeric_strings_to_mm(source_unit: str, raw_value: str, expected_mm: float):
    rows, diagnostics = resolve_geometry_rows_from_accepted_mapping(
        assignment_rows=_assignment_rows(),
        property_rows=_property_rows(width=raw_value, depth=raw_value),
        length_unit_evidence=_unit_evidence(source_unit),
        require_length_unit_evidence=True,
    )

    assert diagnostics == ()
    assert rows[0]["width_mm"] == expected_mm
    assert rows[0]["depth_mm"] == expected_mm
    details = rows[0]["width_normalization"]
    assert details["raw_value"] == raw_value
    assert details["raw_value_type"] == "str"
    assert details["parsed_value"] == float(raw_value)
    assert details["source_unit"] == source_unit
    assert details["target_unit"] == "mm"
    assert details["normalization_factor_to_mm"] == LENGTH_TO_MM_FACTOR[source_unit]
    assert details["normalized_value"] == expected_mm
    assert details["normalized_unit"] == "mm"
    assert details["present_units_raw"]
    assert details["database_units_raw"]


def test_integer_numeric_string_depth_is_parsed_and_normalized():
    rows, diagnostics = resolve_geometry_rows_from_accepted_mapping(
        assignment_rows=_assignment_rows(),
        property_rows=_property_rows(width="0.4", depth="1"),
        length_unit_evidence=_unit_evidence("m"),
        require_length_unit_evidence=True,
    )

    assert diagnostics == ()
    assert rows[0]["width_mm"] == 400.0
    assert rows[0]["depth_mm"] == 1000.0


def test_native_numeric_with_runtime_unit_normalizes_to_mm():
    rows, diagnostics = resolve_geometry_rows_from_accepted_mapping(
        assignment_rows=_assignment_rows(),
        property_rows=_property_rows(width=0.4, depth=0.7),
        length_unit_evidence=_unit_evidence("m"),
        require_length_unit_evidence=True,
    )

    assert diagnostics == ()
    assert rows[0]["width_mm"] == 400.0
    assert rows[0]["depth_mm"] == 700.0


def test_native_numeric_without_unit_legacy_path_preserves_p5_diagnostic():
    rows, diagnostics = resolve_geometry_rows_from_accepted_mapping(
        assignment_rows=_assignment_rows(),
        property_rows=_property_rows(width=400.0, depth=700.0),
        length_unit_evidence=None,
        require_length_unit_evidence=False,
    )

    assert rows == ()
    assert _codes(diagnostics) == {"GEOMETRY_UNIT_NOT_PROVEN_MM"}


def test_native_numeric_without_unit_live_required_path_reports_missing_evidence():
    rows, diagnostics = resolve_geometry_rows_from_accepted_mapping(
        assignment_rows=_assignment_rows(),
        property_rows=_property_rows(width=0.4, depth=0.7),
        length_unit_evidence=None,
        require_length_unit_evidence=True,
    )

    assert rows == ()
    assert _codes(diagnostics) == {"GEOMETRY_UNIT_EVIDENCE_MISSING"}


def test_feature_evidence_preserves_raw_value_unit_factor_and_normalized_value(tmp_path: Path):
    provider = AcceptedMappingGeometryRowProvider(
        assignment_rows=_assignment_rows(),
        property_rows=_property_rows(width="0.4", depth="0.7"),
        component_type_rows=_component_type_rows(),
        length_unit_evidence=_unit_evidence("m"),
        require_length_unit_evidence=True,
    )

    result = probe_geometry_feature_snapshots(provider=provider, output_dir=tmp_path)
    payload = json.loads((tmp_path / "feature_snapshot.json").read_text(encoding="utf-8"))
    evidence = payload["snapshots"][0]["features"]["beam_width_mm"]["evidence"][0]
    source_row = evidence["source_row"]

    assert result.status == "OK"
    assert evidence["raw_value"] == "0.4"
    assert evidence["normalized_value"] == 400.0
    assert source_row["raw_value"] == "0.4"
    assert source_row["raw_value_type"] == "str"
    assert source_row["parsed_value"] == 0.4
    assert source_row["source_unit"] == "m"
    assert source_row["target_unit"] == "mm"
    assert source_row["normalization_factor_to_mm"] == 1000.0
    assert source_row["normalized_value"] == 400.0
    assert source_row["normalized_unit"] == "mm"
    assert source_row["present_units_raw"] == [4, 6, 2, 0]
    assert source_row["database_units_raw"] == [4, 6, 2, 0]
    assert source_row["source_table"] == PROPERTY_TABLE
    assert source_row["source_column"] == "t2"


@pytest.mark.parametrize("bad_value", ["0.4 m", "400mm", "", None])
def test_non_plain_numeric_strings_are_rejected(bad_value: object):
    rows, diagnostics = resolve_geometry_rows_from_accepted_mapping(
        assignment_rows=_assignment_rows(),
        property_rows=_property_rows(width=bad_value, depth="0.7"),
        length_unit_evidence=_unit_evidence("m"),
        require_length_unit_evidence=True,
    )

    assert rows == ()
    assert "GEOMETRY_DIMENSION_VALUE_NOT_NUMERIC" in _codes(diagnostics)


def test_missing_runtime_unit_evidence_blocks_numeric_string_normalization():
    rows, diagnostics = resolve_geometry_rows_from_accepted_mapping(
        assignment_rows=_assignment_rows(),
        property_rows=_property_rows(width="0.4", depth="0.7"),
        length_unit_evidence=None,
        require_length_unit_evidence=True,
    )

    assert rows == ()
    assert "GEOMETRY_UNIT_EVIDENCE_MISSING" in _codes(diagnostics)


def test_unknown_length_enum_reports_unsupported_unit():
    evidence = LiveEtabsLengthUnitEvidence(
        present_force_unit="kN",
        present_length_unit="",
        present_temperature_unit="C",
        database_force_unit="kN",
        database_length_unit="m",
        database_temperature_unit="C",
        present_units_raw=(4, 99, 2, 0),
        database_units_raw=(4, 6, 2, 0),
    )
    rows, diagnostics = resolve_geometry_rows_from_accepted_mapping(
        assignment_rows=_assignment_rows(),
        property_rows=_property_rows(width="0.4", depth="0.7"),
        length_unit_evidence=evidence,
        require_length_unit_evidence=True,
    )

    assert rows == ()
    assert "GEOMETRY_UNIT_NORMALIZATION_UNSUPPORTED" in _codes(diagnostics)


def test_unsupported_explicit_component_type_does_not_emit_join_not_found(tmp_path: Path):
    assignment_rows = (
        {"Story": "+14.5", "Label": "BR1", "UniqueName": "297", "SectProp": "SEC"},
        {"Story": "+14.5", "Label": "B1", "UniqueName": "301", "SectProp": "SEC"},
    )
    component_type_rows = (
        {"UniqueName": "297", "Type": "Brace"},
        {"UniqueName": "301", "Type": "Beam"},
    )
    provider = AcceptedMappingGeometryRowProvider(
        assignment_rows=assignment_rows,
        property_rows=_property_rows(),
        component_type_rows=component_type_rows,
        length_unit_evidence=_unit_evidence("m"),
        require_length_unit_evidence=True,
    )

    result = probe_geometry_feature_snapshots(provider=provider, output_dir=tmp_path)
    diagnostics = tuple(provider.iter_geometry_diagnostics())

    assert result.status == "OK"
    assert result.snapshot_count == 1
    assert "COMPONENT_TYPE_VALUE_UNSUPPORTED" not in _codes(diagnostics)
    assert "COMPONENT_TYPE_JOIN_NOT_FOUND" not in _codes(diagnostics)


def test_direct_beam_aliases_resolve_and_preserve_raw_provenance(tmp_path: Path):
    provider = MappingGeometryRowProvider(
        (
            {
                "component_type": "beam",
                "component_id": "B1",
                "beam_width_mm": 400.0,
                "beam_depth_mm": 700.0,
                "beam_width_mm_unit": "mm",
                "beam_depth_mm_unit": "mm",
                "beam_width_mm_source_column": "BeamWidthFixture",
                "beam_depth_mm_source_column": "BeamDepthFixture",
                "source_table": "direct_fixture",
            },
        )
    )

    result = probe_geometry_feature_snapshots(provider=provider, output_dir=tmp_path)
    payload = json.loads((tmp_path / "feature_snapshot.json").read_text(encoding="utf-8"))
    features = payload["snapshots"][0]["features"]
    width_evidence = features["beam_width_mm"]["evidence"][0]
    depth_evidence = features["beam_depth_mm"]["evidence"][0]

    assert result.status == "OK"
    assert features["beam_width_mm"]["status"] == "RESOLVED"
    assert features["beam_depth_mm"]["status"] == "RESOLVED"
    assert features["beam_width_mm"]["value"] == 400.0
    assert features["beam_depth_mm"]["value"] == 700.0
    assert width_evidence["source_column"] == "BeamWidthFixture"
    assert depth_evidence["source_column"] == "BeamDepthFixture"
    assert width_evidence["raw_value"] == 400.0
    assert depth_evidence["raw_value"] == 700.0


def test_direct_column_aliases_resolve(tmp_path: Path):
    provider = MappingGeometryRowProvider(
        (
            {
                "component_type": "column",
                "component_id": "C1",
                "column_width_mm": 500.0,
                "column_depth_mm": 600.0,
                "unit": "mm",
                "source_table": "direct_fixture",
            },
        )
    )

    result = probe_geometry_feature_snapshots(provider=provider, output_dir=tmp_path)
    payload = json.loads((tmp_path / "feature_snapshot.json").read_text(encoding="utf-8"))
    features = payload["snapshots"][0]["features"]

    assert result.status == "OK"
    assert features["column_width_mm"]["value"] == 500.0
    assert features["column_depth_mm"]["value"] == 600.0
    assert features["column_width_mm"]["evidence"][0]["source_column"] == "column_width_mm"
    assert features["column_depth_mm"]["evidence"][0]["source_column"] == "column_depth_mm"


def test_direct_provider_cm_unit_remains_partial_without_conversion(tmp_path: Path):
    provider = MappingGeometryRowProvider(
        (
            {
                "component_type": "beam",
                "component_id": "B1",
                "beam_width_mm": 40.0,
                "beam_depth_mm": 70.0,
                "unit": "cm",
                "source_table": "direct_fixture",
            },
        )
    )

    result = probe_geometry_feature_snapshots(provider=provider, output_dir=tmp_path)
    payload = json.loads((tmp_path / "feature_snapshot.json").read_text(encoding="utf-8"))
    diagnostics = json.loads((tmp_path / "live_geometry_probe_diagnostics.json").read_text(encoding="utf-8"))
    features = payload["snapshots"][0]["features"]

    assert result.status == "PARTIAL"
    assert features["beam_width_mm"]["status"] == "PARTIAL"
    assert features["beam_depth_mm"]["status"] == "PARTIAL"
    assert features["beam_width_mm"]["unit"] == "cm"
    assert features["beam_depth_mm"]["unit"] == "cm"
    assert {item["code"] for item in diagnostics} == {"GEOMETRY_UNIT_NOT_MM"}


def test_attach_failure_summary_retains_stable_p3_fields(tmp_path: Path):
    attach_result = EtabsAttachResult(
        status="FAILED",
        strategy=None,
        etabs_object=None,
        sap_model=None,
        attempts=(
            EtabsAttachAttempt(
                strategy="comtypes_get_active_object_etabs_api_object",
                status="FAILED",
                message="No running ETABS instance",
                prog_id="CSI.ETABS.API.ETABSObject",
            ),
        ),
    )

    result = write_com_attach_failure_probe_outputs(output_dir=tmp_path, attach_result=attach_result)
    summary = json.loads((tmp_path / "live_geometry_probe_summary.json").read_text(encoding="utf-8"))

    assert result.status == "FAIL"
    assert summary == {
        "assignment_table_row_count": 0,
        "blocking_diagnostic_count": 1,
        "component_type_resolved_row_count": 0,
        "component_type_source_row_count": 0,
        "component_type_source_status": "NOT_ATTEMPTED",
        "component_type_source_table": None,
        "component_type_unresolved_row_count": 0,
        "diagnostic_count": 1,
        "failure_stage": "COM_ATTACH",
        "feature_snapshot_written": False,
        "population_blocked_row_count": 0,
        "population_disposition_counts": {"BLOCKED": 0, "IN_SCOPE": 0, "OUT_OF_SCOPE": 0},
        "population_in_scope_row_count": 0,
        "population_out_of_scope_row_count": 0,
        "population_reason_counts": {},
        "population_source_row_count": 0,
        "property_table_row_count": 0,
        "resolved_geometry_row_count": 0,
        "scope": "LIVE_ETABS_GEOMETRY_FEATURE_SNAPSHOT_PROBE",
        "status": "FAIL",
        "warning_diagnostic_count": 0,
    }


class _FakeDatabaseTables:
    def __init__(self, payloads):
        self.payloads = dict(payloads)

    def GetTableForDisplayArray(self, table_key, *_args):
        return self.payloads[table_key]


def _attached_result(sap_model) -> EtabsAttachResult:
    return EtabsAttachResult(
        status="ATTACHED",
        strategy="comtypes_get_active_object_etabs_api_object",
        etabs_object=object(),
        sap_model=sap_model,
        attempts=(
            EtabsAttachAttempt(
                strategy="comtypes_get_active_object_etabs_api_object",
                status="SUCCESS",
                message="Attached fake ETABS for tests",
                prog_id="CSI.ETABS.API.ETABSObject",
            ),
        ),
    )


def _display_payloads():
    return {
        ASSIGNMENT_TABLE: (0, ASSIGNMENT_COLUMNS, ["+14.5", "B1", "297", "Rectangular", "No", "SEC"]),
        PROPERTY_TABLE: (0, PROPERTY_COLUMNS, ["SEC", "0.4", "0.7", "Beam"]),
        COMPONENT_TYPE_TABLE: (0, COMPONENT_TYPE_COLUMNS, ["+14.5", "B1", "297", "Beam"]),
    }


def test_live_provider_reads_present_units_2_for_display_table_numeric_strings(tmp_path: Path):
    sap_model = SimpleNamespace(
        DatabaseTables=_FakeDatabaseTables(_display_payloads()),
        GetPresentUnits_2=lambda: (4, 6, 2, 0),
        GetDatabaseUnits_2=lambda: (4, 6, 2, 0),
    )
    provider = create_live_etabs_geometry_provider(attach_result=_attached_result(sap_model), max_candidate_tables=1)

    result = probe_geometry_feature_snapshots(provider=provider, output_dir=tmp_path)
    payload = json.loads((tmp_path / "feature_snapshot.json").read_text(encoding="utf-8"))
    beam = payload["snapshots"][0]

    assert result.status == "OK"
    assert beam["features"]["beam_width_mm"]["value"] == 400.0
    assert beam["features"]["beam_depth_mm"]["value"] == 700.0


def test_missing_get_present_units_2_reports_missing_unit(tmp_path: Path):
    sap_model = SimpleNamespace(DatabaseTables=_FakeDatabaseTables(_display_payloads()))
    provider = create_live_etabs_geometry_provider(attach_result=_attached_result(sap_model), max_candidate_tables=1)

    result = probe_geometry_feature_snapshots(provider=provider, output_dir=tmp_path)

    assert result.status == "FAIL"
    assert "GEOMETRY_UNIT_EVIDENCE_MISSING" in _codes(provider.iter_geometry_diagnostics())


def test_nonzero_present_unit_return_code_reports_missing_unit(tmp_path: Path):
    sap_model = SimpleNamespace(
        DatabaseTables=_FakeDatabaseTables(_display_payloads()),
        GetPresentUnits_2=lambda: (4, 6, 2, 1),
        GetDatabaseUnits_2=lambda: (4, 6, 2, 0),
    )
    provider = create_live_etabs_geometry_provider(attach_result=_attached_result(sap_model), max_candidate_tables=1)

    result = probe_geometry_feature_snapshots(provider=provider, output_dir=tmp_path)

    assert result.status == "FAIL"
    assert "GEOMETRY_UNIT_EVIDENCE_MISSING" in _codes(provider.iter_geometry_diagnostics())


def test_section_name_only_is_not_parsed_for_dimensions():
    rows, diagnostics = resolve_geometry_rows_from_accepted_mapping(
        assignment_rows=_assignment_rows(section_name="B40x70"),
        property_rows=_property_rows(width=None, depth=None, section_name="B40x70"),
        length_unit_evidence=_unit_evidence("m"),
        require_length_unit_evidence=True,
    )

    assert rows == ()
    assert "GEOMETRY_DIMENSION_VALUE_NOT_NUMERIC" in _codes(diagnostics)
