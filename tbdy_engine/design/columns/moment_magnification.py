"""Pure TS500 7.6.2.4-7.6.2.6 column moment-magnification kernel.

M2 and M3 are intentionally evaluated as independent local-axis pipelines.
The caller supplies source-bound demand, creep, stiffness and (for sway-
permitted systems) story critical-load aggregates.  This module does not read
ETABS, infer load roles, infer local-axis orientation, or select a governing
load combination.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
import math

from tbdy_engine.design.columns.rebar_selection import ColumnDemandState
from tbdy_engine.design.columns.slenderness import SWAY_PERMITTED, SWAY_PREVENTED


class ColumnMomentMagnificationError(ValueError):
    """Raised when a TS500 moment-magnification basis is malformed."""


MOMENT_MAGNIFICATION_AUTHORITY = "TS500_7.6.2.4_7.6.2.6_MOMENT_MAGNIFICATION"
STIFFNESS_METHOD_EQ_7_20 = "TS500_EQ_7_20"
STIFFNESS_METHOD_EQ_7_21 = "TS500_EQ_7_21"
STATUS_APPLIED = "MOMENT_MAGNIFICATION_APPLIED"
STATUS_BLOCKED = "MOMENT_MAGNIFICATION_BLOCKED"


def _text(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ColumnMomentMagnificationError(f"{label} must be a nonblank canonical string")
    return value


def _finite(value: float, label: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ColumnMomentMagnificationError(f"{label} must be finite")
    return result


def _positive(value: float, label: str) -> float:
    result = _finite(value, label)
    if result <= 0.0:
        raise ColumnMomentMagnificationError(f"{label} must be > 0")
    return result


def _nonnegative(value: float, label: str) -> float:
    result = _finite(value, label)
    if result < 0.0:
        raise ColumnMomentMagnificationError(f"{label} must be >= 0")
    return result


def _ratio(value: float, label: str) -> float:
    result = _finite(value, label)
    if result < -1.0 - 1e-12 or result > 1.0 + 1e-12:
        raise ColumnMomentMagnificationError(f"{label} must be within [-1, 1]")
    return max(-1.0, min(1.0, result))


@dataclass(frozen=True, slots=True)
class ColumnMomentMagnificationAxisBasis:
    demand_state_id: str
    axis: str
    sway_classification: str
    nd_compression_n: float
    m1_over_m2: float
    effective_length_lk_mm: float
    radius_i_mm: float
    ec_mpa: float
    ic_mm4: float
    creep_ratio_rm: float
    stiffness_method: str
    source_refs: tuple[str, ...]
    es_mpa: float | None = None
    is_mm4: float | None = None
    horizontal_load_between_ends: bool = False
    story_sum_nd_n: float | None = None
    story_sum_nk_n: float | None = None
    fck_mpa: float | None = None
    concrete_area_mm2: float | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "demand_state_id", _text(self.demand_state_id, "demand_state_id"))
        axis = _text(self.axis, "axis")
        if axis not in {"M2", "M3"}:
            raise ColumnMomentMagnificationError("axis must be M2 or M3")
        object.__setattr__(self, "axis", axis)
        sway = _text(self.sway_classification, "sway_classification")
        if sway not in {SWAY_PREVENTED, SWAY_PERMITTED}:
            raise ColumnMomentMagnificationError("unsupported sway classification")
        object.__setattr__(self, "sway_classification", sway)
        object.__setattr__(self, "nd_compression_n", _nonnegative(self.nd_compression_n, "nd_compression_n"))
        object.__setattr__(self, "m1_over_m2", _ratio(self.m1_over_m2, "m1_over_m2"))
        object.__setattr__(self, "effective_length_lk_mm", _positive(self.effective_length_lk_mm, "effective_length_lk_mm"))
        object.__setattr__(self, "radius_i_mm", _positive(self.radius_i_mm, "radius_i_mm"))
        object.__setattr__(self, "ec_mpa", _positive(self.ec_mpa, "ec_mpa"))
        object.__setattr__(self, "ic_mm4", _positive(self.ic_mm4, "ic_mm4"))
        rm = _nonnegative(self.creep_ratio_rm, "creep_ratio_rm")
        if rm > 1.0 + 1e-12:
            raise ColumnMomentMagnificationError("creep_ratio_rm must be <= 1")
        object.__setattr__(self, "creep_ratio_rm", min(1.0, rm))
        method = _text(self.stiffness_method, "stiffness_method")
        if method not in {STIFFNESS_METHOD_EQ_7_20, STIFFNESS_METHOD_EQ_7_21}:
            raise ColumnMomentMagnificationError("unsupported TS500 EI method")
        object.__setattr__(self, "stiffness_method", method)
        if type(self.horizontal_load_between_ends) is not bool:
            raise ColumnMomentMagnificationError("horizontal_load_between_ends must be bool")
        refs = tuple(_text(ref, "source_ref") for ref in self.source_refs)
        if not refs or len(set(refs)) != len(refs):
            raise ColumnMomentMagnificationError("source_refs must be nonempty and unique")
        object.__setattr__(self, "source_refs", refs)

        if method == STIFFNESS_METHOD_EQ_7_20:
            if self.es_mpa is None or self.is_mm4 is None:
                raise ColumnMomentMagnificationError("Eq.7.20 requires es_mpa and is_mm4")
            object.__setattr__(self, "es_mpa", _positive(self.es_mpa, "es_mpa"))
            object.__setattr__(self, "is_mm4", _nonnegative(self.is_mm4, "is_mm4"))
        elif self.es_mpa is not None or self.is_mm4 is not None:
            raise ColumnMomentMagnificationError("Eq.7.21 basis must not carry partial Eq.7.20 steel stiffness")

        if sway == SWAY_PERMITTED:
            for name in ("story_sum_nd_n", "story_sum_nk_n", "fck_mpa", "concrete_area_mm2"):
                value = getattr(self, name)
                if value is None:
                    raise ColumnMomentMagnificationError(f"sway-permitted basis requires {name}")
                object.__setattr__(self, name, _positive(value, name))
        else:
            if self.story_sum_nd_n is not None or self.story_sum_nk_n is not None:
                raise ColumnMomentMagnificationError(
                    "sway-prevented axis must not carry sway-permitted story critical-load aggregates"
                )


@dataclass(frozen=True, slots=True)
class ColumnMomentMagnificationAxisResult:
    demand_state_id: str
    axis: str
    status: str
    effective_ei_nmm2: float | None
    critical_load_nk_n: float | None
    cm: float | None
    beta_individual: float | None
    beta_story: float | None
    final_magnification_factor: float | None
    slenderness_lk_over_i: float
    eq729_product_required: bool | None
    blockers: tuple[str, ...]
    source_refs: tuple[str, ...]
    authority: str = MOMENT_MAGNIFICATION_AUTHORITY

    @property
    def applied(self) -> bool:
        return self.status == STATUS_APPLIED


def _effective_ei(basis: ColumnMomentMagnificationAxisBasis) -> float:
    denominator = 1.0 + basis.creep_ratio_rm
    if basis.stiffness_method == STIFFNESS_METHOD_EQ_7_20:
        assert basis.es_mpa is not None and basis.is_mm4 is not None
        return (0.2 * basis.ec_mpa * basis.ic_mm4 + basis.es_mpa * basis.is_mm4) / denominator
    return (0.4 * basis.ec_mpa * basis.ic_mm4) / denominator


def evaluate_ts500_axis_moment_magnification(
    basis: ColumnMomentMagnificationAxisBasis,
) -> ColumnMomentMagnificationAxisResult:
    """Evaluate one local-axis TS500 Eq.7.19-7.29 magnification pipeline."""
    if not isinstance(basis, ColumnMomentMagnificationAxisBasis):
        raise TypeError("basis must be ColumnMomentMagnificationAxisBasis")

    ei = _effective_ei(basis)
    nk = math.pi**2 * ei / (basis.effective_length_lk_mm**2)
    slenderness = basis.effective_length_lk_mm / basis.radius_i_mm
    refs = tuple(dict.fromkeys((*basis.source_refs, "TS500 7.6.2.4-7.6.2.6 Eq.7.19-7.29")))
    if not math.isfinite(ei) or ei <= 0.0 or not math.isfinite(nk) or nk <= 0.0:
        return ColumnMomentMagnificationAxisResult(
            demand_state_id=basis.demand_state_id,
            axis=basis.axis,
            status=STATUS_BLOCKED,
            effective_ei_nmm2=None,
            critical_load_nk_n=None,
            cm=None,
            beta_individual=None,
            beta_story=None,
            final_magnification_factor=None,
            slenderness_lk_over_i=slenderness,
            eq729_product_required=None,
            blockers=("NONPOSITIVE_EFFECTIVE_STIFFNESS_OR_CRITICAL_LOAD",),
            source_refs=refs,
        )

    if basis.sway_classification == SWAY_PREVENTED:
        cm = 1.0 if basis.horizontal_load_between_ends else max(0.4, 0.6 + 0.4 * basis.m1_over_m2)
        denominator = 1.0 - basis.nd_compression_n / (1.3 * nk)
        if denominator <= 0.0:
            return ColumnMomentMagnificationAxisResult(
                demand_state_id=basis.demand_state_id,
                axis=basis.axis,
                status=STATUS_BLOCKED,
                effective_ei_nmm2=ei,
                critical_load_nk_n=nk,
                cm=cm,
                beta_individual=None,
                beta_story=None,
                final_magnification_factor=None,
                slenderness_lk_over_i=slenderness,
                eq729_product_required=None,
                blockers=("TS500_EQ_7_24_NONPOSITIVE_DENOMINATOR",),
                source_refs=refs,
            )
        beta = max(1.0, cm / denominator)
        return ColumnMomentMagnificationAxisResult(
            demand_state_id=basis.demand_state_id,
            axis=basis.axis,
            status=STATUS_APPLIED,
            effective_ei_nmm2=ei,
            critical_load_nk_n=nk,
            cm=cm,
            beta_individual=beta,
            beta_story=None,
            final_magnification_factor=beta,
            slenderness_lk_over_i=slenderness,
            eq729_product_required=False,
            blockers=(),
            source_refs=refs,
        )

    assert basis.story_sum_nd_n is not None
    assert basis.story_sum_nk_n is not None
    assert basis.fck_mpa is not None
    assert basis.concrete_area_mm2 is not None

    story_ratio = basis.story_sum_nd_n / basis.story_sum_nk_n
    if story_ratio > 0.45 + 1e-12:
        return ColumnMomentMagnificationAxisResult(
            demand_state_id=basis.demand_state_id,
            axis=basis.axis,
            status=STATUS_BLOCKED,
            effective_ei_nmm2=ei,
            critical_load_nk_n=nk,
            cm=1.0,
            beta_individual=None,
            beta_story=None,
            final_magnification_factor=None,
            slenderness_lk_over_i=slenderness,
            eq729_product_required=None,
            blockers=("TS500_EQ_7_28_STORY_CRITICAL_LOAD_LIMIT_EXCEEDED",),
            source_refs=refs,
        )

    individual_denominator = 1.0 - basis.nd_compression_n / (1.3 * nk)
    story_denominator = 1.0 - basis.story_sum_nd_n / (1.3 * basis.story_sum_nk_n)
    if individual_denominator <= 0.0 or story_denominator <= 0.0:
        return ColumnMomentMagnificationAxisResult(
            demand_state_id=basis.demand_state_id,
            axis=basis.axis,
            status=STATUS_BLOCKED,
            effective_ei_nmm2=ei,
            critical_load_nk_n=nk,
            cm=1.0,
            beta_individual=None,
            beta_story=None,
            final_magnification_factor=None,
            slenderness_lk_over_i=slenderness,
            eq729_product_required=None,
            blockers=("TS500_SWAY_PERMITTED_MAGNIFICATION_NONPOSITIVE_DENOMINATOR",),
            source_refs=refs,
        )

    beta = max(1.0, 1.0 / individual_denominator)
    beta_story = max(1.0, 1.0 / story_denominator)
    axial_ratio = basis.nd_compression_n / (basis.fck_mpa * basis.concrete_area_mm2)
    if axial_ratio <= 0.0:
        eq729_product_required = False
    else:
        eq729_limit = 35.0 / math.sqrt(axial_ratio)
        eq729_product_required = slenderness > eq729_limit
    final = beta * beta_story if eq729_product_required else max(beta, beta_story)

    return ColumnMomentMagnificationAxisResult(
        demand_state_id=basis.demand_state_id,
        axis=basis.axis,
        status=STATUS_APPLIED,
        effective_ei_nmm2=ei,
        critical_load_nk_n=nk,
        cm=1.0,
        beta_individual=beta,
        beta_story=beta_story,
        final_magnification_factor=final,
        slenderness_lk_over_i=slenderness,
        eq729_product_required=eq729_product_required,
        blockers=(),
        source_refs=refs,
    )


def magnify_concurrent_column_demand_state(
    state: ColumnDemandState,
    *,
    m2: ColumnMomentMagnificationAxisResult | None,
    m3: ColumnMomentMagnificationAxisResult | None,
) -> ColumnDemandState:
    """Apply independent local-axis factors to one exact concurrent P-M2-M3 state."""
    if not isinstance(state, ColumnDemandState):
        raise TypeError("state must be ColumnDemandState")
    for expected_axis, result in (("M2", m2), ("M3", m3)):
        if result is None:
            continue
        if not isinstance(result, ColumnMomentMagnificationAxisResult):
            raise TypeError(f"{expected_axis} result has wrong type")
        if result.axis != expected_axis or result.demand_state_id != state.state_id:
            raise ColumnMomentMagnificationError(
                f"{expected_axis} magnification result does not bind the exact demand state"
            )
        if not result.applied or result.final_magnification_factor is None:
            raise ColumnMomentMagnificationError(
                f"{expected_axis} magnification result is not an applied canonical result"
            )

    factor2 = 1.0 if m2 is None else m2.final_magnification_factor
    factor3 = 1.0 if m3 is None else m3.final_magnification_factor
    assert factor2 is not None and factor3 is not None
    refs = tuple(
        dict.fromkeys(
            (
                state.source_identity,
                *(m2.source_refs if m2 is not None else ()),
                *(m3.source_refs if m3 is not None else ()),
            )
        )
    )
    return replace(
        state,
        m2_nmm=state.m2_nmm * factor2,
        m3_nmm=state.m3_nmm * factor3,
        source_identity=(
            f"{state.source_identity}|TS500_MAGNIFIED|M2={factor2:.12g}|M3={factor3:.12g}|"
            + ";".join(refs[1:])
        ),
    )


__all__ = [
    "ColumnMomentMagnificationAxisBasis",
    "ColumnMomentMagnificationAxisResult",
    "ColumnMomentMagnificationError",
    "MOMENT_MAGNIFICATION_AUTHORITY",
    "STATUS_APPLIED",
    "STATUS_BLOCKED",
    "STIFFNESS_METHOD_EQ_7_20",
    "STIFFNESS_METHOD_EQ_7_21",
    "evaluate_ts500_axis_moment_magnification",
    "magnify_concurrent_column_demand_state",
]
