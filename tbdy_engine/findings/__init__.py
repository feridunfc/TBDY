"""Canonical F0.6 Finding projection surface."""

from .builder import (
    build_finding_from_analysis_basis,
    build_finding_from_check_result,
    build_finding_from_rule_closure,
)
from .contracts import Finding, FindingSourceKind, FindingSourceStatus

__all__ = [
    "Finding",
    "FindingSourceKind",
    "FindingSourceStatus",
    "build_finding_from_analysis_basis",
    "build_finding_from_check_result",
    "build_finding_from_rule_closure",
]
