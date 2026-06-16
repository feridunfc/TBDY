
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CATALOGS = ROOT / "tbdy_engine" / "catalogs"


def load_yaml(name: str):
    return yaml.safe_load((CATALOGS / name).read_text(encoding="utf-8"))


def tables():
    return load_yaml("table_registry.yaml")["tables"]


def source_metadata():
    return load_yaml("etabs_feature_source_contract.yaml")["metadata"]


def test_material_properties_promoted_source_contract_exists():
    material = tables()["material_properties"]
    assert material["evidence_status"] == "VERIFIED_LIVE"
    assert material["verified_by"]["sprint"] == "C13.2-P3"
    assert material["verified_by"]["live_probe"] is True
    assert material["check_unlock_allowed"] is False
    assert material["safe_to_implement_checks_now"] is False
    assert "Material Properties - Basic Mechanical Properties" in material["live_table_names"]
    assert "Material Properties - Concrete Data" in material["live_table_names"]
    assert "Material Properties - Rebar Data" in material["live_table_names"]
    assert set(material["required_columns"]) >= {"Material", "E1", "G12", "U12"}
    assert set(material["must_not_use"]) >= {
        "Material List by Story",
        "Material List by Object Type",
        "Material List by Section Prop",
    }


def test_story_definitions_promoted_with_plural_and_singular_aliases():
    story = tables()["story_definitions"]
    assert story["evidence_status"] == "VERIFIED_LIVE"
    assert story["check_unlock_allowed"] is False
    assert "Story Definitions" in story["live_table_names"]
    assert "Tower and Base Story Definitions" in story["live_table_names"]
    assert "Tower and Base Story Definition" in story["excel_inventory_aliases"]
    assert "Tower and Base Story Definition" in story["backward_compatibility_aliases"]


def test_story_definitions_derived_elevation_policy_is_stable_contract_metadata():
    story = tables()["story_definitions"]
    assert story["derived_elevation_supported"] is True
    assert story["elevation_is_direct_column"] is False
    assert story["base_elevation_column"] == "BSElev"
    assert story["tower_and_base_story_definition_table"] == "Tower and Base Story Definitions"
    assert set(story["required_columns"]) >= {"Story", "Height", "BSElev"}


def test_pier_section_properties_promoted_direct_geometry_without_section_column_requirement():
    pier = tables()["pier_section_properties"]
    assert pier["evidence_status"] == "VERIFIED_LIVE"
    assert pier["check_unlock_allowed"] is False
    assert pier["direct_section_geometry_present"] is True
    assert pier["section_name_column_required"] is False
    assert pier["section_name_column_present"] is False
    assert pier["material_present"] is True
    assert set(pier["required_columns"]) >= {"Story", "Pier", "Width", "Thickness", "Material"}
    assert "Section" not in set(pier["required_columns"])


def test_pier_section_supporting_context_tables_are_recorded_but_do_not_unlock_checks():
    registry = tables()
    pier = registry["pier_section_properties"]
    assert "Wall Bays" in pier["supporting_context_tables"]
    assert "Wall Object Connectivity" in pier["supporting_context_tables"]
    assert registry["wall_bays"]["check_unlock_allowed"] is False
    assert registry["wall_object_connectivity"]["check_unlock_allowed"] is False
    assert registry["wall_bays"]["evidence_status"] == "VERIFIED_LIVE"
    assert registry["wall_object_connectivity"]["evidence_status"] == "VERIFIED_LIVE"


def test_feature_family_map_contains_promoted_source_families_and_keeps_locks():
    families = load_yaml("feature_family_map.yaml")["feature_families"]
    for key in [
        "material_properties_promoted",
        "story_definition_metadata_promoted",
        "pier_section_geometry_promoted",
    ]:
        assert families[key]["evidence_status"] == "VERIFIED_LIVE"
        assert families[key]["check_unlock_allowed"] is False
        assert families[key]["safe_to_implement_checks_now"] is False


def test_feature_source_contract_metadata_records_p4_promotion_without_new_feature_ids():
    metadata = source_metadata()
    promoted = metadata["p4_promoted_source_contracts"]
    assert set(promoted) == {"material_properties", "story_definitions", "pier_section_properties"}
    assert promoted["story_definitions"]["derived_elevation_supported"] is True
    assert promoted["story_definitions"]["elevation_is_direct_column"] is False
    assert promoted["story_definitions"]["base_elevation_column"] == "BSElev"
    assert promoted["pier_section_properties"]["direct_section_geometry_present"] is True
    for row in promoted.values():
        assert row["check_unlock_allowed"] is False
        assert row["safe_to_implement_checks_now"] is False


def test_all_promoted_families_keep_safe_to_implement_checks_false():
    for key in ["material_properties", "story_definitions", "pier_section_properties", "wall_bays", "wall_object_connectivity"]:
        entry = tables()[key]
        assert entry["check_unlock_allowed"] is False
        assert entry["safe_to_implement_checks_now"] is False


def test_promoted_sources_do_not_touch_runtime_check_or_report_logic():
    manifest = (ROOT / "c13_2_p4_changed_files.txt").read_text(encoding="utf-8")
    forbidden = [
        "tbdy_engine/features/resolver/live_smoke.py",
        "tbdy_engine/checks/engine.py",
        "tbdy_engine/catalogs/check_catalog.yaml",
        "tools/render_product_report.py",
        "apps/",
        "runtime/",
        "archx/",
        "runner_v2/",
    ]
    for item in forbidden:
        assert item not in manifest


def test_no_excel_production_path_is_introduced():
    registry = tables()
    for entry in registry.values():
        assert entry.get("source_type") != "excel_production"
        assert entry.get("excel_production_input") is not True
    sources = load_yaml("etabs_feature_source_contract.yaml")["sources"]
    for source in sources:
        assert source.get("source_type") != "excel_production"
    for path in [
        CATALOGS / "table_registry.yaml",
        CATALOGS / "etabs_feature_source_contract.yaml",
        CATALOGS / "feature_family_map.yaml",
    ]:
        text = path.read_text(encoding="utf-8").lower()
        assert "excel production input: true" not in text
        assert "excel_production_input: true" not in text


def test_contract_validator_passes():
    result = subprocess.run(
        [sys.executable, "-m", "tbdy_engine.tools.validate_contract_constitution"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
