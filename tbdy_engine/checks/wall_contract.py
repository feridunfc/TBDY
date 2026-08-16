"""P2.10 Pack B wall-check contract additions loaded from the canonical overlay."""
from __future__ import annotations

from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

import yaml

from tbdy_engine.checks.wall_pack_a_contract import (
    PACK_A_CHECK_DEFINITIONS,
    WALL_GEOM_BODY_THICKNESS_GE_250,
    WALL_GEOM_BODY_THICKNESS_GE_H16,
)

WALL_GEOM_SPECIAL_THICKNESS_GE_HMAX20 = "WALL_GEOM_SPECIAL_THICKNESS_GE_HMAX20"
WALL_GEOM_SPECIAL_THICKNESS_GE_200 = "WALL_GEOM_SPECIAL_THICKNESS_GE_200"
WALL_NET_SECTION_AXIAL_CAPACITY = "WALL_NET_SECTION_AXIAL_CAPACITY"
PACK_B_NEW_CHECK_IDS = (
    WALL_GEOM_SPECIAL_THICKNESS_GE_HMAX20,
    WALL_GEOM_SPECIAL_THICKNESS_GE_200,
    WALL_NET_SECTION_AXIAL_CAPACITY,
)
PACK_B_AFFECTED_CHECK_IDS = (
    WALL_GEOM_BODY_THICKNESS_GE_H16,
    WALL_GEOM_BODY_THICKNESS_GE_250,
    *PACK_B_NEW_CHECK_IDS,
)
_CATALOG_PATH = Path(__file__).resolve().parents[1] / "catalogs" / "check_catalog_p2_10_wall_pack_b.yaml"


def _load_pack_b_check_definitions() -> Mapping[str, Mapping[str, Any]]:
    raw = yaml.safe_load(_CATALOG_PATH.read_text(encoding="utf-8")) or {}
    checks = raw.get("checks") or {}
    if set(checks) != set(PACK_B_NEW_CHECK_IDS):
        raise ValueError("Pack B check overlay must define exactly the three new formal check IDs")
    return MappingProxyType({check_id: MappingProxyType(dict(checks[check_id])) for check_id in PACK_B_NEW_CHECK_IDS})


PACK_B_CHECK_DEFINITIONS = _load_pack_b_check_definitions()
WALL_CHECK_DEFINITIONS: Mapping[str, Mapping[str, Any]] = MappingProxyType({
    **dict(PACK_A_CHECK_DEFINITIONS), **dict(PACK_B_CHECK_DEFINITIONS),
})

__all__ = [
    "PACK_B_AFFECTED_CHECK_IDS", "PACK_B_CHECK_DEFINITIONS", "PACK_B_NEW_CHECK_IDS",
    "WALL_CHECK_DEFINITIONS", "WALL_GEOM_SPECIAL_THICKNESS_GE_200",
    "WALL_GEOM_SPECIAL_THICKNESS_GE_HMAX20", "WALL_NET_SECTION_AXIAL_CAPACITY",
]
