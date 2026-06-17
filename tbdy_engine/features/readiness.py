"""Readiness/status policy for C13.3-P0 source-to-feature projection."""
from __future__ import annotations

from enum import StrEnum


class ReadinessStatus(StrEnum):
    READY_DIRECT_SOURCE = "READY_DIRECT_SOURCE"
    READY_DERIVED_SOURCE = "READY_DERIVED_SOURCE"
    READY_SUPPORTING_CONTEXT_ONLY = "READY_SUPPORTING_CONTEXT_ONLY"
    BLOCKED_NEEDS_LIVE_PROBE = "BLOCKED_NEEDS_LIVE_PROBE"
    BLOCKED_SEMANTIC_REVIEW = "BLOCKED_SEMANTIC_REVIEW"
    BLOCKED_FEATURE_CONTRACT_MISSING = "BLOCKED_FEATURE_CONTRACT_MISSING"
    OUT_OF_SCOPE_UNSUPPORTED = "OUT_OF_SCOPE_UNSUPPORTED"
    LOCKED_CHECK_NOT_ALLOWED = "LOCKED_CHECK_NOT_ALLOWED"


class FeatureProofStatus(StrEnum):
    RESOLVED = "RESOLVED"
    PARTIAL = "PARTIAL"
    BLOCKED_SEMANTIC_REVIEW = "BLOCKED_SEMANTIC_REVIEW"
    BLOCKED_NEEDS_LIVE_PROBE = "BLOCKED_NEEDS_LIVE_PROBE"
    LOCKED_CHECK_NOT_ALLOWED = "LOCKED_CHECK_NOT_ALLOWED"
    OUT_OF_SCOPE_UNSUPPORTED = "OUT_OF_SCOPE_UNSUPPORTED"


ALLOWED_FEATURE_PROOF_STATUSES = {status.value for status in FeatureProofStatus}
FORBIDDEN_ENGINEERING_VERDICT_TOKENS = (
    "PASS",
    "FAIL",
    "CHECK_OK",
    "CHECK_FAIL",
    "TBDY compliance",
    "TS500 compliance",
    "capacity ratio verdict",
    "utilization verdict",
)

LOCKED_CHECK_GUARDRAIL = {
    "check_unlock_allowed": False,
    "safe_to_use_for_check": False,
    "safe_to_implement_checks_now": False,
    "engineering_verdicts_allowed": False,
}


def assert_no_engineering_verdict_text(payload: object) -> None:
    text = str(payload)
    for token in FORBIDDEN_ENGINEERING_VERDICT_TOKENS:
        if token in text:
            raise ValueError(f"Forbidden engineering verdict token leaked into feature payload: {token}")


__all__ = [
    "ALLOWED_FEATURE_PROOF_STATUSES",
    "FORBIDDEN_ENGINEERING_VERDICT_TOKENS",
    "FeatureProofStatus",
    "LOCKED_CHECK_GUARDRAIL",
    "ReadinessStatus",
    "assert_no_engineering_verdict_text",
]
