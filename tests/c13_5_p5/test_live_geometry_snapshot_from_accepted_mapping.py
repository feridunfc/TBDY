from __future__ import annotations

import json
from pathlib import Path

from tbdy_engine.features.live_etabs_geometry_probe import (
    AcceptedGeometryMapping,
    AcceptedMappingGeometryRowProvider,
    DEFAULT_ACCEPTED_GEOMETRY_MAPPING,
    load_accepted_mapping_provider_from_json,
    probe_geometry_feature_snapshots,
    resolve_geometry_rows_from_accepted_mapping,
)
from tools import probe_live_etabs_geometry_snapshot as live_probe_cli
from tools import run_geometry_product_smoke as product_smoke_cli

ROOT = Path(__file__).resolve().parents[2]
ASSIGNMENT_FIXTURE = ROOT / "tests" / "fixtures" / "c13_5_p5" / "fake_assignment_rows.json"
PROPERTY_FIXTURE = ROOT / "tests" / "fixtures" / "c13_5_p5" / "fake_property_definition_rows.json"


def _load_fixture_provider() -> AcceptedMappingGeometryRowProvider:
    return load_accepted_mapping_provider_from_json(
        assignment_rows_path=ASSIGNMENT_FIXTURE,
        property_rows_path=PROPERTY_FIXTURE,
    )


def test_module_imports_without_etabs():
    assert DEFAULT_ACCEPTED_GEOMETRY_MAPPING.property_table_key == "Frame Section Property Definitions - Concrete Rectangular"


def test_accepted_mapping_contract_is_immutable_and_explicit():
    mapping = DEFAULT_ACCEPTED_GEOMETRY_MAPPING

    assert mapping == AcceptedGeometryMapping(
        assignment_table_key="Frame Assignments - Section Properties",
        assignment_section_column="SectProp",
        property_table_key="Frame Section Property Definitions - Concrete Rectangular",
        property_name_column="Name",
        width_column="t2",
        depth_column="t3",
        mapping_basis="explicit_columns_only",
    )
    try:
        mapping.width_column = "Width"  # type: ignore[misc]
    except Exception as exc:
        assert exc.__class__.__name__ in {"FrozenInstanceError", "AttributeError"}
    else:  # pragma: no cover - dataclass(frozen=True) must prevent mutation.
        raise AssertionError("AcceptedGeometryMapping must be immutable")


def test_fake_assignment_and_property_rows_join_by_sectprop_to_name():
    provider = _load_fixture_provider()

    rows = tuple(provider.iter_geometry_rows())
    diagnostics = tuple(provider.iter_geometry_diagnostics())

    assert diagnostics == ()
    assert len(rows) == 2
    assert rows[0]["section_name"] == "B40x70"
    assert rows[0]["width_mm"] == 400.0
    assert rows[0]["depth_mm"] == 700.0
    assert rows[1]["section_name"] == "C50x60"
    assert rows[1]["width_mm"] == 500.0
    assert rows[1]["depth_mm"] == 600.0


def test_t2_t3_produce_width_depth_feature_values(tmp_path: Path):
    result = probe_geometry_feature_snapshots(provider=_load_fixture_provider(), output_dir=tmp_path)
    payload = json.loads((tmp_path / "feature_snapshot.json").read_text(encoding="utf-8"))

    assert result.status == "OK"
    assert result.snapshot_count == 2
    beam = next(snapshot for snapshot in payload["snapshots"] if snapshot["component_type"] == "beam")
    column = next(snapshot for snapshot in payload["snapshots"] if snapshot["component_type"] == "column")

    assert beam["features"]["beam_width_mm"]["value"] == 400.0
    assert beam["features"]["beam_depth_mm"]["value"] == 700.0
    assert column["features"]["column_width_mm"]["value"] == 500.0
    assert column["features"]["column_depth_mm"]["value"] == 600.0


def test_source_evidence_contains_assignment_and_property_table_provenance(tmp_path: Path):
    probe_geometry_feature_snapshots(provider=_load_fixture_provider(), output_dir=tmp_path)
    payload = json.loads((tmp_path / "feature_snapshot.json").read_text(encoding="utf-8"))
    beam = next(snapshot for snapshot in payload["snapshots"] if snapshot["component_type"] == "beam")
    evidence = beam["features"]["beam_width_mm"]["evidence"][0]
    source_row = evidence["source_row"]

    assert evidence["source_table"] == "Frame Section Property Definitions - Concrete Rectangular"
    assert evidence["source_column"] == "t2"
    assert source_row["source_table_assignment"] == "Frame Assignments - Section Properties"
    assert source_row["source_table_property"] == "Frame Section Property Definitions - Concrete Rectangular"
    assert source_row["assignment_section_column"] == "SectProp"
    assert source_row["property_name_column"] == "Name"
    assert source_row["width_column"] == "t2"
    assert source_row["depth_column"] == "t3"
    assert source_row["story"] == "+14.5"
    assert source_row["label"] == "B1"
    assert source_row["unique_name"] == "297"
    assert source_row["section_name"] == "B40x70"
    assert source_row["mapping_basis"] == "explicit_columns_only"


def test_cli_fake_accepted_mapping_fixture_writes_feature_snapshot(tmp_path: Path, capsys):
    exit_code = live_probe_cli.main(
        [
            "--live-etabs",
            "--out",
            str(tmp_path),
            "--fake-assignment-rows-fixture",
            str(ASSIGNMENT_FIXTURE),
            "--fake-property-definition-rows-fixture",
            str(PROPERTY_FIXTURE),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Live geometry probe: OK" in captured.out
    assert "Snapshots: 2" in captured.out
    assert (tmp_path / "feature_snapshot.json").exists()


def test_product_smoke_can_consume_fake_feature_snapshot(tmp_path: Path, capsys):
    probe_out = tmp_path / "probe"
    smoke_out = tmp_path / "smoke"
    probe_geometry_feature_snapshots(provider=_load_fixture_provider(), output_dir=probe_out)

    exit_code = product_smoke_cli.main(
        [
            "--feature-snapshot",
            str(probe_out / "feature_snapshot.json"),
            "--out",
            str(smoke_out),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Geometry product smoke: OK" in captured.out


def test_resolver_returns_no_diagnostics_for_valid_fixture():
    assignment_payload = json.loads(ASSIGNMENT_FIXTURE.read_text(encoding="utf-8"))
    property_payload = json.loads(PROPERTY_FIXTURE.read_text(encoding="utf-8"))

    rows, diagnostics = resolve_geometry_rows_from_accepted_mapping(
        assignment_rows=assignment_payload["rows"],
        property_rows=property_payload["rows"],
        mapping=DEFAULT_ACCEPTED_GEOMETRY_MAPPING,
    )

    assert len(rows) == 2
    assert diagnostics == ()
