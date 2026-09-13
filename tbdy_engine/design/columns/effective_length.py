"""Pure TS500 7.6.2.2 end-restraint/effective-length kernel.

The caller supplies source-bound connected-member mechanics.  This module owns
TS500 Eq.7.16 ``alpha = sum(I/l)_columns / sum(I/l)_beams`` and the existing
Eq.7.14-7.15 effective-length calculation.  It does not infer topology, member
orientation, releases, or ETABS facts.

Eq.7.16 deliberately uses ``I/l`` rather than ``EI/l``.  Beam contributions
must already carry the reviewed cracked-inertia basis (for the supported
fallback this may be 0.5*Ig); Column contributions carry gross/uncracked I.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Sequence

from tbdy_engine.design.columns.slenderness import SWAY_PERMITTED, SWAY_PREVENTED


class ColumnEffectiveLengthError(ValueError):
    """Raised when a supplied TS500 effective-length basis is malformed."""


EFFECTIVE_LENGTH_AUTHORITY = "TS500_EFFECTIVE_LENGTH_FACTOR"
END_RESTRAINT_AUTHORITY = "TS500_7.6.2.2_END_RESTRAINT_RATIO"
END_RESTRAINT_CONTRIBUTION_AUTHORITY = "TS500_7.6.2.2_END_RESTRAINT_I_OVER_L"


def _text(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ColumnEffectiveLengthError(f"{label} must be a nonblank canonical string")
    return value


def _nonnegative(value: float, label: str) -> float:
    result = float(value)
    if not math.isfinite(result) or result < 0.0:
        raise ColumnEffectiveLengthError(f"{label} must be finite and >= 0")
    return result


def _positive(value: float, label: str) -> float:
    result = float(value)
    if not math.isfinite(result) or result <= 0.0:
        raise ColumnEffectiveLengthError(f"{label} must be finite and > 0")
    return result


@dataclass(frozen=True, slots=True)
class EndRestraintMemberContribution:
    """One already-qualified member contribution to TS500 Eq.7.16."""

    member_id: str
    member_role: str
    inertia_m4: float
    member_length_m: float
    inertia_factor: float
    source_refs: tuple[str, ...]
    authority: str = END_RESTRAINT_CONTRIBUTION_AUTHORITY

    def __post_init__(self) -> None:
        object.__setattr__(self, "member_id", _text(self.member_id, "member_id"))
        role = _text(self.member_role, "member_role")
        if role not in {"COLUMN", "BEAM"}:
            raise ColumnEffectiveLengthError("member_role must be COLUMN or BEAM")
        object.__setattr__(self, "member_role", role)
        object.__setattr__(self, "inertia_m4", _positive(self.inertia_m4, "inertia_m4"))
        object.__setattr__(self, "member_length_m", _positive(self.member_length_m, "member_length_m"))
        factor = _positive(self.inertia_factor, "inertia_factor")
        if factor > 1.0 + 1e-12:
            raise ColumnEffectiveLengthError("inertia_factor must be <= 1")
        object.__setattr__(self, "inertia_factor", min(1.0, factor))
        refs = tuple(_text(ref, "source_ref") for ref in self.source_refs)
        if not refs or len(refs) != len(set(refs)):
            raise ColumnEffectiveLengthError("source_refs must be nonempty and unique")
        object.__setattr__(self, "source_refs", refs)
        if self.authority != END_RESTRAINT_CONTRIBUTION_AUTHORITY:
            raise ColumnEffectiveLengthError("unsupported end-restraint contribution authority")

    @property
    def i_over_l_m3(self) -> float:
        return self.inertia_factor * self.inertia_m4 / self.member_length_m


@dataclass(frozen=True, slots=True)
class ColumnEndRestraintRatioResult:
    end_tag: str
    axis: str
    numerator_column_i_over_l_m3: float
    denominator_beam_i_over_l_m3: float
    alpha: float
    column_member_ids: tuple[str, ...]
    beam_member_ids: tuple[str, ...]
    source_refs: tuple[str, ...]
    authority: str = END_RESTRAINT_AUTHORITY


def evaluate_ts500_end_restraint_ratio(
    *,
    end_tag: str,
    axis: str,
    column_contributions: Sequence[EndRestraintMemberContribution],
    beam_contributions: Sequence[EndRestraintMemberContribution],
    source_refs: Sequence[str] = (),
) -> ColumnEndRestraintRatioResult:
    """Evaluate TS500 Eq.7.16 from already qualified connected-member facts."""
    end = _text(end_tag, "end_tag")
    if end not in {"BOTTOM", "TOP"}:
        raise ColumnEffectiveLengthError("end_tag must be BOTTOM or TOP")
    axis_name = _text(axis, "axis")
    if axis_name not in {"M2", "M3"}:
        raise ColumnEffectiveLengthError("axis must be M2 or M3")

    columns = tuple(column_contributions)
    beams = tuple(beam_contributions)
    if not columns:
        raise ColumnEffectiveLengthError("Eq.7.16 requires at least one connected Column contribution")
    if not beams:
        raise ColumnEffectiveLengthError("Eq.7.16 beam-restraint denominator is unresolved/empty")
    if any(item.member_role != "COLUMN" for item in columns):
        raise ColumnEffectiveLengthError("column_contributions contains a non-Column member")
    if any(item.member_role != "BEAM" for item in beams):
        raise ColumnEffectiveLengthError("beam_contributions contains a non-Beam member")
    if len({item.member_id for item in columns}) != len(columns):
        raise ColumnEffectiveLengthError("duplicate connected Column contribution")
    if len({item.member_id for item in beams}) != len(beams):
        raise ColumnEffectiveLengthError("duplicate connected Beam contribution")

    numerator = sum(item.i_over_l_m3 for item in columns)
    denominator = sum(item.i_over_l_m3 for item in beams)
    if not math.isfinite(numerator) or numerator <= 0.0:
        raise ColumnEffectiveLengthError("Eq.7.16 Column numerator must be finite and > 0")
    if not math.isfinite(denominator) or denominator <= 0.0:
        raise ColumnEffectiveLengthError("Eq.7.16 Beam denominator must be finite and > 0")
    alpha = numerator / denominator
    refs = tuple(
        dict.fromkeys(
            (
                *(_text(ref, "source_ref") for ref in source_refs),
                *(ref for item in columns for ref in item.source_refs),
                *(ref for item in beams for ref in item.source_refs),
                "TS500 7.6.2.2 Eq.7.16:I_over_l",
            )
        )
    )
    if not refs:
        raise ColumnEffectiveLengthError("end-restraint ratio requires source refs")
    return ColumnEndRestraintRatioResult(
        end_tag=end,
        axis=axis_name,
        numerator_column_i_over_l_m3=numerator,
        denominator_beam_i_over_l_m3=denominator,
        alpha=alpha,
        column_member_ids=tuple(sorted(item.member_id for item in columns)),
        beam_member_ids=tuple(sorted(item.member_id for item in beams)),
        source_refs=refs,
    )


@dataclass(frozen=True, slots=True)
class ColumnEffectiveLengthAxisBasis:
    axis: str
    sway_classification: str
    alpha_bottom: float
    alpha_top: float
    one_end_hinged: bool
    source_refs: tuple[str, ...]
    end_restraint_authority: str = END_RESTRAINT_AUTHORITY

    def __post_init__(self) -> None:
        axis = _text(self.axis, "axis")
        if axis not in {"M2", "M3"}:
            raise ColumnEffectiveLengthError("axis must be M2 or M3")
        object.__setattr__(self, "axis", axis)
        sway = _text(self.sway_classification, "sway_classification")
        if sway not in {SWAY_PREVENTED, SWAY_PERMITTED}:
            raise ColumnEffectiveLengthError("unsupported sway classification")
        object.__setattr__(self, "sway_classification", sway)
        object.__setattr__(self, "alpha_bottom", _nonnegative(self.alpha_bottom, "alpha_bottom"))
        object.__setattr__(self, "alpha_top", _nonnegative(self.alpha_top, "alpha_top"))
        if type(self.one_end_hinged) is not bool:
            raise ColumnEffectiveLengthError("one_end_hinged must be bool")
        refs = tuple(_text(ref, "source_ref") for ref in self.source_refs)
        if not refs or len(set(refs)) != len(refs):
            raise ColumnEffectiveLengthError("source_refs must be nonempty and unique")
        object.__setattr__(self, "source_refs", refs)
        if self.end_restraint_authority != END_RESTRAINT_AUTHORITY:
            raise ColumnEffectiveLengthError("end-restraint evidence lacks TS500 authority")


@dataclass(frozen=True, slots=True)
class ColumnEffectiveLengthAxisResult:
    axis: str
    sway_classification: str
    alpha1: float
    alpha2: float
    alpha_m: float
    effective_length_factor_k: float
    source_refs: tuple[str, ...]
    authority: str = EFFECTIVE_LENGTH_AUTHORITY


def evaluate_ts500_effective_length_factor(
    basis: ColumnEffectiveLengthAxisBasis,
) -> ColumnEffectiveLengthAxisResult:
    """Evaluate TS500 Eq.7.14-7.15 for one local bending axis."""
    if not isinstance(basis, ColumnEffectiveLengthAxisBasis):
        raise TypeError("basis must be ColumnEffectiveLengthAxisBasis")

    alpha1, alpha2 = sorted((basis.alpha_bottom, basis.alpha_top))
    alpha_m = 0.5 * (alpha1 + alpha2)

    if basis.sway_classification == SWAY_PREVENTED:
        k = min(
            0.7 + 0.05 * (alpha1 + alpha2),
            0.85 + 0.05 * alpha1,
            1.0,
        )
    elif basis.one_end_hinged:
        k = 2.0 + 0.3 * alpha2
    elif alpha_m < 2.0:
        k = ((20.0 - alpha_m) / 20.0) * math.sqrt(1.0 + alpha_m)
    else:
        k = 0.9 * math.sqrt(1.0 + alpha_m)

    if not math.isfinite(k) or k <= 0.0:
        raise ColumnEffectiveLengthError("computed effective-length factor must be finite and > 0")

    return ColumnEffectiveLengthAxisResult(
        axis=basis.axis,
        sway_classification=basis.sway_classification,
        alpha1=alpha1,
        alpha2=alpha2,
        alpha_m=alpha_m,
        effective_length_factor_k=k,
        source_refs=tuple(dict.fromkeys((*basis.source_refs, "TS500 7.6.2.2 Eq.7.14-7.15"))),
    )


def column_effective_length_mm(*, free_length_mm: float, factor: ColumnEffectiveLengthAxisResult) -> float:
    """Return A19 Lk=k*ln without moving the k decision into application code."""
    ln = _positive(free_length_mm, "free_length_mm")
    if not isinstance(factor, ColumnEffectiveLengthAxisResult):
        raise TypeError("factor must be ColumnEffectiveLengthAxisResult")
    return factor.effective_length_factor_k * ln


__all__ = [
    "ColumnEffectiveLengthAxisBasis",
    "ColumnEffectiveLengthAxisResult",
    "ColumnEffectiveLengthError",
    "ColumnEndRestraintRatioResult",
    "EFFECTIVE_LENGTH_AUTHORITY",
    "END_RESTRAINT_AUTHORITY",
    "END_RESTRAINT_CONTRIBUTION_AUTHORITY",
    "EndRestraintMemberContribution",
    "column_effective_length_mm",
    "evaluate_ts500_effective_length_factor",
    "evaluate_ts500_end_restraint_ratio",
]
