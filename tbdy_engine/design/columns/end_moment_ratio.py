"""Exact TS500 M1/M2 evidence from one concurrent static-linear column state pair.

The authority consumes the canonical I/J end demand states already produced by
``design_demand_states``.  It never envelopes ends independently and refuses
response-spectrum permutation states because their cross-end physical sign
correspondence is not established by that reconstruction.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

from tbdy_engine.design.columns.rebar_selection import ColumnDemandState


END_MOMENT_RATIO_AUTHORITY = "TS500_END_MOMENT_RATIO_FROM_CONCURRENT_STATIC_ENDS"


class EndMomentRatioError(ValueError):
    pass


def _text(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise EndMomentRatioError(f"{label} must be a nonblank canonical string")
    return value


@dataclass(frozen=True, slots=True)
class ColumnEndMomentRatioEvidence:
    component_id: str
    output_case: str
    axis: str
    i_end_state_id: str
    j_end_state_id: str
    m1_nmm: float
    m2_nmm: float
    moment_ratio_m1_over_m2: float
    curvature: str
    analysis_result_ref: str
    source_refs: tuple[str, ...]
    authority: str = END_MOMENT_RATIO_AUTHORITY


def build_exact_static_end_moment_ratio(
    *,
    i_end: ColumnDemandState,
    j_end: ColumnDemandState,
    axis: str,
    analysis_result_ref: str,
    source_refs: tuple[str, ...],
) -> ColumnEndMomentRatioEvidence:
    """Build signed |M1|/|M2| from the exact I/J pair of one static combo.

    The returned scalar follows the existing TS500 slenderness contract:
    ``|M1| <= |M2|``; ratio positive for single curvature and negative for
    double curvature.  Original signed end moments and end state IDs are
    retained in provenance.
    """
    if not isinstance(i_end, ColumnDemandState) or not isinstance(j_end, ColumnDemandState):
        raise TypeError("i_end and j_end must be ColumnDemandState")
    if i_end.end_tag != "I_END" or j_end.end_tag != "J_END":
        raise EndMomentRatioError("exact I_END/J_END pair is required")
    if i_end.component_id != j_end.component_id:
        raise EndMomentRatioError("end states have different component_id")
    if i_end.output_case != j_end.output_case:
        raise EndMomentRatioError("end states have different output_case")
    if i_end.case_type != "DesignStaticLinearExact" or j_end.case_type != "DesignStaticLinearExact":
        raise EndMomentRatioError(
            "actual TS500 end-moment ratio requires exact static-linear end states"
        )
    if i_end.step_type is not None or j_end.step_type is not None:
        raise EndMomentRatioError("static exact end states must not carry step_type")
    axis_name = _text(axis, "axis")
    if axis_name not in {"M2", "M3"}:
        raise EndMomentRatioError("axis must be M2 or M3")
    analysis_ref = _text(analysis_result_ref, "analysis_result_ref")
    refs = tuple(_text(item, "source_ref") for item in source_refs)
    if not refs or len(refs) != len(set(refs)):
        raise EndMomentRatioError("source_refs must be nonempty and unique")

    i_moment = float(i_end.m2_nmm if axis_name == "M2" else i_end.m3_nmm)
    j_moment = float(j_end.m2_nmm if axis_name == "M2" else j_end.m3_nmm)
    if not math.isfinite(i_moment) or not math.isfinite(j_moment):
        raise EndMomentRatioError("end moments must be finite")

    # M2 is the larger absolute end moment; ties are deterministically assigned
    # to I_END. Signed values remain available through the exact state refs.
    if abs(i_moment) >= abs(j_moment):
        larger = i_moment
        smaller = j_moment
    else:
        larger = j_moment
        smaller = i_moment
    if abs(larger) <= 1.0e-12:
        ratio = 0.0
        curvature = "ZERO_END_MOMENTS"
    else:
        same_face = (smaller == 0.0) or (math.copysign(1.0, smaller) == math.copysign(1.0, larger))
        ratio = abs(smaller) / abs(larger)
        if not same_face:
            ratio = -ratio
        curvature = "SINGLE_CURVATURE" if same_face else "DOUBLE_CURVATURE"

    retained_refs = tuple(
        dict.fromkeys(
            (
                analysis_ref,
                *refs,
                f"I_END_STATE:{i_end.state_id}",
                f"J_END_STATE:{j_end.state_id}",
                f"I_END_SOURCE:{i_end.source_identity}",
                f"J_END_SOURCE:{j_end.source_identity}",
            )
        )
    )
    return ColumnEndMomentRatioEvidence(
        component_id=i_end.component_id,
        output_case=i_end.output_case,
        axis=axis_name,
        i_end_state_id=i_end.state_id,
        j_end_state_id=j_end.state_id,
        m1_nmm=smaller,
        m2_nmm=larger,
        moment_ratio_m1_over_m2=ratio,
        curvature=curvature,
        analysis_result_ref=analysis_ref,
        source_refs=retained_refs,
    )


__all__ = [
    "ColumnEndMomentRatioEvidence",
    "END_MOMENT_RATIO_AUTHORITY",
    "EndMomentRatioError",
    "build_exact_static_end_moment_ratio",
]
