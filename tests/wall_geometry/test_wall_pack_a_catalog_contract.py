from __future__ import annotations

from pathlib import Path

import yaml

from tbdy_engine.checks.wall_pack_a_contract import (
    LEGACY_NON_EXECUTABLE_CHECK_ALIASES,
    PACK_A_CHECK_DEFINITIONS,
    PACK_A_CHECK_IDS,
    WALL_GEOM_BODY_THICKNESS_GE_250,
    WALL_GEOM_BODY_THICKNESS_GE_H16,
)
from tbdy_engine.features.wall_geometry_contract import (
    WALL_GEOMETRY_FEATURE_DEFINITIONS,
    WALL_GEOMETRY_SUPPLEMENTAL_FEATURE_DEFINITIONS,
)

ROOT = Path(__file__).resolve().parents[2]
CHECK_OVERLAY = ROOT / "tbdy_engine/catalogs/check_catalog_p2_10_wall_pack_a.yaml"
FEATURE_OVERLAY = ROOT / "tbdy_engine/catalogs/feature_catalog_p2_10_wall_pack_a.yaml"
BASE_FEATURE_CATALOG = ROOT / "tbdy_engine/catalogs/feature_catalog.yaml"
BASE_FACTS = {"wall_thickness_mm", "wall_length_mm", "story_height_mm"}


def _yaml(path: Path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_pack_a_check_overlay_matches_runtime_contract_and_ge7_is_metadata_only():
    overlay = _yaml(CHECK_OVERLAY)
    checks = overlay["checks"]
    assert tuple(checks) == PACK_A_CHECK_IDS
    for check_id in PACK_A_CHECK_IDS:
        assert tuple(checks[check_id]["required_features"]) == tuple(
            PACK_A_CHECK_DEFINITIONS[check_id]["required_features"]
        )
        assert checks[check_id]["code_ref"] == PACK_A_CHECK_DEFINITIONS[check_id]["code_ref"]
    assert overlay["metadata"]["legacy_non_executable_aliases"] == dict(
        LEGACY_NON_EXECUTABLE_CHECK_ALIASES
    )
    assert "WALL11_LENGTH_TO_THICKNESS_GE7" not in checks
    assert checks["WALL_GEOM_DEFINITION_LW_BW_GE6"]["output"]["limit"] == 6.0

    for check_id in (WALL_GEOM_BODY_THICKNESS_GE_H16, WALL_GEOM_BODY_THICKNESS_GE_250):
        assert checks[check_id]["readiness"]["status"] == "partial"
        assert "wall_special_branch_7_6_1_3_applies" not in checks[check_id]["required_features"]
        assert "§7.6.1.3" in checks[check_id]["readiness"]["reason"]


def test_wall_geometry_overlay_is_single_runtime_source_for_base_overrides_and_supplemental_facts():
    overlay_features = _yaml(FEATURE_OVERLAY)["features"]
    base_features = _yaml(BASE_FEATURE_CATALOG)["features"]

    assert set(overlay_features) == set(WALL_GEOMETRY_FEATURE_DEFINITIONS)
    assert BASE_FACTS.issubset(base_features)
    assert BASE_FACTS.issubset(overlay_features)
    assert set(WALL_GEOMETRY_SUPPLEMENTAL_FEATURE_DEFINITIONS) == set(overlay_features) - BASE_FACTS
    assert "wall_special_branch_7_6_1_3_applies" not in overlay_features

    assert overlay_features["wall_thickness_mm"]["source"]["table_key"] == "wall_section_properties"
    assert "Thickness" in overlay_features["wall_thickness_mm"]["source"]["field_aliases"]
    assert overlay_features["wall_length_mm"]["source"]["table_key"] == "pier_section_properties"
    assert "Width" in overlay_features["wall_length_mm"]["source"]["field_aliases"]
    assert overlay_features["story_height_mm"]["source"]["table_key"] == "story_definitions"


def test_supplemental_wall_facts_remain_factual_and_do_not_encode_engineering_verdicts():
    supplemental = WALL_GEOMETRY_SUPPLEMENTAL_FEATURE_DEFINITIONS
    assert set(supplemental) == {
        "wall_is_basement",
        "wall_body_classification",
        "unrestrained_plan_length_mm",
        "wall_geometry_classification",
        "wall_both_ends_laterally_restrained",
    }
    forbidden = ("pass", "fail", "check_result", "compliance", "7_6_1_3_applies")
    for feature_id, definition in supplemental.items():
        payload = yaml.safe_dump({feature_id: dict(definition)}, sort_keys=True).casefold()
        assert not any(token in payload for token in forbidden)
