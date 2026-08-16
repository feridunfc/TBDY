from __future__ import annotations

from pathlib import Path

import yaml

from tbdy_engine.checks.wall_pack_a_contract import LEGACY_NON_EXECUTABLE_CHECK_ALIASES, PACK_A_CHECK_DEFINITIONS, PACK_A_CHECK_IDS
from tbdy_engine.features.wall_geometry_contract import WALL_GEOMETRY_SUPPLEMENTAL_FEATURE_DEFINITIONS

ROOT = Path(__file__).resolve().parents[2]
CHECK_OVERLAY = ROOT / "tbdy_engine/catalogs/check_catalog_p2_10_wall_pack_a.yaml"
FEATURE_OVERLAY = ROOT / "tbdy_engine/catalogs/feature_catalog_p2_10_wall_pack_a.yaml"
BASE_FEATURE_CATALOG = ROOT / "tbdy_engine/catalogs/feature_catalog.yaml"


def _yaml(path: Path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_pack_a_check_overlay_matches_frozen_runtime_contract_and_ge7_is_metadata_only():
    overlay = _yaml(CHECK_OVERLAY)
    checks = overlay["checks"]
    assert tuple(checks) == PACK_A_CHECK_IDS
    for check_id in PACK_A_CHECK_IDS:
        assert tuple(checks[check_id]["required_features"]) == tuple(PACK_A_CHECK_DEFINITIONS[check_id]["required_features"])
        assert checks[check_id]["code_ref"] == PACK_A_CHECK_DEFINITIONS[check_id]["code_ref"]
    assert overlay["metadata"]["legacy_non_executable_aliases"] == dict(LEGACY_NON_EXECUTABLE_CHECK_ALIASES)
    assert "WALL11_LENGTH_TO_THICKNESS_GE7" not in checks
    assert checks["WALL_GEOM_DEFINITION_LW_BW_GE6"]["output"]["limit"] == 6.0


def test_pack_a_feature_overlay_only_adds_new_context_facts_and_never_duplicates_existing_geometry_ids():
    overlay_features = _yaml(FEATURE_OVERLAY)["features"]
    base_features = _yaml(BASE_FEATURE_CATALOG)["features"]
    assert set(overlay_features) == set(WALL_GEOMETRY_SUPPLEMENTAL_FEATURE_DEFINITIONS)
    assert set(overlay_features).isdisjoint(base_features)
    assert {"wall_thickness_mm", "wall_length_mm", "story_height_mm"}.issubset(base_features)
