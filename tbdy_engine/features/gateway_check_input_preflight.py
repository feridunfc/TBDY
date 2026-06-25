"""Fail-closed CheckInput readiness preflight for FeatureSnapshot consumers."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from tbdy_engine.features.evidence import FeatureEvidenceStatus
from tbdy_engine.features.snapshot import FeatureSnapshot
from tbdy_engine.features.value import FeatureValueStatus


class CheckInputReadiness(StrEnum):
    READY = "READY"
    BLOCKED = "BLOCKED"


class FeatureRequirementState(StrEnum):
    SATISFIED = "SATISFIED"
    NOT_PRESENT = "NOT_PRESENT"
    VALUE_MISSING = "VALUE_MISSING"
    VALUE_PARTIAL = "VALUE_PARTIAL"
    NONE_NOT_ALLOWED = "NONE_NOT_ALLOWED"
    EVIDENCE_INCOMPLETE = "EVIDENCE_INCOMPLETE"


@dataclass(frozen=True, slots=True)
class CheckInputFeatureRequirement:
    feature_name: str
    allow_partial: bool = False
    allow_none: bool = False
    accepted_evidence_statuses: tuple[
        FeatureEvidenceStatus | str,
        ...,
    ] = (FeatureEvidenceStatus.FULL,)

    def __post_init__(self) -> None:
        if not self.feature_name.strip():
            raise ValueError("feature_name must not be empty.")
        normalized = tuple(
            FeatureEvidenceStatus(str(item))
            for item in self.accepted_evidence_statuses
        )
        if not normalized:
            raise ValueError(
                "accepted_evidence_statuses must not be empty."
            )
        if len(normalized) != len(set(normalized)):
            raise ValueError(
                "accepted_evidence_statuses must not contain duplicates."
            )
        object.__setattr__(
            self,
            "accepted_evidence_statuses",
            normalized,
        )


@dataclass(frozen=True, slots=True)
class CheckInputPreflightSpec:
    consumer_id: str
    required_features: tuple[CheckInputFeatureRequirement, ...]
    purpose: str = ""

    def __init__(
        self,
        *,
        consumer_id: str,
        required_features: Sequence[CheckInputFeatureRequirement],
        purpose: str = "",
    ) -> None:
        if not consumer_id.strip():
            raise ValueError("consumer_id must not be empty.")
        normalized = tuple(required_features)
        if not normalized:
            raise ValueError("required_features must not be empty.")
        if not all(
            isinstance(item, CheckInputFeatureRequirement)
            for item in normalized
        ):
            raise TypeError(
                "required_features must contain "
                "CheckInputFeatureRequirement objects."
            )
        feature_names = [item.feature_name for item in normalized]
        if len(feature_names) != len(set(feature_names)):
            raise ValueError(
                "required_features must not contain duplicate feature names."
            )
        object.__setattr__(self, "consumer_id", consumer_id.strip())
        object.__setattr__(self, "required_features", normalized)
        object.__setattr__(self, "purpose", purpose.strip())


@dataclass(frozen=True, slots=True)
class FeatureRequirementAssessment:
    feature_name: str
    state: FeatureRequirementState | str
    observed_feature_status: str | None
    observed_evidence_statuses: tuple[str, ...] = ()
    reason: str | None = None

    def __post_init__(self) -> None:
        normalized = FeatureRequirementState(str(self.state))
        object.__setattr__(self, "state", normalized)
        if not self.feature_name.strip():
            raise ValueError("feature_name must not be empty.")
        if (
            normalized is not FeatureRequirementState.SATISFIED
            and not self.reason
        ):
            raise ValueError(
                "Blocked feature assessment requires a reason."
            )


@dataclass(frozen=True, slots=True)
class CheckInputPreflightAssessment:
    consumer_id: str
    readiness: CheckInputReadiness | str
    feature_assessments: tuple[FeatureRequirementAssessment, ...]
    snapshot_component_type: str
    snapshot_component_id: str
    snapshot_origin: str | None
    adapter_unlock_allowed: bool
    diagnostics: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        normalized = CheckInputReadiness(str(self.readiness))
        object.__setattr__(self, "readiness", normalized)
        object.__setattr__(
            self,
            "feature_assessments",
            tuple(self.feature_assessments),
        )
        object.__setattr__(
            self,
            "diagnostics",
            MappingProxyType(dict(self.diagnostics)),
        )
        if self.adapter_unlock_allowed is not (
            normalized is CheckInputReadiness.READY
        ):
            raise ValueError(
                "adapter_unlock_allowed must match readiness."
            )

    @property
    def blocked_features(self) -> tuple[str, ...]:
        return tuple(
            item.feature_name
            for item in self.feature_assessments
            if item.state is not FeatureRequirementState.SATISFIED
        )


def evaluate_check_input_preflight(
    *,
    snapshot: FeatureSnapshot,
    spec: CheckInputPreflightSpec,
) -> CheckInputPreflightAssessment:
    if not isinstance(snapshot, FeatureSnapshot):
        raise TypeError("snapshot must be FeatureSnapshot.")
    if not isinstance(spec, CheckInputPreflightSpec):
        raise TypeError("spec must be CheckInputPreflightSpec.")

    assessments = tuple(
        _evaluate_requirement(snapshot, requirement)
        for requirement in spec.required_features
    )
    ready = all(
        item.state is FeatureRequirementState.SATISFIED
        for item in assessments
    )
    readiness = (
        CheckInputReadiness.READY
        if ready
        else CheckInputReadiness.BLOCKED
    )

    return CheckInputPreflightAssessment(
        consumer_id=spec.consumer_id,
        readiness=readiness,
        feature_assessments=assessments,
        snapshot_component_type=snapshot.component_type,
        snapshot_component_id=snapshot.component_id,
        snapshot_origin=_optional_text(
            snapshot.identity.get("origin")
        ),
        adapter_unlock_allowed=ready,
        diagnostics={
            "diagnostic_only": True,
            "check_input_constructed": False,
            "check_engine_invoked": False,
            "engineering_calculation_performed": False,
            "engineering_verdict_emitted": False,
            "purpose": spec.purpose,
        },
    )


def evaluate_check_input_preflights(
    *,
    snapshot: FeatureSnapshot,
    specs: Sequence[CheckInputPreflightSpec],
) -> tuple[CheckInputPreflightAssessment, ...]:
    normalized = tuple(specs)
    consumer_ids = [item.consumer_id for item in normalized]
    if len(consumer_ids) != len(set(consumer_ids)):
        raise ValueError("specs must not contain duplicate consumer IDs.")
    return tuple(
        evaluate_check_input_preflight(
            snapshot=snapshot,
            spec=spec,
        )
        for spec in normalized
    )


def _evaluate_requirement(
    snapshot: FeatureSnapshot,
    requirement: CheckInputFeatureRequirement,
) -> FeatureRequirementAssessment:
    feature = snapshot.features.get(requirement.feature_name)
    if feature is None:
        return FeatureRequirementAssessment(
            feature_name=requirement.feature_name,
            state=FeatureRequirementState.NOT_PRESENT,
            observed_feature_status=None,
            reason="Required feature is not present in the snapshot.",
        )

    feature_status = feature.status.value
    evidence_statuses = tuple(
        evidence.evidence_status.value
        for evidence in feature.evidence
    )

    if feature.status is FeatureValueStatus.MISSING:
        return FeatureRequirementAssessment(
            feature_name=requirement.feature_name,
            state=FeatureRequirementState.VALUE_MISSING,
            observed_feature_status=feature_status,
            observed_evidence_statuses=evidence_statuses,
            reason="Required feature is explicitly MISSING.",
        )

    if (
        feature.status is FeatureValueStatus.PARTIAL
        and not requirement.allow_partial
    ):
        return FeatureRequirementAssessment(
            feature_name=requirement.feature_name,
            state=FeatureRequirementState.VALUE_PARTIAL,
            observed_feature_status=feature_status,
            observed_evidence_statuses=evidence_statuses,
            reason=(
                "Required feature is PARTIAL and partial values "
                "are not explicitly permitted."
            ),
        )

    if feature.value is None and not requirement.allow_none:
        return FeatureRequirementAssessment(
            feature_name=requirement.feature_name,
            state=FeatureRequirementState.NONE_NOT_ALLOWED,
            observed_feature_status=feature_status,
            observed_evidence_statuses=evidence_statuses,
            reason="Required feature resolved to None.",
        )

    accepted = set(requirement.accepted_evidence_statuses)
    if (
        not feature.evidence
        or any(
            evidence.evidence_status not in accepted
            for evidence in feature.evidence
        )
    ):
        return FeatureRequirementAssessment(
            feature_name=requirement.feature_name,
            state=FeatureRequirementState.EVIDENCE_INCOMPLETE,
            observed_feature_status=feature_status,
            observed_evidence_statuses=evidence_statuses,
            reason=(
                "Feature evidence does not satisfy the explicitly "
                "accepted evidence statuses."
            ),
        )

    return FeatureRequirementAssessment(
        feature_name=requirement.feature_name,
        state=FeatureRequirementState.SATISFIED,
        observed_feature_status=feature_status,
        observed_evidence_statuses=evidence_statuses,
    )


def _optional_text(value: Any) -> str | None:
    return None if value is None else str(value)


__all__ = [
    "CheckInputFeatureRequirement",
    "CheckInputPreflightAssessment",
    "CheckInputPreflightSpec",
    "CheckInputReadiness",
    "FeatureRequirementAssessment",
    "FeatureRequirementState",
    "evaluate_check_input_preflight",
    "evaluate_check_input_preflights",
]
