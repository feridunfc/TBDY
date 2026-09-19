"""Project-wide canonical coverage reconciliation for FCR-1A.

This module is a bounded completeness/binding layer only. It does not discover
regulatory scope, execute engineering checks, reinterpret closure statuses,
generate actions, or recalculate report values.

Authority remains with:
- ``CompiledRegulatoryProgram.plan.compiled_closure_inventory`` for denominator,
- ``AssessmentEngine.reconcile`` for closure semantics,
- canonical runtime artifacts / Findings for report-source identity, and
- upstream typed analysis-basis authorities for reanalysis state.

FCR adds exact-identity accounting, report/action binding reconciliation and a
deterministic project reconciliation artifact. It never emits compliance PASS.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Sequence

from tbdy_engine.coverage.column_denominator import (
    ColumnDenominatorLeafIdentity,
    ColumnExpectedLeaf,
    ColumnLeafApplicability,
    ColumnLeafOutcome,
    ColumnLeafOutcomeStatus,
    SupportedColumnDenominator,
)
from tbdy_engine.findings.contracts import Finding
from tbdy_engine.product_reports.slice_report_contribution import SliceReportContribution
from tbdy_engine.regulatory.contracts import (
    ApplicabilityState,
    ClosureExecutionStatus,
    DependencyKey,
    RegulatoryQuantity,
    RuleClosureOutcome,
    RuleInstanceId,
)
from tbdy_engine.regulatory.kernel import (
    AnalysisBasisStatus,
    AssessmentEngine,
    CompiledRegulatoryProgram,
    FormalResultRecord,
    RegulatoryStoreSnapshot,
    StructuralAssessment,
    StructuralAssessmentStatus,
)


class ProjectReconciliationError(ValueError):
    """Base structural error for the FCR-1A reconciliation seam."""


class ReportBindingIdentityBlocked(ProjectReconciliationError):
    """Raised when report contribution identity is not exact and unique."""


def _text(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ProjectReconciliationError(f"{label} must be a nonblank canonical string")
    return value


def _unique_texts(values: Sequence[str], label: str) -> tuple[str, ...]:
    frozen = tuple(_text(value, f"{label}[]") for value in values)
    if len(set(frozen)) != len(frozen):
        raise ProjectReconciliationError(f"{label} must not contain duplicates")
    return tuple(sorted(frozen))


def _sorted_ids(values: Sequence[RuleInstanceId] | set[RuleInstanceId]) -> tuple[RuleInstanceId, ...]:
    return tuple(sorted(values, key=lambda item: item.value))


def _rule_id_values(values: Sequence[RuleInstanceId]) -> tuple[str, ...]:
    return tuple(item.value for item in sorted(values, key=lambda item: item.value))


def canonical_closure_report_source_ref(instance_id: RuleInstanceId) -> str:
    """Exact report-source identity for one canonical reconciled closure outcome."""
    if not isinstance(instance_id, RuleInstanceId):
        raise TypeError("instance_id must be RuleInstanceId")
    return f"{instance_id.value}:RuleClosureOutcome"


def canonical_quantity_report_source_ref(
    instance_id: RuleInstanceId,
    quantity_key: DependencyKey,
) -> str:
    """Exact report-source identity for a derivation output.

    A DependencyKey alone is not project-unique because the same output contract
    may exist for many scopes/directions. The producer RuleInstanceId is always
    part of the binding identity.
    """
    if not isinstance(instance_id, RuleInstanceId):
        raise TypeError("instance_id must be RuleInstanceId")
    if not isinstance(quantity_key, DependencyKey):
        raise TypeError("quantity_key must be DependencyKey")
    return f"{instance_id.value}:RegulatoryQuantity:{quantity_key.value}"


@dataclass(frozen=True, slots=True)
class ReportContributionRef:
    """Exact FCR-local identity for one existing report contribution."""

    slice_id: str
    component_type: str | None
    component_id: str | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "slice_id", _text(self.slice_id, "slice_id"))
        if self.component_type is not None:
            object.__setattr__(self, "component_type", _text(self.component_type, "component_type"))
        if self.component_id is not None:
            object.__setattr__(self, "component_id", _text(self.component_id, "component_id"))

    @classmethod
    def from_contribution(cls, contribution: SliceReportContribution) -> "ReportContributionRef":
        if not isinstance(contribution, SliceReportContribution):
            raise TypeError("contribution must be SliceReportContribution")
        return cls(
            slice_id=contribution.slice_id,
            component_type=contribution.component_type,
            component_id=contribution.component_id,
        )

    @property
    def value(self) -> str:
        return json.dumps(
            [self.slice_id, self.component_type, self.component_id],
            ensure_ascii=True,
            separators=(",", ":"),
        )

    @property
    def sort_key(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class ReportBindingRef:
    """Bind one exact canonical source to one exact report contribution."""

    source_ref: str
    contribution_ref: ReportContributionRef

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_ref", _text(self.source_ref, "source_ref"))
        if not isinstance(self.contribution_ref, ReportContributionRef):
            raise TypeError("contribution_ref must be ReportContributionRef")


@dataclass(frozen=True, slots=True)
class ActionBindingRef:
    """Minimum binding from canonical Finding identity to an action reference."""

    finding_id: str
    action_ref: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "finding_id", _text(self.finding_id, "finding_id"))
        object.__setattr__(self, "action_ref", _text(self.action_ref, "action_ref"))


@dataclass(frozen=True, slots=True)
class AnalysisBasisRef:
    """Typed upstream analysis-basis state preserved without reinterpretation."""

    instance_id: RuleInstanceId | ColumnDenominatorLeafIdentity
    status: AnalysisBasisStatus
    source_ref: str

    def __post_init__(self) -> None:
        if not isinstance(
            self.instance_id,
            (RuleInstanceId, ColumnDenominatorLeafIdentity),
        ):
            raise TypeError(
                "instance_id must be RuleInstanceId or ColumnDenominatorLeafIdentity"
            )
        if not isinstance(self.status, AnalysisBasisStatus):
            raise TypeError("status must be AnalysisBasisStatus")
        object.__setattr__(self, "source_ref", _text(self.source_ref, "source_ref"))


@dataclass(frozen=True, slots=True)
class ProjectCoverageReconciliation:
    """Immutable deterministic FCR-1A reconciliation artifact."""

    plan_identity: str
    structural_assessment: StructuralAssessment
    expected_all_ids: tuple[RuleInstanceId, ...]
    expected_mandatory_ids: tuple[RuleInstanceId, ...]
    accounted_mandatory_ids: tuple[RuleInstanceId, ...]
    executed_mandatory_ids: tuple[RuleInstanceId, ...]
    proven_not_applicable_mandatory_ids: tuple[RuleInstanceId, ...]
    blocked_mandatory_ids: tuple[RuleInstanceId, ...]
    no_data_mandatory_ids: tuple[RuleInstanceId, ...]
    not_executed_mandatory_ids: tuple[RuleInstanceId, ...]
    missing_mandatory_ids: tuple[RuleInstanceId, ...]
    duplicate_mandatory_ids: tuple[RuleInstanceId, ...]
    invalid_mandatory_ids: tuple[RuleInstanceId, ...]
    unresolved_mandatory_ids: tuple[RuleInstanceId, ...]
    silent_missing_mandatory_ids: tuple[RuleInstanceId, ...]
    duplicate_result_instance_ids: tuple[RuleInstanceId, ...]
    duplicate_closure_instance_ids: tuple[RuleInstanceId, ...]
    orphan_result_instance_ids: tuple[RuleInstanceId, ...]
    orphan_quantity_instance_ids: tuple[RuleInstanceId, ...]
    orphan_closure_instance_ids: tuple[RuleInstanceId, ...]
    orphan_diagnostic_refs: tuple[str, ...]
    analysis_basis_refs: tuple[AnalysisBasisRef, ...]
    required_report_source_refs: tuple[str, ...]
    missing_report_source_refs: tuple[str, ...]
    duplicate_report_source_refs: tuple[str, ...]
    orphan_report_binding_source_refs: tuple[str, ...]
    orphan_report_target_refs: tuple[ReportContributionRef, ...]
    required_action_finding_ids: tuple[str, ...]
    missing_action_finding_ids: tuple[str, ...]
    duplicate_action_finding_ids: tuple[str, ...]
    orphan_action_binding_finding_ids: tuple[str, ...]
    regulatory_metadata_conflict_refs: tuple[str, ...]
    closure_partition_complete: bool
    population_reconciled: bool
    report_reconciled: bool
    action_reconciled: bool
    regulatory_metadata_clean: bool

    # A39 product-denominator accounting.  These fields extend the existing
    # FCR artifact; they do not create a second reconciler or reinterpret
    # engineering truth.
    column_expected_leaf_ids: tuple[ColumnDenominatorLeafIdentity, ...] = ()
    column_accounted_leaf_ids: tuple[ColumnDenominatorLeafIdentity, ...] = ()
    column_executed_pass_leaf_ids: tuple[ColumnDenominatorLeafIdentity, ...] = ()
    column_executed_fail_leaf_ids: tuple[ColumnDenominatorLeafIdentity, ...] = ()
    column_proven_not_applicable_leaf_ids: tuple[ColumnDenominatorLeafIdentity, ...] = ()
    column_blocked_leaf_ids: tuple[ColumnDenominatorLeafIdentity, ...] = ()
    column_no_data_leaf_ids: tuple[ColumnDenominatorLeafIdentity, ...] = ()
    column_explicit_unresolved_leaf_ids: tuple[ColumnDenominatorLeafIdentity, ...] = ()
    column_reanalysis_required_leaf_ids: tuple[ColumnDenominatorLeafIdentity, ...] = ()
    column_deferred_cross_domain_leaf_ids: tuple[ColumnDenominatorLeafIdentity, ...] = ()
    column_silent_missing_leaf_ids: tuple[ColumnDenominatorLeafIdentity, ...] = ()
    column_duplicate_outcome_leaf_ids: tuple[ColumnDenominatorLeafIdentity, ...] = ()
    column_orphan_outcome_leaf_ids: tuple[ColumnDenominatorLeafIdentity, ...] = ()
    column_partition_complete: bool = True
    column_population_reconciled: bool = True

    def __post_init__(self) -> None:
        _text(self.plan_identity, "plan_identity")
        if not isinstance(self.structural_assessment, StructuralAssessment):
            raise TypeError("structural_assessment must be StructuralAssessment")
        if self.structural_assessment.plan_identity != self.plan_identity:
            raise ProjectReconciliationError(
                "structural_assessment plan identity must match reconciliation plan identity"
            )
        column_fields = (
            self.column_expected_leaf_ids,
            self.column_accounted_leaf_ids,
            self.column_executed_pass_leaf_ids,
            self.column_executed_fail_leaf_ids,
            self.column_proven_not_applicable_leaf_ids,
            self.column_blocked_leaf_ids,
            self.column_no_data_leaf_ids,
            self.column_explicit_unresolved_leaf_ids,
            self.column_reanalysis_required_leaf_ids,
            self.column_deferred_cross_domain_leaf_ids,
            self.column_silent_missing_leaf_ids,
            self.column_duplicate_outcome_leaf_ids,
            self.column_orphan_outcome_leaf_ids,
        )
        for values in column_fields:
            if any(
                not isinstance(item, ColumnDenominatorLeafIdentity)
                for item in values
            ):
                raise TypeError(
                    "A39 Column reconciliation fields require "
                    "ColumnDenominatorLeafIdentity values"
                )
            ids = tuple(item.value for item in values)
            if len(ids) != len(set(ids)):
                raise ProjectReconciliationError(
                    "A39 Column reconciliation field contains duplicate identities"
                )

    @property
    def mandatory_closure_complete(self) -> bool:
        """Closure completeness only; this is never a compliance PASS."""
        return self.structural_assessment.structural_status is StructuralAssessmentStatus.COMPLETE

    @property
    def reanalysis_required_instance_ids(
        self,
    ) -> tuple[RuleInstanceId | ColumnDenominatorLeafIdentity, ...]:
        return tuple(
            item.instance_id
            for item in self.analysis_basis_refs
            if item.status is AnalysisBasisStatus.REANALYSIS_REQUIRED
        )

    @property
    def column_expected_instance_count(self) -> int:
        return len(self.column_expected_leaf_ids)

    @property
    def column_accounted_instance_count(self) -> int:
        return len(self.column_accounted_leaf_ids)

    @property
    def column_executed_pass_count(self) -> int:
        return len(self.column_executed_pass_leaf_ids)

    @property
    def column_executed_fail_count(self) -> int:
        return len(self.column_executed_fail_leaf_ids)

    @property
    def column_proven_not_applicable_count(self) -> int:
        return len(self.column_proven_not_applicable_leaf_ids)

    @property
    def column_blocked_count(self) -> int:
        return len(self.column_blocked_leaf_ids)

    @property
    def column_no_data_count(self) -> int:
        return len(self.column_no_data_leaf_ids)

    @property
    def column_explicit_unresolved_count(self) -> int:
        return len(self.column_explicit_unresolved_leaf_ids)

    @property
    def column_reanalysis_required_count(self) -> int:
        return len(self.column_reanalysis_required_leaf_ids)

    @property
    def column_deferred_cross_domain_count(self) -> int:
        return len(self.column_deferred_cross_domain_leaf_ids)

    @property
    def column_silent_missing_count(self) -> int:
        return len(self.column_silent_missing_leaf_ids)

    @property
    def column_duplicate_count(self) -> int:
        return len(self.column_duplicate_outcome_leaf_ids)

    @property
    def column_orphan_count(self) -> int:
        return len(self.column_orphan_outcome_leaf_ids)

    @property
    def expected_mandatory_instance_count(self) -> int:
        return len(self.expected_mandatory_ids)

    @property
    def accounted_instance_count(self) -> int:
        return len(self.accounted_mandatory_ids)

    @property
    def executed_result_count(self) -> int:
        return len(self.executed_mandatory_ids)

    @property
    def proven_not_applicable_count(self) -> int:
        return len(self.proven_not_applicable_mandatory_ids)

    @property
    def blocked_count(self) -> int:
        return len(self.blocked_mandatory_ids)

    @property
    def no_data_count(self) -> int:
        return len(self.no_data_mandatory_ids)

    @property
    def unresolved_count(self) -> int:
        return len(self.unresolved_mandatory_ids)

    @property
    def silent_missing_count(self) -> int:
        return len(self.silent_missing_mandatory_ids)

    @property
    def duplicate_result_count(self) -> int:
        return len(self.duplicate_result_instance_ids)

    @property
    def orphan_result_count(self) -> int:
        return len(self.orphan_result_instance_ids)

    @property
    def orphan_diagnostic_count(self) -> int:
        return len(self.orphan_diagnostic_refs)

    @property
    def missing_report_binding_count(self) -> int:
        return len(self.missing_report_source_refs)

    @property
    def orphan_report_binding_count(self) -> int:
        return len(self.orphan_report_binding_source_refs) + len(self.orphan_report_target_refs)

    @property
    def missing_action_binding_count(self) -> int:
        return len(self.missing_action_finding_ids)

    @property
    def orphan_action_binding_count(self) -> int:
        return len(self.orphan_action_binding_finding_ids)

    @property
    def regulatory_metadata_conflict_count(self) -> int:
        return len(self.regulatory_metadata_conflict_refs)

    def as_dict(self) -> dict[str, object]:
        closure_rows = [
            {
                "instance_id": outcome.compiled_record_ref.value,
                "execution_status": outcome.execution_status.value,
                "formal_result_ref": outcome.formal_result_ref,
                "regulatory_quantity_refs": [item.value for item in outcome.regulatory_quantity_refs],
                "diagnostic_refs": list(outcome.diagnostic_refs),
            }
            for outcome in self.structural_assessment.closure_outcomes
        ]
        basis_rows = [
            {
                "instance_id": item.instance_id.value,
                "status": item.status.value,
                "source_ref": item.source_ref,
            }
            for item in self.analysis_basis_refs
        ]
        payload = {
            "schema_version": "project_coverage_reconciliation.fcr_1a.v2",
            "artifact_type": "PROJECT_COVERAGE_RECONCILIATION",
            "plan_identity": self.plan_identity,
            "expected_all_ids": list(_rule_id_values(self.expected_all_ids)),
            "expected_mandatory_ids": list(_rule_id_values(self.expected_mandatory_ids)),
            "accounted_mandatory_ids": list(_rule_id_values(self.accounted_mandatory_ids)),
            "executed_mandatory_ids": list(_rule_id_values(self.executed_mandatory_ids)),
            "proven_not_applicable_mandatory_ids": list(
                _rule_id_values(self.proven_not_applicable_mandatory_ids)
            ),
            "blocked_mandatory_ids": list(_rule_id_values(self.blocked_mandatory_ids)),
            "no_data_mandatory_ids": list(_rule_id_values(self.no_data_mandatory_ids)),
            "not_executed_mandatory_ids": list(_rule_id_values(self.not_executed_mandatory_ids)),
            "missing_mandatory_ids": list(_rule_id_values(self.missing_mandatory_ids)),
            "duplicate_mandatory_ids": list(_rule_id_values(self.duplicate_mandatory_ids)),
            "invalid_mandatory_ids": list(_rule_id_values(self.invalid_mandatory_ids)),
            "unresolved_mandatory_ids": list(_rule_id_values(self.unresolved_mandatory_ids)),
            "silent_missing_mandatory_ids": list(_rule_id_values(self.silent_missing_mandatory_ids)),
            "duplicate_result_instance_ids": list(_rule_id_values(self.duplicate_result_instance_ids)),
            "duplicate_closure_instance_ids": list(_rule_id_values(self.duplicate_closure_instance_ids)),
            "orphan_result_instance_ids": list(_rule_id_values(self.orphan_result_instance_ids)),
            "orphan_quantity_instance_ids": list(_rule_id_values(self.orphan_quantity_instance_ids)),
            "orphan_closure_instance_ids": list(_rule_id_values(self.orphan_closure_instance_ids)),
            "orphan_diagnostic_refs": list(self.orphan_diagnostic_refs),
            "analysis_basis": basis_rows,
            "closure_outcomes": closure_rows,
            "required_report_source_refs": list(self.required_report_source_refs),
            "missing_report_source_refs": list(self.missing_report_source_refs),
            "duplicate_report_source_refs": list(self.duplicate_report_source_refs),
            "orphan_report_binding_source_refs": list(self.orphan_report_binding_source_refs),
            "orphan_report_target_refs": [item.value for item in self.orphan_report_target_refs],
            "required_action_finding_ids": list(self.required_action_finding_ids),
            "missing_action_finding_ids": list(self.missing_action_finding_ids),
            "duplicate_action_finding_ids": list(self.duplicate_action_finding_ids),
            "orphan_action_binding_finding_ids": list(self.orphan_action_binding_finding_ids),
            "regulatory_metadata_conflict_refs": list(self.regulatory_metadata_conflict_refs),
            "summary": {
                "expected_mandatory_instance_count": self.expected_mandatory_instance_count,
                "accounted_instance_count": self.accounted_instance_count,
                "executed_result_count": self.executed_result_count,
                "proven_not_applicable_count": self.proven_not_applicable_count,
                "blocked_count": self.blocked_count,
                "no_data_count": self.no_data_count,
                "unresolved_count": self.unresolved_count,
                "silent_missing_count": self.silent_missing_count,
                "duplicate_result_count": self.duplicate_result_count,
                "orphan_result_count": self.orphan_result_count,
                "orphan_diagnostic_count": self.orphan_diagnostic_count,
                "missing_report_binding_count": self.missing_report_binding_count,
                "orphan_report_binding_count": self.orphan_report_binding_count,
                "missing_action_binding_count": self.missing_action_binding_count,
                "orphan_action_binding_count": self.orphan_action_binding_count,
                "regulatory_metadata_conflict_count": self.regulatory_metadata_conflict_count,
                "closure_partition_complete": self.closure_partition_complete,
                "population_reconciled": self.population_reconciled,
                "mandatory_closure_complete": self.mandatory_closure_complete,
                "report_reconciled": self.report_reconciled,
                "action_reconciled": self.action_reconciled,
                "regulatory_metadata_clean": self.regulatory_metadata_clean,
            },
        }
        if self.column_expected_leaf_ids:
            column_payload = {
                "expected_leaf_ids": [
                    item.value for item in self.column_expected_leaf_ids
                ],
                "accounted_leaf_ids": [
                    item.value for item in self.column_accounted_leaf_ids
                ],
                "executed_pass_leaf_ids": [
                    item.value for item in self.column_executed_pass_leaf_ids
                ],
                "executed_fail_leaf_ids": [
                    item.value for item in self.column_executed_fail_leaf_ids
                ],
                "proven_not_applicable_leaf_ids": [
                    item.value
                    for item in self.column_proven_not_applicable_leaf_ids
                ],
                "blocked_leaf_ids": [
                    item.value for item in self.column_blocked_leaf_ids
                ],
                "no_data_leaf_ids": [
                    item.value for item in self.column_no_data_leaf_ids
                ],
                "explicit_unresolved_leaf_ids": [
                    item.value for item in self.column_explicit_unresolved_leaf_ids
                ],
                "reanalysis_required_leaf_ids": [
                    item.value
                    for item in self.column_reanalysis_required_leaf_ids
                ],
                "deferred_cross_domain_leaf_ids": [
                    item.value
                    for item in self.column_deferred_cross_domain_leaf_ids
                ],
                "silent_missing_leaf_ids": [
                    item.value for item in self.column_silent_missing_leaf_ids
                ],
                "duplicate_outcome_leaf_ids": [
                    item.value
                    for item in self.column_duplicate_outcome_leaf_ids
                ],
                "orphan_outcome_leaf_ids": [
                    item.value for item in self.column_orphan_outcome_leaf_ids
                ],
                "summary": {
                    "expected_instance_count": self.column_expected_instance_count,
                    "accounted_instance_count": self.column_accounted_instance_count,
                    "executed_pass_count": self.column_executed_pass_count,
                    "executed_fail_count": self.column_executed_fail_count,
                    "proven_not_applicable_count": (
                        self.column_proven_not_applicable_count
                    ),
                    "blocked_count": self.column_blocked_count,
                    "no_data_count": self.column_no_data_count,
                    "explicit_unresolved_count": (
                        self.column_explicit_unresolved_count
                    ),
                    "reanalysis_required_count": (
                        self.column_reanalysis_required_count
                    ),
                    "deferred_cross_domain_count": (
                        self.column_deferred_cross_domain_count
                    ),
                    "silent_missing_count": self.column_silent_missing_count,
                    "duplicate_count": self.column_duplicate_count,
                    "orphan_count": self.column_orphan_count,
                    "partition_complete": self.column_partition_complete,
                    "population_reconciled": (
                        self.column_population_reconciled
                    ),
                },
            }
            payload["column_denominator_reconciliation"] = column_payload
            payload["summary"].update(
                {
                    "column_expected_instance_count": (
                        self.column_expected_instance_count
                    ),
                    "column_accounted_instance_count": (
                        self.column_accounted_instance_count
                    ),
                    "column_executed_pass_count": (
                        self.column_executed_pass_count
                    ),
                    "column_executed_fail_count": (
                        self.column_executed_fail_count
                    ),
                    "column_proven_not_applicable_count": (
                        self.column_proven_not_applicable_count
                    ),
                    "column_blocked_count": self.column_blocked_count,
                    "column_no_data_count": self.column_no_data_count,
                    "column_explicit_unresolved_count": (
                        self.column_explicit_unresolved_count
                    ),
                    "column_reanalysis_required_count": (
                        self.column_reanalysis_required_count
                    ),
                    "column_deferred_cross_domain_count": (
                        self.column_deferred_cross_domain_count
                    ),
                    "column_silent_missing_count": (
                        self.column_silent_missing_count
                    ),
                    "column_duplicate_count": self.column_duplicate_count,
                    "column_orphan_count": self.column_orphan_count,
                    "column_partition_complete": (
                        self.column_partition_complete
                    ),
                    "column_population_reconciled": (
                        self.column_population_reconciled
                    ),
                }
            )
        return payload

    def to_json(self) -> str:
        return json.dumps(
            self.as_dict(),
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ) + "\n"


def _sorted_column_ids(
    values: Sequence[ColumnDenominatorLeafIdentity]
    | set[ColumnDenominatorLeafIdentity],
) -> tuple[ColumnDenominatorLeafIdentity, ...]:
    return tuple(sorted(values, key=lambda item: item.value))


@dataclass(frozen=True, slots=True)
class _ColumnPopulationAccounting:
    expected: tuple[ColumnDenominatorLeafIdentity, ...]
    accounted: tuple[ColumnDenominatorLeafIdentity, ...]
    executed_pass: tuple[ColumnDenominatorLeafIdentity, ...]
    executed_fail: tuple[ColumnDenominatorLeafIdentity, ...]
    proven_not_applicable: tuple[ColumnDenominatorLeafIdentity, ...]
    blocked: tuple[ColumnDenominatorLeafIdentity, ...]
    no_data: tuple[ColumnDenominatorLeafIdentity, ...]
    explicit_unresolved: tuple[ColumnDenominatorLeafIdentity, ...]
    reanalysis_required: tuple[ColumnDenominatorLeafIdentity, ...]
    deferred_cross_domain: tuple[ColumnDenominatorLeafIdentity, ...]
    silent_missing: tuple[ColumnDenominatorLeafIdentity, ...]
    duplicate_outcome: tuple[ColumnDenominatorLeafIdentity, ...]
    orphan_outcome: tuple[ColumnDenominatorLeafIdentity, ...]
    analysis_basis_refs: tuple[AnalysisBasisRef, ...]
    partition_complete: bool
    population_reconciled: bool


def _reconcile_supported_column_denominator(
    denominator: SupportedColumnDenominator | None,
) -> _ColumnPopulationAccounting:
    if denominator is None:
        return _ColumnPopulationAccounting(
            expected=(),
            accounted=(),
            executed_pass=(),
            executed_fail=(),
            proven_not_applicable=(),
            blocked=(),
            no_data=(),
            explicit_unresolved=(),
            reanalysis_required=(),
            deferred_cross_domain=(),
            silent_missing=(),
            duplicate_outcome=(),
            orphan_outcome=(),
            analysis_basis_refs=(),
            partition_complete=True,
            population_reconciled=True,
        )
    if not isinstance(denominator, SupportedColumnDenominator):
        raise TypeError(
            "column_denominator must be SupportedColumnDenominator or None"
        )

    expected = tuple(denominator.expected_leaves)
    outcomes = tuple(denominator.outcomes)
    if any(not isinstance(item, ColumnExpectedLeaf) for item in expected):
        raise TypeError(
            "column_denominator.expected_leaves must contain ColumnExpectedLeaf"
        )
    if any(not isinstance(item, ColumnLeafOutcome) for item in outcomes):
        raise TypeError(
            "column_denominator.outcomes must contain ColumnLeafOutcome"
        )

    expected_ids = tuple(item.identity for item in expected)
    expected_values = tuple(item.value for item in expected_ids)
    if len(expected_values) != len(set(expected_values)):
        duplicates = tuple(
            sorted(
                {
                    value
                    for value in expected_values
                    if expected_values.count(value) > 1
                }
            )
        )
        raise ProjectReconciliationError(
            "A38 expected Column denominator contains duplicate leaf identity: "
            + ", ".join(duplicates)
        )

    expected_by_value = {
        item.identity.value: item
        for item in expected
    }
    expected_id_by_value = {
        item.identity.value: item.identity
        for item in expected
    }
    expected_set = set(expected_by_value)

    observed_by_value: dict[str, list[ColumnLeafOutcome]] = {}
    for outcome in outcomes:
        observed_by_value.setdefault(outcome.identity.value, []).append(outcome)

    observed_set = set(observed_by_value)
    silent_missing_values = expected_set - observed_set
    orphan_values = observed_set - expected_set
    duplicate_values = {
        value
        for value, rows in observed_by_value.items()
        if len(rows) > 1
    }
    accounted_values = expected_set & observed_set

    status_sets: dict[
        ColumnLeafOutcomeStatus,
        set[ColumnDenominatorLeafIdentity],
    ] = {
        status: set()
        for status in ColumnLeafOutcomeStatus
    }
    deferred: set[ColumnDenominatorLeafIdentity] = set()
    column_basis_refs: list[AnalysisBasisRef] = []

    for value in sorted(expected_set):
        rows = observed_by_value.get(value, ())
        if len(rows) != 1:
            continue
        outcome = rows[0]
        expected_leaf = expected_by_value[value]
        if outcome.identity != expected_leaf.identity:
            raise ProjectReconciliationError(
                "A39 Column outcome identity metadata differs from expected leaf "
                f"for {value}"
            )
        if (
            expected_leaf.applicability
            is ColumnLeafApplicability.PROVEN_NOT_APPLICABLE
        ) != (
            outcome.status
            is ColumnLeafOutcomeStatus.PROVEN_NOT_APPLICABLE
        ):
            raise ProjectReconciliationError(
                "A39 Column applicability/outcome PNA mismatch for " + value
            )
        status_sets[outcome.status].add(outcome.identity)
        if (
            outcome.status is ColumnLeafOutcomeStatus.EXPLICIT_UNRESOLVED
            and outcome.deferred_owner is not None
        ):
            deferred.add(outcome.identity)

        basis_status: AnalysisBasisStatus | None = None
        if outcome.analysis_basis_ref is not None:
            try:
                basis_status = AnalysisBasisStatus(outcome.analysis_basis_ref)
            except ValueError:
                basis_status = None
        if (
            outcome.status
            is ColumnLeafOutcomeStatus.REANALYSIS_REQUIRED
        ):
            basis_status = AnalysisBasisStatus.REANALYSIS_REQUIRED
        if basis_status is not None:
            column_basis_refs.append(
                AnalysisBasisRef(
                    instance_id=outcome.identity,
                    status=basis_status,
                    source_ref=outcome.source_ref,
                )
            )

    partition_ids: set[ColumnDenominatorLeafIdentity] = set().union(
        *status_sets.values()
    )
    partition_total = sum(len(items) for items in status_sets.values())
    partition_complete = (
        {item.value for item in partition_ids} == expected_set
        and partition_total == len(expected_set)
        and not silent_missing_values
        and not duplicate_values
    )

    orphan_ids: list[ColumnDenominatorLeafIdentity] = []
    for value in sorted(orphan_values):
        rows = observed_by_value[value]
        # The exact unexpected identity is sufficient for orphan accounting;
        # duplicate unexpected rows remain visible through duplicate accounting.
        orphan_ids.append(rows[0].identity)

    duplicate_ids: list[ColumnDenominatorLeafIdentity] = []
    for value in sorted(duplicate_values):
        duplicate_ids.append(observed_by_value[value][0].identity)

    return _ColumnPopulationAccounting(
        expected=_sorted_column_ids(expected_ids),
        accounted=_sorted_column_ids(
            expected_id_by_value[value]
            for value in accounted_values
        ),
        executed_pass=_sorted_column_ids(
            status_sets[ColumnLeafOutcomeStatus.EXECUTED_PASS]
        ),
        executed_fail=_sorted_column_ids(
            status_sets[ColumnLeafOutcomeStatus.EXECUTED_FAIL]
        ),
        proven_not_applicable=_sorted_column_ids(
            status_sets[ColumnLeafOutcomeStatus.PROVEN_NOT_APPLICABLE]
        ),
        blocked=_sorted_column_ids(
            status_sets[ColumnLeafOutcomeStatus.BLOCKED]
        ),
        no_data=_sorted_column_ids(
            status_sets[ColumnLeafOutcomeStatus.NO_DATA]
        ),
        explicit_unresolved=_sorted_column_ids(
            status_sets[ColumnLeafOutcomeStatus.EXPLICIT_UNRESOLVED]
        ),
        reanalysis_required=_sorted_column_ids(
            status_sets[ColumnLeafOutcomeStatus.REANALYSIS_REQUIRED]
        ),
        deferred_cross_domain=_sorted_column_ids(deferred),
        silent_missing=_sorted_column_ids(
            expected_id_by_value[value]
            for value in silent_missing_values
        ),
        duplicate_outcome=_sorted_column_ids(duplicate_ids),
        orphan_outcome=_sorted_column_ids(orphan_ids),
        analysis_basis_refs=tuple(
            sorted(
                column_basis_refs,
                key=lambda item: item.instance_id.value,
            )
        ),
        partition_complete=partition_complete,
        population_reconciled=(
            partition_complete
            and not duplicate_values
            and not orphan_values
        ),
    )


class ProjectCoverageReconciler:
    """Pure FCR-1A service; it never executes checks or mutates upstream state."""

    @staticmethod
    def reconcile(
        *,
        compiled_program: CompiledRegulatoryProgram,
        store_snapshot: RegulatoryStoreSnapshot,
        report_contributions: Sequence[SliceReportContribution] = (),
        report_bindings: Sequence[ReportBindingRef] = (),
        required_report_source_refs: Sequence[str] = (),
        findings: Sequence[Finding] = (),
        action_bindings: Sequence[ActionBindingRef] = (),
        required_action_finding_ids: Sequence[str] = (),
        regulatory_metadata_conflict_refs: Sequence[str] = (),
        analysis_basis_refs: Sequence[AnalysisBasisRef] | None = None,
        column_denominator: SupportedColumnDenominator | None = None,
    ) -> ProjectCoverageReconciliation:
        if not isinstance(compiled_program, CompiledRegulatoryProgram):
            raise TypeError("compiled_program must be CompiledRegulatoryProgram")
        if not isinstance(store_snapshot, RegulatoryStoreSnapshot):
            raise TypeError("store_snapshot must be RegulatoryStoreSnapshot")

        inventory = tuple(compiled_program.plan.compiled_closure_inventory)
        expected_all_ids = tuple(record.instance_id for record in inventory)
        if len(set(expected_all_ids)) != len(expected_all_ids):
            duplicates = sorted(
                item.value for item in set(expected_all_ids) if expected_all_ids.count(item) > 1
            )
            raise ProjectReconciliationError(
                "compiled_closure_inventory contains duplicate RuleInstanceId: " + ", ".join(duplicates)
            )
        expected_mandatory_ids = tuple(
            record.instance_id for record in inventory if record.mandatory is True
        )
        expected_all_set = set(expected_all_ids)
        expected_mandatory_set = set(expected_mandatory_ids)

        assessment = AssessmentEngine.reconcile(compiled_program, store_snapshot)
        assessment_by_id = {
            outcome.compiled_record_ref: outcome for outcome in assessment.closure_outcomes
        }
        if set(assessment_by_id) != expected_all_set:
            raise ProjectReconciliationError(
                "StructuralAssessment does not reconcile exactly to compiled closure inventory"
            )

        formal_by_id: dict[RuleInstanceId, list[FormalResultRecord]] = {}
        for record in store_snapshot.formal_results:
            if type(record) is not FormalResultRecord:
                raise ProjectReconciliationError(
                    "store_snapshot.formal_results must contain FormalResultRecord only"
                )
            formal_by_id.setdefault(record.instance_id, []).append(record)

        quantity_by_id: dict[RuleInstanceId, list[RegulatoryQuantity]] = {}
        for quantity in store_snapshot.regulatory_quantities:
            if type(quantity) is not RegulatoryQuantity:
                raise ProjectReconciliationError(
                    "store_snapshot.regulatory_quantities must contain RegulatoryQuantity only"
                )
            if not isinstance(quantity.producer_instance_id, RuleInstanceId):
                raise ProjectReconciliationError(
                    "regulatory quantity lacks canonical producer_instance_id"
                )
            quantity_by_id.setdefault(quantity.producer_instance_id, []).append(quantity)

        closure_by_id: dict[RuleInstanceId, list[RuleClosureOutcome]] = {}
        for outcome in store_snapshot.closure_outcomes:
            if type(outcome) is not RuleClosureOutcome:
                raise ProjectReconciliationError(
                    "store_snapshot.closure_outcomes must contain RuleClosureOutcome only"
                )
            closure_by_id.setdefault(outcome.compiled_record_ref, []).append(outcome)

        duplicate_result: set[RuleInstanceId] = set()
        duplicate_closure: set[RuleInstanceId] = set()
        for instance_id in expected_all_ids:
            node = compiled_program.node(instance_id)
            result_count = (
                len(quantity_by_id.get(instance_id, ()))
                if node.is_derivation
                else len(formal_by_id.get(instance_id, ()))
            )
            if result_count > 1:
                duplicate_result.add(instance_id)
            if len(closure_by_id.get(instance_id, ())) > 1:
                duplicate_closure.add(instance_id)

        pna_compiled_set = {
            record.instance_id
            for record in inventory
            if record.applicability is ApplicabilityState.PROVEN_NOT_APPLICABLE
        }
        accounted: set[RuleInstanceId] = set()
        silent_missing: set[RuleInstanceId] = set()
        for instance_id in expected_mandatory_ids:
            node = compiled_program.node(instance_id)
            canonical_artifact_count = (
                len(quantity_by_id.get(instance_id, ()))
                if node.is_derivation
                else len(formal_by_id.get(instance_id, ()))
            )
            explicit_closures = len(closure_by_id.get(instance_id, ()))
            if instance_id in pna_compiled_set or canonical_artifact_count or explicit_closures:
                accounted.add(instance_id)
            else:
                silent_missing.add(instance_id)

        orphan_result_ids = set(formal_by_id) - expected_all_set
        orphan_quantity_ids = set(quantity_by_id) - expected_all_set
        orphan_closure_ids = set(closure_by_id) - expected_all_set
        orphan_diagnostic_refs = tuple(
            sorted(
                {
                    ref
                    for instance_id in orphan_closure_ids
                    for outcome in closure_by_id[instance_id]
                    for ref in outcome.diagnostic_refs
                }
            )
        )

        mandatory_outcomes = {
            instance_id: assessment_by_id[instance_id] for instance_id in expected_mandatory_ids
        }
        status_sets: dict[ClosureExecutionStatus, set[RuleInstanceId]] = {
            status: set() for status in ClosureExecutionStatus
        }
        for instance_id, outcome in mandatory_outcomes.items():
            if outcome.execution_status not in status_sets:
                raise ProjectReconciliationError(
                    f"unknown canonical closure status: {outcome.execution_status!r}"
                )
            status_sets[outcome.execution_status].add(instance_id)

        executed_ids = status_sets[ClosureExecutionStatus.EXECUTED]
        pna_ids = status_sets[ClosureExecutionStatus.PROVEN_NOT_APPLICABLE]
        blocked_ids = status_sets[ClosureExecutionStatus.BLOCKED]
        no_data_ids = status_sets[ClosureExecutionStatus.NO_DATA]
        not_executed_ids = status_sets[ClosureExecutionStatus.NOT_EXECUTED]
        missing_ids = status_sets[ClosureExecutionStatus.MISSING]
        duplicate_ids = status_sets[ClosureExecutionStatus.DUPLICATE]
        invalid_ids = status_sets[ClosureExecutionStatus.INVALID]
        unresolved_ids = not_executed_ids | missing_ids | duplicate_ids | invalid_ids

        partition_sets = (
            executed_ids,
            pna_ids,
            blocked_ids,
            no_data_ids,
            not_executed_ids,
            missing_ids,
            duplicate_ids,
            invalid_ids,
        )
        closure_partition_union: set[RuleInstanceId] = set().union(*partition_sets)
        closure_partition_total = sum(len(values) for values in partition_sets)
        closure_partition_complete = (
            closure_partition_union == expected_mandatory_set
            and closure_partition_total == len(expected_mandatory_set)
        )
        if not closure_partition_complete:
            raise ProjectReconciliationError(
                "canonical mandatory closure statuses do not form an exact denominator partition"
            )

        if analysis_basis_refs is None:
            basis_refs = tuple(
                AnalysisBasisRef(
                    instance_id=instance_id,
                    status=compiled_program.node(instance_id).analysis_basis_status,
                    source_ref=f"COMPILED_RULE_NODE:{instance_id.value}",
                )
                for instance_id in expected_all_ids
            )
        else:
            supplied_basis = tuple(analysis_basis_refs)
            if any(not isinstance(item, AnalysisBasisRef) for item in supplied_basis):
                raise TypeError("analysis_basis_refs must contain AnalysisBasisRef only")
            supplied_ids = tuple(item.instance_id for item in supplied_basis)
            if len(set(supplied_ids)) != len(supplied_ids):
                raise ProjectReconciliationError("analysis_basis_refs contain duplicate RuleInstanceId")
            unknown = set(supplied_ids) - expected_all_set
            missing = expected_all_set - set(supplied_ids)
            if unknown or missing:
                raise ProjectReconciliationError(
                    "analysis_basis_refs must reconcile exactly to compiled closure inventory"
                )
            basis_refs = supplied_basis
        basis_refs = tuple(sorted(basis_refs, key=lambda item: item.instance_id.value))

        column_accounting = _reconcile_supported_column_denominator(
            column_denominator
        )
        basis_identity_values = {
            item.instance_id.value for item in basis_refs
        }
        for item in column_accounting.analysis_basis_refs:
            if item.instance_id.value in basis_identity_values:
                raise ProjectReconciliationError(
                    "A39 analysis_basis_refs contain duplicate identity across "
                    "regulatory and Column denominator populations"
                )
            basis_identity_values.add(item.instance_id.value)
        basis_refs = tuple(
            sorted(
                (*basis_refs, *column_accounting.analysis_basis_refs),
                key=lambda item: item.instance_id.value,
            )
        )

        contributions = tuple(report_contributions)
        if any(not isinstance(item, SliceReportContribution) for item in contributions):
            raise TypeError("report_contributions must contain SliceReportContribution only")
        contribution_refs = tuple(ReportContributionRef.from_contribution(item) for item in contributions)
        contribution_ref_counts: dict[ReportContributionRef, int] = {}
        for ref in contribution_refs:
            contribution_ref_counts[ref] = contribution_ref_counts.get(ref, 0) + 1
        duplicate_contribution_refs = tuple(
            sorted(
                (ref for ref, count in contribution_ref_counts.items() if count > 1),
                key=lambda ref: ref.sort_key,
            )
        )
        if duplicate_contribution_refs:
            raise ReportBindingIdentityBlocked(
                "REPORT_BINDING_IDENTITY_BLOCKED duplicate contribution identity: "
                + ", ".join(ref.value for ref in duplicate_contribution_refs)
            )
        known_contribution_refs = set(contribution_refs)

        canonical_findings = tuple(findings)
        if any(not isinstance(item, Finding) for item in canonical_findings):
            raise TypeError("findings must contain canonical Finding only")
        finding_ids = tuple(item.finding_id for item in canonical_findings)
        if len(set(finding_ids)) != len(finding_ids):
            raise ProjectReconciliationError("findings contain duplicate canonical finding_id")
        canonical_finding_ids = set(finding_ids)

        canonical_formal_result_refs = {
            outcome.formal_result_ref
            for outcome in assessment.closure_outcomes
            if outcome.formal_result_ref is not None
        }
        canonical_quantity_refs = {
            canonical_quantity_report_source_ref(
                outcome.compiled_record_ref,
                quantity_key,
            )
            for outcome in assessment.closure_outcomes
            for quantity_key in outcome.regulatory_quantity_refs
        }
        canonical_closure_refs = {
            canonical_closure_report_source_ref(outcome.compiled_record_ref)
            for outcome in assessment.closure_outcomes
        }
        canonical_report_sources = (
            canonical_formal_result_refs
            | canonical_quantity_refs
            | canonical_closure_refs
            | canonical_finding_ids
        )

        required_report = _unique_texts(required_report_source_refs, "required_report_source_refs")
        unknown_required_report = tuple(
            ref for ref in required_report if ref not in canonical_report_sources
        )
        if unknown_required_report:
            raise ProjectReconciliationError(
                "required report source is not a supplied canonical source: "
                + ", ".join(unknown_required_report)
            )

        bindings = tuple(report_bindings)
        if any(not isinstance(item, ReportBindingRef) for item in bindings):
            raise TypeError("report_bindings must contain ReportBindingRef only")
        binding_source_counts: dict[str, int] = {}
        for binding in bindings:
            binding_source_counts[binding.source_ref] = binding_source_counts.get(binding.source_ref, 0) + 1
        missing_report = tuple(
            ref for ref in required_report if binding_source_counts.get(ref, 0) == 0
        )
        duplicate_report = tuple(
            sorted(ref for ref, count in binding_source_counts.items() if count > 1)
        )
        orphan_report_sources = tuple(
            sorted({binding.source_ref for binding in bindings if binding.source_ref not in canonical_report_sources})
        )
        orphan_report_targets = tuple(
            sorted(
                {
                    binding.contribution_ref
                    for binding in bindings
                    if binding.contribution_ref not in known_contribution_refs
                },
                key=lambda ref: ref.sort_key,
            )
        )
        report_reconciled = not (
            missing_report or duplicate_report or orphan_report_sources or orphan_report_targets
        )

        required_actions = _unique_texts(required_action_finding_ids, "required_action_finding_ids")
        unknown_required_actions = tuple(
            ref for ref in required_actions if ref not in canonical_finding_ids
        )
        if unknown_required_actions:
            raise ProjectReconciliationError(
                "required action source is not a supplied canonical Finding: "
                + ", ".join(unknown_required_actions)
            )

        action_refs = tuple(action_bindings)
        if any(not isinstance(item, ActionBindingRef) for item in action_refs):
            raise TypeError("action_bindings must contain ActionBindingRef only")
        action_source_counts: dict[str, int] = {}
        for binding in action_refs:
            action_source_counts[binding.finding_id] = action_source_counts.get(binding.finding_id, 0) + 1
        missing_actions = tuple(
            ref for ref in required_actions if action_source_counts.get(ref, 0) == 0
        )
        duplicate_actions = tuple(
            sorted(ref for ref, count in action_source_counts.items() if count > 1)
        )
        orphan_actions = tuple(
            sorted({binding.finding_id for binding in action_refs if binding.finding_id not in canonical_finding_ids})
        )
        action_reconciled = not (missing_actions or duplicate_actions or orphan_actions)

        conflict_refs = _unique_texts(
            regulatory_metadata_conflict_refs,
            "regulatory_metadata_conflict_refs",
        )

        mandatory_duplicate_results = duplicate_result & expected_mandatory_set
        mandatory_duplicate_closures = duplicate_closure & expected_mandatory_set
        population_reconciled = not (
            silent_missing
            or mandatory_duplicate_results
            or mandatory_duplicate_closures
            or unresolved_ids
        )

        return ProjectCoverageReconciliation(
            plan_identity=compiled_program.plan.plan_identity,
            structural_assessment=assessment,
            expected_all_ids=_sorted_ids(expected_all_ids),
            expected_mandatory_ids=_sorted_ids(expected_mandatory_ids),
            accounted_mandatory_ids=_sorted_ids(accounted),
            executed_mandatory_ids=_sorted_ids(executed_ids),
            proven_not_applicable_mandatory_ids=_sorted_ids(pna_ids),
            blocked_mandatory_ids=_sorted_ids(blocked_ids),
            no_data_mandatory_ids=_sorted_ids(no_data_ids),
            not_executed_mandatory_ids=_sorted_ids(not_executed_ids),
            missing_mandatory_ids=_sorted_ids(missing_ids),
            duplicate_mandatory_ids=_sorted_ids(duplicate_ids),
            invalid_mandatory_ids=_sorted_ids(invalid_ids),
            unresolved_mandatory_ids=_sorted_ids(unresolved_ids),
            silent_missing_mandatory_ids=_sorted_ids(silent_missing),
            duplicate_result_instance_ids=_sorted_ids(duplicate_result),
            duplicate_closure_instance_ids=_sorted_ids(duplicate_closure),
            orphan_result_instance_ids=_sorted_ids(orphan_result_ids),
            orphan_quantity_instance_ids=_sorted_ids(orphan_quantity_ids),
            orphan_closure_instance_ids=_sorted_ids(orphan_closure_ids),
            orphan_diagnostic_refs=orphan_diagnostic_refs,
            analysis_basis_refs=basis_refs,
            required_report_source_refs=required_report,
            missing_report_source_refs=missing_report,
            duplicate_report_source_refs=duplicate_report,
            orphan_report_binding_source_refs=orphan_report_sources,
            orphan_report_target_refs=orphan_report_targets,
            required_action_finding_ids=required_actions,
            missing_action_finding_ids=missing_actions,
            duplicate_action_finding_ids=duplicate_actions,
            orphan_action_binding_finding_ids=orphan_actions,
            regulatory_metadata_conflict_refs=conflict_refs,
            closure_partition_complete=closure_partition_complete,
            population_reconciled=(
                population_reconciled
                and column_accounting.population_reconciled
            ),
            report_reconciled=report_reconciled,
            action_reconciled=action_reconciled,
            regulatory_metadata_clean=not conflict_refs,
            column_expected_leaf_ids=column_accounting.expected,
            column_accounted_leaf_ids=column_accounting.accounted,
            column_executed_pass_leaf_ids=column_accounting.executed_pass,
            column_executed_fail_leaf_ids=column_accounting.executed_fail,
            column_proven_not_applicable_leaf_ids=(
                column_accounting.proven_not_applicable
            ),
            column_blocked_leaf_ids=column_accounting.blocked,
            column_no_data_leaf_ids=column_accounting.no_data,
            column_explicit_unresolved_leaf_ids=(
                column_accounting.explicit_unresolved
            ),
            column_reanalysis_required_leaf_ids=(
                column_accounting.reanalysis_required
            ),
            column_deferred_cross_domain_leaf_ids=(
                column_accounting.deferred_cross_domain
            ),
            column_silent_missing_leaf_ids=column_accounting.silent_missing,
            column_duplicate_outcome_leaf_ids=(
                column_accounting.duplicate_outcome
            ),
            column_orphan_outcome_leaf_ids=column_accounting.orphan_outcome,
            column_partition_complete=column_accounting.partition_complete,
            column_population_reconciled=(
                column_accounting.population_reconciled
            ),
        )


__all__ = [
    "ActionBindingRef",
    "AnalysisBasisRef",
    "ProjectCoverageReconciliation",
    "ProjectCoverageReconciler",
    "ProjectReconciliationError",
    "ReportBindingIdentityBlocked",
    "ReportBindingRef",
    "ReportContributionRef",
    "canonical_closure_report_source_ref",
    "canonical_quantity_report_source_ref",
]
