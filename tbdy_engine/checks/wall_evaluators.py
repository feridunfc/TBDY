"""Pure formal wall-rule evaluators registered by canonical CheckEngine.

Applicability, Coverage, evidence policy, status, and CheckResult construction stay
in CheckEngine. Functions here calculate only the formal engineering expression.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping

from tbdy_engine.checks.wall_pack_a_contract import (
    WALL_GEOM_BODY_THICKNESS_GE_250, WALL_GEOM_BODY_THICKNESS_GE_H16,
    WALL_GEOM_DEFINITION_LW_BW_GE6, WALL_GEOM_RESTRAINED_LEG_THICKNESS,
    WALL_GEOM_UNRESTRAINED_THICKNESS_GE_L30,
)
from tbdy_engine.checks.wall_contract import (
    WALL_END_REGIONS_REQUIRED_HW_LW_GT2,
    WALL_END_REGION_LENGTH_CRITICAL_GE_MAX_0_2LW_2BW,
    WALL_GEOM_SPECIAL_THICKNESS_GE_200, WALL_GEOM_SPECIAL_THICKNESS_GE_HMAX20,
    WALL_HCR_GE_HW_DIV6, WALL_HCR_GE_LW, WALL_HCR_LE_2LW,
    WALL_NET_SECTION_AXIAL_CAPACITY,
)


@dataclass(frozen=True, slots=True)
class WallRuleValue:
    value: float
    limit: float
    ratio: float
    unit: str
    satisfied: bool | None = None
    ratio_type: str = "actual_over_minimum"
    pass_rule: str = "actual_over_minimum"

    @property
    def is_satisfied(self) -> bool:
        return self.value >= self.limit if self.satisfied is None else self.satisfied


def _positive(name: str, value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"Required numeric input is missing or non-numeric: {name}")
    number = float(value)
    if number <= 0:
        raise ValueError(f"Required numeric input must be positive: {name}")
    return number


def _nonnegative(name: str, value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"Required numeric input is missing or non-numeric: {name}")
    number = float(value)
    if number < 0:
        raise ValueError(f"Required numeric input must be non-negative: {name}")
    return number


def definition_ge6(v: Mapping[str, Any], _: Mapping[str, Any]) -> WallRuleValue:
    thickness = _positive("wall_thickness_mm", v.get("wall_thickness_mm")); length = _positive("wall_length_mm", v.get("wall_length_mm")); value = length / thickness
    return WallRuleValue(value, 6.0, value / 6.0, "")

def body_h16(v: Mapping[str, Any], _: Mapping[str, Any]) -> WallRuleValue:
    thickness = _positive("wall_thickness_mm", v.get("wall_thickness_mm")); minimum = _positive("story_height_mm", v.get("story_height_mm")) / 16.0
    return WallRuleValue(thickness, minimum, thickness / minimum, "mm")

def body_250(v: Mapping[str, Any], _: Mapping[str, Any]) -> WallRuleValue:
    thickness = _positive("wall_thickness_mm", v.get("wall_thickness_mm")); return WallRuleValue(thickness, 250.0, thickness / 250.0, "mm")

def unrestrained_l30(v: Mapping[str, Any], _: Mapping[str, Any]) -> WallRuleValue:
    thickness = _positive("wall_thickness_mm", v.get("wall_thickness_mm")); length = _positive("unrestrained_plan_length_mm", v.get("unrestrained_plan_length_mm")); minimum = length / 30.0
    return WallRuleValue(thickness, minimum, thickness / minimum, "mm")

def restrained_leg(v: Mapping[str, Any], _: Mapping[str, Any]) -> WallRuleValue:
    thickness = _positive("wall_thickness_mm", v.get("wall_thickness_mm")); minimum = max(_positive("story_height_mm", v.get("story_height_mm")) / 20.0, 250.0)
    return WallRuleValue(thickness, minimum, thickness / minimum, "mm")

def special_hmax20(v: Mapping[str, Any], e: Mapping[str, Any]) -> WallRuleValue:
    thickness = _positive("wall_thickness_mm", v.get("wall_thickness_mm")); minimum = _positive("highest_applicable_story_height_mm", e.get("highest_applicable_story_height_mm")) / 20.0
    return WallRuleValue(thickness, minimum, thickness / minimum, "mm")

def special_200(v: Mapping[str, Any], _: Mapping[str, Any]) -> WallRuleValue:
    thickness = _positive("wall_thickness_mm", v.get("wall_thickness_mm")); return WallRuleValue(thickness, 200.0, thickness / 200.0, "mm")

def net_axial(v: Mapping[str, Any], e: Mapping[str, Any]) -> WallRuleValue:
    ac = _positive("net_section_area_mm2", e.get("net_section_area_mm2")); ndm_n = _positive("Ndm_N", e.get("Ndm_N")); fck = _positive("concrete_fck_mpa", v.get("concrete_fck_mpa")); required = ndm_n / (0.35 * fck)
    return WallRuleValue(ac, required, ac / required, "mm2")

def end_regions_required(_: Mapping[str, Any], e: Mapping[str, Any]) -> WallRuleValue:
    actual = _nonnegative("proven_end_region_ends", e.get("proven_end_region_ends", 0.0)); return WallRuleValue(actual, 2.0, actual / 2.0, "")

def hcr_ge_lw(_: Mapping[str, Any], e: Mapping[str, Any]) -> WallRuleValue:
    hcr = _positive("hcr_governing_mm", e.get("hcr_governing_mm")); lw = _positive("lw_governing_mm", e.get("lw_governing_mm")); return WallRuleValue(hcr, lw, hcr / lw, "mm")

def hcr_ge_hw_div6(_: Mapping[str, Any], e: Mapping[str, Any]) -> WallRuleValue:
    hcr = _positive("hcr_governing_mm", e.get("hcr_governing_mm")); minimum = _positive("hw_governing_mm", e.get("hw_governing_mm")) / 6.0; return WallRuleValue(hcr, minimum, hcr / minimum, "mm")

def hcr_le_2lw(_: Mapping[str, Any], e: Mapping[str, Any]) -> WallRuleValue:
    hcr = _positive("hcr_governing_mm", e.get("hcr_governing_mm")); maximum = 2.0 * _positive("lw_governing_mm", e.get("lw_governing_mm"))
    return WallRuleValue(hcr, maximum, hcr / maximum, "mm", satisfied=hcr <= maximum, ratio_type="value_over_maximum", pass_rule="value_over_maximum")

def critical_end_region_length(_: Mapping[str, Any], e: Mapping[str, Any]) -> WallRuleValue:
    actual = _nonnegative("governing_end_region_plan_length_mm", e.get("governing_end_region_plan_length_mm")); minimum = _positive("governing_required_end_region_plan_length_mm", e.get("governing_required_end_region_plan_length_mm"))
    return WallRuleValue(actual, minimum, actual / minimum, "mm")


WallEvaluator = Callable[[Mapping[str, Any], Mapping[str, Any]], WallRuleValue]
WALL_EVALUATORS: Mapping[str, WallEvaluator] = {
    WALL_GEOM_DEFINITION_LW_BW_GE6: definition_ge6,
    WALL_GEOM_BODY_THICKNESS_GE_H16: body_h16,
    WALL_GEOM_BODY_THICKNESS_GE_250: body_250,
    WALL_GEOM_UNRESTRAINED_THICKNESS_GE_L30: unrestrained_l30,
    WALL_GEOM_RESTRAINED_LEG_THICKNESS: restrained_leg,
    WALL_GEOM_SPECIAL_THICKNESS_GE_HMAX20: special_hmax20,
    WALL_GEOM_SPECIAL_THICKNESS_GE_200: special_200,
    WALL_NET_SECTION_AXIAL_CAPACITY: net_axial,
    WALL_END_REGIONS_REQUIRED_HW_LW_GT2: end_regions_required,
    WALL_HCR_GE_LW: hcr_ge_lw,
    WALL_HCR_GE_HW_DIV6: hcr_ge_hw_div6,
    WALL_HCR_LE_2LW: hcr_le_2lw,
    WALL_END_REGION_LENGTH_CRITICAL_GE_MAX_0_2LW_2BW: critical_end_region_length,
}

__all__ = ["WALL_EVALUATORS", "WallRuleValue"]
