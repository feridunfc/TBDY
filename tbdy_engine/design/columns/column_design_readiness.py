"""Canonical FND-COL-2 column design-demand/stability readiness authority.

This module is a bounded orchestration layer over the accepted VS6 pure kernels.
It deliberately does not perform ETABS acquisition, section-capacity/PMM work,
reinforcement layout, or ENGINE_SELECTED_REBAR selection.

The authority derives combination scope, TS500 minimum eccentricity,
slenderness basis/neglect treatment, and the stability/reanalysis boundary from
source-bound evidence.  Callers cannot authorize readiness by supplying custom
``RESOLVED`` flags.

Concurrent P-M2-M3 states are preserved exactly.  No independent component
maximum or synthetic PMM envelope is formed here.  When TS500 moment
magnification is required, M2 and M3 remain independent local-axis pipelines
and are recombined only into the exact concurrent demand state that produced
them.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
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
from tbdy_engine.design.columns.moment_magnification import (
    ColumnMomentMagnificationAxisBasis,
    ColumnMomentMagnificationAxisResult,
    evaluate_ts500_axis_moment_magnification,
    magnify_concurrent_column_demand_state,
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
SECOND_ORDER_MOMENT_MAGNIFICATION_APPLIED = "MOMENT_MAGNIFICATION_APPLIED"
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
    moment_magnification_results: tuple[ColumnMomentMagnificationAxisResult, ...] = ()
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
    magnification: Sequence[ColumnMomentMagnificationAxisResult] = (),
) -> tuple[str, ...]:
    values: list[str] = []
    for source in (
        minimum.source_refs,
        basis.source_refs,
        slenderness.source_refs,
        () if stiffness is None else stiffness.source_refs,
        tuple(ref for result in magnification for ref in result.source_refs),
    ):
        for item in source:
            ref = _text(item, "source_ref")
            if ref not in values:
                values.append(ref)
    return tuple(values)


def _close(left: float, right: float) -> bool:
    return math.isclose(float(left), float(right), rel_tol=1e-10, abs_tol=1e-6)


def _apply_required_magnification(
    *,
    states: tuple[ColumnDemandState, ...],
    slenderness_basis: ColumnSlendernessBasis,
    slenderness: ColumnSlendernessResult,
    bases: Sequence[ColumnMomentMagnificationAxisBasis],
) -> tuple[
    tuple[ColumnDemandState, ...] | None,
    tuple[ColumnMomentMagnificationAxisResult, ...],
    tuple[str, ...],
]:
    required_axes = tuple(
        item.axis
        for item in (slenderness.m2, slenderness.m3)
        if item.status == "MOMENT_MAGNIFICATION_REQUIRED"
    )
    if not required_axes:
        return states, (), ()

    state_by_id = {state.state_id: state for state in states}
    if len(state_by_id) != len(states):
        raise ColumnDesignReadinessError("minimum-eccentricity demand states require unique state_id")

    supplied: dict[tuple[str, str], ColumnMomentMagnificationAxisBasis] = {}
    for basis in tuple(bases):
        if not isinstance(basis, ColumnMomentMagnificationAxisBasis):
            raise TypeError("moment_magnification_bases must contain ColumnMomentMagnificationAxisBasis")
        key = (basis.demand_state_id, basis.axis)
        if key in supplied:
            raise ColumnDesignReadinessError("duplicate demand-state/axis moment magnification basis")
        supplied[key] = basis

    expected = {
        (state.state_id, axis)
        for state in states
        for axis in required_axes
    }
    actual = set(supplied)
    missing = tuple(sorted(expected - actual))
    extra = tuple(sorted(actual - expected))
    if missing or extra:
        blockers = tuple(
            [f"{state_id}:{axis}:MOMENT_MAGNIFICATION_BASIS_MISSING" for state_id, axis in missing]
            + [f"{state_id}:{axis}:UNEXPECTED_MOMENT_MAGNIFICATION_BASIS" for state_id, axis in extra]
        )
        return None, (), blockers

    axis_slenderness = {"M2": slenderness.m2, "M3": slenderness.m3}
    axis_basis = {"M2": slenderness_basis.m2, "M3": slenderness_basis.m3}
    results: dict[tuple[str, str], ColumnMomentMagnificationAxisResult] = {}
    blockers: list[str] = []

    for key in sorted(expected):
        state_id, axis = key
        state = state_by_id[state_id]
        evidence = supplied[key]
        slender_axis = axis_slenderness[axis]
        regulatory_axis = axis_basis[axis]
        if slender_axis.effective_length_lk_mm is None or slender_axis.radius_of_gyration_i_mm is None:
            blockers.append(f"{state_id}:{axis}:SLENDERNESS_GEOMETRY_NOT_RESOLVED")
            continue
        if evidence.sway_classification != regulatory_axis.sway_classification:
            blockers.append(f"{state_id}:{axis}:SWAY_CLASSIFICATION_MISMATCH")
            continue
        if not _close(evidence.nd_compression_n, state.nd_compression_n):
            blockers.append(f"{state_id}:{axis}:AXIAL_DEMAND_IDENTITY_MISMATCH")
            continue
        if not _close(evidence.effective_length_lk_mm, slender_axis.effective_length_lk_mm):
            blockers.append(f"{state_id}:{axis}:EFFECTIVE_LENGTH_IDENTITY_MISMATCH")
            continue
        if not _close(evidence.radius_i_mm, slender_axis.radius_of_gyration_i_mm):
            blockers.append(f"{state_id}:{axis}:RADIUS_OF_GYRATION_IDENTITY_MISMATCH")
            continue
        if (
            regulatory_axis.moment_ratio_m1_over_m2 is not None
            and not _close(evidence.m1_over_m2, regulatory_axis.moment_ratio_m1_over_m2)
        ):
            blockers.append(f"{state_id}:{axis}:M1_M2_RATIO_IDENTITY_MISMATCH")
            continue
        result = evaluate_ts500_axis_moment_magnification(evidence)
        results[key] = result
        blockers.extend(
            f"{state_id}:{axis}:{item}" for item in result.blockers
        )

    if blockers or set(results) != expected:
        return None, tuple(results[key] for key in sorted(results)), tuple(dict.fromkeys(blockers))

    magnified: list[ColumnDemandState] = []
    for state in states:
        m2 = results.get((state.state_id, "M2"))
        m3 = results.get((state.state_id, "M3"))
        magnified.append(
            magnify_concurrent_column_demand_state(state, m2=m2, m3=m3)
        )
    return (
        tuple(magnified),
        tuple(results[key] for key in sorted(results)),
        (),
    )


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
    moment_magnification_bases: Sequence[ColumnMomentMagnificationAxisBasis] = (),
    observed_combo_demands: Sequence[ColumnDemandState] = (),
    verify_observed_rows: bool = False,
    force_tolerance_n: float = 250.0,
    moment_tolerance_nmm: float = 250_000.0,
) -> ColumnDesignDemandReadiness:
    """Derive authoritative demand/stability readiness without caller flags.

    The second-order branch is conditional and axis-specific.  ``lk/i`` first
    determines whether second-order treatment is required.  Only axes with
    ``MOMENT_MAGNIFICATION_REQUIRED`` may enter the TS500 7.6.2.4-7.6.2.6
    kernel.  ``lk/i > 100`` remains a hard boundary to the general second-order
    route and is never forced through moment magnification.
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
    magnification_results: tuple[ColumnMomentMagnificationAxisResult, ...] = ()
    final_states = minimum.states
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
                assert basis_resolution.basis is not None
                magnified, magnification_results, magnification_blockers = _apply_required_magnification(
                    states=minimum.states,
                    slenderness_basis=basis_resolution.basis,
                    slenderness=slenderness,
                    bases=moment_magnification_bases,
                )
                if magnified is None:
                    status = BLOCKED
                    analysis_basis_status = ANALYSIS_BASIS_MATCH
                    second_order_treatment = SECOND_ORDER_MOMENT_MAGNIFICATION_REQUIRED
                    blocked_items.extend(magnification_blockers)
                else:
                    final_states = magnified
                    status = READY
                    analysis_basis_status = ANALYSIS_BASIS_MATCH
                    second_order_treatment = SECOND_ORDER_MOMENT_MAGNIFICATION_APPLIED
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
        demand_states=final_states,
        blocked_items=tuple(dict.fromkeys(blocked_items)),
        source_refs=_refs(
            minimum,
            basis_resolution,
            slenderness,
            stability_stiffness_basis,
            magnification_results,
        ),
        stability_stiffness_basis=stability_stiffness_basis,
        moment_magnification_results=magnification_results,
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
    "SECOND_ORDER_MOMENT_MAGNIFICATION_APPLIED",
    "SECOND_ORDER_MOMENT_MAGNIFICATION_REQUIRED",
    "SECOND_ORDER_NOT_REQUIRED",
    "SECOND_ORDER_UNRESOLVED",
    "UNRESOLVED",
    "resolve_column_design_demand_readiness",
]
