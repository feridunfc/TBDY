"""Immutable canonical Finding projection contract for F0.6."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
import hashlib
import json

from tbdy_engine.checks.result import CheckStatus
from tbdy_engine.regulatory.contracts import ClosureExecutionStatus, DependencyKey, RuleInstanceId
from tbdy_engine.regulatory.kernel import AnalysisBasisStatus


class FindingSourceKind(StrEnum):
    CHECK_RESULT = "CHECK_RESULT"
    RULE_CLOSURE = "RULE_CLOSURE"
    ANALYSIS_BASIS_COMPATIBILITY = "ANALYSIS_BASIS_COMPATIBILITY"


FindingSourceStatus = CheckStatus | ClosureExecutionStatus | AnalysisBasisStatus


def _canonical_text(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError(f"{label} must be a nonblank canonical string")
    return value


def _refs(values: tuple[str, ...], label: str) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise TypeError(f"{label} must be a tuple of strings")
    if any(not isinstance(item, str) for item in values):
        raise TypeError(f"{label} must contain strings only")
    return tuple(_canonical_text(item, label) for item in values)


def _messages(values: tuple[str, ...]) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise TypeError("messages must be a tuple of strings")
    if any(not isinstance(item, str) for item in values):
        raise TypeError("messages must contain strings only")
    return tuple(values)


def _dependency_keys(values: tuple[DependencyKey, ...]) -> tuple[DependencyKey, ...]:
    if type(values) is not tuple:
        raise TypeError("regulatory_quantity_keys must be a tuple of DependencyKey")
    if any(not isinstance(item, DependencyKey) for item in values):
        raise TypeError("regulatory_quantity_keys must contain DependencyKey only")
    return tuple(values)


def _validate_source_status(source_kind: FindingSourceKind, source_status: FindingSourceStatus) -> None:
    expected = {
        FindingSourceKind.CHECK_RESULT: CheckStatus,
        FindingSourceKind.RULE_CLOSURE: ClosureExecutionStatus,
        FindingSourceKind.ANALYSIS_BASIS_COMPATIBILITY: AnalysisBasisStatus,
    }[source_kind]
    if type(source_status) is not expected:
        raise TypeError(f"{source_kind.value} requires source_status type {expected.__name__}")


def _validate_prefixed_sha(value: str, prefix: str, label: str) -> str:
    value = _canonical_text(value, label)
    if not value.startswith(prefix):
        raise ValueError(f"{label} must use {prefix}<sha256> form")
    digest = value.removeprefix(prefix)
    if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
        raise ValueError(f"{label} must contain a lowercase sha256 digest")
    return value


def _finding_identity(
    *,
    source_kind: FindingSourceKind,
    source_ref: str,
    source_status: FindingSourceStatus,
    scope_ref: str,
    direction: str | None,
    rule_instance_ref: RuleInstanceId | None,
    code_refs: tuple[str, ...],
    regulatory_quantity_keys: tuple[DependencyKey, ...],
    evidence_refs: tuple[str, ...],
    diagnostic_refs: tuple[str, ...],
    messages: tuple[str, ...],
    provenance_refs: tuple[str, ...],
) -> str:
    if not isinstance(source_kind, FindingSourceKind):
        raise TypeError("source_kind must be FindingSourceKind")
    _validate_source_status(source_kind, source_status)
    source_ref = _canonical_text(source_ref, "source_ref")
    scope_ref = _canonical_text(scope_ref, "scope_ref")
    if direction is not None:
        direction = _canonical_text(direction, "direction")
    if rule_instance_ref is not None and not isinstance(rule_instance_ref, RuleInstanceId):
        raise TypeError("rule_instance_ref must be RuleInstanceId or None")
    code_refs = _refs(code_refs, "code_ref")
    regulatory_quantity_keys = _dependency_keys(regulatory_quantity_keys)
    evidence_refs = _refs(evidence_refs, "evidence_ref")
    diagnostic_refs = _refs(diagnostic_refs, "diagnostic_ref")
    messages = _messages(messages)
    provenance_refs = _refs(provenance_refs, "provenance_ref")
    payload = {
        "source_kind": source_kind.value,
        "source_ref": source_ref,
        "source_status": source_status.value,
        "scope_ref": scope_ref,
        "direction": direction,
        "rule_instance_ref": None if rule_instance_ref is None else rule_instance_ref.value,
        "code_refs": list(code_refs),
        "regulatory_quantity_keys": [item.value for item in regulatory_quantity_keys],
        "evidence_refs": list(evidence_refs),
        "diagnostic_refs": list(diagnostic_refs),
        "messages": list(messages),
        "provenance_refs": list(provenance_refs),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return "finding:" + hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class Finding:
    """Read-only projection of one already-authoritative adverse/unresolved state."""

    finding_id: str
    source_kind: FindingSourceKind
    source_ref: str
    source_status: FindingSourceStatus
    scope_ref: str
    direction: str | None
    rule_instance_ref: RuleInstanceId | None
    code_refs: tuple[str, ...] = field(default_factory=tuple)
    regulatory_quantity_keys: tuple[DependencyKey, ...] = field(default_factory=tuple)
    evidence_refs: tuple[str, ...] = field(default_factory=tuple)
    diagnostic_refs: tuple[str, ...] = field(default_factory=tuple)
    messages: tuple[str, ...] = field(default_factory=tuple)
    provenance_refs: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        finding_id = _validate_prefixed_sha(self.finding_id, "finding:", "finding_id")
        if not isinstance(self.source_kind, FindingSourceKind):
            raise TypeError("source_kind must be FindingSourceKind")
        _validate_source_status(self.source_kind, self.source_status)
        source_ref = _canonical_text(self.source_ref, "source_ref")
        scope_ref = _canonical_text(self.scope_ref, "scope_ref")
        direction = self.direction
        if direction is not None:
            direction = _canonical_text(direction, "direction")
        if self.rule_instance_ref is not None and not isinstance(self.rule_instance_ref, RuleInstanceId):
            raise TypeError("rule_instance_ref must be RuleInstanceId or None")
        code_refs = _refs(self.code_refs, "code_ref")
        regulatory_quantity_keys = _dependency_keys(self.regulatory_quantity_keys)
        evidence_refs = _refs(self.evidence_refs, "evidence_ref")
        diagnostic_refs = _refs(self.diagnostic_refs, "diagnostic_ref")
        messages = _messages(self.messages)
        provenance_refs = _refs(self.provenance_refs, "provenance_ref")
        object.__setattr__(self, "code_refs", code_refs)
        object.__setattr__(self, "regulatory_quantity_keys", regulatory_quantity_keys)
        object.__setattr__(self, "evidence_refs", evidence_refs)
        object.__setattr__(self, "diagnostic_refs", diagnostic_refs)
        object.__setattr__(self, "messages", messages)
        object.__setattr__(self, "provenance_refs", provenance_refs)
        expected_id = _finding_identity(
            source_kind=self.source_kind,
            source_ref=source_ref,
            source_status=self.source_status,
            scope_ref=scope_ref,
            direction=direction,
            rule_instance_ref=self.rule_instance_ref,
            code_refs=code_refs,
            regulatory_quantity_keys=regulatory_quantity_keys,
            evidence_refs=evidence_refs,
            diagnostic_refs=diagnostic_refs,
            messages=messages,
            provenance_refs=provenance_refs,
        )
        if finding_id != expected_id:
            raise ValueError("finding_id does not match canonical stored semantic fields")


__all__ = ["Finding", "FindingSourceKind", "FindingSourceStatus"]
