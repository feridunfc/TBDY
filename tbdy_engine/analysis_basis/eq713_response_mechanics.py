"""Source-bound response-mode closure for the existing TS500 Eq.7.13 authority.

This subordinate analysis-basis helper resolves only mode participation that the
static geometry/role projection deliberately leaves unknown.  It consumes exact
local generalized-result populations from one qualified B5 generation.  It never
acquires ETABS facts and never changes an already-resolved static disposition.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import math
from typing import Mapping, Sequence

from .eq713_frame_mechanics import (
    FrameEq713MechanicsError,
    FrameModeParticipationClassification,
    FrameModeParticipationEvidence,
)
from .eq713_uncracked_analysis_state import (
    AreaEq713TargetDisposition,
    AreaStiffnessMode,
    ContributorDisposition,
    FrameStiffnessMode,
    ModeDisposition,
)

EQ713_MEMBER_RESPONSE_MECHANICS_CONTRACT = "TS500_EQ713_MEMBER_RESPONSE_MECHANICS_V1"

_AREA_SLOT = {
    AreaStiffnessMode.F11: 0,
    AreaStiffnessMode.F22: 1,
    AreaStiffnessMode.F12: 2,
    AreaStiffnessMode.M11: 3,
    AreaStiffnessMode.M22: 4,
    AreaStiffnessMode.M12: 5,
    AreaStiffnessMode.V13: 6,
    AreaStiffnessMode.V23: 7,
}
_RESPONSE_AREA_MODES = {
    AreaStiffnessMode.M11,
    AreaStiffnessMode.M22,
    AreaStiffnessMode.M12,
    AreaStiffnessMode.V13,
    AreaStiffnessMode.V23,
}


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError(f"{label} must be a nonblank canonical string")
    return value


def _refs(values: Sequence[str]) -> tuple[str, ...]:
    result = tuple(dict.fromkeys(_text(value, "source_ref") for value in values))
    if not result:
        raise ValueError("source_refs must not be empty")
    return result


def _decimal(value: object, label: str) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise ValueError(f"{label} must be numeric")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{label} must be numeric") from exc
    if not result.is_finite():
        raise ValueError(f"{label} must be finite")
    return result


def _values(values: Sequence[object], label: str) -> tuple[float, ...]:
    result = []
    for index, value in enumerate(values):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{label}[{index}] must be numeric")
        number = float(value)
        if not math.isfinite(number):
            raise ValueError(f"{label}[{index}] must be finite")
        result.append(number)
    return tuple(result)


def _response_truth(
    *,
    values: Sequence[object],
    effective_modifier: object,
) -> tuple[bool | None, str]:
    observed = _values(values, "response_values")
    effective = _decimal(effective_modifier, "effective_modifier")
    if not observed:
        return None, "exact response population is empty"
    if effective <= 0:
        return None, "effective stiffness modifier is non-positive; response evidence cannot prove participation"
    if any(value != 0.0 for value in observed):
        return True, "exact local generalized-result population contains nonzero response with positive effective stiffness"
    return None, "exact local generalized-result population is identically zero; response evidence cannot prove non-participation"


@dataclass(frozen=True, slots=True)
class ResponseModeResolution:
    participates: bool | None
    reason: str


def classify_frame_response_participation(
    *,
    base: FrameModeParticipationClassification,
    values_by_mode: Mapping[FrameStiffnessMode, Sequence[object]],
    effective_modifiers: Mapping[FrameStiffnessMode, object],
    source_refs: Sequence[str],
) -> FrameModeParticipationClassification:
    """Resolve only static ``None`` Frame modes from exact local response facts."""
    if not isinstance(base, FrameModeParticipationClassification):
        raise TypeError("base must be FrameModeParticipationClassification")
    refs = _refs((*base.source_refs, *source_refs, EQ713_MEMBER_RESPONSE_MECHANICS_CONTRACT))
    rows = []
    for row in base.mode_evidence:
        if row.participates is not None:
            rows.append(row)
            continue
        if row.mode not in values_by_mode or row.mode not in effective_modifiers:
            rows.append(
                FrameModeParticipationEvidence(
                    row.mode,
                    None,
                    "member-level response evidence is absent for unresolved Frame mode",
                    refs,
                )
            )
            continue
        participates, reason = _response_truth(
            values=values_by_mode[row.mode],
            effective_modifier=effective_modifiers[row.mode],
        )
        rows.append(FrameModeParticipationEvidence(row.mode, participates, reason, refs))
    try:
        return FrameModeParticipationClassification(base.component_uid, tuple(rows), refs)
    except FrameEq713MechanicsError:
        raise


def resolve_area_response_modes(
    *,
    base: AreaEq713TargetDisposition,
    values_by_mode: Mapping[AreaStiffnessMode, Sequence[object]],
    effective_modifiers: Mapping[AreaStiffnessMode, object],
    source_refs: Sequence[str],
) -> AreaEq713TargetDisposition:
    """Resolve only blocked ShellThick plate/transverse modes, slot by slot."""
    if not isinstance(base, AreaEq713TargetDisposition):
        raise TypeError("base must be AreaEq713TargetDisposition")
    if base.target_property_modifiers is None:
        return base
    refs = _refs((*base.source_refs, *source_refs, EQ713_MEMBER_RESPONSE_MECHANICS_CONTRACT))
    target = list(base.target_property_modifiers)
    rows = []
    for row in base.mode_dispositions:
        if (
            row.disposition is not ContributorDisposition.BLOCKED_UNSUPPORTED
            or row.mode not in _RESPONSE_AREA_MODES
        ):
            rows.append(row)
            continue
        if row.mode not in values_by_mode or row.mode not in effective_modifiers:
            rows.append(ModeDisposition(row.mode, row.disposition, row.reason, refs))
            continue
        participates, reason = _response_truth(
            values=values_by_mode[row.mode],
            effective_modifier=effective_modifiers[row.mode],
        )
        if participates is True:
            target[_AREA_SLOT[row.mode]] = Decimal("1")
            disposition = ContributorDisposition.TARGETED_UNCRACKED
        elif participates is False:
            disposition = ContributorDisposition.PROVEN_NON_PARTICIPATING_MODE
        else:
            disposition = ContributorDisposition.BLOCKED_UNSUPPORTED
        rows.append(ModeDisposition(row.mode, disposition, reason, refs))
    blocked = tuple(
        dict.fromkeys(
            row.reason
            for row in rows
            if row.disposition is ContributorDisposition.BLOCKED_UNSUPPORTED
        )
    )
    return AreaEq713TargetDisposition(
        area_name=base.area_name,
        mode_dispositions=tuple(rows),
        target_property_modifiers=tuple(target),
        blocked_reasons=blocked,
        source_refs=refs,
        audit_limitations=base.audit_limitations,
    )


__all__ = [
    "EQ713_MEMBER_RESPONSE_MECHANICS_CONTRACT",
    "ResponseModeResolution",
    "classify_frame_response_participation",
    "resolve_area_response_modes",
]
