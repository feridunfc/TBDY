"""P2.10 shared formal wall-check contracts for Packs A, B and C."""
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

WALL_END_REGIONS_REQUIRED_HW_LW_GT2 = "WALL_END_REGIONS_REQUIRED_HW_LW_GT2"
WALL_HCR_GE_LW = "WALL_HCR_GE_LW"
WALL_HCR_GE_HW_DIV6 = "WALL_HCR_GE_HW_DIV6"
WALL_HCR_LE_2LW = "WALL_HCR_LE_2LW"
WALL_END_REGION_LENGTH_CRITICAL_GE_MAX_0_2LW_2BW = "WALL_END_REGION_LENGTH_CRITICAL_GE_MAX_0_2LW_2BW"
PACK_C_CHECK_IDS = (
    WALL_END_REGIONS_REQUIRED_HW_LW_GT2,
    WALL_HCR_GE_LW,
    WALL_HCR_GE_HW_DIV6,
    WALL_HCR_LE_2LW,
    WALL_END_REGION_LENGTH_CRITICAL_GE_MAX_0_2LW_2BW,
)

_CATALOG_DIR = Path(__file__).resolve().parents[1] / "catalogs"
_PACK_B_CATALOG_PATH = _CATALOG_DIR / "check_catalog_p2_10_wall_pack_b.yaml"
_PACK_C_CATALOG_PATH = _CATALOG_DIR / "check_catalog_p2_10_wall_pack_c.yaml"


def _load_exact(path: Path, expected_ids: tuple[str, ...], label: str) -> Mapping[str, Mapping[str, Any]]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    checks = raw.get("checks") or {}
    if set(checks) != set(expected_ids):
        raise ValueError(f"{label} check overlay must define exactly its frozen formal check IDs")
    return MappingProxyType({check_id: MappingProxyType(dict(checks[check_id])) for check_id in expected_ids})


PACK_B_CHECK_DEFINITIONS = _load_exact(_PACK_B_CATALOG_PATH, PACK_B_NEW_CHECK_IDS, "Pack B")
PACK_C_CHECK_DEFINITIONS = _load_exact(_PACK_C_CATALOG_PATH, PACK_C_CHECK_IDS, "Pack C")
WALL_CHECK_DEFINITIONS: Mapping[str, Mapping[str, Any]] = MappingProxyType({
    **dict(PACK_A_CHECK_DEFINITIONS),
    **dict(PACK_B_CHECK_DEFINITIONS),
    **dict(PACK_C_CHECK_DEFINITIONS),
})

__all__ = [
    "PACK_B_AFFECTED_CHECK_IDS", "PACK_B_CHECK_DEFINITIONS", "PACK_B_NEW_CHECK_IDS",
    "PACK_C_CHECK_DEFINITIONS", "PACK_C_CHECK_IDS", "WALL_CHECK_DEFINITIONS",
    "WALL_END_REGIONS_REQUIRED_HW_LW_GT2",
    "WALL_END_REGION_LENGTH_CRITICAL_GE_MAX_0_2LW_2BW",
    "WALL_GEOM_SPECIAL_THICKNESS_GE_200", "WALL_GEOM_SPECIAL_THICKNESS_GE_HMAX20",
    "WALL_HCR_GE_HW_DIV6", "WALL_HCR_GE_LW", "WALL_HCR_LE_2LW",
    "WALL_NET_SECTION_AXIAL_CAPACITY",
]
