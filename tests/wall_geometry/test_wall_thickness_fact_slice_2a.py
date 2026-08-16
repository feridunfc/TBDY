from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from tbdy_engine.canonical_tables.table import CanonicalTable
from tbdy_engine.contracts.models import ContractBundle
from tbdy_engine.features.resolver.wall_thickness import WallThicknessFeatureResolver
from tbdy_engine.features.value import FeatureValueStatus
from tbdy_engine.features.wall_inventory import (
    WallInventoryRecord,
    WallInventoryStatus,
    build_wall_inventory,
)

ROOT = Path(__file__).resolve().parents[2]
PROPERTY_NAME = "BsmntWall_40cm"


def contract_bundle() -> ContractBundle:
    catalogs = {}
    for name in ("feature_catalog.yaml", "table_registry.yaml"):
        catalogs[name] = yaml.safe_load(
            (ROOT / "tbdy_engine" / "catalogs" / name).read_text(encoding="utf-8")
        )
    return ContractBundle.from_raw(
        catalog_dir=str(ROOT / "tbdy_engine" / "catalogs"),
        catalogs=catalogs,
        schemas={},
        examples={},
    )


def wall_property_row(
    *,
    name: str = PROPERTY_NAME,
    thickness: object = "0.4",
) -> dict[str, object]:
    return {
        "Name": name,
        "ModelType": "Shell-Thin",
        "Material": "C35/45",
        "Thickness": thickness,
    }


def wall_property_table(
    *,
    length_unit: str | None,
    status: str = "RESOLVED",
    thickness: object = "0.4",
    property_name: str = PROPERTY_NAME,
) -> CanonicalTable:
    units = {
        "unit_context_source": "fixture_etabs_present_units",
        "force_unit": "kN",
        "length_unit": length_unit,
        "temperature_unit": "C",
        "unit_query_status": status,
        "unit_query_succeeded": status == "RESOLVED",
        "unit_basis_confidence": "high" if status == "RESOLVED" else "low",
    }
    return CanonicalTable(
        table_key="wall_section_properties",
        actual_table_name="Wall Property Definitions - Specified",
        columns=("Name", "ModelType", "Material", "Thickness"),
        rows=(wall_property_row(name=property_name, thickness=thickness),),
        units=units,
        source="FAKE_ETABS_TABLE_CLIENT",
    )


def area(unique: str, *, prop: str = PROPERTY_NAME, label: str | None = None):
    return {
        "UniqueName": unique,
        "Story": "Story 1",
        "Label": label or f"W-{unique}",
        "SectionProperty": prop,
        "PropertyType": "Wall",
    }


def inventory_for_rows(rows):
    return build_wall_inventory(
        model_fingerprint="MODEL-1",
        area_assignment_rows=rows,
        wall_property_rows=(wall_property_row(),),
        pier_assignment_rows=(),
    )


def resolve_one(
    *,
    length_unit: str | None,
    thickness: object = "0.4",
    status: str = "RESOLVED",
    external_unit_context=None,
):
    inventory = inventory_for_rows((area("A1"),))
    resolver = WallThicknessFeatureResolver(
        contract_bundle(),
        wall_property_table(
            length_unit=length_unit,
            status=status,
            thickness=thickness,
        ),
        external_unit_context=external_unit_context,
    )
    snapshot = resolver.build_snapshots(inventory)[0]
    return snapshot, snapshot.features["wall_thickness_mm"]


def resolved_external(length_unit: str):
    return {
        "source": "explicit_test_context",
        "force_unit": "kN",
        "length_unit": length_unit,
        "temperature_unit": "C",
        "unit_query_status": "RESOLVED",
        "unit_query_succeeded": True,
        "unit_basis_confidence": "high",
    }


def test_live_style_04_metres_resolves_to_400_mm_from_source_table_units():
    snapshot, feature = resolve_one(length_unit="m", thickness="0.4")
    assert feature.status == FeatureValueStatus.RESOLVED
    assert feature.value == pytest.approx(400.0)
    assert feature.unit == "mm"
    evidence = feature.evidence[0]
    assert evidence.raw_value == "0.4"
    assert evidence.normalized_value == pytest.approx(400.0)
    assert evidence.source_column == "Thickness"
    assert evidence.source_row["source_unit_authority"] == "CanonicalTable.units"
    assert evidence.source_row["source_unit_context"]["length_unit"] == "m"
    assert snapshot.component_id == snapshot.identity["wall_object_id"]


