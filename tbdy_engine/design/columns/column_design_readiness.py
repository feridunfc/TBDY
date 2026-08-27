"""Canonical FND-COL-2 column design-demand/stability readiness authority.

This module is a bounded orchestration layer over the accepted VS6 pure kernels.
It deliberately does not perform ETABS acquisition, section-capacity/PMM work,
reinforcement layout, or ENGINE_SELECTED_REBAR selection.

The authority derives combination scope, TS500 minimum eccentricity,
slenderness basis/neglect treatment, and the stability/reanalysis boundary from
source-bound evidence.  Callers cannot authorize readiness by supplying custom
``RESOLVED`` flags.

Concurrent P-M2-M3 states are preserved exactly.  No independent component
maximum or synthetic PMM envelope is formed here.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from tbdy_engine.design.columns.column_design_demand_engine import (
    ColumnComboDefinition,
    ColumnDesignDemandEngineResult,
    evaluate_column_design_demands,
)
from tbdy_engine.design.columns.minimum_eccentricity import (
    ColumnMinimumEccentricityResult,
    apply_ts500_minimum_eccentricity,
)
from tbdy_engine.design.columns.rebar_selection import ColumnDemandState
from tbdy_engine.design.columns.slenderness import (
    ColumnSlendernessBasis,
    ColumnSlendernessResult,
    evaluate_ts500_column_slenderness,
)
from tbdy_engine.design.columns.slenderness_basis import (
    ColumnSlendernessBasisResolution,
    ColumnSlendernessEvidence,
    resolve_ts500_column_slenderness_basis,
)
from tbdy_engine.design.columns.stability_stiffness_basis import (
    StabilityStiffnessBasisResolution,
)


READY = "READY"
BLOCKED = "BLOCKED"
REANALYSIS_REQUIRED = "REANALYSIS_REQUIRED"
UNRESOLVED = "UNRESOLVED"

ANALYSIS_BASIS_MATCH = "MATCH"
ANALYSIS_BASIS_REANALYSIS_REQUIRED = "REANALYSIS_REQUIRED"
ANALYSIS_BASIS_UNRESOLVED = "UNRESOLVED"

SECOND_ORDER_NOT_REQUIRED = "NOT_REQUIRED"
SECOND_ORDER_MOMENT_MAGNIFICATION_REQUIRED = "MOMENT_MAGNIFICATION_REQUIRED"
SECOND_ORDER_GENERAL_ANALYSIS_REQUIRED = "GENERAL_SECOND_ORDER_ANALYSIS_REQUIRED"
SECOND_ORDER_UNRESOLVED = "UNRESOLVED"
SECOND_ORDER_BLOCKED = "BLOCKED"

AUTHORITY = "FND_COL_2_CANONICAL_COLUMN_DESIGN_DEMAND_READINESS"


class ColumnDesignReadinessError(ValueError):
    """Raised when canonical readiness inputs are malformed or inconsistent."""


@dataclass(frozen=True, slots=True)
class ColumnDesignDemandReadiness:
    component_id: str
    status: str
    analysis_basis_status: str
    second_order_treatment: str
    stability_sway_status: str
    design_demands: ColumnDesignDemandEngineResult
    minimum_eccentricity: ColumnMinimumEccentricityResult
    slenderness_basis: ColumnSlendernessBasisResolution
    slenderness: ColumnSlendernessResult
    demand_states: tuple[ColumnDemandState, ...]
    blocked_items: tuple[str, ...]
    source_refs: tuple[str, ...]
    stability_stiffness_basis: StabilityStiffnessBasisResolution | None = None
    authority: str = AUTHORITY

    @property
    def ready(self) -> bool:
        return self.status == READY

    @property
    def reanalysis_required(self) -> bool:
        return self.status == REANALYSIS_REQUIRED


def _text(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ColumnDesignReadinessError(f"{label} must be a nonblank canonical string")
    return value


def _prepromoted_resolution(
    component_id: str,
    basis: ColumnSlendernessBasis,
) -> ColumnSlendernessBasisResolution:
    if basis.component_id != component_id:
        raise ColumnDesignReadinessError("slenderness_basis.component_id differs from component_id")
    refs = tuple(dict.fromkeys((*basis.source_refs, *basis.m2.source_refs, *basis.m3.source_refs)))
    return ColumnSlendernessBasisResolution(
        component_id=component_id,
        status="PROVEN_TS500_SLENDERNESS_BASIS",
        basis=basis,
        blocked_items=(),
        derivation_notes=("Canonical pre-promoted TS500 slenderness basis supplied",),
        source_refs=refs,
    )


def _conservative_ratio_axes(resolution: ColumnSlendernessBasisResolution) -> frozenset[str]:
    axes: set[str] = set()
    for note in resolution.derivation_notes:
        if "conservative all-curvature screening bound used" not in note:
            continue
        if note.startswith("M2:"):
            axes.add("M2")
        elif note.startswith("M3:"):
            axes.add("M3")
    return frozenset(axes)


def _sway_status(resolution: ColumnSlendernessBasisResolution) -> str:
    basis = resolution.basis
    if basis is None:
        return "UNRESOLVED"
    values = {basis.m2.sway_classification, basis.m3.sway_classification}
    if len(values) == 1:
        return next(iter(values))
    return "AXIS_SPECIFIC"


def _refs(
    minimum: ColumnMinimumEccentricityResult,
    basis: ColumnSlendernessBasisResolution,
    slenderness: ColumnSlendernessResult,
    stiffness: StabilityStiffnessBasisResolution | None,
) -> tuple[str, ...]:
    values: list[str] = []
    for source in (
        minimum.source_refs,
        basis.source_refs,
        slenderness.source_refs,
        () if stiffness is None else stiffness.source_refs,
    ):
        for item in source:
            ref = _text(item, "source_ref")
            if ref not in values:
                values.append(ref)
    return tuple(values)


def resolve_column_design_demand_readiness(
    *,
    component_id: str,
    combo_definitions: Sequence[ColumnComboDefinition],
    constituent_case_demands: Sequence[ColumnDemandState],
    width_mm: float,
    depth_mm: float,
    slenderness_evidence: ColumnSlendernessEvidence | None = None,
    slenderness_basis: ColumnSlendernessBasis | None = None,
    stability_stiffness_basis: StabilityStiffnessBasisResolution | None = None,
    observed_combo_demands: Sequence[ColumnDemandState] = (),
    verify_observed_rows: bool = False,
    force_tolerance_n: float = 250.0,
    moment_tolerance_nmm: float = 250_000.0,
) -> ColumnDesignDemandReadiness:
    """Derive authoritative demand/stability readiness without caller flags.

    The approximate TS500 7.6.2 method is intentionally bounded.  When a
    source-bound actual M1/M2 ratio proves that the 7.6.2.3 neglect limit is
    exceeded, moment magnification is required but not performed in this slice.
    When only the conservative ``M1/M2=+1`` screening bound was used, failure of
    that screening bound is *unresolved*, not proof that magnification is
    required.

    ``lk/i > 100`` requires the TS500 7.6.1 general second-order route; the
    current first-order design-demand population is therefore incompatible and
    the canonical state is ``REANALYSIS_REQUIRED``.
    """
    component = _text(component_id, "component_id")
    if slenderness_evidence is not None and slenderness_basis is not None:
        raise ColumnDesignReadinessError("supply slenderness_evidence or slenderness_basis, not both")

    design_demands = evaluate_column_design_demands(
        component_id=component,
        definitions=combo_definitions,
        case_demands=constituent_case_demands,
        observed_combo_demands=observed_combo_demands,
        verify_observed_rows=verify_observed_rows,
        force_tolerance_n=force_tolerance_n,
        moment_tolerance_nmm=moment_tolerance_nmm,
    )
    minimum = apply_ts500_minimum_eccentricity(
        component_id=component,
        width_mm=width_mm,
        depth_mm=depth_mm,
        demands=design_demands.promoted_states,
        source_refs=("TS500 6.3.10 Eq.6.16",),
    )

    if slenderness_basis is not None:
        basis_resolution = _prepromoted_resolution(component, slenderness_basis)
    else:
        basis_resolution = resolve_ts500_column_slenderness_basis(
            slenderness_evidence,
            component_id=component,
        )
    slenderness = evaluate_ts500_column_slenderness(
        component_id=component,
        basis=basis_resolution.basis,
    )

    blocked_items: list[str] = []
    status = BLOCKED
    analysis_basis_status = ANALYSIS_BASIS_UNRESOLVED
    second_order_treatment = SECOND_ORDER_BLOCKED

    if not design_demands.combination_scope_resolved:
        blocked_items.extend(f"COMBINATION_SCOPE:{name}" for name in design_demands.blocked_combo_names)
    elif not minimum.resolved:
        blocked_items.append("MINIMUM_ECCENTRICITY_NOT_RESOLVED")
    else:
        sway_not_promoted = any(
            item.endswith(":SWAY_CLASSIFICATION_NOT_PROMOTED")
            for item in basis_resolution.blocked_items
        )
        if (
            stability_stiffness_basis is not None
            and stability_stiffness_basis.reanalysis_required
            and sway_not_promoted
        ):
            status = REANALYSIS_REQUIRED
            analysis_basis_status = ANALYSIS_BASIS_REANALYSIS_REQUIRED
            second_order_treatment = SECOND_ORDER_GENERAL_ANALYSIS_REQUIRED
            blocked_items.append(stability_stiffness_basis.status)
        elif not basis_resolution.resolved:
            blocked_items.extend(basis_resolution.blocked_items)
            unresolved_basis = any(
                item.endswith(":SWAY_CLASSIFICATION_NOT_PROMOTED")
                or item.endswith(":M1_M2_RATIO_NOT_PROMOTED")
                for item in basis_resolution.blocked_items
            )
            status = UNRESOLVED if unresolved_basis else BLOCKED
            analysis_basis_status = ANALYSIS_BASIS_UNRESOLVED
            second_order_treatment = SECOND_ORDER_UNRESOLVED if unresolved_basis else SECOND_ORDER_BLOCKED
        elif slenderness.status == "GENERAL_SECOND_ORDER_ANALYSIS_REQUIRED":
            status = REANALYSIS_REQUIRED
            analysis_basis_status = ANALYSIS_BASIS_REANALYSIS_REQUIRED
            second_order_treatment = SECOND_ORDER_GENERAL_ANALYSIS_REQUIRED
            blocked_items.append("TS500_7.6.1_GENERAL_SECOND_ORDER_ANALYSIS_REQUIRED")
        elif slenderness.requires_moment_magnification:
            conservative_axes = _conservative_ratio_axes(basis_resolution)
            failing_axes = {
                item.axis
                for item in (slenderness.m2, slenderness.m3)
                if item.status == "MOMENT_MAGNIFICATION_REQUIRED"
            }
            if failing_axes & conservative_axes:
                status = UNRESOLVED
                analysis_basis_status = ANALYSIS_BASIS_UNRESOLVED
                second_order_treatment = SECOND_ORDER_UNRESOLVED
                blocked_items.extend(
                    f"{axis}:ACTUAL_M1_M2_RATIO_REQUIRED" for axis in sorted(failing_axes & conservative_axes)
                )
            else:
                status = BLOCKED
                analysis_basis_status = ANALYSIS_BASIS_MATCH
                second_order_treatment = SECOND_ORDER_MOMENT_MAGNIFICATION_REQUIRED
                blocked_items.append("TS500_7.6.2_MOMENT_MAGNIFICATION_NOT_IMPLEMENTED_IN_FND_COL_2")
        elif slenderness.resolved:
            status = READY
            analysis_basis_status = ANALYSIS_BASIS_MATCH
            second_order_treatment = SECOND_ORDER_NOT_REQUIRED
        else:
            status = UNRESOLVED
            analysis_basis_status = ANALYSIS_BASIS_UNRESOLVED
            second_order_treatment = SECOND_ORDER_UNRESOLVED
            blocked_items.append(slenderness.status)

    return ColumnDesignDemandReadiness(
        component_id=component,
        status=status,
        analysis_basis_status=analysis_basis_status,
        second_order_treatment=second_order_treatment,
        stability_sway_status=_sway_status(basis_resolution),
        design_demands=design_demands,
        minimum_eccentricity=minimum,
        slenderness_basis=basis_resolution,
        slenderness=slenderness,
        demand_states=minimum.states,
        blocked_items=tuple(dict.fromkeys(blocked_items)),
        source_refs=_refs(minimum, basis_resolution, slenderness, stability_stiffness_basis),
        stability_stiffness_basis=stability_stiffness_basis,
    )


__all__ = [
    "ANALYSIS_BASIS_MATCH",
    "ANALYSIS_BASIS_REANALYSIS_REQUIRED",
    "ANALYSIS_BASIS_UNRESOLVED",
    "AUTHORITY",
    "BLOCKED",
    "ColumnDesignDemandReadiness",
    "ColumnDesignReadinessError",
    "READY",
    "REANALYSIS_REQUIRED",
    "SECOND_ORDER_BLOCKED",
    "SECOND_ORDER_GENERAL_ANALYSIS_REQUIRED",
    "SECOND_ORDER_MOMENT_MAGNIFICATION_REQUIRED",
    "SECOND_ORDER_NOT_REQUIRED",
    "SECOND_ORDER_UNRESOLVED",
    "UNRESOLVED",
    "resolve_column_design_demand_readiness",
]
