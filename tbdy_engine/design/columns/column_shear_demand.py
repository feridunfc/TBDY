"""Pure source-bound VS6-P7 column shear demand mechanics.

No ETABS acquisition and no formal compliance verdicts live here. This module
reuses the VS6-P5 strain-compatibility capacity kernel and preserves local-axis,
end, axial-state and source identity throughout TBDY 2018 7.3.7 demand
construction.

P7 working convention is kN, kN*m, mm and MPa. The pre-existing VS6-P5 section
capacity kernel internally uses N/N*mm; conversion to and from that legacy
kernel is isolated to ``resolve_exact_column_end_moment_capacity`` and is not a
P7 working-unit convention.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Sequence

from tbdy_engine.design.columns.rebar_layout import ColumnBarPoint
from tbdy_engine.design.columns.section_capacity import (
    ColumnSectionMaterial,
    build_interaction_envelope_at_axial_force,
    radial_moment_capacity,
)


class ColumnShearDemandError(ValueError):
    """Raised when a P7 demand input is malformed or loses authority."""


V2 = "V2"
V3 = "V3"
M2 = "M2"
M3 = "M3"
_ALLOWED_DIRECTIONS = frozenset({V2, V3})
_ASSOCIATED_MOMENT_AXIS = {V2: M3, V3: M2}

CAPACITY_PROVEN = "PROVEN_EXACT_COLUMN_END_CAPACITY"
CAPACITY_BLOCKED = "BLOCKED_COLUMN_END_CAPACITY"
DEMAND_PROVEN = "PROVEN_TBDY_7_3_7_VE"
BLOCKED_LN = "BLOCKED_FREE_LENGTH_BASIS"
BLOCKED_D = "BLOCKED_D_AMPLIFIED_SHEAR_BASIS"
BLOCKED_RS_CONCURRENCY = "BLOCKED_RESPONSE_SPECTRUM_SHEAR_CONCURRENCY"
BLOCKED_END_CAPACITY = "BLOCKED_COLUMN_END_CAPACITY"
SECTION_CAPACITY_UNIT_ADAPTER_REF = "VS6_P5_CAPACITY_UNIT_ADAPTER:kN-kNm<->N-Nmm"


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ColumnShearDemandError(f"{label} must be a nonblank canonical string")
    return value


def _positive(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ColumnShearDemandError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result) or result <= 0.0:
        raise ColumnShearDemandError(f"{label} must be finite and > 0")
    return result


def _nonnegative(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ColumnShearDemandError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result) or result < 0.0:
        raise ColumnShearDemandError(f"{label} must be finite and >= 0")
    return result


def associated_moment_axis(direction: str) -> str:
    canonical = _text(direction, "direction")
    try:
        return _ASSOCIATED_MOMENT_AXIS[canonical]
    except KeyError as exc:
        raise ColumnShearDemandError("direction must be V2 or V3") from exc


@dataclass(frozen=True, slots=True)
class ColumnEndMomentCapacityBasis:
    component_id: str
    end_tag: str
    direction: str
    moment_axis: str
    moment_sign: int
    nd_compression_kn: float
    capacity_knm: float | None
    status: str
    source_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        _text(self.component_id, "component_id")
        end = _text(self.end_tag, "end_tag")
        if end not in {"BOTTOM", "TOP"}:
            raise ColumnShearDemandError("end_tag must be BOTTOM or TOP")
        direction = _text(self.direction, "direction")
        expected_axis = associated_moment_axis(direction)
        if self.moment_axis != expected_axis:
            raise ColumnShearDemandError(
                f"{direction} must preserve associated bending axis {expected_axis}"
            )
        if self.moment_sign not in {-1, 1}:
            raise ColumnShearDemandError("moment_sign must be -1 or +1")
        _nonnegative(self.nd_compression_kn, "nd_compression_kn")
        if self.capacity_knm is not None:
            _positive(self.capacity_knm, "capacity_knm")
        _text(self.status, "status")
        refs = tuple(_text(ref, "source_ref") for ref in self.source_refs)
        if not refs or len(refs) != len(set(refs)):
            raise ColumnShearDemandError("source_refs must be nonempty and unique")
        object.__setattr__(self, "source_refs", refs)

    @property
    def resolved(self) -> bool:
        return self.status == CAPACITY_PROVEN and self.capacity_knm is not None


def resolve_exact_column_end_moment_capacity(
    *,
    component_id: str,
    end_tag: str,
    direction: str,
    moment_sign: int,
    nd_compression_kn: float,
    width_mm: float,
    depth_mm: float,
    bars: Sequence[ColumnBarPoint],
    material: ColumnSectionMaterial,
    source_refs: Sequence[str],
    angle_count: int = 72,
) -> ColumnEndMomentCapacityBasis:
    """Resolve exact #145 capacity and expose it to P7 as kN*m."""
    component = _text(component_id, "component_id")
    end = _text(end_tag, "end_tag")
    direction = _text(direction, "direction")
    axis = associated_moment_axis(direction)
    if moment_sign not in {-1, 1}:
        raise ColumnShearDemandError("moment_sign must be -1 or +1")
    nd_kn = _nonnegative(nd_compression_kn, "nd_compression_kn")
    width = _positive(width_mm, "width_mm")
    depth = _positive(depth_mm, "depth_mm")
    refs = tuple(_text(ref, "source_ref") for ref in source_refs)
    if not refs:
        raise ColumnShearDemandError("source_refs must be nonempty")
    if not bars:
        raise ColumnShearDemandError("bars must be nonempty")

    # Compatibility seam only: the frozen #145 kernel is N/N*mm.
    envelope = build_interaction_envelope_at_axial_force(
        width_mm=width,
        depth_mm=depth,
        bars=tuple(bars),
        material=material,
        target_n_compression_n=nd_kn * 1000.0,
        angle_count=angle_count,
    )
    resolved_refs = tuple(dict.fromkeys((*refs, SECTION_CAPACITY_UNIT_ADAPTER_REF)))
    if envelope.status != "PROVEN":
        return ColumnEndMomentCapacityBasis(
            component_id=component,
            end_tag=end,
            direction=direction,
            moment_axis=axis,
            moment_sign=moment_sign,
            nd_compression_kn=nd_kn,
            capacity_knm=None,
            status=CAPACITY_BLOCKED,
            source_refs=resolved_refs,
        )

    demand_m2 = float(moment_sign) if axis == M2 else 0.0
    demand_m3 = float(moment_sign) if axis == M3 else 0.0
    radial = radial_moment_capacity(
        envelope,
        demand_m2_nmm=demand_m2,
        demand_m3_nmm=demand_m3,
    )
    if radial.status != "PROVEN" or not math.isfinite(radial.capacity_nmm) or radial.capacity_nmm <= 0.0:
        return ColumnEndMomentCapacityBasis(
            component_id=component,
            end_tag=end,
            direction=direction,
            moment_axis=axis,
            moment_sign=moment_sign,
            nd_compression_kn=nd_kn,
            capacity_knm=None,
            status=CAPACITY_BLOCKED,
            source_refs=resolved_refs,
        )

    return ColumnEndMomentCapacityBasis(
        component_id=component,
        end_tag=end,
        direction=direction,
        moment_axis=axis,
        moment_sign=moment_sign,
        nd_compression_kn=nd_kn,
        capacity_knm=float(radial.capacity_nmm) / 1_000_000.0,
        status=CAPACITY_PROVEN,
        source_refs=resolved_refs,
    )


