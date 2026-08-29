"""FND-COL-4C1A source-bound column candidate adequacy decision authority.

Regulatory PMM adequacy is the TS500 ultimate-limit-state relation Rd >= Fd,
expressed as demand/capacity utilization <= 1.0.

The ETABS-required longitudinal-area condition is intentionally separate:
it is a reviewed selection guard preserving every canonical P8A
ETABS_REQUIRED_REBAR row. It is not represented as a regulatory requirement.

This module contains decision semantics only. It does not acquire ETABS data,
enumerate candidates, rank candidates, or perform final reinforcement selection.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math

from tbdy_engine.checks.result import (
    CheckResult,
    CheckStatus,
    EvaluationLevel,
)
from tbdy_engine.regulatory.authority import (
    RegulatoryAuthorityCatalog,
    ValidatedRuleAuthority,
    validate_rule_authority,
)
from tbdy_engine.regulatory.contracts import (
    ApplicabilityBinding,
    ApplicabilityState,
    CheckEvaluatorBinding,
    CheckSpec,
    RuleId,
)


class ColumnCandidateAdequacyAuthorityError(ValueError):
    """Fail-closed COL-4C1A authority error."""


FND_COL_4_CANDIDATE_ADEQUACY_RULE_ID = RuleId(
    "FND_COL_4_COLUMN_CANDIDATE_PMM_ADEQUACY"
)
FND_COL_4_CANDIDATE_ADEQUACY_RULE_VERSION = "1.0.0"
FND_COL_4_CANDIDATE_ADEQUACY_EVALUATOR_BINDING_ID = (
    "FND_COL_4_COLUMN_CANDIDATE_PMM_ADEQUACY_CHECK_V1"
)

CANDIDATE_ADEQUACY_IMPLEMENTATION_MODULES = (
    "tbdy_engine.regulatory.column_candidate_adequacy_authority",
)

REQUIRED_CANDIDATE_ADEQUACY_CLAIM_IDS = frozenset(
    {
        "TBDY2018_COLUMN_PMM_TS500_DESIGN_BASIS",
        "TS500_COLUMN_PMM_DESIGN_ACTION_AND_STRENGTH",
        "TS500_COLUMN_PMM_AXIAL_BENDING_METHOD_SCOPE",
        (
            "TS500_ULTIMATE_LIMIT_STATE_RESISTANCE_"
            "NOT_LESS_THAN_DESIGN_ACTION"
        ),
    }
)

FND_COL_4_CANDIDATE_ADEQUACY_POLICY_ID = (
    "FND_COL_4_CANDIDATE_ADEQUACY_POLICY"
)
FND_COL_4_CANDIDATE_ADEQUACY_POLICY_VERSION = "1.0.0"

# TS500 6.2.3 Eq. 6.1: Rd >= Fd.
FND_COL_4_PMM_UTILIZATION_LIMIT = 1.0

# No hidden area tolerance is authorized.
FND_COL_4_ETABS_AREA_TOLERANCE_MM2 = Decimal("0")

FND_COL_4_ETABS_REQUIRED_AREA_GUARD_REVIEW_REF = (
    "FND_COL_4_SUPERVISOR_P8A_REQUIRED_AREA_GUARD_2026_08_29"
)

AREA_GUARD_SATISFIED = "SATISFIED"
AREA_GUARD_INSUFFICIENT = "INSUFFICIENT"

CANDIDATE_ADEQUATE = "ADEQUATE"
CANDIDATE_INADEQUATE = "INADEQUATE"
CANDIDATE_UNRESOLVED = "UNRESOLVED"

_FACTORY_TOKEN = object()


def _text(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or value != value.strip()
    ):
        raise ColumnCandidateAdequacyAuthorityError(
            f"{label} must be a nonblank canonical string"
        )
    return value


def _nonnegative_decimal(
    value: object,
    label: str,
) -> Decimal:
    if value is None or isinstance(value, bool):
        raise ColumnCandidateAdequacyAuthorityError(
            f"{label} must be a nonnegative finite scalar"
        )

    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ColumnCandidateAdequacyAuthorityError(
            f"{label} must be a nonnegative finite scalar"
        ) from exc

    if not result.is_finite() or result < 0:
        raise ColumnCandidateAdequacyAuthorityError(
            f"{label} must be a nonnegative finite scalar"
        )

    return result


def _fingerprint(payload: object) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")

    return "sha256:" + hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class CandidatePmmAdequacyProbe:
    component_id: str
    numerically_resolved: bool
    utilization: float | None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "component_id",
            _text(self.component_id, "component_id"),
        )

        if not isinstance(self.numerically_resolved, bool):
            raise TypeError(
                "numerically_resolved must be bool"
            )

        if not self.numerically_resolved:
            if self.utilization is not None:
                raise ColumnCandidateAdequacyAuthorityError(
                    "unresolved PMM probe may not carry utilization"
                )
            return

        if (
            self.utilization is None
            or isinstance(self.utilization, bool)
        ):
            raise ColumnCandidateAdequacyAuthorityError(
                "resolved PMM probe requires utilization"
            )

        utilization = float(self.utilization)

        if (
            not math.isfinite(utilization)
            or utilization < 0.0
        ):
            raise ColumnCandidateAdequacyAuthorityError(
                "utilization must be finite and nonnegative"
            )

        object.__setattr__(
            self,
            "utilization",
            utilization,
        )


def _probe_applicability(
    value: object,
) -> ApplicabilityState:
    if not isinstance(
        value,
        CandidatePmmAdequacyProbe,
    ):
        return ApplicabilityState.INVALID_CONTEXT

    if not value.numerically_resolved:
        return ApplicabilityState.UNRESOLVED

    return ApplicabilityState.APPLIES


def _evaluate_probe(value: object) -> CheckResult:
    if not isinstance(
        value,
        CandidatePmmAdequacyProbe,
    ):
        return CheckResult(
            check_id=(
                FND_COL_4_CANDIDATE_ADEQUACY_RULE_ID.value
            ),
            component="UNKNOWN",
            component_type="COLUMN",
            status=CheckStatus.NO_DATA,
            evaluation_level=EvaluationLevel.NO_DATA,
            messages=(
                "Column PMM adequacy input is missing or invalid.",
            ),
            code_ref=(
                "TS500 6.2.3 Eq. 6.1 + 7.2 + 7.5"
            ),
        )

    if not value.numerically_resolved:
        return CheckResult(
            check_id=(
                FND_COL_4_CANDIDATE_ADEQUACY_RULE_ID.value
            ),
            component=value.component_id,
            component_type="COLUMN",
            status=CheckStatus.NO_DATA,
            evaluation_level=EvaluationLevel.NO_DATA,
            messages=(
                "PMM capacity is numerically unresolved; "
                "adequacy may not be asserted.",
            ),
            code_ref=(
                "TS500 6.2.3 Eq. 6.1 + 7.2 + 7.5"
            ),
        )

    utilization = float(value.utilization)

    status = (
        CheckStatus.OK
        if utilization
        <= FND_COL_4_PMM_UTILIZATION_LIMIT
        else CheckStatus.FAIL
    )

    return CheckResult(
        check_id=(
            FND_COL_4_CANDIDATE_ADEQUACY_RULE_ID.value
        ),
        component=value.component_id,
        component_type="COLUMN",
        status=status,
        value=utilization,
        limit=FND_COL_4_PMM_UTILIZATION_LIMIT,
        ratio=utilization,
        ratio_type="demand_over_capacity",
        pass_rule="ratio <= limit",
        unit="-",
        evaluation_level=EvaluationLevel.DESIGN_LEVEL,
        messages=(),
        code_ref=(
            "TS500 6.2.3 Eq. 6.1 + 7.2 + 7.5; "
            "TBDY2018 7.2.2/7.2.4"
        ),
    )


FND_COL_4_CANDIDATE_ADEQUACY_CHECK_SPEC = CheckSpec(
    rule_id=FND_COL_4_CANDIDATE_ADEQUACY_RULE_ID,
    code_refs=(
        "TBDY2018 7.2.2",
        "TBDY2018 7.2.4",
        "TS500 6.2.3 Eq. 6.1",
        "TS500 7.2",
        "TS500 7.5",
    ),
    rule_version=(
        FND_COL_4_CANDIDATE_ADEQUACY_RULE_VERSION
    ),
    formal_result_type=CheckResult,
    dependencies=(),
    applicability=ApplicabilityBinding(
        binding_id=(
            "FND_COL_4_COLUMN_CANDIDATE_"
            "ADEQUACY_APPLICABILITY_V1"
        ),
        input_type=CandidatePmmAdequacyProbe,
        evaluator=_probe_applicability,
    ),
    evaluator=CheckEvaluatorBinding(
        binding_id=(
            FND_COL_4_CANDIDATE_ADEQUACY_EVALUATOR_BINDING_ID
        ),
        input_type=CandidatePmmAdequacyProbe,
        evaluator=_evaluate_probe,
    ),
)


@dataclass(frozen=True, slots=True, init=False)
class ValidatedCandidateAdequacyPolicy:
    policy_id: str
    policy_version: str
    pmm_utilization_limit: float
    require_every_pmm_row: bool
    require_every_etabs_required_rebar_row: bool
    etabs_area_tolerance_mm2: Decimal
    etabs_area_guard_review_ref: str
    rule_id: str
    authority_binding_ref: str
    implementation_fingerprint: str
    source_claim_refs: tuple[str, ...]
    source_review_refs: tuple[str, ...]
    policy_fingerprint: str
    authority: str

    def __init__(
        self,
        *,
        _token: object = None,
    ) -> None:
        if _token is not _FACTORY_TOKEN:
            raise TypeError(
                "ValidatedCandidateAdequacyPolicy is "
                "authority-created only; use "
                "authorize_candidate_adequacy_policy"
            )


@dataclass(frozen=True, slots=True)
class CandidateRequiredAreaGuardDecision:
    candidate_as_mm2: Decimal
    required_as_mm2: Decimal
    margin_mm2: Decimal
    status: str
    policy_fingerprint: str
    authority: str = (
        "REVIEWED_P8A_REQUIRED_REBAR_SELECTION_GUARD"
    )


@dataclass(frozen=True, slots=True)
class CandidateAdequacyAggregateDecision:
    status: str
    pmm_ok_count: int
    pmm_fail_count: int
    pmm_unresolved_count: int
    area_satisfied_count: int
    area_insufficient_count: int
    policy_fingerprint: str
    authority: str = (
        "VALIDATED_COLUMN_CANDIDATE_ADEQUACY_AGGREGATE"
    )


def _validated(
    catalog: RegulatoryAuthorityCatalog,
) -> ValidatedRuleAuthority:
    if not isinstance(
        catalog,
        RegulatoryAuthorityCatalog,
    ):
        raise TypeError(
            "authority_catalog must be "
            "RegulatoryAuthorityCatalog"
        )

    validated = validate_rule_authority(
        FND_COL_4_CANDIDATE_ADEQUACY_CHECK_SPEC,
        catalog,
    )

    if not REQUIRED_CANDIDATE_ADEQUACY_CLAIM_IDS.issubset(
        set(validated.claim_refs)
    ):
        raise ColumnCandidateAdequacyAuthorityError(
            "validated authority is missing one or more "
            "mandatory candidate adequacy source claims"
        )

    return validated


def authorize_candidate_adequacy_policy(
    *,
    authority_catalog: RegulatoryAuthorityCatalog,
) -> ValidatedCandidateAdequacyPolicy:
    validated = _validated(authority_catalog)

    payload = {
        "policy_id": (
            FND_COL_4_CANDIDATE_ADEQUACY_POLICY_ID
        ),
        "policy_version": (
            FND_COL_4_CANDIDATE_ADEQUACY_POLICY_VERSION
        ),
        "pmm_utilization_limit": (
            FND_COL_4_PMM_UTILIZATION_LIMIT
        ),
        "require_every_pmm_row": True,
        "require_every_etabs_required_rebar_row": True,
        "etabs_area_tolerance_mm2": str(
            FND_COL_4_ETABS_AREA_TOLERANCE_MM2
        ),
        "etabs_area_guard_review_ref": (
            FND_COL_4_ETABS_REQUIRED_AREA_GUARD_REVIEW_REF
        ),
        "authority_binding_ref": validated.binding_ref,
        "implementation_fingerprint": (
            validated.approved_implementation_fingerprint
        ),
    }

    artifact = ValidatedCandidateAdequacyPolicy(
        _token=_FACTORY_TOKEN
    )

    values = {
        **payload,
        "etabs_area_tolerance_mm2": (
            FND_COL_4_ETABS_AREA_TOLERANCE_MM2
        ),
        "rule_id": (
            FND_COL_4_CANDIDATE_ADEQUACY_RULE_ID.value
        ),
        "source_claim_refs": validated.claim_refs,
        "source_review_refs": validated.review_refs,
        "policy_fingerprint": _fingerprint(payload),
        "authority": (
            "VALIDATED_COLUMN_CANDIDATE_ADEQUACY_POLICY"
        ),
    }

    for name, value in values.items():
        object.__setattr__(artifact, name, value)

    return artifact


def _require_policy(
    policy: ValidatedCandidateAdequacyPolicy,
) -> None:
    if not isinstance(
        policy,
        ValidatedCandidateAdequacyPolicy,
    ):
        raise TypeError(
            "policy must be ValidatedCandidateAdequacyPolicy"
        )

    if (
        policy.authority
        != "VALIDATED_COLUMN_CANDIDATE_ADEQUACY_POLICY"
        or policy.pmm_utilization_limit
        != FND_COL_4_PMM_UTILIZATION_LIMIT
        or policy.etabs_area_tolerance_mm2
        != FND_COL_4_ETABS_AREA_TOLERANCE_MM2
        or not policy.require_every_pmm_row
        or not policy.require_every_etabs_required_rebar_row
    ):
        raise ColumnCandidateAdequacyAuthorityError(
            "candidate adequacy policy is not the "
            "validated canonical policy"
        )


def evaluate_candidate_pmm_adequacy(
    *,
    policy: ValidatedCandidateAdequacyPolicy,
    component_id: str,
    numerically_resolved: bool,
    utilization: float | None,
) -> CheckResult:
    _require_policy(policy)

    return _evaluate_probe(
        CandidatePmmAdequacyProbe(
            component_id=component_id,
            numerically_resolved=numerically_resolved,
            utilization=utilization,
        )
    )


def evaluate_required_area_guard(
    *,
    policy: ValidatedCandidateAdequacyPolicy,
    candidate_as_mm2: object,
    required_as_mm2: object,
) -> CandidateRequiredAreaGuardDecision:
    _require_policy(policy)

    candidate = _nonnegative_decimal(
        candidate_as_mm2,
        "candidate_as_mm2",
    )
    required = _nonnegative_decimal(
        required_as_mm2,
        "required_as_mm2",
    )

    margin = candidate - required

    status = (
        AREA_GUARD_SATISFIED
        if (
            candidate
            + policy.etabs_area_tolerance_mm2
            >= required
        )
        else AREA_GUARD_INSUFFICIENT
    )

    return CandidateRequiredAreaGuardDecision(
        candidate_as_mm2=candidate,
        required_as_mm2=required,
        margin_mm2=margin,
        status=status,
        policy_fingerprint=policy.policy_fingerprint,
    )


def aggregate_candidate_adequacy(
    *,
    policy: ValidatedCandidateAdequacyPolicy,
    pmm_statuses: tuple[CheckStatus | str, ...],
    area_guard_statuses: tuple[str, ...],
) -> CandidateAdequacyAggregateDecision:
    """Aggregate exhaustive row decisions under the reviewed policy."""

    _require_policy(policy)

    if not pmm_statuses:
        raise ColumnCandidateAdequacyAuthorityError(
            "candidate adequacy requires every PMM row; "
            "PMM decision population is empty"
        )

    if not area_guard_statuses:
        raise ColumnCandidateAdequacyAuthorityError(
            "candidate adequacy requires every P8A row; "
            "required-area decision population is empty"
        )

    try:
        normalized_pmm = tuple(
            CheckStatus(str(status))
            for status in pmm_statuses
        )
    except ValueError as exc:
        raise ColumnCandidateAdequacyAuthorityError(
            "candidate PMM aggregate contains "
            "unsupported decision status"
        ) from exc

    allowed_pmm = {
        CheckStatus.OK,
        CheckStatus.FAIL,
        CheckStatus.NO_DATA,
    }

    if any(
        status not in allowed_pmm
        for status in normalized_pmm
    ):
        raise ColumnCandidateAdequacyAuthorityError(
            "candidate PMM aggregate accepts only "
            "OK, FAIL, or NO_DATA"
        )

    normalized_area = tuple(
        str(status)
        for status in area_guard_statuses
    )

    allowed_area = {
        AREA_GUARD_SATISFIED,
        AREA_GUARD_INSUFFICIENT,
    }

    if any(
        status not in allowed_area
        for status in normalized_area
    ):
        raise ColumnCandidateAdequacyAuthorityError(
            "candidate required-area aggregate contains "
            "unsupported guard status"
        )

    pmm_ok = normalized_pmm.count(CheckStatus.OK)
    pmm_fail = normalized_pmm.count(CheckStatus.FAIL)
    pmm_unresolved = normalized_pmm.count(
        CheckStatus.NO_DATA
    )

    area_satisfied = normalized_area.count(
        AREA_GUARD_SATISFIED
    )
    area_insufficient = normalized_area.count(
        AREA_GUARD_INSUFFICIENT
    )

    # Any proven inadequacy is sufficient to make the candidate
    # unsuitable. Unknown rows remain UNKNOWN only when no
    # decisive inadequacy has already been established.
    if pmm_fail > 0 or area_insufficient > 0:
        status = CANDIDATE_INADEQUATE
    elif pmm_unresolved > 0:
        status = CANDIDATE_UNRESOLVED
    else:
        status = CANDIDATE_ADEQUATE

    return CandidateAdequacyAggregateDecision(
        status=status,
        pmm_ok_count=pmm_ok,
        pmm_fail_count=pmm_fail,
        pmm_unresolved_count=pmm_unresolved,
        area_satisfied_count=area_satisfied,
        area_insufficient_count=area_insufficient,
        policy_fingerprint=policy.policy_fingerprint,
    )


__all__ = [
    "AREA_GUARD_INSUFFICIENT",
    "AREA_GUARD_SATISFIED",
    "CANDIDATE_ADEQUATE",
    "CANDIDATE_INADEQUATE",
    "CANDIDATE_UNRESOLVED",
    "CandidateAdequacyAggregateDecision",
    "CANDIDATE_ADEQUACY_IMPLEMENTATION_MODULES",
    "CandidatePmmAdequacyProbe",
    "CandidateRequiredAreaGuardDecision",
    "ColumnCandidateAdequacyAuthorityError",
    "FND_COL_4_CANDIDATE_ADEQUACY_CHECK_SPEC",
    "FND_COL_4_CANDIDATE_ADEQUACY_EVALUATOR_BINDING_ID",
    "FND_COL_4_CANDIDATE_ADEQUACY_POLICY_ID",
    "FND_COL_4_CANDIDATE_ADEQUACY_POLICY_VERSION",
    "FND_COL_4_CANDIDATE_ADEQUACY_RULE_ID",
    "FND_COL_4_CANDIDATE_ADEQUACY_RULE_VERSION",
    "FND_COL_4_ETABS_AREA_TOLERANCE_MM2",
    "FND_COL_4_ETABS_REQUIRED_AREA_GUARD_REVIEW_REF",
    "FND_COL_4_PMM_UTILIZATION_LIMIT",
    "REQUIRED_CANDIDATE_ADEQUACY_CLAIM_IDS",
    "ValidatedCandidateAdequacyPolicy",
    "aggregate_candidate_adequacy",
    "authorize_candidate_adequacy_policy",
    "evaluate_candidate_pmm_adequacy",
    "evaluate_required_area_guard",
]
