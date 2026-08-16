from __future__ import annotations

from pathlib import Path

import yaml

from tbdy_engine.checks.wall_contract import PACK_C_CHECK_IDS
from tbdy_engine.providers.table_registry import TableRegistry

ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "tbdy_engine/catalogs/check_catalog_p2_10_wall_pack_c.yaml"


def _status(item):
    return item.get("evidence_status") or item.get("source_contract_status")


def test_pack_c_reuses_only_existing_live_promoted_geometry_identity_sources():
    registry = TableRegistry.from_catalog_dir(ROOT / "tbdy_engine/catalogs")
    for key in (
        "pier_section_properties",
        "story_definitions",
        "area_assignments_summary",
        "pier_assignments",
    ):
        assert key in registry.tables
        assert _status(registry.tables[key]) == "VERIFIED_LIVE"
    pier = registry.tables["pier_section_properties"]
    columns = set(pier.get("required_columns") or pier.get("columns") or ())
    assert {"Story", "Pier", "Width", "Thickness"}.issubset(columns)
    story = registry.tables["story_definitions"]
    story_columns = set(story.get("required_columns") or story.get("columns") or ())
    assert {"Story", "Height", "BSElev"}.issubset(story_columns)
    assignments = registry.tables["pier_assignments"]
    assignment_columns = set(assignments.get("required_columns") or assignments.get("columns") or ())
    assert {"Story", "Label", "Pier"}.issubset(assignment_columns)


def test_pack_c_does_not_promote_unproven_connectivity_or_end_region_source_by_name():
    catalog_dir = ROOT / "tbdy_engine/catalogs"
    pack_c_catalogs = sorted(path for path in catalog_dir.glob("*pack_c*") if path.is_file())
    text = "\n".join(path.read_text(encoding="utf-8") for path in pack_c_catalogs)
    assert "Wall Object Connectivity" not in text
    assert "Wall Bays" not in text
    assert "source_contract_status: VERIFIED_LIVE" not in text
    assert "evidence_status: VERIFIED_LIVE" not in text


def test_pack_c_catalog_defines_exact_five_formal_checks_and_no_derived_snapshot_features():
    raw = yaml.safe_load(CATALOG.read_text(encoding="utf-8"))
    assert tuple(raw["checks"]) == PACK_C_CHECK_IDS
    text = CATALOG.read_text(encoding="utf-8")
    for forbidden in (
        "wall_hw_mm:",
        "wall_hcr_mm:",
        "wall_hw_lw_gt2:",
        "critical_region_membership:",
    ):
        assert forbidden not in text
    assert "derived_hw_hcr_not_feature_snapshot: true" in text
    assert "no_property_name_inference: true" in text
    assert "no_magnitude_unit_heuristic: true" in text


def test_pack_c_clause_refs_and_execution_dependencies_are_frozen():
    raw = yaml.safe_load(CATALOG.read_text(encoding="utf-8"))["checks"]
    assert raw["WALL_END_REGIONS_REQUIRED_HW_LW_GT2"]["code_ref"] == "TBDY 2018 §7.6.2.1"
    assert raw["WALL_HCR_GE_LW"]["formula_ref"] == "TBDY_EQ_7_15A_HCR_GE_LW"
    assert raw["WALL_HCR_GE_HW_DIV6"]["formula_ref"] == "TBDY_EQ_7_15B_HCR_GE_HW_DIV6"
    assert raw["WALL_HCR_LE_2LW"]["code_ref"] == "TBDY 2018 §7.6.2.2"
    assert raw["WALL_END_REGION_LENGTH_CRITICAL_GE_MAX_0_2LW_2BW"]["code_ref"] == "TBDY 2018 §7.6.2.3"
    base = ["wall_vertical_profile", "wall_regulatory_reference_facts", "wall_section_reduction_evidence"]
    for check_id in ("WALL_HCR_GE_LW", "WALL_HCR_GE_HW_DIV6", "WALL_HCR_LE_2LW"):
        assert raw[check_id]["required_execution_context"] == base
    for check_id in ("WALL_END_REGIONS_REQUIRED_HW_LW_GT2", "WALL_END_REGION_LENGTH_CRITICAL_GE_MAX_0_2LW_2BW"):
        assert raw[check_id]["required_execution_context"] == base + ["wall_end_region_topology"]
