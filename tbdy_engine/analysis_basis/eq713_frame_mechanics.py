"""Bounded Frame mechanics projection for the existing TS500 Eq.7.13 authority.

This module is a tightly subordinate part of the existing Eq713 analysis-basis
family.  It owns no ETABS acquisition or mutation.  Factual callers supply
member geometry/axis/end-condition evidence; this module classifies only the
narrow horizontal story-translation mechanism that can be proven from those
facts.  Unknown mode participation remains ``None`` and therefore fails closed
when passed to ``audit_frame_eq713_modes``.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import math
from typing import Mapping, Sequence

from .eq713_uncracked_analysis_state import (
    ContributorDisposition,
    FrameModeAuditDisposition,
    FrameStiffnessMode,
    _FRAME_SLOT,
)

FRAME_EQ713_MECHANICS_CONTRACT = "TS500_EQ713_FRAME_MECHANICS_CLASSIFICATION_V1"
FRAME_EQ713_TARGET_CONTRACT = "TS500_EQ713_FRAME_MODIFIER_TARGET_V1"
FRAME_HORIZONTAL_TRANSLATIONAL_RESPONSE_SCOPE_REF = (
    "TS500_EQ713_HORIZONTAL_STORY_TRANSLATION_RESPONSE_SCOPE"
)


class FrameEq713MechanicsError(RuntimeError):
    """Fail-closed error for malformed/unsupported Frame mechanics evidence."""


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise FrameEq713MechanicsError(f"{label} must be a nonblank canonical string")
    return value


def _refs(values: Sequence[str]) -> tuple[str, ...]:
    refs = tuple(dict.fromkeys(_text(value, "source_ref") for value in values))
    if not refs:
        raise FrameEq713MechanicsError("source_refs must not be empty")
    return refs


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise FrameEq713MechanicsError(f"{label} must be finite numeric")
    result = float(value)
    if not math.isfinite(result):
        raise FrameEq713MechanicsError(f"{label} must be finite numeric")
    return result


def _decimal(value: object, label: str) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise FrameEq713MechanicsError(f"{label} must be numeric")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise FrameEq713MechanicsError(f"{label} must be numeric") from exc
    if not result.is_finite():
        raise FrameEq713MechanicsError(f"{label} must be finite")
    return result


@dataclass(frozen=True, slots=True)
class FrameMechanicsEvidence:
    component_uid: str
    member_role: str
    member_axis_vector: tuple[float, float, float]
    supported_end_condition: bool
    local_axis_explicit: bool
    local_axis_angle_degrees: float | None
    source_refs: tuple[str, ...]
    contract: str = FRAME_EQ713_MECHANICS_CONTRACT

    def __post_init__(self) -> None:
        object.__setattr__(self, "component_uid", _text(self.component_uid, "component_uid"))
        if self.member_role not in {"COLUMN", "BEAM"}:
            raise FrameEq713MechanicsError("member_role must be COLUMN or BEAM")
        vector = tuple(_number(value, f"member_axis_vector[{index}]") for index, value in enumerate(self.member_axis_vector))
        if len(vector) != 3 or math.sqrt(sum(value * value for value in vector)) <= 0.0:
            raise FrameEq713MechanicsError("member_axis_vector must be a nonzero three-vector")
        object.__setattr__(self, "member_axis_vector", vector)
        if type(self.supported_end_condition) is not bool:
            raise FrameEq713MechanicsError("supported_end_condition must be bool")
        if type(self.local_axis_explicit) is not bool:
            raise FrameEq713MechanicsError("local_axis_explicit must be bool")
        if self.local_axis_angle_degrees is not None:
            object.__setattr__(
                self,
                "local_axis_angle_degrees",
                _number(self.local_axis_angle_degrees, "local_axis_angle_degrees"),
            )
        object.__setattr__(self, "source_refs", _refs(self.source_refs))
        if self.contract != FRAME_EQ713_MECHANICS_CONTRACT:
            raise FrameEq713MechanicsError("Frame mechanics contract mismatch")

    @property
    def strictly_vertical(self) -> bool:
        dx, dy, dz = self.member_axis_vector
        scale = max(abs(dz), 1.0)
        return abs(dz) > 0.0 and abs(dx) <= 1e-9 * scale and abs(dy) <= 1e-9 * scale


@dataclass(frozen=True, slots=True)
class FrameModeParticipationEvidence:
    mode: FrameStiffnessMode
    participates: bool | None
    reason: str
    source_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.mode, FrameStiffnessMode):
            raise TypeError("mode must be FrameStiffnessMode")
        if self.participates is not None and type(self.participates) is not bool:
            raise FrameEq713MechanicsError("participates must be bool or None")
        object.__setattr__(self, "reason", _text(self.reason, "reason"))
        object.__setattr__(self, "source_refs", _refs(self.source_refs))


@dataclass(frozen=True, slots=True)
class FrameModeParticipationClassification:
    component_uid: str
    mode_evidence: tuple[FrameModeParticipationEvidence, ...]
    source_refs: tuple[str, ...]
    contract: str = FRAME_EQ713_MECHANICS_CONTRACT

    def __post_init__(self) -> None:
        object.__setattr__(self, "component_uid", _text(self.component_uid, "component_uid"))
        rows = tuple(self.mode_evidence)
        if tuple(row.mode for row in rows) != tuple(FrameStiffnessMode):
            raise FrameEq713MechanicsError("classification must account for every Frame stiffness mode exactly once")
        object.__setattr__(self, "mode_evidence", rows)
        object.__setattr__(self, "source_refs", _refs(self.source_refs))
        if self.contract != FRAME_EQ713_MECHANICS_CONTRACT:
            raise FrameEq713MechanicsError("Frame participation classification contract mismatch")

    def as_mapping(self) -> Mapping[FrameStiffnessMode, bool | None]:
        return {row.mode: row.participates for row in self.mode_evidence}

    @property
    def resolved(self) -> bool:
        return all(row.participates is not None for row in self.mode_evidence)


def classify_frame_eq713_participation(
    evidence: FrameMechanicsEvidence,
) -> FrameModeParticipationClassification:
    """Classify only source-proven mode participation for the bounded slice.

    A straight vertical COLUMN has local-1 aligned with the vertical member axis.
    For the bounded horizontal story-translation response, the two transverse
    shear/flexure families are the translational resistance mechanisms; local-1
    axial deformation and local-1 torsional rotation are orthogonal/non-
    translational mechanisms for this slice.  A BEAM/nonvertical member needs a
    response-direction-to-local-axis projection not present in this bounded
    evidence and therefore remains unresolved.
    """
    if not isinstance(evidence, FrameMechanicsEvidence):
        raise TypeError("evidence must be FrameMechanicsEvidence")
    refs = _refs((*evidence.source_refs, FRAME_HORIZONTAL_TRANSLATIONAL_RESPONSE_SCOPE_REF))

    if not evidence.supported_end_condition:
        reason = "Frame end condition is outside the supported no-release/no-partial-fixity slice"
        rows = tuple(FrameModeParticipationEvidence(mode, None, reason, refs) for mode in FrameStiffnessMode)
        return FrameModeParticipationClassification(evidence.component_uid, rows, refs)

    if evidence.member_role != "COLUMN" or not evidence.strictly_vertical:
        reason = (
            "Frame local-mode participation requires a response-direction/local-axis projection; "
            "the bounded mechanics evidence resolves only strictly vertical COLUMN members"
        )
        rows = tuple(FrameModeParticipationEvidence(mode, None, reason, refs) for mode in FrameStiffnessMode)
        return FrameModeParticipationClassification(evidence.component_uid, rows, refs)

    resolved = {
        FrameStiffnessMode.AXIAL: (
            False,
            "strictly vertical local-1 axial deformation is orthogonal to the bounded horizontal story-translation mechanism",
        ),
        FrameStiffnessMode.SHEAR_2: (
            True,
            "local-2 transverse shear is a horizontal translation resistance mechanism for a strictly vertical Frame member",
        ),
        FrameStiffnessMode.SHEAR_3: (
            True,
            "local-3 transverse shear is a horizontal translation resistance mechanism for a strictly vertical Frame member",
        ),
        FrameStiffnessMode.TORSION: (
            False,
            "local-1 torsional rotation is not a translational stiffness mode in the bounded horizontal story-translation mechanism",
        ),
        FrameStiffnessMode.FLEXURE_2: (
            True,
            "local-2 flexural stiffness participates in horizontal translation resistance for a strictly vertical Frame member",
        ),
        FrameStiffnessMode.FLEXURE_3: (
            True,
            "local-3 flexural stiffness participates in horizontal translation resistance for a strictly vertical Frame member",
        ),
    }
    rows = tuple(
        FrameModeParticipationEvidence(mode, resolved[mode][0], resolved[mode][1], refs)
        for mode in FrameStiffnessMode
    )
    return FrameModeParticipationClassification(evidence.component_uid, rows, refs)


@dataclass(frozen=True, slots=True)
class FrameEq713ModifierTarget:
    component_uid: str
    current_modifiers: tuple[Decimal, ...]
    target_modifiers: tuple[Decimal, ...]
    targeted_modes: tuple[FrameStiffnessMode, ...]
    preserved_modes: tuple[FrameStiffnessMode, ...]
    source_refs: tuple[str, ...]
    contract: str = FRAME_EQ713_TARGET_CONTRACT


def build_frame_eq713_modifier_target(
    *,
    current_modifiers: Sequence[object],
    disposition: FrameModeAuditDisposition,
) -> FrameEq713ModifierTarget:
    """Normalize TARGETED_UNCRACKED slots only; preserve every other slot.

    Mass and weight slots are never Eq713 stiffness targets and are always
    copied byte-for-value from the current observed vector representation.
    """
    if not isinstance(disposition, FrameModeAuditDisposition):
        raise TypeError("disposition must be FrameModeAuditDisposition")
    current = tuple(_decimal(value, f"current_modifiers[{index}]") for index, value in enumerate(current_modifiers))
    if len(current) != 8:
        raise FrameEq713MechanicsError("Frame modifier vector must contain exactly 8 values")
    by_mode = {row.mode: row for row in disposition.mode_dispositions}
    if set(by_mode) != set(FrameStiffnessMode) or len(by_mode) != len(disposition.mode_dispositions):
        raise FrameEq713MechanicsError("Frame disposition must account for every mode exactly once")

    target = list(current)
    targeted: list[FrameStiffnessMode] = []
    preserved: list[FrameStiffnessMode] = []
    for mode in FrameStiffnessMode:
        row = by_mode[mode]
        if row.disposition is ContributorDisposition.TARGETED_UNCRACKED:
            target[_FRAME_SLOT[mode]] = Decimal("1")
            targeted.append(mode)
        else:
            preserved.append(mode)
    # slots 6/7 (mass/weight) are intentionally untouched.
    return FrameEq713ModifierTarget(
        component_uid=disposition.component_uid,
        current_modifiers=current,
        target_modifiers=tuple(target),
        targeted_modes=tuple(targeted),
        preserved_modes=tuple(preserved),
        source_refs=_refs((*disposition.source_refs, FRAME_EQ713_TARGET_CONTRACT)),
    )


__all__ = [
    "FRAME_EQ713_MECHANICS_CONTRACT",
    "FRAME_EQ713_TARGET_CONTRACT",
    "FRAME_HORIZONTAL_TRANSLATIONAL_RESPONSE_SCOPE_REF",
    "FrameEq713MechanicsError",
    "FrameEq713ModifierTarget",
    "FrameMechanicsEvidence",
    "FrameModeParticipationClassification",
    "FrameModeParticipationEvidence",
    "build_frame_eq713_modifier_target",
    "classify_frame_eq713_participation",
]
