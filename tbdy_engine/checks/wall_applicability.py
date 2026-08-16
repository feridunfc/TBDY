"""Engineering-only helpers for wall applicability and derived result quantities.

Called by CheckEngine. Nothing here promotes an engineering-derived quantity to
VERIFIED_LIVE raw source evidence.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from tbdy_engine.features.result_evidence import ResultRowEvidenceBundle

_REQUIRED_NDM_POLICY_FIELDS = (
    "eligible_output_cases", "earthquake_direction", "envelope_rule",
    "compression_sign", "governing_location", "response_spectrum_handling",
)


@dataclass(frozen=True, slots=True)
class DerivedQuantity:
    value: float | None
    status: str
    diagnostic: str | None = None
    evidence: tuple[Mapping[str, Any], ...] = ()


def directional_eq714_quantities(
    *, gross_wall_areas_mm2_by_axis: Mapping[str, Sequence[float]],
    floor_plan_areas_mm2_by_story: Mapping[str, float],
    vt_n_by_axis: Mapping[str, float] | None = None,
    fctd_mpa: float | None = None,
) -> Mapping[str, float | None]:
    sum_ag_x = sum(float(v) for v in gross_wall_areas_mm2_by_axis.get("X", ()))
    sum_ag_y = sum(float(v) for v in gross_wall_areas_mm2_by_axis.get("Y", ()))
    sum_ap = sum(float(v) for v in floor_plan_areas_mm2_by_story.values())
    if sum_ap <= 0:
        raise ValueError("All-floor ΣAp requires positive factual floor-plan areas")
    out: dict[str, float | None] = {
        "sum_ag_x_mm2": sum_ag_x, "sum_ag_y_mm2": sum_ag_y,
        "sum_ap_all_floors_mm2": sum_ap,
        "sum_ag_x_over_sum_ap": sum_ag_x / sum_ap,
        "sum_ag_y_over_sum_ap": sum_ag_y / sum_ap,
        "vt_x_over_sum_ag_x_fctd": None, "vt_y_over_sum_ag_y_fctd": None,
    }
    if vt_n_by_axis is not None and fctd_mpa is not None:
        fctd = float(fctd_mpa)
        if fctd <= 0:
            raise ValueError("fctd must be positive")
        if sum_ag_x > 0 and "X" in vt_n_by_axis:
            out["vt_x_over_sum_ag_x_fctd"] = float(vt_n_by_axis["X"]) / (sum_ag_x * fctd)
        if sum_ag_y > 0 and "Y" in vt_n_by_axis:
            out["vt_y_over_sum_ag_y_fctd"] = float(vt_n_by_axis["Y"]) / (sum_ag_y * fctd)
    return out


def resolve_special_branch_applicability(
    *, component_id: str, reviewed_structural_system_classification: Any,
    engineering_context: Mapping[str, Any] | None,
) -> tuple[bool | None, str | None]:
    if not isinstance(reviewed_structural_system_classification, str) or not reviewed_structural_system_classification.strip():
        return None, "Regulatory structural-system classification is UNKNOWN"
    decisions = (engineering_context or {}).get("TBDY_7_6_1_3_applies")
    if not isinstance(decisions, Mapping):
        return None, "§7.6.1.3 engineering applicability proof is unavailable"
    decision = decisions.get(component_id)
    if not isinstance(decision, bool):
        return None, "§7.6.1.3 engineering applicability is unresolved; no default branch assumption is allowed"
    return decision, None


def derive_highest_applicable_story_height_mm(component_id: str, engineering_context: Mapping[str, Any] | None) -> DerivedQuantity:
    values = (engineering_context or {}).get("highest_applicable_story_height_mm")
    if not isinstance(values, Mapping):
        return DerivedQuantity(None, "BLOCKED", "Highest applicable story-height derivation is unavailable")
    value = values.get(component_id)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or float(value) <= 0:
        return DerivedQuantity(None, "BLOCKED", "Highest applicable story height is not proven for this wall")
    return DerivedQuantity(float(value), "RESOLVED")


def _to_newtons(value: float, bundle: ResultRowEvidenceBundle) -> float | None:
    unit = str(bundle.units.get("force_unit") or bundle.units.get("force") or "").strip()
    if unit == "N":
        return value
    if unit == "kN":
        return value * 1000.0
    return None


def derive_ndm_n(
    *, component_id: str, pier_name: str | None,
    pier_forces: ResultRowEvidenceBundle | None, selection_policy: Mapping[str, Any] | None,
) -> DerivedQuantity:
    """Derive Ndm only under a complete explicit result-selection policy."""
    if pier_forces is None or pier_forces.table_key != "pier_forces":
        return DerivedQuantity(None, "BLOCKED", "VERIFIED_LIVE Pier Forces raw evidence is unavailable")
    policy = selection_policy if isinstance(selection_policy, Mapping) else {}
    missing = [field for field in _REQUIRED_NDM_POLICY_FIELDS if field not in policy]
    if missing:
        return DerivedQuantity(None, "BLOCKED", "Ndm result policy is incomplete: " + ", ".join(missing))
    if not pier_name:
        return DerivedQuantity(None, "BLOCKED", "Wall-to-pier result identity is unavailable")
    eligible_cases = policy.get("eligible_output_cases")
    if not isinstance(eligible_cases, (list, tuple, set)) or not eligible_cases:
        return DerivedQuantity(None, "BLOCKED", "Ndm cannot select a result merely by output-case name")
    governing_location = str(policy.get("governing_location"))
    compression_sign = str(policy.get("compression_sign"))
    envelope_rule = str(policy.get("envelope_rule"))
    spectrum_rule = str(policy.get("response_spectrum_handling"))
    if governing_location not in {"Top", "Bottom", "BOTH_ENVELOPE"}:
        return DerivedQuantity(None, "BLOCKED", "Pier Top/Bottom governing-location policy is unresolved")
    if compression_sign not in {"POSITIVE", "NEGATIVE"}:
        return DerivedQuantity(None, "BLOCKED", "Pier compression sign policy is unresolved")
    if envelope_rule not in {"MAX_COMPRESSION", "SIGNED_MAX_MIN"}:
        return DerivedQuantity(None, "BLOCKED", "Pier signed envelope rule is unresolved")
    if spectrum_rule in {"", "UNKNOWN", "BY_NAME"}:
        return DerivedQuantity(None, "BLOCKED", "Response-spectrum handling is unresolved")
    rows = []
    for row in pier_forces.rows:
        if row.get("Pier") != pier_name or row.get("OutputCase") not in eligible_cases:
            continue
        if governing_location != "BOTH_ENVELOPE" and row.get("Location") != governing_location:
            continue
        p = row.get("P")
        if isinstance(p, bool) or not isinstance(p, (int, float)):
            continue
        rows.append(row)
    if not rows:
        return DerivedQuantity(None, "BLOCKED", "No Pier Forces row satisfies the complete authoritative Ndm policy")
    p_values = [float(row["P"]) for row in rows]
    signed = max(p_values) if compression_sign == "POSITIVE" else min(p_values)
    compression_source = signed if compression_sign == "POSITIVE" else -signed
    if compression_source < 0:
        return DerivedQuantity(None, "BLOCKED", "Selected pier result is not compressive under the authoritative sign policy")
    compression_n = _to_newtons(compression_source, pier_forces)
    if compression_n is None:
        return DerivedQuantity(None, "BLOCKED", "Pier Forces force unit is unresolved; Ndm cannot be normalized to N")
    return DerivedQuantity(compression_n, "RESOLVED", evidence=tuple(dict(row) for row in rows))


def derive_net_section_area_mm2(component_id: str, topology_context: Mapping[str, Any] | None) -> DerivedQuantity:
    context = topology_context if isinstance(topology_context, Mapping) else {}
    if "shell_surface_area" in context or "wall_shell_surface_area" in context:
        return DerivedQuantity(None, "BLOCKED", "Vertical shell surface Area is not wall net cross-sectional Ac")
    if context.get("topology_verified") is not True or context.get("section_semantics_verified") is not True:
        return DerivedQuantity(None, "BLOCKED", "Exact parent opening-to-wall and section semantics are not established")
    gross = context.get("gross_cross_section_area_mm2")
    if isinstance(gross, bool) or not isinstance(gross, (int, float)) or float(gross) <= 0:
        return DerivedQuantity(None, "BLOCKED", "Gross wall cross-sectional area is unavailable")
    openings = context.get("openings", ())
    if not isinstance(openings, (list, tuple)):
        return DerivedQuantity(None, "BLOCKED", "Opening topology evidence is malformed")
    deducted = 0.0
    evidence = []
    for opening in openings:
        if not isinstance(opening, Mapping) or opening.get("parent_wall_id") != component_id:
            continue
        if opening.get("topology_verified") is not True or opening.get("section_semantics") != "NET_SECTION_OPENING":
            return DerivedQuantity(None, "BLOCKED", "Parent opening exists but its net-section semantics are not proven")
        area = opening.get("opening_cross_section_area_mm2")
        if isinstance(area, bool) or not isinstance(area, (int, float)) or float(area) < 0:
            return DerivedQuantity(None, "BLOCKED", "Opening cross-sectional area is invalid")
        deducted += float(area)
        evidence.append(dict(opening))
    net = float(gross) - deducted
    if net <= 0:
        return DerivedQuantity(None, "BLOCKED", "Derived wall net cross-sectional area is non-positive")
    return DerivedQuantity(net, "RESOLVED", evidence=tuple(evidence))


__all__ = [
    "DerivedQuantity", "derive_highest_applicable_story_height_mm", "derive_ndm_n",
    "derive_net_section_area_mm2", "directional_eq714_quantities", "resolve_special_branch_applicability",
]