def test_live_style_04_centimetres_resolves_to_4_mm():
    _, feature = resolve_one(length_unit="cm", thickness="0.4")
    assert feature.status == FeatureValueStatus.RESOLVED
    assert feature.value == pytest.approx(4.0)


def test_live_style_04_millimetres_resolves_to_04_mm():
    _, feature = resolve_one(length_unit="mm", thickness="0.4")
    assert feature.status == FeatureValueStatus.RESOLVED
    assert feature.value == pytest.approx(0.4)


def test_live_style_03_metres_resolves_to_300_mm():
    _, feature = resolve_one(length_unit="m", thickness="0.3")
    assert feature.value == pytest.approx(300.0)


def test_conversion_is_unit_context_driven_not_magnitude_driven():
    _, metres = resolve_one(length_unit="m", thickness="40")
    _, millimetres = resolve_one(length_unit="mm", thickness="0.4")
    assert metres.value == pytest.approx(40000.0)
    assert millimetres.value == pytest.approx(0.4)


def test_untrusted_source_table_unit_context_is_partial_and_never_guesses():
    _, feature = resolve_one(length_unit="m", thickness="0.4", status="PARTIAL")
    assert feature.status == FeatureValueStatus.PARTIAL
    assert feature.value is None
    assert feature.evidence[0].raw_value == "0.4"
    assert feature.evidence[0].normalized_value is None


def test_missing_source_table_unit_context_is_partial_and_never_guesses():
    _, feature = resolve_one(length_unit=None, thickness="0.4", status="MISSING")
    assert feature.status == FeatureValueStatus.PARTIAL
    assert feature.value is None


def test_conflicting_external_context_cannot_override_source_table_context():
    _, feature = resolve_one(
        length_unit="m",
        thickness="0.4",
        external_unit_context=resolved_external("mm"),
    )
    assert feature.status == FeatureValueStatus.PARTIAL
    assert feature.value is None
    payload = feature.evidence[0].source_row
    assert payload["source_unit_context"]["length_unit"] == "m"
    assert payload["external_unit_context"]["length_unit"] == "mm"
    assert "length_unit" in payload["unit_context_mismatches"]


def test_resolved_external_context_cannot_bypass_partial_source_table_context():
    _, feature = resolve_one(
        length_unit="m",
        thickness="0.4",
        status="PARTIAL",
        external_unit_context=resolved_external("m"),
    )
    assert feature.status == FeatureValueStatus.PARTIAL
    assert feature.value is None
    assert feature.evidence[0].source_row["source_unit_context"]["unit_query_status"] == "PARTIAL"


def test_matching_external_context_is_only_validation_not_authority():
    _, feature = resolve_one(
        length_unit="m",
        thickness="0.4",
        external_unit_context=resolved_external("m"),
    )
    assert feature.status == FeatureValueStatus.RESOLVED
    assert feature.value == pytest.approx(400.0)
    evidence = feature.evidence[0].source_row
    assert evidence["source_unit_authority"] == "CanonicalTable.units"
    assert evidence["external_unit_context_validation"] == "MATCHED_SOURCE_TABLE"


def test_exact_property_identity_is_case_sensitive_and_not_rewritten():
    inventory = inventory_for_rows((area("A1"),))
    resolver = WallThicknessFeatureResolver(
        contract_bundle(),
        wall_property_table(length_unit="m", property_name=PROPERTY_NAME.lower()),
    )
    feature = resolver.build_snapshots(inventory)[0].features["wall_thickness_mm"]
    assert feature.status == FeatureValueStatus.MISSING
    assert feature.value is None


