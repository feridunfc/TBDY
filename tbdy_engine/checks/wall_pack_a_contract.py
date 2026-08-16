"""Frozen TBDY 2018 §7.6.1/§7.6.1.2 Pack A wall geometry contract."""
from __future__ import annotations

from types import MappingProxyType
from typing import Any, Mapping

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

# Historical identifier only. Intentionally absent from the executable allowlist.
LEGACY_NON_EXECUTABLE_CHECK_ALIASES: Mapping[str, str] = MappingProxyType(
    {"WALL11_LENGTH_TO_THICKNESS_GE7": WALL_GEOM_DEFINITION_LW_BW_GE6}
)

WALL_BODY_CLASSIFICATIONS = frozenset({"RECTANGULAR_BODY", "U_BODY", "L_BODY", "T_BODY"})
UNRESTRAINED_GEOMETRY_CLASSIFICATIONS = frozenset({"RECTANGULAR_WALL", "WALL_LEG"})
_COMMON_NON_BASEMENT = ("wall_is_basement",)

PACK_A_CHECK_DEFINITIONS: Mapping[str, Mapping[str, Any]] = MappingProxyType(
    {
        WALL_GEOM_DEFINITION_LW_BW_GE6: {
            "title": "Wall definition lw/bw >= 6", "element_type": "wall", "category": "GEOMETRY",
            "required_features": ("wall_length_mm", "wall_thickness_mm", *_COMMON_NON_BASEMENT),
            "formula_ref": "lw / bw >= 6", "ratio_type": "actual_over_minimum", "unit": "",
            "code_ref": "TBDY 2018 §7.6.1.2 first sentence", "evaluation_level": "DESIGN_LEVEL",
        },
        WALL_GEOM_BODY_THICKNESS_GE_H16: {
            "title": "Wall body thickness >= story height / 16", "element_type": "wall", "category": "GEOMETRY",
            "required_features": ("wall_thickness_mm", "story_height_mm", "wall_body_classification", "wall_special_branch_7_6_1_3_applies", *_COMMON_NON_BASEMENT),
            "formula_ref": "bw >= h_story / 16", "ratio_type": "actual_over_minimum", "unit": "mm",
            "code_ref": "TBDY 2018 §7.6.1.2(a)", "evaluation_level": "DESIGN_LEVEL",
        },
        WALL_GEOM_BODY_THICKNESS_GE_250: {
            "title": "Wall body thickness >= 250 mm", "element_type": "wall", "category": "GEOMETRY",
            "required_features": ("wall_thickness_mm", "wall_body_classification", "wall_special_branch_7_6_1_3_applies", *_COMMON_NON_BASEMENT),
            "formula_ref": "bw >= 250 mm", "ratio_type": "actual_over_minimum", "unit": "mm",
            "code_ref": "TBDY 2018 §7.6.1.2(a)", "evaluation_level": "DESIGN_LEVEL",
        },
        WALL_GEOM_UNRESTRAINED_THICKNESS_GE_L30: {
            "title": "Unrestrained wall/leg thickness >= unrestrained plan length / 30", "element_type": "wall", "category": "GEOMETRY",
            "required_features": ("wall_thickness_mm", "unrestrained_plan_length_mm", "wall_geometry_classification", *_COMMON_NON_BASEMENT),
            "formula_ref": "bw >= l_unrestrained / 30", "ratio_type": "actual_over_minimum", "unit": "mm",
            "code_ref": "TBDY 2018 §7.6.1.2(b)", "evaluation_level": "DESIGN_LEVEL",
        },
        WALL_GEOM_RESTRAINED_LEG_THICKNESS: {
            "title": "Both-ends restrained wall-leg thickness", "element_type": "wall", "category": "GEOMETRY",
            "required_features": ("wall_thickness_mm", "story_height_mm", "wall_both_ends_laterally_restrained", *_COMMON_NON_BASEMENT),
            "formula_ref": "bw >= max(h_story / 20, 250 mm)", "ratio_type": "actual_over_minimum", "unit": "mm",
            "code_ref": "TBDY 2018 §7.6.1.2(c)", "evaluation_level": "DESIGN_LEVEL",
        },
    }
)

__all__ = [
    "LEGACY_NON_EXECUTABLE_CHECK_ALIASES", "PACK_A_CHECK_DEFINITIONS", "PACK_A_CHECK_IDS",
    "UNRESTRAINED_GEOMETRY_CLASSIFICATIONS", "WALL_BODY_CLASSIFICATIONS",
    "WALL_GEOM_BODY_THICKNESS_GE_250", "WALL_GEOM_BODY_THICKNESS_GE_H16",
    "WALL_GEOM_DEFINITION_LW_BW_GE6", "WALL_GEOM_RESTRAINED_LEG_THICKNESS",
    "WALL_GEOM_UNRESTRAINED_THICKNESS_GE_L30",
]