@dataclass(frozen=True, slots=True)
class ColumnShearDesignDemandInput:
    component_id: str
    direction: str
    free_length_ln_mm: float | None
    free_length_basis_ref: str | None
    bottom_capacity: ColumnEndMomentCapacityBasis
    top_capacity: ColumnEndMomentCapacityBasis
    d_amplified_candidate_kn: float | None
    d_amplified_basis_ref: str | None
    vd_floor_kn: float
    vd_source_ref: str
    response_spectrum_concurrency_required: bool = False
    response_spectrum_concurrency_proven: bool = True

    def __post_init__(self) -> None:
        _text(self.component_id, "component_id")
        associated_moment_axis(self.direction)
        if self.free_length_ln_mm is not None:
            _positive(self.free_length_ln_mm, "free_length_ln_mm")
        if self.free_length_basis_ref is not None:
            _text(self.free_length_basis_ref, "free_length_basis_ref")
        if self.d_amplified_candidate_kn is not None:
            _nonnegative(self.d_amplified_candidate_kn, "d_amplified_candidate_kn")
        if self.d_amplified_basis_ref is not None:
            _text(self.d_amplified_basis_ref, "d_amplified_basis_ref")
        _nonnegative(self.vd_floor_kn, "vd_floor_kn")
        _text(self.vd_source_ref, "vd_source_ref")
        if type(self.response_spectrum_concurrency_required) is not bool:
            raise ColumnShearDemandError("response_spectrum_concurrency_required must be bool")
        if type(self.response_spectrum_concurrency_proven) is not bool:
            raise ColumnShearDemandError("response_spectrum_concurrency_proven must be bool")


@dataclass(frozen=True, slots=True)
class ColumnShearDesignDemandResult:
    component_id: str
    direction: str
    status: str
    ve_capacity_eq75_kn: float | None
    d_amplified_candidate_kn: float | None
    vd_floor_kn: float
    final_ve_kn: float | None
    governing_rule: str | None
    bottom_capacity: ColumnEndMomentCapacityBasis
    top_capacity: ColumnEndMomentCapacityBasis
    source_refs: tuple[str, ...]