def test_many_walls_sharing_one_property_remain_distinct_wall_objects():
    rows = tuple(area(f"A{i:03d}") for i in range(46))
    inventory = inventory_for_rows(rows)
    resolver = WallThicknessFeatureResolver(
        contract_bundle(),
        wall_property_table(length_unit="m"),
    )
    snapshots = resolver.build_snapshots(inventory)
    assert len(snapshots) == 46
    assert len({snapshot.component_id for snapshot in snapshots}) == 46
    assert all(snapshot.features["wall_thickness_mm"].value == pytest.approx(400.0)
               for snapshot in snapshots)
    assert {snapshot.identity["assigned_wall_property"] for snapshot in snapshots} == {PROPERTY_NAME}


def test_missing_property_assignment_does_not_fabricate_thickness():
    record = WallInventoryRecord(
        wall_object_id="wall-area:abc",
        anonymous_inventory_record_id=None,
        model_fingerprint="MODEL-1",
        etabs_area_unique_name="A1",
        area_label="W1",
        story="Story 1",
        assigned_area_property=None,
        material_reference=None,
        pier_assignment=None,
        classification_status=WallInventoryStatus.STRUCTURAL_WALL_CANDIDATE,
        classification_evidence=(),
        source_row_references=(),
        diagnostics=(),
    )
    resolver = WallThicknessFeatureResolver(
        contract_bundle(),
        wall_property_table(length_unit="m"),
    )
    feature = resolver.resolve_candidate(record).features["wall_thickness_mm"]
    assert feature.status == FeatureValueStatus.MISSING
    assert feature.value is None


def test_unmatched_property_does_not_fabricate_thickness():
    record = WallInventoryRecord(
        wall_object_id="wall-area:abc",
        anonymous_inventory_record_id=None,
        model_fingerprint="MODEL-1",
        etabs_area_unique_name="A1",
        area_label="W1",
        story="Story 1",
        assigned_area_property="UNKNOWN_WALL_PROPERTY",
        material_reference=None,
        pier_assignment=None,
        classification_status=WallInventoryStatus.STRUCTURAL_WALL_CANDIDATE,
        classification_evidence=(),
        source_row_references=(),
        diagnostics=(),
    )
    resolver = WallThicknessFeatureResolver(
        contract_bundle(),
        wall_property_table(length_unit="m"),
    )
    feature = resolver.resolve_candidate(record).features["wall_thickness_mm"]
    assert feature.status == FeatureValueStatus.MISSING
    assert feature.value is None


def test_slice_output_contains_no_regulatory_verdict_or_applicability_semantics():
    snapshot, _ = resolve_one(length_unit="m", thickness="0.4")
    text = repr(snapshot.as_dict())
    for token in ("'PASS'", "'FAIL'", "TBDY", "applicability", "250 mm", "h/16", "h/20", "lw/30"):
        assert token not in text


def test_existing_wall_thickness_feature_and_live_source_contract_are_reused():
    feature_catalog = yaml.safe_load(
        (ROOT / "tbdy_engine/catalogs/feature_catalog.yaml").read_text(encoding="utf-8")
    )
    feature = feature_catalog["features"]["wall_thickness_mm"]
    assert feature["unit"] == "mm"
    assert feature["source"]["table_key"] == "wall_section_data"
    assert "Thickness" in feature["source"]["field_aliases"]
    assert feature["unit_policy"]["source_unit"] == "ETABS_PRESENT_LENGTH"
    assert feature["unit_policy"]["target_unit"] == "mm"

    source_contract = yaml.safe_load(
        (ROOT / "tbdy_engine/catalogs/etabs_feature_source_contract.yaml").read_text(encoding="utf-8")
    )
    wall = next(
        row for row in source_contract["sources"]
        if row["feature_id"] == "wall_thickness_mm"
    )
    assert wall["etabs_table_name"] == "Wall Property Definitions - Specified"
    assert wall["table_registry_key"] == "wall_section_properties"
    assert wall["column"] == "Thickness"
    assert "Thickness" in wall["required_columns"]
    assert wall["evidence_status"] == "VERIFIED_LIVE"
    assert wall["check_unlock_allowed"] is False
    assert wall["unit_expectation"]["unit"] == "ETABS_PRESENT_LENGTH"
    assert wall["unit_normalization"]["target_unit"] == "mm"
