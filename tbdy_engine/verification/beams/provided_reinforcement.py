"""
BeamProvidedReinforcement — existing reinforcement for verification.
Verification layer input only. Design engine does not consume it.
Units: mm and cm².
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping


@dataclass(frozen=True)
class ProvidedStirrup:
    """Existing stirrup detail."""
    diameter_mm: float = 0.0
    legs: int = 2
    spacing_mm: float = 0.0


@dataclass(frozen=True)
class BeamProvidedReinforcement:
    """Existing beam reinforcement used only by verification."""
    beam_id: str
    label: str
    source: str = "manual"

    top_left_As_cm2: float | None = None
    bottom_mid_As_cm2: float | None = None
    top_right_As_cm2: float | None = None
    stirrup: ProvidedStirrup | None = None

    evidence: Mapping[str, object] = field(default_factory=dict)


def validate_beam_provided_reinforcement(reinf: BeamProvidedReinforcement) -> tuple[str, ...]:
    """Validate BeamProvidedReinforcement identity and source."""
    invalid: list[str] = []
    if not reinf.beam_id:
        invalid.append("beam_id")
    if not reinf.label:
        invalid.append("label")
    if reinf.source == "unknown":
        invalid.append("source")
    return tuple(invalid)
