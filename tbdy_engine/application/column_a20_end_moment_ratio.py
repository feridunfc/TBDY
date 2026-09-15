"""COLUMN-R1 A20 exact same-state signed TS500 end-moment materialization.

This seam performs identity joins only.  The sign/curvature and M1/M2 authority
remains ``design.columns.end_moment_ratio.build_exact_static_end_moment_ratio``.
Response-spectrum/permutation states and synthetic defaults are rejected.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from tbdy_engine.design.columns.end_moment_ratio import (
    ColumnEndMomentRatioEvidence,
    EndMomentRatioError,
    build_exact_static_end_moment_ratio,
)
from tbdy_engine.design.columns.rebar_selection import ColumnDemandState

A20_READY = "READY"
A20_EXPLICIT_UNRESOLVED = "EXPLICIT_UNRESOLVED"
A20_AUTHORITY = "COLUMN_R1_A20_EXACT_STATIC_END_MOMENT_COMPOSITION"


@dataclass(frozen=True, slots=True)
class A20AxisEndMomentMaterialization:
    component_id: str
    output_case: str
    local_bending_axis: str
    disposition: str
    evidence: ColumnEndMomentRatioEvidence | None
    analysis_result_ref: str
    source_refs: tuple[str, ...]
    unresolved_reasons: tuple[str, ...] = ()
    authority: str = A20_AUTHORITY


def _refs(values: Sequence[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(value for value in values if isinstance(value, str) and value.strip()))


def _pair(states: Sequence[ColumnDemandState], component_id: str, output_case: str):
    exact = tuple(
        state for state in states
        if state.component_id == component_id
        and state.output_case == output_case
        and state.case_type == "DesignStaticLinearExact"
        and state.step_type is None
    )
    i_rows = tuple(state for state in exact if state.end_tag == "I_END")
    j_rows = tuple(state for state in exact if state.end_tag == "J_END")
    if len(i_rows) != 1 or len(j_rows) != 1:
        raise EndMomentRatioError(
            f"{output_case} requires exactly one I_END and one J_END exact static state; "
            f"got I={len(i_rows)} J={len(j_rows)}"
        )
    if i_rows[0].step_number is not None or j_rows[0].step_number is not None:
        raise EndMomentRatioError("exact static end pair must not carry step_number")
    return i_rows[0], j_rows[0]


def materialize_exact_static_end_moment_ratios(
    *,
    component_id: str,
    demand_states: Sequence[ColumnDemandState],
    qualified_static_case_names: Sequence[str],
    analysis_result_ref: str,
    execution_proof_ref: str,
    case_scope_refs: Sequence[str],
) -> tuple[A20AxisEndMomentMaterialization, ...]:
    """Materialize M2/M3 signed end ratios for every exact qualified static case."""
    if not isinstance(component_id, str) or not component_id.strip():
        raise ValueError("component_id must be nonblank")
    if not isinstance(analysis_result_ref, str) or not analysis_result_ref.strip():
        raise ValueError("analysis_result_ref must be nonblank")
    if not isinstance(execution_proof_ref, str) or not execution_proof_ref.strip():
        raise ValueError("execution_proof_ref must be nonblank")
    cases = tuple(qualified_static_case_names)
    if not cases or len(cases) != len(set(cases)):
        raise ValueError("qualified_static_case_names must be nonempty and unique")

    common = _refs((analysis_result_ref, execution_proof_ref, *tuple(case_scope_refs), A20_AUTHORITY))
    outputs: list[A20AxisEndMomentMaterialization] = []
    for output_case in cases:
        try:
            i_end, j_end = _pair(demand_states, component_id, output_case)
        except EndMomentRatioError as exc:
            for axis in ("M2", "M3"):
                outputs.append(
                    A20AxisEndMomentMaterialization(
                        component_id=component_id,
                        output_case=output_case,
                        local_bending_axis=axis,
                        disposition=A20_EXPLICIT_UNRESOLVED,
                        evidence=None,
                        analysis_result_ref=analysis_result_ref,
                        source_refs=common,
                        unresolved_reasons=(str(exc),),
                    )
                )
            continue

        pair_refs = _refs(
            (
                *common,
                f"I_END_STATE:{i_end.state_id}",
                f"J_END_STATE:{j_end.state_id}",
                f"QUALIFIED_STATIC_CASE:{output_case}",
            )
        )
        for axis in ("M2", "M3"):
            try:
                evidence = build_exact_static_end_moment_ratio(
                    i_end=i_end,
                    j_end=j_end,
                    axis=axis,
                    analysis_result_ref=analysis_result_ref,
                    source_refs=pair_refs,
                )
            except (EndMomentRatioError, TypeError, ValueError) as exc:
                outputs.append(
                    A20AxisEndMomentMaterialization(
                        component_id=component_id,
                        output_case=output_case,
                        local_bending_axis=axis,
                        disposition=A20_EXPLICIT_UNRESOLVED,
                        evidence=None,
                        analysis_result_ref=analysis_result_ref,
                        source_refs=pair_refs,
                        unresolved_reasons=(f"END_MOMENT_RATIO_FAILED:{exc}",),
                    )
                )
                continue
            outputs.append(
                A20AxisEndMomentMaterialization(
                    component_id=component_id,
                    output_case=output_case,
                    local_bending_axis=axis,
                    disposition=A20_READY,
                    evidence=evidence,
                    analysis_result_ref=analysis_result_ref,
                    source_refs=_refs((*pair_refs, *evidence.source_refs, evidence.authority)),
                )
            )
    return tuple(outputs)


__all__ = [
    "A20_AUTHORITY",
    "A20_EXPLICIT_UNRESOLVED",
    "A20_READY",
    "A20AxisEndMomentMaterialization",
    "materialize_exact_static_end_moment_ratios",
]
