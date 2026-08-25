"""Source-bound TS500 column slenderness/second-order closure for VS6.

This module deliberately separates *regulatory basis evidence* from the TS500
calculation itself.  It does not promote factual ETABS object length, story
height, end offsets, sway classification, local-axis semantics or an effective
length coefficient on its own.

The current production scope closes slenderness only when it is proven that the
TS500 7.6.2.3 neglect limits are satisfied in both principal bending directions.
If either direction requires moment magnification, the result is truthful
``REQUIRES_MOMENT_MAGNIFICATION`` and downstream longitudinal-rebar authority
remains blocked until the TS500 7.6.2.4-7.6.2.6 magnification path is implemented.
"""
from __future__ import annotations

from dataclasses import dataclass
import math


class ColumnSlendernessError(ValueError):
    """Raised when a supplied regulatory slenderness basis is malformed."""


SWAY_PREVENTED = "SWAY_PREVENTED"
SWAY_PERMITTED = "SWAY_PERMITTED"
_ALLOWED_SWAY = frozenset({SWAY_PREVENTED, SWAY_PERMITTED})

TS500_RECTANGULAR_RADIUS_FACTOR = 0.30
TS500_SWAY_PERMITTED_NEGLECT_LIMIT = 22.0
TS500_SWAY_PREVENTED_LIMIT_CAP = 40.0
TS500_APPROX_METHOD_MAX_SLENDERNESS = 100.0


def _text(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ColumnSlendernessError(f"{label} must be a nonblank canonical string")
    return value


def _positive(value: float, label: str) -> float:
    result = float(value)
    if not math.isfinite(result) or result <= 0.0:
        raise ColumnSlendernessError(f"{label} must be finite and > 0")
    return result


def _ratio(value: float, label: str) -> float:
    result = float(value)
    if not math.isfinite(result) or result < -1.0 - 1e-12 or result > 1.0 + 1e-12:
        raise ColumnSlendernessError(f"{label} must be finite and within [-1, 1]")
    return max(-1.0, min(1.0, result))


@dataclass(frozen=True, slots=True)
class ColumnSlendernessAxisBasis:
    """Regulatory evidence required to evaluate one bending direction.

    ``section_dimension_mm`` is the rectangular-section dimension in the
    bending plane used for TS500's i=0.30h approximation.  ``free_length_ln_mm``
    must already be promoted as the TS500 column free length; a factual ETABS
    geometry candidate is not sufficient by itself.

    ``moment_ratio_m1_over_m2`` follows TS500 7.6.2.3: |M1| <= |M2| and the sign
    is positive for single curvature, negative for double curvature.  It is
    required only for sway-prevented columns.
    """

    axis: str
    section_dimension_mm: float
    free_length_ln_mm: float
    effective_length_factor_k: float
    sway_classification: str
    moment_ratio_m1_over_m2: float | None
    source_refs: tuple[str, ...]
    free_length_authority: str = "TS500_REGULATORY_FREE_LENGTH"
    effective_length_authority: str = "TS500_EFFECTIVE_LENGTH_FACTOR"
    sway_authority: str = "TS500_SWAY_CLASSIFICATION"
    moment_ratio_authority: str = "TS500_END_MOMENT_RATIO"

    def __post_init__(self) -> None:
        axis = _text(self.axis, "axis")
        if axis not in {"M2", "M3"}:
            raise ColumnSlendernessError("axis must be M2 or M3")
        object.__setattr__(self, "axis", axis)
        object.__setattr__(
            self, "section_dimension_mm", _positive(self.section_dimension_mm, "section_dimension_mm")
        )
        object.__setattr__(self, "free_length_ln_mm", _positive(self.free_length_ln_mm, "free_length_ln_mm"))
        object.__setattr__(
            self,
            "effective_length_factor_k",
            _positive(self.effective_length_factor_k, "effective_length_factor_k"),
        )
        sway = _text(self.sway_classification, "sway_classification")
        if sway not in _ALLOWED_SWAY:
            raise ColumnSlendernessError(f"unsupported sway_classification={sway}")
        object.__setattr__(self, "sway_classification", sway)

        if sway == SWAY_PREVENTED:
            if self.moment_ratio_m1_over_m2 is None:
                raise ColumnSlendernessError(
                    "sway-prevented slenderness neglect check requires moment_ratio_m1_over_m2"
                )
            object.__setattr__(
                self,
                "moment_ratio_m1_over_m2",
                _ratio(self.moment_ratio_m1_over_m2, "moment_ratio_m1_over_m2"),
            )
        elif self.moment_ratio_m1_over_m2 is not None:
            object.__setattr__(
                self,
                "moment_ratio_m1_over_m2",
                _ratio(self.moment_ratio_m1_over_m2, "moment_ratio_m1_over_m2"),
            )

        refs = tuple(_text(item, "source_ref") for item in self.source_refs)
        if not refs or len(refs) != len(set(refs)):
            raise ColumnSlendernessError("source_refs must be nonempty and unique")
        object.__setattr__(self, "source_refs", refs)

        if self.free_length_authority != "TS500_REGULATORY_FREE_LENGTH":
            raise ColumnSlendernessError("free length has not been promoted to TS500 regulatory authority")
        if self.effective_length_authority != "TS500_EFFECTIVE_LENGTH_FACTOR":
            raise ColumnSlendernessError("effective-length factor lacks TS500 authority")
        if self.sway_authority != "TS500_SWAY_CLASSIFICATION":
            raise ColumnSlendernessError("sway classification lacks TS500 authority")
        if sway == SWAY_PREVENTED and self.moment_ratio_authority != "TS500_END_MOMENT_RATIO":
            raise ColumnSlendernessError("M1/M2 ratio lacks TS500 end-moment-ratio authority")


@dataclass(frozen=True, slots=True)
class ColumnSlendernessBasis:
    component_id: str
    m2: ColumnSlendernessAxisBasis
    m3: ColumnSlendernessAxisBasis
    source_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "component_id", _text(self.component_id, "component_id"))
        if self.m2.axis != "M2" or self.m3.axis != "M3":
            raise ColumnSlendernessError("basis requires exactly M2 and M3 axis records")
        refs = tuple(_text(item, "basis_source_ref") for item in self.source_refs)
        if not refs or len(refs) != len(set(refs)):
            raise ColumnSlendernessError("basis source_refs must be nonempty and unique")
        object.__setattr__(self, "source_refs", refs)


