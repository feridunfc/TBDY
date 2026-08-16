"""Canonical data-only wall feature contract overlays for P2.10 wall checks."""
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


def _load_wall_geometry_feature_definitions() -> Mapping[str, Mapping[str, Any]]:
    features = _read_features(_PACK_A_PATH)
    if _PACK_B_PATH.exists():
        for name, definition in _read_features(_PACK_B_PATH).items():
            if name in features:
                raise ValueError(f"Pack B factual feature duplicates existing wall feature: {name}")
            features[name] = definition
    required = {
        "wall_thickness_mm", "wall_length_mm", "story_height_mm", "wall_is_basement",
        "wall_body_classification", "unrestrained_plan_length_mm", "wall_geometry_classification",
        "wall_both_ends_laterally_restrained", "wall_regulatory_structural_system_classification",
    }
    missing = required - set(features)
    if missing:
        raise ValueError("Wall geometry overlay is missing required feature definitions: " + ", ".join(sorted(missing)))
    forbidden = {"wall_special_branch_7_6_1_3_applies", "Vt", "Ndm", "net_Ac", "sum_ag", "sum_ap"}
    found = forbidden & set(features)
    if found:
        raise ValueError("Engineering-derived quantities must not be FeatureSnapshot facts: " + ", ".join(sorted(found)))
    return MappingProxyType({name: MappingProxyType(dict(definition)) for name, definition in features.items()})


WALL_GEOMETRY_FEATURE_DEFINITIONS = _load_wall_geometry_feature_definitions()
WALL_GEOMETRY_SUPPLEMENTAL_FEATURE_DEFINITIONS: Mapping[str, Mapping[str, Any]] = MappingProxyType({
    name: definition for name, definition in WALL_GEOMETRY_FEATURE_DEFINITIONS.items() if name not in _BASE_FEATURE_IDS
})

__all__ = ["WALL_GEOMETRY_FEATURE_DEFINITIONS", "WALL_GEOMETRY_SUPPLEMENTAL_FEATURE_DEFINITIONS"]