def evaluate_tbdy_737_column_shear_demand(
    inputs: ColumnShearDesignDemandInput,
) -> ColumnShearDesignDemandResult:
    """Evaluate TBDY 7.3.7.1/7.3.7.5 demand in kN, kN*m and mm."""
    if not isinstance(inputs, ColumnShearDesignDemandInput):
        raise TypeError("inputs must be ColumnShearDesignDemandInput")

    component = inputs.component_id
    direction = inputs.direction
    for basis in (inputs.bottom_capacity, inputs.top_capacity):
        if basis.component_id != component or basis.direction != direction:
            raise ColumnShearDemandError("end capacity identity differs from demand identity")

    common_refs = list(
        dict.fromkeys(
            (
                *inputs.bottom_capacity.source_refs,
                *inputs.top_capacity.source_refs,
                inputs.vd_source_ref,
            )
        )
    )

    def blocked(status: str) -> ColumnShearDesignDemandResult:
        return ColumnShearDesignDemandResult(
            component_id=component,
            direction=direction,
            status=status,
            ve_capacity_eq75_kn=None,
            d_amplified_candidate_kn=inputs.d_amplified_candidate_kn,
            vd_floor_kn=float(inputs.vd_floor_kn),
            final_ve_kn=None,
            governing_rule=None,
            bottom_capacity=inputs.bottom_capacity,
            top_capacity=inputs.top_capacity,
            source_refs=tuple(common_refs),
        )

    if not inputs.bottom_capacity.resolved or not inputs.top_capacity.resolved:
        return blocked(BLOCKED_END_CAPACITY)
    if inputs.free_length_ln_mm is None or inputs.free_length_basis_ref is None:
        return blocked(BLOCKED_LN)
    if inputs.d_amplified_candidate_kn is None or inputs.d_amplified_basis_ref is None:
        return blocked(BLOCKED_D)
    if inputs.response_spectrum_concurrency_required and not inputs.response_spectrum_concurrency_proven:
        return blocked(BLOCKED_RS_CONCURRENCY)

    common_refs.extend((inputs.free_length_basis_ref, inputs.d_amplified_basis_ref))
    common_refs = list(dict.fromkeys(common_refs))

    bottom_knm = float(inputs.bottom_capacity.capacity_knm)
    top_knm = float(inputs.top_capacity.capacity_knm)
    ln_mm = float(inputs.free_length_ln_mm)
    # kN*m * 1000 mm/m / mm = kN
    ve_capacity_kn = (bottom_knm + top_knm) * 1000.0 / ln_mm
    d_candidate_kn = float(inputs.d_amplified_candidate_kn)
    vd_kn = float(inputs.vd_floor_kn)

    pre_floor_kn = min(ve_capacity_kn, d_candidate_kn)
    if vd_kn > pre_floor_kn:
        final_ve_kn = vd_kn
        governing = "TBDY_7_3_7_5_VD_FLOOR"
    elif ve_capacity_kn <= d_candidate_kn:
        final_ve_kn = ve_capacity_kn
        governing = "TBDY_7_3_7_1_EQ7_5"
    else:
        final_ve_kn = d_candidate_kn
        governing = "TBDY_7_3_7_1_D_AMPLIFIED_CANDIDATE"

    return ColumnShearDesignDemandResult(
        component_id=component,
        direction=direction,
        status=DEMAND_PROVEN,
        ve_capacity_eq75_kn=ve_capacity_kn,
        d_amplified_candidate_kn=d_candidate_kn,
        vd_floor_kn=vd_kn,
        final_ve_kn=final_ve_kn,
        governing_rule=governing,
        bottom_capacity=inputs.bottom_capacity,
        top_capacity=inputs.top_capacity,
        source_refs=tuple(common_refs),
    )


__all__ = [
    "V2",
    "V3",
    "M2",
    "M3",
    "CAPACITY_PROVEN",
    "CAPACITY_BLOCKED",
    "DEMAND_PROVEN",
    "BLOCKED_LN",
    "BLOCKED_D",
    "BLOCKED_RS_CONCURRENCY",
    "BLOCKED_END_CAPACITY",
    "SECTION_CAPACITY_UNIT_ADAPTER_REF",
    "ColumnEndMomentCapacityBasis",
    "ColumnShearDesignDemandInput",
    "ColumnShearDesignDemandResult",
    "ColumnShearDemandError",
    "associated_moment_axis",
    "evaluate_tbdy_737_column_shear_demand",
    "resolve_exact_column_end_moment_capacity",
]
