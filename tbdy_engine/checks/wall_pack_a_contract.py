"""Frozen TBDY 2018 §7.6.1/§7.6.1.2 Pack A wall geometry contract."""
from __future__ import annotations

from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

import yaml

WALL_GEOM_DEFINITION_LW_BW_GE6 = "WALL_GEOM_DEFINITION_LW_BW_GE6"
WALL_GEOM_BODY_THICKNESS_GE_H16 = "WALL_GEOM_BODY_THICKNESS_GE_H16"
WALL_GEOM_BODY_THICKNESS_GE_250 = "WALL_GEOM_BODY_THICKNESS_GE_250"
WALL_GEOM_UNRESTRAINED_THICKNESS_GE_L30 = "WALL_GEOM_UNRESTRAINED_THICKNESS_GE_L30"
WALL_GEOM_RESTRAINED_LEG_THICKNESS = "WALL_GEOM_RESTRAINED_LEG_THICKNESS"

PACK_A_CHECK_IDS = (
    WALL_GEOM_DEFINITION_LW_BW_GE6,
    WALL_GEOM_BODY_THICKNESS_GE_H16,
    WALL_GEOM_BODY_THICKNESS_GE_250,
    WALL_GEOM_UNRESTRAINED_THICKNESS_GE_L30,
    WALL_GEOM_RESTRAINED_LEG_THICKNESS,
)

LEGACY_NON_EXECUTABLE_CHECK_ALIASES: Mapping[str, str] = MappingProxyType(
    {"WALL11_LENGTH_TO_THICKNESS_GE7": WALL_GEOM_DEFINITION_LW_BW_GE6}
)

WALL_BODY_CLASSIFICATIONS = frozenset({"RECTANGULAR_BODY", "U_BODY", "L_BODY", "T_BODY"})
UNRESTRAINED_GEOMETRY_CLASSIFICATIONS = frozenset({"RECTANGULAR_WALL", "WALL_LEG"})

_CATALOG_PATH = (
    Path(__file__).resolve().parents[1]
    / "catalogs"
    / "check_catalog_p2_10_wall_pack_a.yaml"
)


def _load_pack_a_check_definitions() -> Mapping[str, Mapping[str, Any]]:
    raw = yaml.safe_load(_CATALOG_PATH.read_text(encoding="utf-8")) or {}
    checks = raw.get("checks") or {}
    if set(checks) != set(PACK_A_CHECK_IDS):
        raise ValueError("Pack A check overlay must define exactly the frozen five check IDs")
    legacy = (raw.get("metadata") or {}).get("legacy_non_executable_aliases") or {}
    if legacy.get("WALL11_LENGTH_TO_THICKNESS_GE7") != WALL_GEOM_DEFINITION_LW_BW_GE6:
        raise ValueError("Pack A overlay must preserve GE7 only as a non-executable legacy alias to GE6")
    return MappingProxyType(
        {check_id: MappingProxyType(dict(checks[check_id])) for check_id in PACK_A_CHECK_IDS}
    )


PACK_A_CHECK_DEFINITIONS = _load_pack_a_check_definitions()

__all__ = [
    "LEGACY_NON_EXECUTABLE_CHECK_ALIASES",
    "PACK_A_CHECK_DEFINITIONS",
    "PACK_A_CHECK_IDS",
    "UNRESTRAINED_GEOMETRY_CLASSIFICATIONS",
    "WALL_BODY_CLASSIFICATIONS",
    "WALL_GEOM_BODY_THICKNESS_GE_250",
    "WALL_GEOM_BODY_THICKNESS_GE_H16",
    "WALL_GEOM_DEFINITION_LW_BW_GE6",
    "WALL_GEOM_RESTRAINED_LEG_THICKNESS",
    "WALL_GEOM_UNRESTRAINED_THICKNESS_GE_L30",
]
