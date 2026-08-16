"""Engineering-only helpers for wall applicability and derived result quantities.

These helpers do not promote derived quantities into FeatureSnapshot facts or
VERIFIED_LIVE sources. CheckEngine owns applicability execution; Coverage may
query only whether the same frozen system context is sufficient to execute it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from tbdy_engine.features.result_evidence import ResultRowEvidenceBundle


@dataclass(frozen=True, slots=True)
class Eq714SystemEvidence:
    """Directional/system engineering evidence used by §7.6.1.3 applicability."""

    condition_1_satisfied: bool | None
    condition_2_satisfied: bool | None
    directional_evidence: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name, value in (
            ("condition_1_satisfied", self.condition_1_satisfied),
            ("condition_2_satisfied", self.condition_2_satisfied),
        ):
            if value is not None and not isinstance(value, bool):
                raise TypeError(f"{name} must be bool or None")
        object.__setattr__(self, "directional_evidence", MappingProxyType(dict(self.directional_evidence or {})))


@dataclass(frozen=True, slots=True)
class ReviewedWallSystemContext:
    """Single reviewed structural-system authority shared by every wall in a run."""

    system_id: str
    wall_only_status: bool | None
    eq714: Eq714SystemEvidence | None = None
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.system_id, str) or not self.system_id.strip():
            raise ValueError("ReviewedWallSystemContext requires a nonblank system_id")
        if self.wall_only_status is not None and not isinstance(self.wall_only_status, bool):
            raise TypeError("wall_only_status must be bool or None")
        if self.eq714 is not None and not isinstance(self.eq714, Eq714SystemEvidence):
            raise TypeError("eq714 must be Eq714SystemEvidence or None")
        object.__setattr__(self, "system_id", self.system_id.strip())
        object.__setattr__(self, "evidence_refs", tuple(str(item) for item in self.evidence_refs))


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
    """Derive directional Eq.7.14 quantities without collapsing X/Y or floors."""
    sum_ag_x = sum(float(v) for v in gross_wall_areas_mm2_by_axis.get("X", ()))
    sum_ag_y = sum(float(v) for v in gross_wall_areas_mm2_by_axis.get("Y", ()))
    sum_ap = sum(float(v) for v in floor_plan_areas_mm2_by_story.values())
    if sum_ap <= 0:
        raise ValueError("All-floor ΣAp requires positive factual floor-plan areas")
    out: dict[str, float | None] = {
        "sum_ag_x_mm2": sum_ag_x,
        "sum_ag_y_mm2": sum_ag_y,
        "sum_ap_all_floors_mm2": sum_ap,
        "sum_ag_x_over_sum_ap": sum_ag_x / sum_ap,
        "sum_ag_y_over_sum_ap": sum_ag_y / sum_ap,
        "vt_x_over_sum_ag_x_fctd": None,
        "vt_y_over_sum_ag_y_fctd": None,
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


def _special_branch_state(
    system_context: ReviewedWallSystemContext | None,
) -> tuple[bool | None, str | None]:
    if system_context is None:
        return None, "Reviewed regulatory structural-system context is unavailable"
    if not isinstance(system_context, ReviewedWallSystemContext):
        return None, "Reviewed regulatory structural-system context has invalid type"
    if system_context.wall_only_status is None:
        return None, "Reviewed wall-only structural-system classification is UNKNOWN"
    if system_context.wall_only_status is False:
        return False, None
    eq714 = system_context.eq714
    if eq714 is None:
        return None, "Directional/system Eq.7.14 evidence is unavailable"
    condition_1 = eq714.condition_1_satisfied
    condition_2 = eq714.condition_2_satisfied
    if condition_1 is False or condition_2 is False:
        return False, None
    if condition_1 is True and condition_2 is True:
        return True, None
    return None, "Eq.7.14 applicability remains UNKNOWN because at least one condition is unresolved"


def special_branch_context_readiness(
    system_context: ReviewedWallSystemContext | None,
) -> tuple[bool, str | None]:
    """Return only whether system evidence is sufficient for CheckEngine execution."""
    state, reason = _special_branch_state(system_context)
    return state is not None, reason


def resolve_special_branch_applicability(
    system_context: ReviewedWallSystemContext | None,
) -> tuple[bool | None, str | None]:
    """CheckEngine-facing §7.6.1.3 applicability at regulatory-system grain."""
    return _special_branch_state(system_context)


def derive_highest_applicable_story_height_mm(value: Any) -> DerivedQuantity:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or float(value) <= 0:
        return DerivedQuantity(None, "BLOCKED", "Highest applicable story height is not proven for this wall")
    return DerivedQuantity(float(value), "RESOLVED")


def derive_ndm_n(
    *, component_id: str, pier_name: str | None,
    pier_forces: ResultRowEvidenceBundle | None,
    selection_policy: Mapping[str, Any] | None = None,
) -> DerivedQuantity:
    """Keep Ndm blocked until a frozen authoritative result-selection policy exists."""
    del component_id, pier_name, selection_policy
    if pier_forces is None or pier_forces.table_key != "pier_forces":
        return DerivedQuantity(None, "BLOCKED", "VERIFIED_LIVE Pier Forces raw evidence is unavailable")
    if not pier_forces.is_full_capture:
        return DerivedQuantity(
            None,
            "BLOCKED",
            "Ndm requires runtime FULL Pier Forces acquisition; truncated/sampled/partial evidence cannot form an envelope",
        )
    return DerivedQuantity(
        None,
        "BLOCKED",
        "Authoritative Ndm result-selection policy is not implemented: directional selection, response-spectrum handling, Max/Min, signed envelope, and governing-location semantics remain unresolved",
    )


def derive_net_section_area_mm2(component_id: str, topology_context: Mapping[str, Any] | None) -> DerivedQuantity:
    """Derive net Ac from proven section/opening topology only."""
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
    "DerivedQuantity", "Eq714SystemEvidence", "ReviewedWallSystemContext",
    "derive_highest_applicable_story_height_mm", "derive_ndm_n",
    "derive_net_section_area_mm2", "directional_eq714_quantities",
    "resolve_special_branch_applicability", "special_branch_context_readiness",
]