@dataclass(frozen=True, slots=True)
class ColumnSlendernessAxisResult:
    axis: str
    sway_classification: str | None
    section_dimension_mm: float | None
    free_length_ln_mm: float | None
    effective_length_factor_k: float | None
    effective_length_lk_mm: float | None
    radius_of_gyration_i_mm: float | None
    slenderness_ratio_lk_over_i: float | None
    moment_ratio_m1_over_m2: float | None
    neglect_limit: float | None
    status: str
    source_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ColumnSlendernessResult:
    component_id: str
    status: str
    m2: ColumnSlendernessAxisResult
    m3: ColumnSlendernessAxisResult
    source_refs: tuple[str, ...]
    authority: str = "TS500_7.6_COLUMN_SLENDERNESS"

    @property
    def resolved(self) -> bool:
        return self.status == "PROVEN_SLENDERNESS_EFFECTS_NEGLIGIBLE"

    @property
    def requires_moment_magnification(self) -> bool:
        return self.status == "REQUIRES_MOMENT_MAGNIFICATION"


def _blocked_axis(axis: str) -> ColumnSlendernessAxisResult:
    return ColumnSlendernessAxisResult(
        axis=axis,
        sway_classification=None,
        section_dimension_mm=None,
        free_length_ln_mm=None,
        effective_length_factor_k=None,
        effective_length_lk_mm=None,
        radius_of_gyration_i_mm=None,
        slenderness_ratio_lk_over_i=None,
        moment_ratio_m1_over_m2=None,
        neglect_limit=None,
        status="BLOCKED_MISSING_REGULATORY_BASIS",
        source_refs=(),
    )


