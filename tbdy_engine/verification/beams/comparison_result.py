"""
ETABS comparison result types.
Diagnostic only. Never mutates design or verification results.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


# =============================================================================
# Status Constants
# =============================================================================

STATUS_CLOSE = "CLOSE"
STATUS_MODERATE = "MODERATE"
STATUS_LARGE = "LARGE"
STATUS_INCOMPLETE = "INCOMPLETE"


# =============================================================================
# Data Types
# =============================================================================

@dataclass(frozen=True)
class ETABSComparisonItem:
    """Tek bir alan için ETABS karşılaştırma sonucu"""
    field: str
    status: str
    engine_value: float | None = None
    etabs_value: float | None = None
    difference: float | None = None
    difference_percent: float | None = None
    agreement_ratio: float | None = None
    message: str = ""
    evidence: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class ETABSComparisonResult:
    """
    Engine vs ETABS karşılaştırma sonucu.
    BeamDesignResult veya BeamVerificationResult status'unu DEĞİŞTİRMEZ.
    """
    beam_id: str
    label: str
    status: str
    items: tuple[ETABSComparisonItem, ...] = ()
    evidence: Mapping[str, object] = field(default_factory=dict)


# =============================================================================
# Helpers
# =============================================================================

def overall_comparison_status(items: tuple[ETABSComparisonItem, ...]) -> str:
    """Check listesinden overall comparison status çıkar."""
    if not items:
        return STATUS_INCOMPLETE

    statuses = [item.status for item in items]

    if STATUS_LARGE in statuses:
        return STATUS_LARGE
    if STATUS_MODERATE in statuses:
        return STATUS_MODERATE
    if STATUS_INCOMPLETE in statuses:
        return STATUS_INCOMPLETE
    if all(s == STATUS_CLOSE for s in statuses):
        return STATUS_CLOSE

    return STATUS_INCOMPLETE
