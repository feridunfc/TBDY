"""TS500 6.3.10 minimum-eccentricity closure for column design demands.

This pure production kernel sits between canonical promoted P-M2-M3 demand
states and longitudinal-reinforcement selection.  It does not acquire ETABS
results and does not select reinforcement.

For a rectangular local-2/local-3 section convention used by the VS6 layout and
capacity kernels:
- M2 bends in the local 1-3 plane, therefore ``h = depth_mm``;
- M3 bends in the local 1-2 plane, therefore ``h = width_mm``.

TS500 6.3.10 requires the eccentricity calculated from a column end design
moment not to be less than ``emin = 15 mm + 0.03 h``.  The rule is applied to
each principal bending plane.  When a compression state has exactly zero moment
in a required direction, both signs of the minimum moment are retained so the
engine does not invent an imperfection sign.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Sequence

from tbdy_engine.design.columns.rebar_selection import ColumnDemandState


TS500_MIN_ECCENTRICITY_BASE_MM = 15.0
TS500_MIN_ECCENTRICITY_H_FACTOR = 0.03
TS500_MIN_ECCENTRICITY_AUTHORITY = "TS500_6.3.10_MINIMUM_ECCENTRICITY"


class ColumnMinimumEccentricityError(ValueError):
    """Raised when minimum-eccentricity inputs are malformed or inconsistent."""


@dataclass(frozen=True, slots=True)
class MinimumEccentricityAdjustment:
    source_state_id: str
    nd_compression_n: float
    emin_for_m2_mm: float
    emin_for_m3_mm: float
    required_abs_m2_nmm: float
    required_abs_m3_nmm: float
    original_m2_nmm: float
    original_m3_nmm: float
    m2_adjusted: bool
    m3_adjusted: bool
    generated_state_ids: tuple[str, ...]
    application_status: str


@dataclass(frozen=True, slots=True)
class ColumnMinimumEccentricityResult:
    component_id: str
    status: str
    authority: str
    input_state_count: int
    output_state_count: int
    adjusted_source_state_count: int
    sign_branch_source_state_count: int
    states: tuple[ColumnDemandState, ...]
    adjustments: tuple[MinimumEccentricityAdjustment, ...]
    source_refs: tuple[str, ...]

    @property
    def resolved(self) -> bool:
        return self.status == "PROVEN_TS500_MINIMUM_ECCENTRICITY"


def ts500_minimum_eccentricity_mm(h_mm: float) -> float:
    h = float(h_mm)
    if not math.isfinite(h) or h <= 0.0:
        raise ColumnMinimumEccentricityError("bending-plane section dimension h_mm must be finite and > 0")
    return TS500_MIN_ECCENTRICITY_BASE_MM + TS500_MIN_ECCENTRICITY_H_FACTOR * h


def _moment_choices(
    moment_nmm: float,
    required_abs_nmm: float,
    *,
    zero_tolerance_nmm: float,
) -> tuple[tuple[str, float], ...]:
    moment = float(moment_nmm)
    required = float(required_abs_nmm)
    if abs(moment) + zero_tolerance_nmm >= required:
        return (("ORIGINAL", moment),)
    if abs(moment) > zero_tolerance_nmm:
        return (("AMPLIFIED_TO_EMIN", math.copysign(required, moment)),)
    if required <= zero_tolerance_nmm:
        return (("ORIGINAL", moment),)
    return (
        ("NEGATIVE_EMIN_BRANCH", -required),
        ("POSITIVE_EMIN_BRANCH", required),
    )


def apply_ts500_minimum_eccentricity(
    *,
    component_id: str,
    width_mm: float,
    depth_mm: float,
    demands: Sequence[ColumnDemandState],
    source_refs: Sequence[str] = ("TS500 6.3.10 Eq. 6.16",),
    zero_tolerance_nmm: float = 1e-9,
) -> ColumnMinimumEccentricityResult:
    """Apply TS500 6.3.10 to canonical promoted column end demand states.

    Positive ``nd_compression_n`` is compression in the VS6 canonical demand
    convention.  Zero/tension axial states are preserved without introducing a
    fictitious eccentricity because ``M/N`` minimum eccentricity is a
    compression-column requirement.
    """
    if not isinstance(component_id, str) or not component_id.strip():
        raise ColumnMinimumEccentricityError("component_id must be nonblank")
    width = float(width_mm)
    depth = float(depth_mm)
    if not math.isfinite(width) or width <= 0.0 or not math.isfinite(depth) or depth <= 0.0:
        raise ColumnMinimumEccentricityError("width_mm and depth_mm must be finite and > 0")
    tolerance = float(zero_tolerance_nmm)
    if not math.isfinite(tolerance) or tolerance < 0.0:
        raise ColumnMinimumEccentricityError("zero_tolerance_nmm must be finite and >= 0")

    refs = tuple(str(item).strip() for item in source_refs)
    if not refs or any(not item for item in refs) or len(refs) != len(set(refs)):
        raise ColumnMinimumEccentricityError("source_refs must be a nonempty unique sequence")

    source_states = tuple(demands)
    if not source_states:
        return ColumnMinimumEccentricityResult(
            component_id=component_id,
            status="NO_DATA_TS500_MINIMUM_ECCENTRICITY",
            authority=TS500_MIN_ECCENTRICITY_AUTHORITY,
            input_state_count=0,
            output_state_count=0,
            adjusted_source_state_count=0,
            sign_branch_source_state_count=0,
            states=(),
            adjustments=(),
            source_refs=refs,
        )
    if any(item.component_id != component_id for item in source_states):
        raise ColumnMinimumEccentricityError("demands contain a different component_id")

    # M2 acts in local 1-3 plane -> h is local-3/depth dimension.
    emin_m2_mm = ts500_minimum_eccentricity_mm(depth)
    # M3 acts in local 1-2 plane -> h is local-2/width dimension.
    emin_m3_mm = ts500_minimum_eccentricity_mm(width)

    output: list[ColumnDemandState] = []
    adjustments: list[MinimumEccentricityAdjustment] = []
    seen_ids: set[str] = set()
    adjusted_count = 0
    sign_branch_count = 0

    for state in source_states:
        n = float(state.nd_compression_n)
        if not math.isfinite(n):
            raise ColumnMinimumEccentricityError("nd_compression_n must be finite")

        if n <= 0.0:
            state_id = f"{state.state_id}|TS5006.3.10|NOT_APPLICABLE_NONCOMPRESSION"
            promoted = ColumnDemandState(
                state_id=state_id,
                component_id=state.component_id,
                output_case=state.output_case,
                case_type=state.case_type,
                step_type=state.step_type,
                step_number=state.step_number,
                station_m=state.station_m,
                end_tag=state.end_tag,
                nd_compression_n=state.nd_compression_n,
                m2_nmm=state.m2_nmm,
                m3_nmm=state.m3_nmm,
                source_identity=(
                    state.source_identity
                    + "|TS5006.3.10:NOT_APPLICABLE_NONCOMPRESSION"
                ),
            )
            if state_id in seen_ids:
                raise ColumnMinimumEccentricityError("duplicate post-eccentricity state identity")
            seen_ids.add(state_id)
            output.append(promoted)
            adjustments.append(
                MinimumEccentricityAdjustment(
                    source_state_id=state.state_id,
                    nd_compression_n=n,
                    emin_for_m2_mm=emin_m2_mm,
                    emin_for_m3_mm=emin_m3_mm,
                    required_abs_m2_nmm=0.0,
                    required_abs_m3_nmm=0.0,
                    original_m2_nmm=state.m2_nmm,
                    original_m3_nmm=state.m3_nmm,
                    m2_adjusted=False,
                    m3_adjusted=False,
                    generated_state_ids=(state_id,),
                    application_status="NOT_APPLICABLE_NONCOMPRESSION",
                )
            )
            continue

        required_m2 = n * emin_m2_mm
        required_m3 = n * emin_m3_mm
        m2_choices = _moment_choices(
            state.m2_nmm,
            required_m2,
            zero_tolerance_nmm=tolerance,
        )
        m3_choices = _moment_choices(
            state.m3_nmm,
            required_m3,
            zero_tolerance_nmm=tolerance,
        )
        m2_adjusted = abs(state.m2_nmm) + tolerance < required_m2
        m3_adjusted = abs(state.m3_nmm) + tolerance < required_m3
        branched = len(m2_choices) > 1 or len(m3_choices) > 1
        if m2_adjusted or m3_adjusted:
            adjusted_count += 1
        if branched:
            sign_branch_count += 1

        generated_ids: list[str] = []
        for m2_label, m2_value in m2_choices:
            for m3_label, m3_value in m3_choices:
                suffix = f"TS5006.3.10|M2={m2_label}|M3={m3_label}"
                state_id = f"{state.state_id}|{suffix}"
                if state_id in seen_ids:
                    raise ColumnMinimumEccentricityError("duplicate post-eccentricity state identity")
                seen_ids.add(state_id)
                generated_ids.append(state_id)
                output.append(
                    ColumnDemandState(
                        state_id=state_id,
                        component_id=state.component_id,
                        output_case=state.output_case,
                        case_type=state.case_type,
                        step_type=state.step_type,
                        step_number=state.step_number,
                        station_m=state.station_m,
                        end_tag=state.end_tag,
                        nd_compression_n=state.nd_compression_n,
                        m2_nmm=m2_value,
                        m3_nmm=m3_value,
                        source_identity=(
                            state.source_identity
                            + f"|TS5006.3.10:emin_m2_mm={emin_m2_mm:g}:emin_m3_mm={emin_m3_mm:g}"
                            + f":M2={m2_label}:M3={m3_label}"
                        ),
                    )
                )

        adjustments.append(
            MinimumEccentricityAdjustment(
                source_state_id=state.state_id,
                nd_compression_n=n,
                emin_for_m2_mm=emin_m2_mm,
                emin_for_m3_mm=emin_m3_mm,
                required_abs_m2_nmm=required_m2,
                required_abs_m3_nmm=required_m3,
                original_m2_nmm=state.m2_nmm,
                original_m3_nmm=state.m3_nmm,
                m2_adjusted=m2_adjusted,
                m3_adjusted=m3_adjusted,
                generated_state_ids=tuple(generated_ids),
                application_status=(
                    "APPLIED_WITH_SIGN_BRANCHING"
                    if branched
                    else ("APPLIED_MOMENT_FLOOR" if (m2_adjusted or m3_adjusted) else "ALREADY_SATISFIED")
                ),
            )
        )

    output.sort(key=lambda item: item.state_id)
    return ColumnMinimumEccentricityResult(
        component_id=component_id,
        status="PROVEN_TS500_MINIMUM_ECCENTRICITY",
        authority=TS500_MIN_ECCENTRICITY_AUTHORITY,
        input_state_count=len(source_states),
        output_state_count=len(output),
        adjusted_source_state_count=adjusted_count,
        sign_branch_source_state_count=sign_branch_count,
        states=tuple(output),
        adjustments=tuple(adjustments),
        source_refs=refs,
    )


__all__ = [
    "TS500_MIN_ECCENTRICITY_AUTHORITY",
    "TS500_MIN_ECCENTRICITY_BASE_MM",
    "TS500_MIN_ECCENTRICITY_H_FACTOR",
    "ColumnMinimumEccentricityError",
    "ColumnMinimumEccentricityResult",
    "MinimumEccentricityAdjustment",
    "apply_ts500_minimum_eccentricity",
    "ts500_minimum_eccentricity_mm",
]
