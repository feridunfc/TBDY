"""Immutable explicit RemediationPlan contract skeleton for F0.6."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
import hashlib
import json
from typing import Sequence

from tbdy_engine.findings.contracts import Finding


class RemediationClass(StrEnum):
    NO_MUTATION_REQUIRED = "NO_MUTATION_REQUIRED"
    DETERMINISTIC_FIX_AVAILABLE = "DETERMINISTIC_FIX_AVAILABLE"
    USER_ACTION_REQUIRED = "USER_ACTION_REQUIRED"
    ENGINEERING_DECISION_REQUIRED = "ENGINEERING_DECISION_REQUIRED"
    ENGINEERING_REDESIGN_REQUIRED = "ENGINEERING_REDESIGN_REQUIRED"
    UNSUPPORTED_AUTOMATION = "UNSUPPORTED_AUTOMATION"


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


def _validate_finding_ref(value: str) -> str:
    value = _canonical_text(value, "finding_ref")
    if not value.startswith("finding:"):
        raise ValueError("finding_ref must use finding:<sha256> form")
    digest = value.removeprefix("finding:")
    if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
        raise ValueError("finding_ref must contain a lowercase sha256 digest")
    return value


def _finding_refs(values: tuple[str, ...]) -> tuple[str, ...]:
    refs = _refs(values, "finding_ref")
    if not refs:
        raise ValueError("RemediationPlan requires at least one finding_ref")
    refs = tuple(_validate_finding_ref(item) for item in refs)
    if len(set(refs)) != len(refs):
        raise ValueError("duplicate finding identity")
    return tuple(sorted(refs))


def _validate_flags(
    *,
    remediation_class: RemediationClass,
    user_authorization_required: bool,
    reanalysis_required: bool,
    redesign_required: bool,
) -> None:
    if not isinstance(remediation_class, RemediationClass):
        raise TypeError("remediation_class must be RemediationClass")
    if type(user_authorization_required) is not bool:
        raise TypeError("user_authorization_required must be bool")
    if type(reanalysis_required) is not bool:
        raise TypeError("reanalysis_required must be bool")
    if type(redesign_required) is not bool:
        raise TypeError("redesign_required must be bool")
    if remediation_class is RemediationClass.DETERMINISTIC_FIX_AVAILABLE and not user_authorization_required:
        raise ValueError("DETERMINISTIC_FIX_AVAILABLE requires explicit user authorization")
    if remediation_class is RemediationClass.ENGINEERING_REDESIGN_REQUIRED and not redesign_required:
        raise ValueError("ENGINEERING_REDESIGN_REQUIRED requires redesign_required=True")
    if remediation_class is RemediationClass.NO_MUTATION_REQUIRED and user_authorization_required:
        raise ValueError("NO_MUTATION_REQUIRED requires user_authorization_required=False")


def _plan_identity(
    *,
    finding_refs: tuple[str, ...],
    remediation_class: RemediationClass,
    proposed_action_refs: tuple[str, ...],
    user_authorization_required: bool,
    reanalysis_required: bool,
    redesign_required: bool,
    provenance_refs: tuple[str, ...],
) -> str:
    finding_refs = _finding_refs(finding_refs)
    proposed_action_refs = _refs(proposed_action_refs, "proposed_action_ref")
    provenance_refs = _refs(provenance_refs, "provenance_ref")
    _validate_flags(
        remediation_class=remediation_class,
        user_authorization_required=user_authorization_required,
        reanalysis_required=reanalysis_required,
        redesign_required=redesign_required,
    )
    payload = {
        "finding_refs": list(finding_refs),
        "remediation_class": remediation_class.value,
        "proposed_action_refs": list(proposed_action_refs),
        "user_authorization_required": user_authorization_required,
        "reanalysis_required": reanalysis_required,
        "redesign_required": redesign_required,
        "provenance_refs": list(provenance_refs),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return "remediation-plan:" + hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class RemediationPlan:
    """Explicit proposed handling contract; never an execution instruction."""

    plan_id: str
    finding_refs: tuple[str, ...]
    remediation_class: RemediationClass
    proposed_action_refs: tuple[str, ...]
    user_authorization_required: bool
    reanalysis_required: bool
    redesign_required: bool
    provenance_refs: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        plan_id = _canonical_text(self.plan_id, "plan_id")
        if not plan_id.startswith("remediation-plan:"):
            raise ValueError("plan_id must use remediation-plan:<sha256> form")
        digest = plan_id.removeprefix("remediation-plan:")
        if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
            raise ValueError("plan_id must contain a lowercase sha256 digest")
        finding_refs = _finding_refs(self.finding_refs)
        proposed_action_refs = _refs(self.proposed_action_refs, "proposed_action_ref")
        provenance_refs = _refs(self.provenance_refs, "provenance_ref")
        _validate_flags(
            remediation_class=self.remediation_class,
            user_authorization_required=self.user_authorization_required,
            reanalysis_required=self.reanalysis_required,
            redesign_required=self.redesign_required,
        )
        object.__setattr__(self, "finding_refs", finding_refs)
        object.__setattr__(self, "proposed_action_refs", proposed_action_refs)
        object.__setattr__(self, "provenance_refs", provenance_refs)
        expected_id = _plan_identity(
            finding_refs=finding_refs,
            remediation_class=self.remediation_class,
            proposed_action_refs=proposed_action_refs,
            user_authorization_required=self.user_authorization_required,
            reanalysis_required=self.reanalysis_required,
            redesign_required=self.redesign_required,
            provenance_refs=provenance_refs,
        )
        if plan_id != expected_id:
            raise ValueError("plan_id does not match canonical stored semantic fields")


def build_remediation_plan(
    *,
    findings: Sequence[Finding],
    remediation_class: RemediationClass,
    proposed_action_refs: tuple[str, ...] = (),
    user_authorization_required: bool,
    reanalysis_required: bool,
    redesign_required: bool,
    provenance_refs: tuple[str, ...] = (),
) -> RemediationPlan:
    if isinstance(findings, (str, bytes)):
        raise TypeError("findings must be a sequence of Finding")
    frozen_findings = tuple(findings)
    if not frozen_findings:
        raise ValueError("RemediationPlan requires at least one Finding")
    if any(not isinstance(item, Finding) for item in frozen_findings):
        raise TypeError("findings must contain canonical Finding only")
    finding_ids = tuple(item.finding_id for item in frozen_findings)
    if len(set(finding_ids)) != len(finding_ids):
        raise ValueError("duplicate finding identity")
    finding_refs = tuple(sorted(finding_ids))
    proposed_action_refs = _refs(proposed_action_refs, "proposed_action_ref")
    provenance_refs = _refs(provenance_refs, "provenance_ref")
    _validate_flags(
        remediation_class=remediation_class,
        user_authorization_required=user_authorization_required,
        reanalysis_required=reanalysis_required,
        redesign_required=redesign_required,
    )
    plan_id = _plan_identity(
        finding_refs=finding_refs,
        remediation_class=remediation_class,
        proposed_action_refs=proposed_action_refs,
        user_authorization_required=user_authorization_required,
        reanalysis_required=reanalysis_required,
        redesign_required=redesign_required,
        provenance_refs=provenance_refs,
    )
    return RemediationPlan(
        plan_id=plan_id,
        finding_refs=finding_refs,
        remediation_class=remediation_class,
        proposed_action_refs=proposed_action_refs,
        user_authorization_required=user_authorization_required,
        reanalysis_required=reanalysis_required,
        redesign_required=redesign_required,
        provenance_refs=provenance_refs,
    )


__all__ = ["RemediationClass", "RemediationPlan", "build_remediation_plan"]
