"""Canonical FND-COL-2 column design-demand/stability readiness authority.

This module is a bounded orchestration layer over the accepted VS6 pure kernels.
It deliberately does not perform ETABS acquisition, section-capacity/PMM work,
reinforcement layout, or ENGINE_SELECTED_REBAR selection.

Concurrent P-M2-M3 states are preserved exactly.  Legacy single-basis callers
remain supported.  The COLUMN-R1 production join may additionally provide one
canonical slenderness basis per output case; those bases are re-evaluated here
and can never authorize READY by flag alone.
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
class ColumnStateSlendernessBasis:
    """Canonical A21 slenderness basis bound to one exact output case."""

    output_case: str
    basis: ColumnSlendernessBasis
    source_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "output_case", _text(self.output_case, "output_case"))
        if not isinstance(self.basis, ColumnSlendernessBasis):
            raise TypeError("basis must be ColumnSlendernessBasis")
        refs = tuple(_text(item, "source_ref") for item in self.source_refs)
        if len(refs) != len(set(refs)):
            raise ColumnDesignReadinessError("state slenderness source_refs must be unique")
        object.__setattr__(self, "source_refs", refs)


@dataclass(frozen=True, slots=True)
class ColumnStateSlendernessEvaluation:
    output_case: str
    basis: ColumnSlendernessBasis
    result: ColumnSlendernessResult
    source_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ColumnDesignDemandReadiness:
    component_id: str
    status: str
    analysis_basis_status: str
    second_order_treatment: str
    stability_sway_status: str
    design_demands: ColumnDesignDemandEngineResult
    minimum_eccentricity: ColumnMinimumEccentricityResult
    slenderness_basis: ColumnSlendernessBasisResolution | None
    slenderness: ColumnSlendernessResult | None
    demand_states: tuple[ColumnDemandState, ...]
    blocked_items: tuple[str, ...]
    source_refs: tuple[str, ...]
    stability_stiffness_basis: StabilityStiffnessBasisResolution | None = None
    moment_magnification_results: tuple[ColumnMomentMagnificationAxisResult, ...] = ()
    state_slenderness: tuple[ColumnStateSlendernessEvaluation, ...] = ()
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


def _sway_status(resolution: ColumnSlendernessBasisResolution | None) -> str:
    if resolution is None or resolution.basis is None:
        return "UNRESOLVED"
    values = {resolution.basis.m2.sway_classification, resolution.basis.m3.sway_classification}
    if len(values) == 1:
        return next(iter(values))
    return "AXIS_SPECIFIC"


def _state_sway_status(rows: Sequence[ColumnStateSlendernessEvaluation]) -> str:
    values = {
        axis.sway_classification
        for row in rows
        for axis in (row.basis.m2, row.basis.m3)
    }
    if not values:
        return "UNRESOLVED"
    if len(values) == 1:
        return next(iter(values))
    return "AXIS_SPECIFIC"


def _refs(
    minimum: ColumnMinimumEccentricityResult,
    basis: ColumnSlendernessBasisResolution | None,
    slenderness: ColumnSlendernessResult | None,
    stiffness: StabilityStiffnessBasisResolution | None,
    magnification: Sequence[ColumnMomentMagnificationAxisResult] = (),
    state_slenderness: Sequence[ColumnStateSlendernessEvaluation] = (),
) -> tuple[str, ...]:
    values: list[str] = []
    sources = (
        minimum.source_refs,
        () if basis is None else basis.source_refs,
        () if slenderness is None else slenderness.source_refs,
        () if stiffness is None else stiffness.source_refs,
        tuple(ref for result in magnification for ref in result.source_refs),
        tuple(ref for row in state_slenderness for ref in row.source_refs),
    )
    for source in sources:
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
) -> tuple[tuple[ColumnDemandState, ...] | None, tuple[ColumnMomentMagnificationAxisResult, ...], tuple[str, ...]]:
    required_axes = tuple(
        item.axis for item in (slenderness.m2, slenderness.m3)
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
    expected = {(state.state_id, axis) for state in states for axis in required_axes}
    missing = tuple(sorted(expected - set(supplied)))
    extra = tuple(sorted(set(supplied) - expected))
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
        if regulatory_axis.moment_ratio_m1_over_m2 is not None and not _close(
            evidence.m1_over_m2, regulatory_axis.moment_ratio_m1_over_m2
        ):
            blockers.append(f"{state_id}:{axis}:M1_M2_RATIO_IDENTITY_MISMATCH")
            continue
        result = evaluate_ts500_axis_moment_magnification(evidence)
        results[key] = result
        blockers.extend(f"{state_id}:{axis}:{item}" for item in result.blockers)
    if blockers or set(results) != expected:
        return None, tuple(results[key] for key in sorted(results)), tuple(dict.fromkeys(blockers))
    magnified = tuple(
        magnify_concurrent_column_demand_state(
            state,
            m2=results.get((state.state_id, "M2")),
            m3=results.get((state.state_id, "M3")),
        )
        for state in states
    )
    return magnified, tuple(results[key] for key in sorted(results)), ()


def _evaluate_state_slenderness(
    *,
    component_id: str,
    states: tuple[ColumnDemandState, ...],
    carriers: Sequence[ColumnStateSlendernessBasis],
) -> tuple[tuple[ColumnStateSlendernessEvaluation, ...], tuple[str, ...]]:
    by_case: dict[str, ColumnStateSlendernessBasis] = {}
    for carrier in tuple(carriers):
        if not isinstance(carrier, ColumnStateSlendernessBasis):
            raise TypeError("state_slenderness_bases must contain ColumnStateSlendernessBasis")
        if carrier.output_case in by_case:
            raise ColumnDesignReadinessError("duplicate output_case state slenderness basis")
        if carrier.basis.component_id != component_id:
            raise ColumnDesignReadinessError("state slenderness basis component_id differs from component_id")
        by_case[carrier.output_case] = carrier
    expected_cases = {state.output_case for state in states}
    missing = tuple(sorted(expected_cases - set(by_case)))
    extra = tuple(sorted(set(by_case) - expected_cases))
    if missing or extra:
        return (), tuple(
            [f"{name}:STATE_SLENDERNESS_BASIS_MISSING" for name in missing]
            + [f"{name}:UNEXPECTED_STATE_SLENDERNESS_BASIS" for name in extra]
        )
    evaluations: list[ColumnStateSlendernessEvaluation] = []
    for output_case in sorted(expected_cases):
        carrier = by_case[output_case]
        result = evaluate_ts500_column_slenderness(component_id=component_id, basis=carrier.basis)
        refs = tuple(dict.fromkeys((*carrier.source_refs, *carrier.basis.source_refs, *result.source_refs, result.authority)))
        evaluations.append(
            ColumnStateSlendernessEvaluation(
                output_case=output_case,
                basis=carrier.basis,
                result=result,
                source_refs=refs,
            )
        )
    return tuple(evaluations), ()


def _apply_state_specific_magnification(
    *,
    states: tuple[ColumnDemandState, ...],
    evaluations: Sequence[ColumnStateSlendernessEvaluation],
    bases: Sequence[ColumnMomentMagnificationAxisBasis],
) -> tuple[tuple[ColumnDemandState, ...] | None, tuple[ColumnMomentMagnificationAxisResult, ...], tuple[str, ...], bool]:
    by_case = {row.output_case: row for row in evaluations}
    supplied: dict[tuple[str, str], ColumnMomentMagnificationAxisBasis] = {}
    for basis in tuple(bases):
        if not isinstance(basis, ColumnMomentMagnificationAxisBasis):
            raise TypeError("moment_magnification_bases must contain ColumnMomentMagnificationAxisBasis")
        key = (basis.demand_state_id, basis.axis)
        if key in supplied:
            raise ColumnDesignReadinessError("duplicate demand-state/axis moment magnification basis")
        supplied[key] = basis
    expected: set[tuple[str, str]] = set()
    for state in states:
        evaluation = by_case[state.output_case]
        for axis_result in (evaluation.result.m2, evaluation.result.m3):
            if axis_result.status == "MOMENT_MAGNIFICATION_REQUIRED":
                expected.add((state.state_id, axis_result.axis))
    missing = tuple(sorted(expected - set(supplied)))
    extra = tuple(sorted(set(supplied) - expected))
    if missing or extra:
        blockers = tuple(
            [f"{state_id}:{axis}:MOMENT_MAGNIFICATION_BASIS_UNRESOLVED" for state_id, axis in missing]
            + [f"{state_id}:{axis}:UNEXPECTED_MOMENT_MAGNIFICATION_BASIS" for state_id, axis in extra]
        )
        return None, (), blockers, bool(expected)
    state_by_id = {state.state_id: state for state in states}
    if len(state_by_id) != len(states):
        raise ColumnDesignReadinessError("minimum-eccentricity demand states require unique state_id")
    results: dict[tuple[str, str], ColumnMomentMagnificationAxisResult] = {}
    blockers: list[str] = []
    for key in sorted(expected):
        state_id, axis = key
        state = state_by_id[state_id]
        evaluation = by_case[state.output_case]
        axis_result = evaluation.result.m2 if axis == "M2" else evaluation.result.m3
        axis_basis = evaluation.basis.m2 if axis == "M2" else evaluation.basis.m3
        evidence = supplied[key]
        if axis_result.effective_length_lk_mm is None or axis_result.radius_of_gyration_i_mm is None:
            blockers.append(f"{state_id}:{axis}:SLENDERNESS_GEOMETRY_NOT_RESOLVED")
            continue
        if evidence.sway_classification != axis_basis.sway_classification:
            blockers.append(f"{state_id}:{axis}:SWAY_CLASSIFICATION_MISMATCH")
            continue
        if not _close(evidence.nd_compression_n, state.nd_compression_n):
            blockers.append(f"{state_id}:{axis}:AXIAL_DEMAND_IDENTITY_MISMATCH")
            continue
        if not _close(evidence.effective_length_lk_mm, axis_result.effective_length_lk_mm):
            blockers.append(f"{state_id}:{axis}:EFFECTIVE_LENGTH_IDENTITY_MISMATCH")
            continue
        if not _close(evidence.radius_i_mm, axis_result.radius_of_gyration_i_mm):
            blockers.append(f"{state_id}:{axis}:RADIUS_OF_GYRATION_IDENTITY_MISMATCH")
            continue
        if axis_basis.moment_ratio_m1_over_m2 is not None and not _close(
            evidence.m1_over_m2, axis_basis.moment_ratio_m1_over_m2
        ):
            blockers.append(f"{state_id}:{axis}:M1_M2_RATIO_IDENTITY_MISMATCH")
            continue
        result = evaluate_ts500_axis_moment_magnification(evidence)
        results[key] = result
        blockers.extend(f"{state_id}:{axis}:{item}" for item in result.blockers)
    if blockers or set(results) != expected:
        return None, tuple(results[key] for key in sorted(results)), tuple(dict.fromkeys(blockers)), bool(expected)
    final_states = tuple(
        magnify_concurrent_column_demand_state(
            state,
            m2=results.get((state.state_id, "M2")),
            m3=results.get((state.state_id, "M3")),
        )
        for state in states
    )
    return final_states, tuple(results[key] for key in sorted(results)), (), bool(expected)


def _verify_expected_states(
    actual: Sequence[ColumnDemandState],
    expected: Sequence[ColumnDemandState],
) -> tuple[str, ...]:
    if not expected:
        return ()
    actual_by_id = {item.state_id: item for item in actual}
    expected_by_id = {item.state_id: item for item in expected}
    if len(actual_by_id) != len(tuple(actual)) or len(expected_by_id) != len(tuple(expected)):
        return ("A23_FINAL_STATE_ID_NOT_UNIQUE",)
    if set(actual_by_id) != set(expected_by_id):
        return ("A23_FINAL_STATE_ID_SET_MISMATCH",)
    blockers: list[str] = []
    for state_id in sorted(actual_by_id):
        left = actual_by_id[state_id]
        right = expected_by_id[state_id]
        if (
            left.component_id != right.component_id
            or left.output_case != right.output_case
            or left.case_type != right.case_type
            or left.step_type != right.step_type
            or left.step_number != right.step_number
            or not _close(left.station_m, right.station_m)
            or left.end_tag != right.end_tag
            or not _close(left.nd_compression_n, right.nd_compression_n)
            or not _close(left.m2_nmm, right.m2_nmm)
            or not _close(left.m3_nmm, right.m3_nmm)
        ):
            blockers.append(f"{state_id}:A23_FINAL_STATE_MISMATCH")
    return tuple(blockers)


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
    state_slenderness_bases: Sequence[ColumnStateSlendernessBasis] = (),
    canonical_second_order_blockers: Sequence[str] = (),
    canonical_second_order_reanalysis_items: Sequence[str] = (),
    expected_final_states: Sequence[ColumnDemandState] = (),
    observed_combo_demands: Sequence[ColumnDemandState] = (),
    verify_observed_rows: bool = False,
    force_tolerance_n: float = 250.0,
    moment_tolerance_nmm: float = 250_000.0,
) -> ColumnDesignDemandReadiness:
    """Derive authoritative demand/stability readiness without caller READY flags."""
    component = _text(component_id, "component_id")
    stateful = bool(
        state_slenderness_bases
        or canonical_second_order_blockers
        or canonical_second_order_reanalysis_items
        or expected_final_states
    )
    if slenderness_evidence is not None and slenderness_basis is not None:
        raise ColumnDesignReadinessError("supply slenderness_evidence or slenderness_basis, not both")
    if stateful and (slenderness_evidence is not None or slenderness_basis is not None):
        raise ColumnDesignReadinessError("state-specific second-order join cannot also supply legacy slenderness authority")

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

    if stateful:
        blocked_items: list[str] = []
        magnification_results: tuple[ColumnMomentMagnificationAxisResult, ...] = ()
        state_rows: tuple[ColumnStateSlendernessEvaluation, ...] = ()
        final_states = minimum.states
        status = BLOCKED
        analysis_basis_status = ANALYSIS_BASIS_UNRESOLVED
        second_order_treatment = SECOND_ORDER_BLOCKED
        if not design_demands.combination_scope_resolved:
            blocked_items.extend(f"COMBINATION_SCOPE:{name}" for name in design_demands.blocked_combo_names)
        elif not minimum.resolved:
            blocked_items.append("MINIMUM_ECCENTRICITY_NOT_RESOLVED")
        elif canonical_second_order_reanalysis_items:
            status = REANALYSIS_REQUIRED
            analysis_basis_status = ANALYSIS_BASIS_REANALYSIS_REQUIRED
            second_order_treatment = SECOND_ORDER_GENERAL_ANALYSIS_REQUIRED
            blocked_items.extend(_text(item, "canonical_second_order_reanalysis_item") for item in canonical_second_order_reanalysis_items)
        elif canonical_second_order_blockers:
            status = UNRESOLVED
            analysis_basis_status = ANALYSIS_BASIS_UNRESOLVED
            second_order_treatment = SECOND_ORDER_UNRESOLVED
            blocked_items.extend(_text(item, "canonical_second_order_blocker") for item in canonical_second_order_blockers)
        else:
            state_rows, state_blockers = _evaluate_state_slenderness(
                component_id=component,
                states=minimum.states,
                carriers=state_slenderness_bases,
            )
            if state_blockers:
                status = UNRESOLVED
                analysis_basis_status = ANALYSIS_BASIS_UNRESOLVED
                second_order_treatment = SECOND_ORDER_UNRESOLVED
                blocked_items.extend(state_blockers)
            elif any(row.result.status == "GENERAL_SECOND_ORDER_ANALYSIS_REQUIRED" for row in state_rows):
                status = REANALYSIS_REQUIRED
                analysis_basis_status = ANALYSIS_BASIS_REANALYSIS_REQUIRED
                second_order_treatment = SECOND_ORDER_GENERAL_ANALYSIS_REQUIRED
                blocked_items.append("TS500_7.6.1_GENERAL_SECOND_ORDER_ANALYSIS_REQUIRED")
            else:
                final, magnification_results, magnification_blockers, used_magnification = _apply_state_specific_magnification(
                    states=minimum.states,
                    evaluations=state_rows,
                    bases=moment_magnification_bases,
                )
                if final is None:
                    status = UNRESOLVED
                    analysis_basis_status = ANALYSIS_BASIS_UNRESOLVED
                    second_order_treatment = SECOND_ORDER_MOMENT_MAGNIFICATION_REQUIRED if used_magnification else SECOND_ORDER_UNRESOLVED
                    blocked_items.extend(magnification_blockers)
                else:
                    final_states = final
                    expected_blockers = _verify_expected_states(final_states, expected_final_states)
                    if expected_blockers:
                        status = UNRESOLVED
                        analysis_basis_status = ANALYSIS_BASIS_UNRESOLVED
                        second_order_treatment = SECOND_ORDER_UNRESOLVED
                        blocked_items.extend(expected_blockers)
                    else:
                        status = READY
                        analysis_basis_status = ANALYSIS_BASIS_MATCH
                        second_order_treatment = (
                            SECOND_ORDER_MOMENT_MAGNIFICATION_APPLIED
                            if used_magnification
                            else SECOND_ORDER_NOT_REQUIRED
                        )
        return ColumnDesignDemandReadiness(
            component_id=component,
            status=status,
            analysis_basis_status=analysis_basis_status,
            second_order_treatment=second_order_treatment,
            stability_sway_status=_state_sway_status(state_rows),
            design_demands=design_demands,
            minimum_eccentricity=minimum,
            slenderness_basis=None,
            slenderness=None,
            demand_states=final_states,
            blocked_items=tuple(dict.fromkeys(blocked_items)),
            source_refs=_refs(
                minimum,
                None,
                None,
                stability_stiffness_basis,
                magnification_results,
                state_rows,
            ),
            stability_stiffness_basis=stability_stiffness_basis,
            moment_magnification_results=magnification_results,
            state_slenderness=state_rows,
        )

    if slenderness_basis is not None:
        basis_resolution = _prepromoted_resolution(component, slenderness_basis)
    else:
        basis_resolution = resolve_ts500_column_slenderness_basis(slenderness_evidence, component_id=component)
    slenderness = evaluate_ts500_column_slenderness(component_id=component, basis=basis_resolution.basis)
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
        sway_not_promoted = any(item.endswith(":SWAY_CLASSIFICATION_NOT_PROMOTED") for item in basis_resolution.blocked_items)
        if stability_stiffness_basis is not None and stability_stiffness_basis.reanalysis_required and sway_not_promoted:
            status = REANALYSIS_REQUIRED
            analysis_basis_status = ANALYSIS_BASIS_REANALYSIS_REQUIRED
            second_order_treatment = SECOND_ORDER_GENERAL_ANALYSIS_REQUIRED
            blocked_items.append(stability_stiffness_basis.status)
        elif not basis_resolution.resolved:
            blocked_items.extend(basis_resolution.blocked_items)
            unresolved_basis = any(
                item.endswith(":SWAY_CLASSIFICATION_NOT_PROMOTED") or item.endswith(":M1_M2_RATIO_NOT_PROMOTED")
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
                item.axis for item in (slenderness.m2, slenderness.m3)
                if item.status == "MOMENT_MAGNIFICATION_REQUIRED"
            }
            if failing_axes & conservative_axes:
                status = UNRESOLVED
                analysis_basis_status = ANALYSIS_BASIS_UNRESOLVED
                second_order_treatment = SECOND_ORDER_UNRESOLVED
                blocked_items.extend(f"{axis}:ACTUAL_M1_M2_RATIO_REQUIRED" for axis in sorted(failing_axes & conservative_axes))
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
        source_refs=_refs(minimum, basis_resolution, slenderness, stability_stiffness_basis, magnification_results),
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
    "ColumnStateSlendernessBasis",
    "ColumnStateSlendernessEvaluation",
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
