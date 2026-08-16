"""Engineering-only helpers for wall applicability and derived result quantities.

These helpers do not promote derived quantities into FeatureSnapshot facts or
VERIFIED_LIVE sources. CheckEngine owns applicability execution; Coverage may
query only whether the same frozen factual context is sufficient to execute it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from tbdy_engine.checks.ndm_selection import (
    EngineeringQuantityRequest, ReviewedNdmLoadBinding, ReviewedNdmPolicy, select_ndm_demand,
)
from tbdy_engine.features.result_evidence import ResultRowEvidenceBundle
from tbdy_engine.features.wall_critical_evidence import (
    WallCriticalHeightFactualEvidence,
    WallRegulatoryReferenceFacts,
)


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


@dataclass(frozen=True, slots=True)
class WallCriticalSegment:
    """One engineering-derived §7.6.2 reference segment."""

    reference_story: str
    reference_elevation_mm: float
    hw_mm: float
    lw_mm: float
    bw_mm: float
    hw_over_lw: float
    hcr_lower_bound_mm: float
    hcr_cap_mm: float
    hcr_governing_mm: float
    critical_start_elevation_mm: float
    critical_end_elevation_mm: float
    reference_reason: str


@dataclass(frozen=True, slots=True)
class WallCriticalHeightDerivation:
    """Engineering-derived Hw/Hcr state; never a FeatureSnapshot fact."""

    status: str
    segments: tuple[WallCriticalSegment, ...] = ()
    diagnostic: str | None = None

    @property
    def applicable_segments(self) -> tuple[WallCriticalSegment, ...]:
        return tuple(segment for segment in self.segments if segment.hw_over_lw > 2.0)

    @property
    def end_regions_required(self) -> bool | None:
        if self.status != "RESOLVED":
            return None
        return bool(self.applicable_segments)

    @property
    def governing_hcr_mm(self) -> float | None:
        applicable = self.applicable_segments
        return max((segment.hcr_governing_mm for segment in applicable), default=None)


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
    story_name: str | None = None,
    load_binding: ReviewedNdmLoadBinding | None = None,
    policy: ReviewedNdmPolicy | None = None,
    selection_policy: Mapping[str, Any] | None = None,
) -> DerivedQuantity:
    """Derive Ndm only through the reviewed B2 result-selection authority."""
    if pier_forces is None or pier_forces.table_key != "pier_forces":
        return DerivedQuantity(None, "BLOCKED", "VERIFIED_LIVE Pier Forces raw evidence is unavailable")
    if not pier_forces.is_full_capture:
        return DerivedQuantity(
            None, "BLOCKED",
            "Ndm requires runtime FULL Pier Forces acquisition; truncated/sampled/partial evidence cannot be selected",
        )
    if selection_policy is not None and policy is None:
        return DerivedQuantity(
            None, "BLOCKED",
            "Legacy selection_policy mapping is not implemented as a ReviewedNdmPolicy authority",
        )
    if not isinstance(story_name, str) or not story_name.strip():
        return DerivedQuantity(None, "BLOCKED", "Exact wall Story result identity is unavailable for Ndm selection")
    if not isinstance(pier_name, str) or not pier_name.strip():
        return DerivedQuantity(None, "BLOCKED", "Exact wall-to-pier result identity is unavailable for Ndm selection")
    try:
        request = EngineeringQuantityRequest(
            request_id=f"Ndm:{component_id}",
            component_id=component_id,
            story=story_name,
            pier=pier_name,
        )
        demand = select_ndm_demand(request, pier_forces, load_binding, policy)
    except (TypeError, ValueError) as exc:
        return DerivedQuantity(None, "BLOCKED", str(exc))
    trace_evidence = ({
        "selection_trace": demand.trace.as_dict(),
        "provenance": list(demand.provenance),
    },)
    return DerivedQuantity(
        demand.ndm_n,
        demand.availability.value,
        demand.trace.reason,
        evidence=trace_evidence,
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


def _rigid_basement_state(
    facts: WallRegulatoryReferenceFacts | None,
) -> tuple[bool | None, str | None]:
    if facts is None:
        return None, "Foundation/regulatory reference facts are unavailable"
    perimeter = facts.rigid_basement_perimeter_walls
    diaphragm = facts.rigid_basement_diaphragm
    if perimeter is False or diaphragm is False:
        return False, None
    if perimeter is True and diaphragm is True:
        return True, None
    return None, "Rigid-basement applicability facts are incomplete"


def derive_wall_critical_height(
    bundle: WallCriticalHeightFactualEvidence | None,
    reference_facts: WallRegulatoryReferenceFacts | None,
) -> WallCriticalHeightDerivation:
    """Derive Hw, reference levels, applicability and governing Hcr from facts.

    Reduction detection is engineering-side: plan length reduction is strict
    >20% and section-width/thickness reduction is strict >50%. Regulatory
    reference truth is supplied once at run/system grain. No property-name or
    magnitude-unit inference is used.
    """
    if bundle is None or not isinstance(bundle, WallCriticalHeightFactualEvidence):
        return WallCriticalHeightDerivation("BLOCKED", diagnostic="Canonical wall critical-height factual evidence is unavailable")
    if bundle.vertical_continuity_proven is not True:
        return WallCriticalHeightDerivation("BLOCKED", diagnostic="Wall vertical continuity is not proven")
    if bundle.section_reduction_evidence_complete is not True:
        return WallCriticalHeightDerivation("BLOCKED", diagnostic="Story-by-story section reduction evidence is incomplete")
    rows = tuple(bundle.story_geometry)
    if not rows:
        return WallCriticalHeightDerivation("BLOCKED", diagnostic="Story-by-story wall geometry is unavailable")
    for lower, upper in zip(rows, rows[1:]):
        if abs(lower.top_elevation_mm - upper.base_elevation_mm) > 1e-6:
            return WallCriticalHeightDerivation("BLOCKED", diagnostic="Wall story geometry has an elevation gap despite continuity proof")
    if reference_facts is None or not isinstance(reference_facts, WallRegulatoryReferenceFacts):
        return WallCriticalHeightDerivation("BLOCKED", diagnostic="Run-level foundation/regulatory reference facts are unavailable")
    if reference_facts.foundation_top_elevation_mm is None:
        return WallCriticalHeightDerivation("BLOCKED", diagnostic="Foundation-top elevation is not proven")
    rigid, rigid_reason = _rigid_basement_state(reference_facts)
    if rigid is None:
        return WallCriticalHeightDerivation("BLOCKED", diagnostic=rigid_reason)
    below_extension = 0.0
    if rigid:
        if reference_facts.ground_floor_elevation_mm is None:
            return WallCriticalHeightDerivation("BLOCKED", diagnostic="Rigid-basement case requires proven ground-floor elevation")
        if reference_facts.first_basement_story_height_mm is None:
            return WallCriticalHeightDerivation("BLOCKED", diagnostic="Rigid-basement case requires proven first-basement story height")
        base_reference = float(reference_facts.ground_floor_elevation_mm)
        below_extension = float(reference_facts.first_basement_story_height_mm)
        base_reason = "RIGID_BASEMENT_GROUND_FLOOR"
    else:
        base_reference = float(reference_facts.foundation_top_elevation_mm)
        base_reason = "FOUNDATION_TOP"
    eligible = tuple(row for row in rows if row.top_elevation_mm > base_reference + 1e-6)
    if not eligible:
        return WallCriticalHeightDerivation("BLOCKED", diagnostic="No wall geometry exists above the regulatory reference level")
    first = next((row for row in eligible if row.base_elevation_mm <= base_reference + 1e-6 < row.top_elevation_mm + 1e-6), None)
    if first is None:
        return WallCriticalHeightDerivation("BLOCKED", diagnostic="Regulatory reference level does not intersect proven wall geometry")
    references: list[tuple[int, float, str]] = []
    first_index = rows.index(first)
    references.append((first_index, base_reference, base_reason))
    for index in range(first_index + 1, len(rows)):
        lower = rows[index - 1]
        upper = rows[index]
        length_reduction = upper.wall_length_mm < 0.8 * lower.wall_length_mm
        width_reduction = upper.wall_thickness_mm < 0.5 * lower.wall_thickness_mm
        if length_reduction or width_reduction:
            reasons = []
            if length_reduction:
                reasons.append("PLAN_LENGTH_REDUCTION_GT20")
            if width_reduction:
                reasons.append("SECTION_WIDTH_REDUCTION_GT50")
            references.append((index, upper.base_elevation_mm, "+".join(reasons)))
    wall_top = max(row.top_elevation_mm for row in rows)
    segments: list[WallCriticalSegment] = []
    for index, reference, reason in references:
        row = rows[index]
        hw = wall_top - reference
        if hw <= 0:
            return WallCriticalHeightDerivation("BLOCKED", diagnostic="Derived Hw is non-positive")
        lw = row.wall_length_mm
        bw = row.wall_thickness_mm
        lower_bound = max(lw, hw / 6.0)
        cap = 2.0 * lw
        hcr = min(lower_bound, cap)
        critical_start = reference - (below_extension if reason == "RIGID_BASEMENT_GROUND_FLOOR" else 0.0)
        segments.append(WallCriticalSegment(
            reference_story=row.story,
            reference_elevation_mm=reference,
            hw_mm=hw,
            lw_mm=lw,
            bw_mm=bw,
            hw_over_lw=hw / lw,
            hcr_lower_bound_mm=lower_bound,
            hcr_cap_mm=cap,
            hcr_governing_mm=hcr,
            critical_start_elevation_mm=critical_start,
            critical_end_elevation_mm=reference + hcr,
            reference_reason=reason,
        ))
    return WallCriticalHeightDerivation("RESOLVED", segments=tuple(segments))


def critical_region_story_names(
    bundle: WallCriticalHeightFactualEvidence,
    derivation: WallCriticalHeightDerivation,
) -> tuple[str, ...]:
    """Return story identities intersecting any applicable derived critical interval."""
    if derivation.status != "RESOLVED":
        return ()
    applicable = derivation.applicable_segments
    names: list[str] = []
    for row in bundle.story_geometry:
        if any(
            row.top_elevation_mm > segment.critical_start_elevation_mm + 1e-6
            and row.base_elevation_mm < segment.critical_end_elevation_mm - 1e-6
            for segment in applicable
        ):
            names.append(row.story)
    return tuple(names)


__all__ = [
    "DerivedQuantity", "Eq714SystemEvidence", "ReviewedWallSystemContext",
    "WallCriticalHeightDerivation", "WallCriticalSegment", "critical_region_story_names",
    "derive_highest_applicable_story_height_mm", "derive_ndm_n",
    "derive_net_section_area_mm2", "derive_wall_critical_height",
    "directional_eq714_quantities", "resolve_special_branch_applicability",
    "special_branch_context_readiness",
]
