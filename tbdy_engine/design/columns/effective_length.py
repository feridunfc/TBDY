"""Pure TS500 7.6.2.2 effective-length kernel for one column axis.

The caller must provide source-bound end-restraint ratios.  This module owns
only the TS500 Eq.7.14-7.16 calculation.  It does not infer connected members,
local-axis orientation, joint fixity, or ETABS facts.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

from tbdy_engine.design.columns.slenderness import SWAY_PERMITTED, SWAY_PREVENTED


class ColumnEffectiveLengthError(ValueError):
    """Raised when a supplied TS500 effective-length basis is malformed."""


EFFECTIVE_LENGTH_AUTHORITY = "TS500_EFFECTIVE_LENGTH_FACTOR"
END_RESTRAINT_AUTHORITY = "TS500_7.6.2.2_END_RESTRAINT_RATIO"


def _text(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ColumnEffectiveLengthError(f"{label} must be a nonblank canonical string")
    return value


def _nonnegative(value: float, label: str) -> float:
    result = float(value)
    if not math.isfinite(result) or result < 0.0:
        raise ColumnEffectiveLengthError(f"{label} must be finite and >= 0")
    return result


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
    """Evaluate TS500 Eq.7.14-7.16 for one local bending axis."""
    if not isinstance(basis, ColumnEffectiveLengthAxisBasis):
        raise TypeError("basis must be ColumnEffectiveLengthAxisBasis")

    alpha1, alpha2 = sorted((basis.alpha_bottom, basis.alpha_top))
    alpha_m = 0.5 * (alpha1 + alpha2)

    if basis.sway_classification == SWAY_PREVENTED:
        # TS500 Eq.7.14, including both stated upper bounds.
        k = min(
            0.7 + 0.05 * (alpha1 + alpha2),
            0.85 + 0.05 * alpha1,
            1.0,
        )
    elif basis.one_end_hinged:
        # TS500 7.6.2.2 special sway-permitted one-end-hinged expression.
        k = 2.0 + 0.3 * alpha2
    elif alpha_m < 2.0:
        # TS500 Eq.7.15, alpha_m < 2 branch.
        k = ((20.0 - alpha_m) / 20.0) * math.sqrt(1.0 + alpha_m)
    else:
        # TS500 Eq.7.15, alpha_m >= 2 branch.
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
        source_refs=tuple(
            dict.fromkeys(
                (
                    *basis.source_refs,
                    "TS500 7.6.2.2 Eq.7.14-7.16",
                )
            )
        ),
    )


__all__ = [
    "ColumnEffectiveLengthAxisBasis",
    "ColumnEffectiveLengthAxisResult",
    "ColumnEffectiveLengthError",
    "EFFECTIVE_LENGTH_AUTHORITY",
    "END_RESTRAINT_AUTHORITY",
    "evaluate_ts500_effective_length_factor",
]
