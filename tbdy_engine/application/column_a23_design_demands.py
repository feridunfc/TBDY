"""COLUMN-R1 A23 final exact concurrent P-M2-M3 design-demand composition.

No demand equation is owned here.  Existing canonical owners produce promoted
combo states, TS500 minimum eccentricity, slenderness decisions, and exact-state
moment magnification.  A23 only performs identity-safe composition and retains
B5/source lineage for the final population.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from tbdy_engine.application.column_a21_slenderness import (
    A21_READY,
    A21StateSlendernessMaterialization,
)
from tbdy_engine.application.column_a22_moment_magnification import (
    A22_NOT_REQUIRED,
    A22_READY,
    A22_REANALYSIS_REQUIRED,
    A22AxisStateMaterialization,
    A22MomentMagnificationMaterialization,
)
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
    magnify_concurrent_column_demand_state,
)
from tbdy_engine.design.columns.rebar_selection import ColumnDemandState
from tbdy_engine.design.columns.slenderness import (
    GENERAL_SECOND_ORDER_ANALYSIS_REQUIRED,
    MOMENT_MAGNIFICATION_REQUIRED,
)

A23_READY = "READY"
A23_EXPLICIT_UNRESOLVED = "EXPLICIT_UNRESOLVED"
A23_REANALYSIS_REQUIRED = "REANALYSIS_REQUIRED"
A23_AUTHORITY = "COLUMN_R1_A23_CANONICAL_CONCURRENT_DESIGN_DEMAND_COMPOSITION"


@dataclass(frozen=True, slots=True)
class A23CanonicalDemandState:
    component_id: str
    state: ColumnDemandState
    analysis_result_ref: str
    execution_proof_ref: str
    source_model_ref: str
    m2_second_order_treatment: str
    m3_second_order_treatment: str
    source_refs: tuple[str, ...]
    authority: str = A23_AUTHORITY


@dataclass(frozen=True, slots=True)
class A23CanonicalDemandPopulation:
    component_id: str
    status: str
    design_demands: ColumnDesignDemandEngineResult
    minimum_eccentricity: ColumnMinimumEccentricityResult
    states: tuple[A23CanonicalDemandState, ...]
    blocked_items: tuple[str, ...]
    source_refs: tuple[str, ...]
    authority: str = A23_AUTHORITY

    @property
    def demand_states(self) -> tuple[ColumnDemandState, ...]:
        return tuple(item.state for item in self.states)


def _refs(values: Sequence[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(value for value in values if isinstance(value, str) and value.strip()))


def build_a23_pre_magnification_population(
    *,
    component_id: str,
    combo_definitions: Sequence[ColumnComboDefinition],
    constituent_case_demands: Sequence[ColumnDemandState],
    width_mm: float,
    depth_mm: float,
) -> tuple[ColumnDesignDemandEngineResult, ColumnMinimumEccentricityResult]:
    """Use canonical owners to produce the exact A23 population before A22."""
    design_demands = evaluate_column_design_demands(
        component_id=component_id,
        definitions=combo_definitions,
        case_demands=constituent_case_demands,
    )
    minimum = apply_ts500_minimum_eccentricity(
        component_id=component_id,
        width_mm=width_mm,
        depth_mm=depth_mm,
        demands=design_demands.promoted_states,
        source_refs=("TS500 6.3.10 Eq.6.16", A23_AUTHORITY),
    )
    return design_demands, minimum


def _a21(rows: Sequence[A21StateSlendernessMaterialization], output_case: str):
    matches = tuple(item for item in rows if item.output_case == output_case)
    if len(matches) != 1 or matches[0].disposition != A21_READY or matches[0].result is None:
        raise ValueError(f"A21_NOT_READY:{output_case}")
    return matches[0]


def _a22(
    rows: Sequence[A22AxisStateMaterialization],
    state_id: str,
    axis: str,
) -> A22AxisStateMaterialization:
    matches = tuple(
        item for item in rows
        if item.demand_state_id == state_id and item.local_bending_axis == axis
    )
    if len(matches) != 1:
        raise ValueError(f"A22_EXACT_STATE_AXIS_NOT_UNIQUE:{state_id}:{axis}:{len(matches)}")
    return matches[0]


def materialize_canonical_concurrent_design_demands(
    *,
    component_id: str,
    design_demands: ColumnDesignDemandEngineResult,
    minimum_eccentricity: ColumnMinimumEccentricityResult,
    a21_rows: Sequence[A21StateSlendernessMaterialization],
    a22: A22MomentMagnificationMaterialization,
    analysis_result_ref: str,
    execution_proof_ref: str,
    source_model_ref: str,
) -> A23CanonicalDemandPopulation:
    """Apply only exact-state A22 results and retain the original concurrent P."""
    if not design_demands.combination_scope_resolved:
        return A23CanonicalDemandPopulation(
            component_id=component_id,
            status=A23_EXPLICIT_UNRESOLVED,
            design_demands=design_demands,
            minimum_eccentricity=minimum_eccentricity,
            states=(),
            blocked_items=tuple(
                f"COMBINATION_SCOPE:{name}" for name in design_demands.blocked_combo_names
            ),
            source_refs=(A23_AUTHORITY, analysis_result_ref, execution_proof_ref, source_model_ref),
        )
    if not minimum_eccentricity.resolved:
        return A23CanonicalDemandPopulation(
            component_id=component_id,
            status=A23_EXPLICIT_UNRESOLVED,
            design_demands=design_demands,
            minimum_eccentricity=minimum_eccentricity,
            states=(),
            blocked_items=("MINIMUM_ECCENTRICITY_NOT_RESOLVED",),
            source_refs=(A23_AUTHORITY, analysis_result_ref, execution_proof_ref, source_model_ref),
        )

    output: list[A23CanonicalDemandState] = []
    blocked: list[str] = []
    reanalysis: list[str] = []
    for state in minimum_eccentricity.states:
        try:
            slender = _a21(a21_rows, state.output_case)
            m2_slender = slender.result.m2
            m3_slender = slender.result.m3
            if (
                m2_slender.status == GENERAL_SECOND_ORDER_ANALYSIS_REQUIRED
                or m3_slender.status == GENERAL_SECOND_ORDER_ANALYSIS_REQUIRED
            ):
                reanalysis.append(f"{state.state_id}:TS500_7.6.1_GENERAL_SECOND_ORDER_ANALYSIS_REQUIRED")
                continue

            axis_results = {}
            treatments = {}
            for axis, slender_axis in (("M2", m2_slender), ("M3", m3_slender)):
                a22_row = _a22(a22.rows, state.state_id, axis)
                if slender_axis.status == MOMENT_MAGNIFICATION_REQUIRED:
                    if a22_row.disposition == A22_REANALYSIS_REQUIRED:
                        reanalysis.append(f"{state.state_id}:{axis}:REANALYSIS_REQUIRED")
                        break
                    if a22_row.disposition != A22_READY or a22_row.result is None:
                        raise ValueError(f"A22_MAGNIFICATION_NOT_READY:{state.state_id}:{axis}")
                    axis_results[axis] = a22_row.result
                    treatments[axis] = "MOMENT_MAGNIFICATION_APPLIED"
                else:
                    if a22_row.disposition != A22_NOT_REQUIRED:
                        raise ValueError(f"A22_NOT_REQUIRED_IDENTITY_MISMATCH:{state.state_id}:{axis}")
                    axis_results[axis] = None
                    treatments[axis] = "NOT_REQUIRED"
            else:
                final_state = magnify_concurrent_column_demand_state(
                    state,
                    m2=axis_results["M2"],
                    m3=axis_results["M3"],
                )
                if final_state.nd_compression_n != state.nd_compression_n:
                    raise ValueError(f"A23_AXIAL_IDENTITY_CHANGED:{state.state_id}")
                refs = _refs(
                    (
                        A23_AUTHORITY,
                        analysis_result_ref,
                        execution_proof_ref,
                        source_model_ref,
                        state.source_identity,
                        final_state.source_identity,
                        *slender.source_refs,
                        *tuple(
                            ref
                            for axis in ("M2", "M3")
                            for ref in _a22(a22.rows, state.state_id, axis).source_refs
                        ),
                    )
                )
                output.append(
                    A23CanonicalDemandState(
                        component_id=component_id,
                        state=final_state,
                        analysis_result_ref=analysis_result_ref,
                        execution_proof_ref=execution_proof_ref,
                        source_model_ref=source_model_ref,
                        m2_second_order_treatment=treatments["M2"],
                        m3_second_order_treatment=treatments["M3"],
                        source_refs=refs,
                    )
                )
                continue
            # loop broke because one axis requires reanalysis
            continue
        except (TypeError, ValueError) as exc:
            blocked.append(f"{state.state_id}:{exc}")

    refs = _refs(
        (
            A23_AUTHORITY,
            analysis_result_ref,
            execution_proof_ref,
            source_model_ref,
            *minimum_eccentricity.source_refs,
            *a22.source_refs,
            *tuple(ref for item in a21_rows for ref in item.source_refs),
            *tuple(ref for item in output for ref in item.source_refs),
        )
    )
    if reanalysis:
        status = A23_REANALYSIS_REQUIRED
        final_states: tuple[A23CanonicalDemandState, ...] = ()
        items = tuple(dict.fromkeys((*reanalysis, *blocked)))
    elif blocked or len(output) != len(minimum_eccentricity.states):
        status = A23_EXPLICIT_UNRESOLVED
        final_states = ()
        items = tuple(dict.fromkeys(blocked or ("A23_FINAL_POPULATION_INCOMPLETE",)))
    else:
        status = A23_READY
        final_states = tuple(sorted(output, key=lambda item: item.state.state_id))
        items = ()
    return A23CanonicalDemandPopulation(
        component_id=component_id,
        status=status,
        design_demands=design_demands,
        minimum_eccentricity=minimum_eccentricity,
        states=final_states,
        blocked_items=items,
        source_refs=refs,
    )


__all__ = [
    "A23_AUTHORITY",
    "A23_EXPLICIT_UNRESOLVED",
    "A23_READY",
    "A23_REANALYSIS_REQUIRED",
    "A23CanonicalDemandPopulation",
    "A23CanonicalDemandState",
    "build_a23_pre_magnification_population",
    "materialize_canonical_concurrent_design_demands",
]
