"""Canonical data-only wall geometry feature overlay for P2.10 and later checks."""
from __future__ import annotations

from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

import yaml

_CATALOG_PATH = (
    Path(__file__).resolve().parents[1]
    / "catalogs"
    / "feature_catalog_p2_10_wall_pack_a.yaml"
)
_BASE_FEATURE_IDS = frozenset({"wall_thickness_mm", "wall_length_mm", "story_height_mm"})


def _load_wall_geometry_feature_definitions() -> Mapping[str, Mapping[str, Any]]:
    raw = yaml.safe_load(_CATALOG_PATH.read_text(encoding="utf-8")) or {}
    features = raw.get("features") or {}
    required = {
        "wall_thickness_mm",
        "wall_length_mm",
        "story_height_mm",
        "wall_is_basement",
        "wall_body_classification",
        "unrestrained_plan_length_mm",
        "wall_geometry_classification",
        "wall_both_ends_laterally_restrained",
    }
    missing = required - set(features)
    if missing:
        raise ValueError("Wall geometry overlay is missing required feature definitions: " + ", ".join(sorted(missing)))
    if "wall_special_branch_7_6_1_3_applies" in features:
        raise ValueError("Engineering-derived §7.6.1.3 eligibility must not be stored as a FeatureSnapshot fact")
    return MappingProxyType(
        {name: MappingProxyType(dict(definition)) for name, definition in features.items()}
    )


WALL_GEOMETRY_FEATURE_DEFINITIONS = _load_wall_geometry_feature_definitions()
WALL_GEOMETRY_SUPPLEMENTAL_FEATURE_DEFINITIONS: Mapping[str, Mapping[str, Any]] = MappingProxyType(
    {
        name: definition
        for name, definition in WALL_GEOMETRY_FEATURE_DEFINITIONS.items()
        if name not in _BASE_FEATURE_IDS
    }
)

__all__ = [
    "WALL_GEOMETRY_FEATURE_DEFINITIONS",
    "WALL_GEOMETRY_SUPPLEMENTAL_FEATURE_DEFINITIONS",
]
