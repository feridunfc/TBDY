"""TS500 7.6.2.1 stiffness-basis assessment for the stability-index route.

The Eq. 7.13 stability-index route requires an UNCRACKED-section analysis
basis. This module consumes already factual, assigned RC-frame bending
modifiers and answers only whether those facts are incompatible with that
requirement.

Important asymmetry:

* one assigned RC frame section with I2/I3 modifier different from 1.0 is
  sufficient to prove that the current analysis model is not an all-uncracked
  basis for Eq. 7.13, therefore reanalysis is required before this proof route
  can be authorized;
* seeing only unit modifiers on the inspected RC-frame population is NOT enough
  to prove the whole structural model uncracked, because other stiffness
  contributors (walls, slabs, links, releases, staged/nonlinear definitions,
  etc.) may still matter. That positive proof remains blocked until a broader
  analysis-basis contract exists.

This module performs no ETABS acquisition, no analysis and no sway
classification.
"""
from __future__ import annotations

from dataclasses import dataclass
import math


STIFFNESS_BASIS_AUTHORITY = "TS500_7.6.2.1_STIFFNESS_BASIS_ASSESSMENT"
FACTUAL_FRAME_MODIFIER_AUTHORITY = "ETABS_ASSIGNED_RC_FRAME_BENDING_MODIFIERS"

STATUS_REANALYSIS_REQUIRED = "REANALYSIS_REQUIRED_TS500_EQ7_13_UNCRACKED_BASIS"
STATUS_BLOCKED_GLOBAL_PROOF = "BLOCKED_TS500_EQ7_13_GLOBAL_UNCRACKED_BASIS_NOT_PROVEN"


class StabilityStiffnessBasisError(ValueError):
    """Raised when factual stiffness evidence is malformed or contradictory."""


@dataclass(frozen=True, slots=True)
class AssignedFrameBendingModifierEvidence:
    section_name: str
    member_kind: str
    i2_modifier: float
    i3_modifier: float
    source_refs: tuple[str, ...]
    authority: str = FACTUAL_FRAME_MODIFIER_AUTHORITY


@dataclass(frozen=True, slots=True)
class StabilityStiffnessBasisResolution:
    status: str
    reanalysis_required: bool
    inspected_section_count: int
    inspected_member_kinds: tuple[str, ...]
    nonunit_sections: tuple[AssignedFrameBendingModifierEvidence, ...]
    source_refs: tuple[str, ...]
    authority: str = STIFFNESS_BASIS_AUTHORITY

    @property
    def proves_uncracked(self) -> bool:
        # This slice intentionally cannot emit positive global uncracked proof.
        return False


def _text(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise StabilityStiffnessBasisError(f"{label} must be a nonblank canonical string")
    return value


def _modifier(value: float, label: str) -> float:
    if isinstance(value, bool):
        raise StabilityStiffnessBasisError(f"{label} must be a finite positive scalar")
    result = float(value)
    if not math.isfinite(result) or result <= 0.0:
        raise StabilityStiffnessBasisError(f"{label} must be a finite positive scalar")
    return result


def _canonical_evidence(item: AssignedFrameBendingModifierEvidence) -> AssignedFrameBendingModifierEvidence:
    section = _text(item.section_name, "section_name")
    kind = _text(item.member_kind, "member_kind")
    if kind not in {"BEAM", "COLUMN"}:
        raise StabilityStiffnessBasisError("member_kind must be BEAM or COLUMN")
    if item.authority != FACTUAL_FRAME_MODIFIER_AUTHORITY:
        raise StabilityStiffnessBasisError("unsupported factual frame-modifier authority")
    refs = tuple(_text(ref, "source_ref") for ref in item.source_refs)
    if not refs or len(refs) != len(set(refs)):
        raise StabilityStiffnessBasisError("source_refs must be nonempty and unique")
    return AssignedFrameBendingModifierEvidence(
        section_name=section,
        member_kind=kind,
        i2_modifier=_modifier(item.i2_modifier, f"{section}.I2Mod"),
        i3_modifier=_modifier(item.i3_modifier, f"{section}.I3Mod"),
        source_refs=refs,
    )


def assess_ts500_eq713_stiffness_basis(
    evidences: tuple[AssignedFrameBendingModifierEvidence, ...],
    *,
    unit_tolerance: float = 1e-12,
) -> StabilityStiffnessBasisResolution:
    """Detect whether factual assigned RC-frame modifiers force reanalysis.

    Non-unit I2/I3 on any assigned RC frame section is a sufficient
    incompatibility proof for the Eq. 7.13 uncracked-section basis. The inverse
    is deliberately not claimed from this limited evidence population.
    """
    if not evidences:
        raise StabilityStiffnessBasisError("at least one assigned RC-frame stiffness evidence item is required")
    tolerance = float(unit_tolerance)
    if not math.isfinite(tolerance) or tolerance < 0.0:
        raise StabilityStiffnessBasisError("unit_tolerance must be finite and >= 0")

    canonical = tuple(_canonical_evidence(item) for item in evidences)
    identities = tuple((item.member_kind, item.section_name) for item in canonical)
    if len(identities) != len(set(identities)):
        raise StabilityStiffnessBasisError("duplicate member_kind/section_name stiffness evidence")

    nonunit = tuple(
        item
        for item in canonical
        if abs(item.i2_modifier - 1.0) > tolerance or abs(item.i3_modifier - 1.0) > tolerance
    )
    refs = tuple(dict.fromkeys(ref for item in canonical for ref in item.source_refs))
    kinds = tuple(sorted({item.member_kind for item in canonical}))

    if nonunit:
        return StabilityStiffnessBasisResolution(
            status=STATUS_REANALYSIS_REQUIRED,
            reanalysis_required=True,
            inspected_section_count=len(canonical),
            inspected_member_kinds=kinds,
            nonunit_sections=nonunit,
            source_refs=tuple(dict.fromkeys((*refs, "TS500 7.6.2.1 Eq.7.13 requires uncracked-section basis"))),
        )

    return StabilityStiffnessBasisResolution(
        status=STATUS_BLOCKED_GLOBAL_PROOF,
        reanalysis_required=False,
        inspected_section_count=len(canonical),
        inspected_member_kinds=kinds,
        nonunit_sections=(),
        source_refs=tuple(dict.fromkeys((*refs, "Positive global uncracked proof requires complete analysis-basis evidence"))),
    )


__all__ = [
    "AssignedFrameBendingModifierEvidence",
    "FACTUAL_FRAME_MODIFIER_AUTHORITY",
    "STATUS_BLOCKED_GLOBAL_PROOF",
    "STATUS_REANALYSIS_REQUIRED",
    "STIFFNESS_BASIS_AUTHORITY",
    "StabilityStiffnessBasisError",
    "StabilityStiffnessBasisResolution",
    "assess_ts500_eq713_stiffness_basis",
]
