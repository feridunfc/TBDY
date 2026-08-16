"""Canonical data-only wall feature contracts for P2.10 wall checks."""
from __future__ import annotations

from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

import yaml

_CATALOG_ROOT = Path(__file__).resolve().parents[1] / "catalogs"
_PACK_A_PATH = _CATALOG_ROOT / "feature_catalog_p2_10_wall_pack_a.yaml"
_PACK_B_PATH = _CATALOG_ROOT / "feature_catalog_p2_10_wall_pack_b.yaml"
_BASE_FEATURE_IDS = frozenset({"wall_thickness_mm", "wall_length_mm", "story_height_mm"})


def _read_features(path: Path) -> dict[str, Mapping[str, Any]]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    features = raw.get("features") or {}
    if not isinstance(features, Mapping):
        raise ValueError(f"{path.name} features must be a mapping")
    return {str(name): dict(definition) for name, definition in features.items()}


def _freeze(features: Mapping[str, Mapping[str, Any]]) -> Mapping[str, Mapping[str, Any]]:
    return MappingProxyType({name: MappingProxyType(dict(definition)) for name, definition in features.items()})


_pack_a = _read_features(_PACK_A_PATH)
required_a = {
    "wall_thickness_mm", "wall_length_mm", "story_height_mm", "wall_is_basement",
    "wall_body_classification", "unrestrained_plan_length_mm", "wall_geometry_classification",
    "wall_both_ends_laterally_restrained",
}
missing = required_a - set(_pack_a)
if missing:
    raise ValueError("Wall Pack A overlay is missing required feature definitions: " + ", ".join(sorted(missing)))
if "wall_special_branch_7_6_1_3_applies" in _pack_a:
    raise ValueError("Engineering-derived §7.6.1.3 eligibility must not be a FeatureSnapshot fact")

# Pack-A compatibility authority remains exactly the Pack-A overlay.
WALL_GEOMETRY_FEATURE_DEFINITIONS = _freeze(_pack_a)
WALL_GEOMETRY_SUPPLEMENTAL_FEATURE_DEFINITIONS = _freeze({
    name: definition for name, definition in _pack_a.items() if name not in _BASE_FEATURE_IDS
})

_pack_b = _read_features(_PACK_B_PATH) if _PACK_B_PATH.exists() else {}
if "wall_special_branch_7_6_1_3_applies" in _pack_b:
    raise ValueError("Engineering-derived §7.6.1.3 eligibility must not be a FeatureSnapshot fact")
WALL_PACK_B_FEATURE_DEFINITIONS = _freeze(_pack_b)
_combined = {**_pack_a, **_pack_b}
WALL_ALL_FEATURE_DEFINITIONS = _freeze(_combined)
WALL_ALL_SUPPLEMENTAL_FEATURE_DEFINITIONS = _freeze({
    name: definition for name, definition in _combined.items() if name not in _BASE_FEATURE_IDS
})

__all__ = [
    "WALL_GEOMETRY_FEATURE_DEFINITIONS", "WALL_GEOMETRY_SUPPLEMENTAL_FEATURE_DEFINITIONS",
    "WALL_PACK_B_FEATURE_DEFINITIONS", "WALL_ALL_FEATURE_DEFINITIONS",
    "WALL_ALL_SUPPLEMENTAL_FEATURE_DEFINITIONS",
]
