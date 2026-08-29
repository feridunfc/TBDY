"""FND-COL-4C2A reviewed longitudinal-rebar ranking authority.

This module binds the explicit COL-4A project selection-policy input to one
deterministic executable ranking behavior.

It is project engineering-selection policy, not a regulatory-source rule.

Authorized ranking:
1. minimum total longitudinal reinforcement area;
2. minimum bar count;
3. minimum bar diameter;
4. ascending exact candidate identity only as deterministic final resolution
   when all reviewed engineering ranking criteria are equal.

Final selection additionally requires a complete candidate-adequacy population
with zero unresolved candidates.

This module does not acquire ETABS data, evaluate structural adequacy, enumerate
geometry, or emit final selected reinforcement.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import hashlib
import json

from tbdy_engine.design.columns.column_longitudinal_selection_contract import (
    ColumnLongitudinalSelectionPolicyInput,
)


AUTHORITY = "VALIDATED_COLUMN_LONGITUDINAL_RANKING_POLICY"

POLICY_ID = "PROJECT_COLUMN_REBAR_POLICY"
POLICY_VERSION = "v1"

PRIMARY_OBJECTIVE = "MIN_TOTAL_AS"

TIE_BREAKERS = (
    "MIN_BAR_COUNT",
    "MIN_BAR_DIAMETER",
)

INPUT_REVIEW_REF = "review:column-selection-policy:v1"

BINDING_REVIEW_REF = (
    "FND_COL_4_SUPERVISOR_LONGITUDINAL_RANKING_POLICY_2026_08_29"
)

STABLE_RESOLUTION = "CANDIDATE_ID_ASC"

RANKING_DOMAIN = (
    "COMPLETE_ZERO_UNRESOLVED_PROVEN_ADEQUATE_CANDIDATES"
)

_FACTORY_TOKEN = object()


class ColumnLongitudinalRankingAuthorityError(ValueError):
    """Fail-closed COL-4C2A ranking-policy authority error."""


def _text(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or value != value.strip()
    ):
        raise ColumnLongitudinalRankingAuthorityError(
            f"{label} must be a nonblank canonical string"
        )

    return value


def _positive_decimal(
    value: object,
    label: str,
) -> Decimal:
    if value is None or isinstance(value, bool):
        raise ColumnLongitudinalRankingAuthorityError(
            f"{label} must be finite and > 0"
        )

    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ColumnLongitudinalRankingAuthorityError(
            f"{label} must be finite and > 0"
        ) from exc

    if not result.is_finite() or result <= 0:
        raise ColumnLongitudinalRankingAuthorityError(
            f"{label} must be finite and > 0"
        )

    return result


def _positive_int(
    value: object,
    label: str,
) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value <= 0
    ):
        raise ColumnLongitudinalRankingAuthorityError(
            f"{label} must be a positive integer"
        )

    return value


def _fingerprint(payload: object) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")

    return "sha256:" + hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class ColumnLongitudinalRankingCandidate:
    """Only the fields authorized to participate in ranking."""

    candidate_id: str
    as_total_mm2: Decimal
    bar_count: int
    bar_diameter_mm: Decimal

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "candidate_id",
            _text(
                self.candidate_id,
                "candidate_id",
            ),
        )

        object.__setattr__(
            self,
            "as_total_mm2",
            _positive_decimal(
                self.as_total_mm2,
                "as_total_mm2",
            ),
        )

        object.__setattr__(
            self,
            "bar_count",
            _positive_int(
                self.bar_count,
                "bar_count",
            ),
        )

        object.__setattr__(
            self,
            "bar_diameter_mm",
            _positive_decimal(
                self.bar_diameter_mm,
                "bar_diameter_mm",
            ),
        )


@dataclass(
    frozen=True,
    slots=True,
    order=True,
)
class ColumnLongitudinalRankingKey:
    """Ascending tuple implementing the reviewed policy exactly."""

    total_as_mm2: Decimal
    bar_count: int
    bar_diameter_mm: Decimal
    stable_candidate_id: str


@dataclass(frozen=True, slots=True, init=False)
class ValidatedColumnLongitudinalRankingPolicy:
    policy_id: str
    policy_version: str
    primary_objective: str
    tie_breakers: tuple[str, ...]
    input_review_ref: str
    binding_review_ref: str
    stable_resolution: str
    ranking_domain: str
    require_complete_adequacy_population: bool
    require_zero_unresolved_candidates: bool
    policy_fingerprint: str
    authority: str

    def __init__(
        self,
        *,
        _token: object = None,
    ) -> None:
        if _token is not _FACTORY_TOKEN:
            raise TypeError(
                "ValidatedColumnLongitudinalRankingPolicy "
                "is authority-created only; use "
                "authorize_column_longitudinal_ranking_policy"
            )


def authorize_column_longitudinal_ranking_policy(
    policy_input: ColumnLongitudinalSelectionPolicyInput,
) -> ValidatedColumnLongitudinalRankingPolicy:
    """Bind one reviewed COL-4A policy identity to executable ranking."""

    if not isinstance(
        policy_input,
        ColumnLongitudinalSelectionPolicyInput,
    ):
        raise TypeError(
            "policy_input must be "
            "ColumnLongitudinalSelectionPolicyInput"
        )

    expected = (
        POLICY_ID,
        POLICY_VERSION,
        PRIMARY_OBJECTIVE,
        TIE_BREAKERS,
        INPUT_REVIEW_REF,
    )

    actual = (
        policy_input.policy_id,
        policy_input.policy_version,
        policy_input.primary_objective,
        policy_input.tie_breakers,
        policy_input.review_ref,
    )

    if actual != expected:
        raise ColumnLongitudinalRankingAuthorityError(
            "selection policy input does not match the "
            "reviewed COL-4C2 ranking policy"
        )

    payload = {
        "policy_id": POLICY_ID,
        "policy_version": POLICY_VERSION,
        "primary_objective": PRIMARY_OBJECTIVE,
        "tie_breakers": list(TIE_BREAKERS),
        "input_review_ref": INPUT_REVIEW_REF,
        "binding_review_ref": BINDING_REVIEW_REF,
        "stable_resolution": STABLE_RESOLUTION,
        "ranking_domain": RANKING_DOMAIN,
        "require_complete_adequacy_population": True,
        "require_zero_unresolved_candidates": True,
    }

    artifact = ValidatedColumnLongitudinalRankingPolicy(
        _token=_FACTORY_TOKEN
    )

    values = {
        **payload,
        "tie_breakers": TIE_BREAKERS,
        "policy_fingerprint": _fingerprint(payload),
        "authority": AUTHORITY,
    }

    for name, value in values.items():
        object.__setattr__(
            artifact,
            name,
            value,
        )

    return artifact


def _require_policy(
    policy: ValidatedColumnLongitudinalRankingPolicy,
) -> None:
    if not isinstance(
        policy,
        ValidatedColumnLongitudinalRankingPolicy,
    ):
        raise TypeError(
            "policy must be "
            "ValidatedColumnLongitudinalRankingPolicy"
        )

    if (
        policy.authority != AUTHORITY
        or policy.policy_id != POLICY_ID
        or policy.policy_version != POLICY_VERSION
        or policy.primary_objective
        != PRIMARY_OBJECTIVE
        or policy.tie_breakers != TIE_BREAKERS
        or policy.input_review_ref
        != INPUT_REVIEW_REF
        or policy.binding_review_ref
        != BINDING_REVIEW_REF
        or policy.stable_resolution
        != STABLE_RESOLUTION
        or policy.ranking_domain
        != RANKING_DOMAIN
        or not policy.require_complete_adequacy_population
        or not policy.require_zero_unresolved_candidates
    ):
        raise ColumnLongitudinalRankingAuthorityError(
            "ranking policy artifact does not match "
            "the canonical reviewed behavior"
        )


def ranking_key_for_candidate(
    *,
    policy: ValidatedColumnLongitudinalRankingPolicy,
    candidate: ColumnLongitudinalRankingCandidate,
) -> ColumnLongitudinalRankingKey:
    """Return the exact ascending key authorized by the reviewed policy."""

    _require_policy(policy)

    if not isinstance(
        candidate,
        ColumnLongitudinalRankingCandidate,
    ):
        raise TypeError(
            "candidate must be "
            "ColumnLongitudinalRankingCandidate"
        )

    return ColumnLongitudinalRankingKey(
        total_as_mm2=candidate.as_total_mm2,
        bar_count=candidate.bar_count,
        bar_diameter_mm=candidate.bar_diameter_mm,
        stable_candidate_id=candidate.candidate_id,
    )


__all__ = [
    "AUTHORITY",
    "BINDING_REVIEW_REF",
    "ColumnLongitudinalRankingAuthorityError",
    "ColumnLongitudinalRankingCandidate",
    "ColumnLongitudinalRankingKey",
    "INPUT_REVIEW_REF",
    "POLICY_ID",
    "POLICY_VERSION",
    "PRIMARY_OBJECTIVE",
    "RANKING_DOMAIN",
    "STABLE_RESOLUTION",
    "TIE_BREAKERS",
    "ValidatedColumnLongitudinalRankingPolicy",
    "authorize_column_longitudinal_ranking_policy",
    "ranking_key_for_candidate",
]
