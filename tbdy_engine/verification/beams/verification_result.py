"""
Beam verification result contracts.
Verification and crosscheck outputs are immutable and never mutate design results.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

STATUS_PASS = "PASS"
STATUS_FAIL = "FAIL"
STATUS_UNKNOWN = "UNKNOWN"
STATUS_NOT_APPLICABLE = "NOT_APPLICABLE"


@dataclass(frozen=True)
class VerificationCheck:
    """Single verification check item."""
    check_id: str = ""
    status: str = STATUS_UNKNOWN
    category: str = ""
    demand_value: float | None = None
    provided_value: float | None = None
    utilization: float | None = None
    unit: str = ""
    message: str = ""
    evidence: Mapping[str, object] = field(default_factory=dict)


# Backward-compatible alias for earlier R9C contract/tests.
ReinforcementVerificationItem = VerificationCheck


@dataclass(frozen=True)
class BeamVerificationResult:
    """Provided reinforcement verification result."""
    beam_id: str
    label: str
    status: str = "NOT_EVALUATED"
    checks: tuple[VerificationCheck, ...] = ()
    evidence: Mapping[str, object] = field(default_factory=dict)



def overall_status(checks: tuple[VerificationCheck, ...] | list[VerificationCheck]) -> str:
    """Aggregate verification check statuses."""
    if not checks:
        return STATUS_NOT_APPLICABLE
    statuses = [check.status for check in checks]
    if any(status == STATUS_FAIL for status in statuses):
        return STATUS_FAIL
    if any(status == STATUS_UNKNOWN for status in statuses):
        return STATUS_UNKNOWN
    return STATUS_PASS
