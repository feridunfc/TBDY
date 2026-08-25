"""Source-bound response-combination pattern classification for column design.

The classifier is intentionally name-blind. Combination names are identifiers,
not engineering semantics. A combination is supported only when its factual
ETABS definition and the factual case types of all constituents match an
explicitly implemented pattern.

This module performs no demand arithmetic and no ETABS calls.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Mapping, Sequence


SUPPORTED_COMBO_TYPE = "LINEAR_ADD"
SUPPORTED_CASE_TYPES = frozenset({"LinStatic", "LinRespSpec"})
PATTERN_STATIC_LINEAR = "SUPPORTED_STATIC_LINEAR"
PATTERN_STATIC_PLUS_RESPONSE_SPECTRUM = "SUPPORTED_STATIC_PLUS_RESPONSE_SPECTRUM"
PATTERN_RESPONSE_SPECTRUM_ONLY = "SUPPORTED_RESPONSE_SPECTRUM_ONLY"
PATTERN_UNSUPPORTED = "UNSUPPORTED_COMBO_PATTERN"


class ComboPatternError(ValueError):
    """Raised when factual classifier inputs are malformed."""


def _nonblank(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ComboPatternError(f"{label} must be a nonblank canonical string")
    return value


@dataclass(frozen=True, slots=True)
class ComboPatternConstituent:
    """Factual combination constituent before any support/authority decision."""

    name: str
    scale_factor: float
    cname_type: str = "LOAD_CASE"

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _nonblank(self.name, "constituent.name"))
        object.__setattr__(self, "cname_type", _nonblank(self.cname_type, "constituent.cname_type"))
        factor = float(self.scale_factor)
        if not math.isfinite(factor):
            raise ComboPatternError("constituent.scale_factor must be finite")
        object.__setattr__(self, "scale_factor", factor)


@dataclass(frozen=True, slots=True)
class ComboPatternClassification:
    combo_name: str
    combo_type: str
    status: str
    pattern: str
    supported: bool
    static_case_names: tuple[str, ...]
    response_spectrum_case_names: tuple[str, ...]
    unsupported_case_names: tuple[str, ...]
    reasons: tuple[str, ...]


def classify_combo_pattern(
    *,
    combo_name: str,
    combo_type: str,
    constituents: Sequence[ComboPatternConstituent],
    case_types: Mapping[str, str],
) -> ComboPatternClassification:
    """Classify one factual ETABS combination without using its name as semantics.

    Current production scope is deliberately narrow:
    * LINEAR_ADD only;
    * flattened LOAD_CASE constituents only;
    * LinStatic and LinRespSpec case types only.

    Anything else is returned as unsupported rather than guessed or coerced.
    """
    name = _nonblank(combo_name, "combo_name")
    ctype = _nonblank(combo_type, "combo_type")
    terms = tuple(constituents)
    if not terms:
        raise ComboPatternError("combination must contain at least one constituent")

    reasons: list[str] = []
    if ctype != SUPPORTED_COMBO_TYPE:
        reasons.append(f"combo_type={ctype} is not {SUPPORTED_COMBO_TYPE}")

    nested = tuple(term.name for term in terms if term.cname_type != "LOAD_CASE")
    if nested:
        reasons.append("nested/non-load-case constituents are not supported: " + ",".join(sorted(nested)))

    load_case_terms = tuple(term for term in terms if term.cname_type == "LOAD_CASE")
    missing = tuple(sorted({term.name for term in load_case_terms if term.name not in case_types}))
    if missing:
        reasons.append("factual case type missing for: " + ",".join(missing))

    static_names: list[str] = []
    spectrum_names: list[str] = []
    unsupported_names: list[str] = []
    for term in load_case_terms:
        case_type = case_types.get(term.name)
        if case_type == "LinStatic":
            static_names.append(term.name)
        elif case_type == "LinRespSpec":
            spectrum_names.append(term.name)
        elif case_type is not None:
            unsupported_names.append(term.name)

    if unsupported_names:
        details = ",".join(f"{case}:{case_types[case]}" for case in sorted(unsupported_names))
        reasons.append("unsupported constituent case type(s): " + details)

    if reasons:
        return ComboPatternClassification(
            combo_name=name,
            combo_type=ctype,
            status="BLOCKED_UNSUPPORTED_COMBO_PATTERN",
            pattern=PATTERN_UNSUPPORTED,
            supported=False,
            static_case_names=tuple(static_names),
            response_spectrum_case_names=tuple(spectrum_names),
            unsupported_case_names=tuple(sorted(unsupported_names)),
            reasons=tuple(reasons),
        )

    if spectrum_names and static_names:
        pattern = PATTERN_STATIC_PLUS_RESPONSE_SPECTRUM
    elif spectrum_names:
        pattern = PATTERN_RESPONSE_SPECTRUM_ONLY
    else:
        pattern = PATTERN_STATIC_LINEAR

    return ComboPatternClassification(
        combo_name=name,
        combo_type=ctype,
        status="PROVEN_SUPPORTED_COMBO_PATTERN",
        pattern=pattern,
        supported=True,
        static_case_names=tuple(static_names),
        response_spectrum_case_names=tuple(spectrum_names),
        unsupported_case_names=(),
        reasons=(),
    )


__all__ = [
    "ComboPatternClassification",
    "ComboPatternConstituent",
    "ComboPatternError",
    "PATTERN_RESPONSE_SPECTRUM_ONLY",
    "PATTERN_STATIC_LINEAR",
    "PATTERN_STATIC_PLUS_RESPONSE_SPECTRUM",
    "PATTERN_UNSUPPORTED",
    "SUPPORTED_CASE_TYPES",
    "SUPPORTED_COMBO_TYPE",
    "classify_combo_pattern",
]
