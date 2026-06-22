"""Canonical CheckResult serialization for C14.1-P1."""
from __future__ import annotations
from collections.abc import Mapping
from tbdy_engine.checks.result import CheckResult
def _record(result: CheckResult, *, result_status: str | None = None, candidate: Mapping[str, object] | None = None) -> dict[str, object]:
    payload = result.as_dict()
    payload["result_status"] = result_status or result.status.value
    if candidate is not None:
        payload["candidate_clear_span"] = dict(candidate)
    return payload
__all__ = ["_record"]
