"""FND-COL-4 source-bound PMM capacity and numerical-policy authority.

This module authorizes the already validated rectangular-column PMM kernel for a
bounded concrete-strength domain. It does not acquire ETABS data, rank rebar
candidates, select reinforcement, or emit ENGINE_SELECTED_REBAR.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math

from tbdy_engine.checks.result import CheckResult, CheckStatus, EvaluationLevel
from tbdy_engine.design.columns.section_capacity import ts500_k1_for_fck_mpa
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


class ColumnPmmAuthorityError(ValueError):
    """Fail-closed FND-COL-4 PMM authority error."""


FND_COL_4_PMM_RULE_ID = RuleId("FND_COL_4_COLUMN_PMM_CAPACITY_AUTHORITY")
FND_COL_4_PMM_RULE_VERSION = "1.0.0"
FND_COL_4_PMM_EVALUATOR_BINDING_ID = "FND_COL_4_COLUMN_PMM_CAPACITY_CHECK_V1"

PMM_IMPLEMENTATION_MODULES = (
    "tbdy_engine.design.columns.section_capacity",
    "tbdy_engine.regulatory.column_pmm_authority",
)

REQUIRED_PMM_CLAIM_IDS = frozenset(
    {
        "TBDY2018_COLUMN_PMM_TS500_DESIGN_BASIS",
        "TS500_COLUMN_PMM_STRAIN_COMPATIBILITY",
        "TS500_COLUMN_PMM_EQUIVALENT_RECTANGULAR_BLOCK",
        "TS500_COLUMN_PMM_DESIGN_ACTION_AND_STRENGTH",
        "TS500_COLUMN_PMM_AXIAL_BENDING_METHOD_SCOPE",
    }
)

FND_COL_4_PMM_NUMERICAL_POLICY_ID = "FND_COL_4_PMM_NUMERICAL_POLICY"
FND_COL_4_PMM_NUMERICAL_POLICY_VERSION = "1.0.0"

# COL-3 production/oracle validation family reviewed for COL-4 use.
FND_COL_4_PMM_ANGLE_COUNT = 1152
FND_COL_4_PMM_AXIAL_TOLERANCE_N = 1.0

# Deliberately narrower than the underlying TS500 k1 kernel.
# COL-4 numerical authority is not silently extended below C25 or above C50.
FND_COL_4_PMM_SUPPORTED_FCK_MPA = (
    25.0,
    30.0,
    35.0,
    40.0,
    45.0,
    50.0,
)

FND_COL_4_PMM_VALIDATED_DOMAIN_REF = (
    "FND_COL_3_RECTANGULAR_RC_PMM_C25_C50_VALIDATION_V1"
)

FND_COL_4_PMM_NUMERICAL_REVIEW_REF = (
    "FND_COL_4_SUPERVISOR_PMM_NUMERICAL_POLICY_2026_08_29"
)

FND_COL_4_PMM_VALIDATION_EVIDENCE_REFS = (
    "tests/design/columns/test_fnd_col_3_section_capacity_analytic.py",
    "tests/design/columns/test_fnd_col_3_section_capacity_convergence.py",
    "tests/design/columns/test_fnd_col_3_section_capacity_determinism.py",
    "tests/design/columns/test_fnd_col_3_section_capacity_invariants.py",
    "tests/design/columns/test_fnd_col_3_section_capacity_oracle.py",
)

_FACTORY_TOKEN = object()


def _text(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or value != value.strip()
    ):
        raise ColumnPmmAuthorityError(
            f"{label} must be a nonblank canonical string"
        )
    return value


def _positive(value: object, label: str) -> float:
    if value is None or isinstance(value, bool):
        raise ColumnPmmAuthorityError(
            f"{label} must be finite and > 0"
        )
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ColumnPmmAuthorityError(
            f"{label} must be finite and > 0"
        ) from exc

    if not math.isfinite(result) or result <= 0.0:
        raise ColumnPmmAuthorityError(
            f"{label} must be finite and > 0"
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
class ColumnPmmRuleProbe:
    component_id: str
    fck_mpa: float
    fcd_mpa: float
    fyd_mpa: float

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "component_id",
            _text(self.component_id, "component_id"),
        )

        for name in ("fck_mpa", "fcd_mpa", "fyd_mpa"):
            object.__setattr__(
                self,
                name,
                _positive(getattr(self, name), name),
            )


def _probe_applicability(value: object) -> ApplicabilityState:
    if not isinstance(value, ColumnPmmRuleProbe):
        return ApplicabilityState.INVALID_CONTEXT

    if value.fck_mpa not in FND_COL_4_PMM_SUPPORTED_FCK_MPA:
        return ApplicabilityState.UNRESOLVED

    return ApplicabilityState.APPLIES


def _evaluate_probe(value: object) -> CheckResult:
    if not isinstance(value, ColumnPmmRuleProbe):
        return CheckResult(
            check_id=FND_COL_4_PMM_RULE_ID.value,
            component="UNKNOWN",
            component_type="COLUMN",
            status=CheckStatus.NO_DATA,
            evaluation_level=EvaluationLevel.NO_DATA,
            messages=(
                "FND-COL-4 PMM authority probe is missing or invalid.",
            ),
            code_ref=(
                "TBDY2018 7.2.2/7.2.4 + "
                "TS500 7.1/7.2/7.5"
            ),
        )

    supported = (
        value.fck_mpa in FND_COL_4_PMM_SUPPORTED_FCK_MPA
    )

    if supported:
        k1 = ts500_k1_for_fck_mpa(value.fck_mpa)
        status = CheckStatus.OK
        level = EvaluationLevel.DESIGN_LEVEL
        messages = ()
    else:
        k1 = None
        status = CheckStatus.NO_DATA
        level = EvaluationLevel.NO_DATA
        messages = (
            "FND-COL-4 numerical PMM authority is bounded "
            "to reviewed C25-C50 concrete classes.",
        )

    return CheckResult(
        check_id=FND_COL_4_PMM_RULE_ID.value,
        component=value.component_id,
        component_type="COLUMN",
        status=status,
        value={
            "fck_mpa": value.fck_mpa,
            "fcd_mpa": value.fcd_mpa,
            "fyd_mpa": value.fyd_mpa,
            "k1": k1,
            "numerical_policy_domain_supported": supported,
        },
        evaluation_level=level,
        messages=messages,
        code_ref=(
            "TBDY2018 7.2.2/7.2.4 + "
            "TS500 7.1/7.2/7.5 + Table 7.1"
        ),
    )


FND_COL_4_PMM_CHECK_SPEC = CheckSpec(
    rule_id=FND_COL_4_PMM_RULE_ID,
    code_refs=(
        "TBDY2018 7.2.2",
        "TBDY2018 7.2.4",
        "TS500 7.1",
        "TS500 7.2",
        "TS500 7.5",
        "TS500 Table 7.1",
    ),
    rule_version=FND_COL_4_PMM_RULE_VERSION,
    formal_result_type=CheckResult,
    dependencies=(),
    applicability=ApplicabilityBinding(
        binding_id="FND_COL_4_COLUMN_PMM_APPLICABILITY_V1",
        input_type=ColumnPmmRuleProbe,
        evaluator=_probe_applicability,
    ),
    evaluator=CheckEvaluatorBinding(
        binding_id=FND_COL_4_PMM_EVALUATOR_BINDING_ID,
        input_type=ColumnPmmRuleProbe,
        evaluator=_evaluate_probe,
    ),
)


@dataclass(frozen=True, slots=True, init=False)
class ValidatedPmmNumericalPolicy:
    policy_id: str
    policy_version: str
    angle_count: int
    axial_tolerance_n: float
    supported_fck_mpa: tuple[float, ...]
    validated_domain_ref: str
    validation_evidence_refs: tuple[str, ...]
    review_ref: str
    rule_id: str
    authority_binding_ref: str
    implementation_fingerprint: str
    source_claim_refs: tuple[str, ...]
    source_review_refs: tuple[str, ...]
    policy_fingerprint: str
    authority: str

    def __init__(self, *, _token: object = None) -> None:
        if _token is not _FACTORY_TOKEN:
            raise TypeError(
                "ValidatedPmmNumericalPolicy is authority-created only; "
                "use authorize_pmm_numerical_policy"
            )


def _validated(
    catalog: RegulatoryAuthorityCatalog,
) -> ValidatedRuleAuthority:
    if not isinstance(catalog, RegulatoryAuthorityCatalog):
        raise TypeError(
            "authority_catalog must be RegulatoryAuthorityCatalog"
        )

    validated = validate_rule_authority(
        FND_COL_4_PMM_CHECK_SPEC,
        catalog,
    )

    if not REQUIRED_PMM_CLAIM_IDS.issubset(
        set(validated.claim_refs)
    ):
        raise ColumnPmmAuthorityError(
            "validated authority is missing one or more mandatory "
            "FND-COL-4 PMM source claims"
        )

    return validated


def authorize_pmm_numerical_policy(
    *,
    authority_catalog: RegulatoryAuthorityCatalog,
) -> ValidatedPmmNumericalPolicy:
    """Create the one reviewed COL-4 PMM numerical policy artifact."""

    validated = _validated(authority_catalog)

    payload = {
        "policy_id": FND_COL_4_PMM_NUMERICAL_POLICY_ID,
        "policy_version": (
            FND_COL_4_PMM_NUMERICAL_POLICY_VERSION
        ),
        "angle_count": FND_COL_4_PMM_ANGLE_COUNT,
        "axial_tolerance_n": (
            FND_COL_4_PMM_AXIAL_TOLERANCE_N
        ),
        "supported_fck_mpa": list(
            FND_COL_4_PMM_SUPPORTED_FCK_MPA
        ),
        "validated_domain_ref": (
            FND_COL_4_PMM_VALIDATED_DOMAIN_REF
        ),
        "validation_evidence_refs": list(
            FND_COL_4_PMM_VALIDATION_EVIDENCE_REFS
        ),
        "review_ref": FND_COL_4_PMM_NUMERICAL_REVIEW_REF,
        "authority_binding_ref": validated.binding_ref,
        "implementation_fingerprint": (
            validated.approved_implementation_fingerprint
        ),
    }

    artifact = ValidatedPmmNumericalPolicy(
        _token=_FACTORY_TOKEN
    )

    values = {
        **payload,
        "supported_fck_mpa": (
            FND_COL_4_PMM_SUPPORTED_FCK_MPA
        ),
        "validation_evidence_refs": (
            FND_COL_4_PMM_VALIDATION_EVIDENCE_REFS
        ),
        "rule_id": FND_COL_4_PMM_RULE_ID.value,
        "source_claim_refs": validated.claim_refs,
        "source_review_refs": validated.review_refs,
        "policy_fingerprint": _fingerprint(payload),
        "authority": "VALIDATED_PMM_NUMERICAL_POLICY",
    }

    for name, value in values.items():
        object.__setattr__(artifact, name, value)

    return artifact


__all__ = [
    "ColumnPmmAuthorityError",
    "ColumnPmmRuleProbe",
    "FND_COL_4_PMM_ANGLE_COUNT",
    "FND_COL_4_PMM_AXIAL_TOLERANCE_N",
    "FND_COL_4_PMM_CHECK_SPEC",
    "FND_COL_4_PMM_EVALUATOR_BINDING_ID",
    "FND_COL_4_PMM_NUMERICAL_POLICY_ID",
    "FND_COL_4_PMM_NUMERICAL_POLICY_VERSION",
    "FND_COL_4_PMM_NUMERICAL_REVIEW_REF",
    "FND_COL_4_PMM_RULE_ID",
    "FND_COL_4_PMM_RULE_VERSION",
    "FND_COL_4_PMM_SUPPORTED_FCK_MPA",
    "FND_COL_4_PMM_VALIDATED_DOMAIN_REF",
    "FND_COL_4_PMM_VALIDATION_EVIDENCE_REFS",
    "PMM_IMPLEMENTATION_MODULES",
    "REQUIRED_PMM_CLAIM_IDS",
    "ValidatedPmmNumericalPolicy",
    "authorize_pmm_numerical_policy",
]