def _evaluate_axis(basis: ColumnSlendernessAxisBasis) -> ColumnSlendernessAxisResult:
    radius = TS500_RECTANGULAR_RADIUS_FACTOR * basis.section_dimension_mm
    effective_length = basis.effective_length_factor_k * basis.free_length_ln_mm
    slenderness = effective_length / radius

    if basis.sway_classification == SWAY_PREVENTED:
        ratio = float(basis.moment_ratio_m1_over_m2)
        limit = min(TS500_SWAY_PREVENTED_LIMIT_CAP, 34.0 - 12.0 * ratio)
    else:
        ratio = basis.moment_ratio_m1_over_m2
        limit = TS500_SWAY_PERMITTED_NEGLECT_LIMIT

    if slenderness > TS500_APPROX_METHOD_MAX_SLENDERNESS + 1e-12:
        status = "GENERAL_SECOND_ORDER_ANALYSIS_REQUIRED"
    elif slenderness <= limit + 1e-12:
        status = "SLENDERNESS_EFFECTS_NEGLIGIBLE"
    else:
        status = "MOMENT_MAGNIFICATION_REQUIRED"

    return ColumnSlendernessAxisResult(
        axis=basis.axis,
        sway_classification=basis.sway_classification,
        section_dimension_mm=basis.section_dimension_mm,
        free_length_ln_mm=basis.free_length_ln_mm,
        effective_length_factor_k=basis.effective_length_factor_k,
        effective_length_lk_mm=effective_length,
        radius_of_gyration_i_mm=radius,
        slenderness_ratio_lk_over_i=slenderness,
        moment_ratio_m1_over_m2=ratio,
        neglect_limit=limit,
        status=status,
        source_refs=basis.source_refs,
    )


def evaluate_ts500_column_slenderness(
    *,
    component_id: str,
    basis: ColumnSlendernessBasis | None,
) -> ColumnSlendernessResult:
    """Evaluate TS500 7.6.2.3 neglect limits without inventing missing basis.

    ``basis=None`` is intentionally a normal fail-closed result.  This lets the
    integrated design engine own the slenderness authority while live evidence
    promotion is developed independently.
    """
    component = _text(component_id, "component_id")
    if basis is None:
        return ColumnSlendernessResult(
            component_id=component,
            status="BLOCKED_SLENDERNESS_BASIS",
            m2=_blocked_axis("M2"),
            m3=_blocked_axis("M3"),
            source_refs=("TS500 7.6 slenderness basis not yet promoted",),
        )
    if basis.component_id != component:
        raise ColumnSlendernessError("slenderness basis component_id differs from component_id")

    m2 = _evaluate_axis(basis.m2)
    m3 = _evaluate_axis(basis.m3)
    statuses = {m2.status, m3.status}
    if statuses == {"SLENDERNESS_EFFECTS_NEGLIGIBLE"}:
        status = "PROVEN_SLENDERNESS_EFFECTS_NEGLIGIBLE"
    elif "GENERAL_SECOND_ORDER_ANALYSIS_REQUIRED" in statuses:
        status = "GENERAL_SECOND_ORDER_ANALYSIS_REQUIRED"
    else:
        status = "REQUIRES_MOMENT_MAGNIFICATION"

    refs = tuple(dict.fromkeys((*basis.source_refs, *basis.m2.source_refs, *basis.m3.source_refs)))
    return ColumnSlendernessResult(
        component_id=component,
        status=status,
        m2=m2,
        m3=m3,
        source_refs=refs,
    )


__all__ = [
    "ColumnSlendernessAxisBasis",
    "ColumnSlendernessAxisResult",
    "ColumnSlendernessBasis",
    "ColumnSlendernessError",
    "ColumnSlendernessResult",
    "SWAY_PERMITTED",
    "SWAY_PREVENTED",
    "TS500_APPROX_METHOD_MAX_SLENDERNESS",
    "TS500_RECTANGULAR_RADIUS_FACTOR",
    "TS500_SWAY_PERMITTED_NEGLECT_LIMIT",
    "TS500_SWAY_PREVENTED_LIMIT_CAP",
    "evaluate_ts500_column_slenderness",
]
