"""Project-wide canonical coverage reconciliation for FCR-1A.

This module is a bounded completeness/binding layer only.  It does not discover
regulatory scope, execute engineering checks, reinterpret closure statuses,
generate actions, or recalculate report values.

Authoritative responsibilities remain with:
- ``CompiledRegulatoryProgram.plan.compiled_closure_inventory`` for expected scope,
- ``AssessmentEngine.reconcile`` / ``StructuralAssessment`` for closure semantics,
- canonical ``Finding`` objects for unresolved-condition identity, and
- ``SliceReportContribution`` for presentation projection.

FCR adds exact-identity population, report-binding, and action-binding
reconciliation around those existing authorities.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import json
from typing import Sequence

from tbdy_engine.findings.contracts import Finding
from tbdy_engine.product_reports.slice_report_contribution import SliceReportContribution
from tbdy_engine.regulatory.contracts import (
    ApplicabilityState,
    ClosureExecutionStatus,
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


def _rule_id_values(values: Sequence[RuleInstanceId]) -> tuple[str, ...]:
    return tuple(item.value for item in sorted(values, key=lambda item: item.value))


@dataclass(frozen=True, slots=True)
class ReportContributionRef:
    """Exact FCR-local identity for one existing report contribution."""

    slice_id: str
    component_type: str | None
    component_id: str | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "slice_id", _text(self.slice_id, "slice_id"))
        if self.component_type is not None:
            object.__setattr__(
                self, "component_type", _text(self.component_type, "component_type")
            )
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
    """Bind one exact canonical report source to one exact contribution."""

    source_ref: str
    contribution_ref: ReportContributionRef

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_ref", _text(self.source_ref, "source_ref"))
        if not isinstance(self.contribution_ref, ReportContributionRef):
            raise TypeError("contribution_ref must be ReportContributionRef")

    @property
    def sort_key(self) -> tuple[str, str]:
        return self.source_ref, self.contribution_ref.value


@dataclass(frozen=True, slots=True)
class ActionBindingRef:
    """Minimum FCR-local binding from canonical Finding to an existing action ref."""

    finding_id: str
    action_ref: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "finding_id", _text(self.finding_id, "finding_id"))
        object.__setattr__(self, "action_ref", _text(self.action_ref, "action_ref"))

    @property
    def sort_key(self) -> tuple[str, str]:
        return self.finding_id, self.action_ref


@dataclass(frozen=True, slots=True)
class AnalysisBasisRef:
    """Preserve the existing analysis-basis state without translating it."""

    instance_id: RuleInstanceId
    status: AnalysisBasisStatus

    def __post_init__(self) -> None:
        if not isinstance(self.instance_id, RuleInstanceId):
            raise TypeError("instance_id must be RuleInstanceId")
        if not isinstance(self.status, AnalysisBasisStatus):
            raise TypeError("status must be AnalysisBasisStatus")


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
    population_reconciled: bool
    report_reconciled: bool
    action_reconciled: bool
    regulatory_metadata_clean: bool

    def __post_init__(self) -> None:
        _text(self.plan_identity, "plan_identity")
        if not isinstance(self.structural_assessment, StructuralAssessment):
            raise TypeError("structural_assessment must be StructuralAssessment")
        if self.structural_assessment.plan_identity != self.plan_identity:
            raise ProjectReconciliationError(
                "structural_assessment plan identity must match reconciliation plan identity"
            )

    @property
    def mandatory_closure_complete(self) -> bool:
        """Reuse canonical StructuralAssessment; this is not a compliance PASS."""

        return (
            self.structural_assessment.structural_status
            is StructuralAssessmentStatus.COMPLETE
        )

    @property
    def reanalysis_required_instance_ids(self) -> tuple[RuleInstanceId, ...]:
        return tuple(
            item.instance_id
            for item in self.analysis_basis_refs
            if item.status is AnalysisBasisStatus.REANALYSIS_REQUIRED
        )

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
        return len(self.orphan_report_binding_source_refs) + len(
            self.orphan_report_target_refs
        )

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
                "regulatory_quantity_refs": [
                    item.value for item in outcome.regulatory_quantity_refs
                ],
                "diagnostic_refs": list(outcome.diagnostic_refs),
            }
            for outcome in self.structural_assessment.closure_outcomes
        ]
        basis_rows = [
            {"instance_id": item.instance_id.value, "status": item.status.value}
            for item in self.analysis_basis_refs
        ]
        return {
            "schema_version": "project_coverage_reconciliation.fcr_1a.v1",
            "artifact_type": "PROJECT_COVERAGE_RECONCILIATION",
            "plan_identity": self.plan_identity,
            "expected_all_ids": list(_rule_id_values(self.expected_all_ids)),
            "expected_mandatory_ids": list(
                _rule_id_values(self.expected_mandatory_ids)
            ),
            "accounted_mandatory_ids": list(
                _rule_id_values(self.accounted_mandatory_ids)
            ),
            "executed_mandatory_ids": list(
                _rule_id_values(self.executed_mandatory_ids)
            ),
            "proven_not_applicable_mandatory_ids": list(
                _rule_id_values(self.proven_not_applicable_mandatory_ids)
            ),
            "blocked_mandatory_ids": list(
                _rule_id_values(self.blocked_mandatory_ids)
            ),
            "no_data_mandatory_ids": list(
                _rule_id_values(self.no_data_mandatory_ids)
            ),
            "silent_missing_mandatory_ids": list(
                _rule_id_values(self.silent_missing_mandatory_ids)
            ),
            "duplicate_result_instance_ids": list(
                _rule_id_values(self.duplicate_result_instance_ids)
            ),
            "duplicate_closure_instance_ids": list(
                _rule_id_values(self.duplicate_closure_instance_ids)
            ),
            "orphan_result_instance_ids": list(
                _rule_id_values(self.orphan_result_instance_ids)
            ),
            "orphan_quantity_instance_ids": list(
                _rule_id_values(self.orphan_quantity_instance_ids)
            ),
            "orphan_closure_instance_ids": list(
                _rule_id_values(self.orphan_closure_instance_ids)
            ),
            "orphan_diagnostic_refs": list(self.orphan_diagnostic_refs),
            "analysis_basis": basis_rows,
            "closure_outcomes": closure_rows,
            "required_report_source_refs": list(self.required_report_source_refs),
            "missing_report_source_refs": list(self.missing_report_source_refs),
            "duplicate_report_source_refs": list(self.duplicate_report_source_refs),
            "orphan_report_binding_source_refs": list(
                self.orphan_report_binding_source_refs
            ),
            "orphan_report_target_refs": [
                item.value for item in self.orphan_report_target_refs
            ],
            "required_action_finding_ids": list(
                self.required_action_finding_ids
            ),
            "missing_action_finding_ids": list(self.missing_action_finding_ids),
            "duplicate_action_finding_ids": list(
                self.duplicate_action_finding_ids
            ),
            "orphan_action_binding_finding_ids": list(
                self.orphan_action_binding_finding_ids
            ),
            "regulatory_metadata_conflict_refs": list(
                self.regulatory_metadata_conflict_refs
            ),
            "summary": {
                "expected_mandatory_instance_count": self.expected_mandatory_instance_count,
                "accounted_instance_count": self.accounted_instance_count,
                "executed_result_count": self.executed_result_count,
                "proven_not_applicable_count": self.proven_not_applicable_count,
                "blocked_count": self.blocked_count,
                "no_data_count": self.no_data_count,
                "silent_missing_count": self.silent_missing_count,
                "duplicate_result_count": self.duplicate_result_count,
                "orphan_result_count": self.orphan_result_count,
                "orphan_diagnostic_count": self.orphan_diagnostic_count,
                "missing_report_binding_count": self.missing_report_binding_count,
                "orphan_report_binding_count": self.orphan_report_binding_count,
                "missing_action_binding_count": self.missing_action_binding_count,
                "orphan_action_binding_count": self.orphan_action_binding_count,
                "regulatory_metadata_conflict_count": self.regulatory_metadata_conflict_count,
                "population_reconciled": self.population_reconciled,
                "mandatory_closure_complete": self.mandatory_closure_complete,
                "report_reconciled": self.report_reconciled,
                "action_reconciled": self.action_reconciled,
                "regulatory_metadata_clean": self.regulatory_metadata_clean,
            },
        }

    def to_json(self) -> str:
        """Canonical byte-stable JSON text for identical canonical inputs."""

        return (
            json.dumps(
                self.as_dict(),
                ensure_ascii=True,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
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
    ) -> ProjectCoverageReconciliation:
        if not isinstance(compiled_program, CompiledRegulatoryProgram):
            raise TypeError("compiled_program must be CompiledRegulatoryProgram")
        if not isinstance(store_snapshot, RegulatoryStoreSnapshot):
            raise TypeError("store_snapshot must be RegulatoryStoreSnapshot")

        inventory = tuple(compiled_program.plan.compiled_closure_inventory)
        expected_all_ids = tuple(record.instance_id for record in inventory)
        if len(set(expected_all_ids)) != len(expected_all_ids):
            duplicates = sorted(
                {
                    item.value
                    for item in expected_all_ids
                    if expected_all_ids.count(item) > 1
                }
            )
            raise ProjectReconciliationError(
                "compiled_closure_inventory contains duplicate RuleInstanceId: "
                + ", ".join(duplicates)
            )
        expected_mandatory_ids = tuple(
            record.instance_id for record in inventory if record.mandatory is True
        )
        expected_all_set = set(expected_all_ids)
        expected_mandatory_set = set(expected_mandatory_ids)

        # Canonical closure authority is reused as-is.  FCR never derives its own
        # engineering closure status from CheckResult/status text.
        assessment = AssessmentEngine.reconcile(compiled_program, store_snapshot)
        assessment_by_id = {
            outcome.compiled_record_ref: outcome
            for outcome in assessment.closure_outcomes
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

        quantity_by_id: dict[RuleInstanceId, list[object]] = {}
        for quantity in store_snapshot.regulatory_quantities:
            instance_id = getattr(quantity, "producer_instance_id", None)
            if not isinstance(instance_id, RuleInstanceId):
                raise ProjectReconciliationError(
                    "regulatory quantity lacks canonical producer_instance_id"
                )
            quantity_by_id.setdefault(instance_id, []).append(quantity)

        closure_by_id: dict[RuleInstanceId, list[RuleClosureOutcome]] = {}
        for outcome in store_snapshot.closure_outcomes:
            if type(outcome) is not RuleClosureOutcome:
                raise ProjectReconciliationError(
                    "store_snapshot.closure_outcomes must contain RuleClosureOutcome only"
                )
            closure_by_id.setdefault(outcome.compiled_record_ref, []).append(outcome)

        pna_compiled_set = {
            record.instance_id
            for record in inventory
            if record.applicability is ApplicabilityState.PROVEN_NOT_APPLICABLE
        }
        accounted: set[RuleInstanceId] = set()
        silent_missing: set[RuleInstanceId] = set()
        duplicate_result: set[RuleInstanceId] = set()
        duplicate_closure: set[RuleInstanceId] = set()

        # Track duplication across the whole compiled plan, while the mandatory
        # population gate below only considers the mandatory subset.
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

        for instance_id in expected_mandatory_ids:
            node = compiled_program.node(instance_id)
            canonical_artifact_count = (
                len(quantity_by_id.get(instance_id, ()))
                if node.is_derivation
                else len(formal_by_id.get(instance_id, ()))
            )
            explicit_closures = len(closure_by_id.get(instance_id, ()))
            if (
                instance_id in pna_compiled_set
                or canonical_artifact_count
                or explicit_closures
            ):
                accounted.add(instance_id)
            else:
                silent_missing.add(instance_id)

        orphan_result_ids = {
            instance_id
            for instance_id in formal_by_id
            if instance_id not in expected_all_set
        }
        orphan_quantity_ids = {
            instance_id
            for instance_id in quantity_by_id
            if instance_id not in expected_all_set
        }
        orphan_closure_ids = {
            instance_id
            for instance_id in closure_by_id
            if instance_id not in expected_all_set
        }
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
            instance_id: assessment_by_id[instance_id]
            for instance_id in expected_mandatory_ids
        }
        executed_ids = {
            instance_id
            for instance_id, outcome in mandatory_outcomes.items()
            if outcome.execution_status is ClosureExecutionStatus.EXECUTED
        }
        pna_ids = {
            instance_id
            for instance_id, outcome in mandatory_outcomes.items()
            if outcome.execution_status
            is ClosureExecutionStatus.PROVEN_NOT_APPLICABLE
        }
        blocked_ids = {
            instance_id
            for instance_id, outcome in mandatory_outcomes.items()
            if outcome.execution_status is ClosureExecutionStatus.BLOCKED
        }
        no_data_ids = {
            instance_id
            for instance_id, outcome in mandatory_outcomes.items()
            if outcome.execution_status is ClosureExecutionStatus.NO_DATA
        }
        analysis_basis_refs = tuple(
            sorted(
                (
                    AnalysisBasisRef(
                        instance_id=instance_id,
                        status=compiled_program.node(instance_id).analysis_basis_status,
                    )
                    for instance_id in expected_all_ids
                ),
                key=lambda item: item.instance_id.value,
            )
        )

        contributions = tuple(report_contributions)
        if any(
            not isinstance(item, SliceReportContribution) for item in contributions
        ):
            raise TypeError(
                "report_contributions must contain SliceReportContribution only"
            )
        contribution_refs = tuple(
            ReportContributionRef.from_contribution(item) for item in contributions
        )
        contribution_ref_counts: dict[ReportContributionRef, int] = {}
        for ref in contribution_refs:
            contribution_ref_counts[ref] = contribution_ref_counts.get(ref, 0) + 1
        duplicate_contribution_refs = tuple(
            sorted(
                (
                    ref
                    for ref, count in contribution_ref_counts.items()
                    if count > 1
                ),
                key=lambda ref: ref.sort_key,
            )
        )
        if duplicate_contribution_refs:
            raise ReportBindingIdentityBlocked(
                "REPORT_BINDING_IDENTITY_BLOCKED duplicate contribution identity: "
                + ", ".join(ref.value for ref in duplicate_contribution_refs)
            )
        known_contribution_refs = set(contribution_refs)

        canonical_formal_result_refs = {
            outcome.formal_result_ref
            for outcome in assessment.closure_outcomes
            if outcome.formal_result_ref is not None
        }

        canonical_findings = tuple(findings)
        if any(not isinstance(item, Finding) for item in canonical_findings):
            raise TypeError("findings must contain canonical Finding only")
        finding_ids = tuple(item.finding_id for item in canonical_findings)
        if len(set(finding_ids)) != len(finding_ids):
            raise ProjectReconciliationError(
                "findings contain duplicate canonical finding_id"
            )
        canonical_finding_ids = set(finding_ids)
        canonical_report_sources = canonical_formal_result_refs | canonical_finding_ids

        required_report = _unique_texts(
            required_report_source_refs, "required_report_source_refs"
        )
        unknown_required_report = tuple(
            ref for ref in required_report if ref not in canonical_report_sources
        )
        if unknown_required_report:
            raise ProjectReconciliationError(
                "required report source is not a supplied canonical result/Finding: "
                + ", ".join(unknown_required_report)
            )

        bindings = tuple(report_bindings)
        if any(not isinstance(item, ReportBindingRef) for item in bindings):
            raise TypeError("report_bindings must contain ReportBindingRef only")
        binding_source_counts: dict[str, int] = {}
        for binding in bindings:
            binding_source_counts[binding.source_ref] = (
                binding_source_counts.get(binding.source_ref, 0) + 1
            )

        missing_report = tuple(
            ref for ref in required_report if binding_source_counts.get(ref, 0) == 0
        )
        duplicate_report = tuple(
            sorted(
                ref
                for ref, count in binding_source_counts.items()
                if count > 1
            )
        )
        orphan_report_sources = tuple(
            sorted(
                {
                    binding.source_ref
                    for binding in bindings
                    if binding.source_ref not in canonical_report_sources
                }
            )
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
            missing_report
            or duplicate_report
            or orphan_report_sources
            or orphan_report_targets
        )

        required_actions = _unique_texts(
            required_action_finding_ids, "required_action_finding_ids"
        )
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
            action_source_counts[binding.finding_id] = (
                action_source_counts.get(binding.finding_id, 0) + 1
            )
        missing_actions = tuple(
            ref for ref in required_actions if action_source_counts.get(ref, 0) == 0
        )
        duplicate_actions = tuple(
            sorted(
                ref
                for ref, count in action_source_counts.items()
                if count > 1
            )
        )
        orphan_actions = tuple(
            sorted(
                {
                    binding.finding_id
                    for binding in action_refs
                    if binding.finding_id not in canonical_finding_ids
                }
            )
        )
        action_reconciled = not (
            missing_actions or duplicate_actions or orphan_actions
        )

        conflict_refs = _unique_texts(
            regulatory_metadata_conflict_refs,
            "regulatory_metadata_conflict_refs",
        )

        # Mandatory population reconciliation is intentionally a completeness
        # axis only.  Valid optional rules and unrelated orphans do not alter its
        # denominator; they are tracked separately.
        mandatory_duplicate_results = duplicate_result & expected_mandatory_set
        mandatory_duplicate_closures = duplicate_closure & expected_mandatory_set
        population_reconciled = not (
            silent_missing
            or mandatory_duplicate_results
            or mandatory_duplicate_closures
        )

        return ProjectCoverageReconciliation(
            plan_identity=compiled_program.plan.plan_identity,
            structural_assessment=assessment,
            expected_all_ids=tuple(
                sorted(expected_all_ids, key=lambda item: item.value)
            ),
            expected_mandatory_ids=tuple(
                sorted(expected_mandatory_ids, key=lambda item: item.value)
            ),
            accounted_mandatory_ids=tuple(
                sorted(accounted, key=lambda item: item.value)
            ),
            executed_mandatory_ids=tuple(
                sorted(executed_ids, key=lambda item: item.value)
            ),
            proven_not_applicable_mandatory_ids=tuple(
                sorted(pna_ids, key=lambda item: item.value)
            ),
            blocked_mandatory_ids=tuple(
                sorted(blocked_ids, key=lambda item: item.value)
            ),
            no_data_mandatory_ids=tuple(
                sorted(no_data_ids, key=lambda item: item.value)
            ),
            silent_missing_mandatory_ids=tuple(
                sorted(silent_missing, key=lambda item: item.value)
            ),
            duplicate_result_instance_ids=tuple(
                sorted(duplicate_result, key=lambda item: item.value)
            ),
            duplicate_closure_instance_ids=tuple(
                sorted(duplicate_closure, key=lambda item: item.value)
            ),
            orphan_result_instance_ids=tuple(
                sorted(orphan_result_ids, key=lambda item: item.value)
            ),
            orphan_quantity_instance_ids=tuple(
                sorted(orphan_quantity_ids, key=lambda item: item.value)
            ),
            orphan_closure_instance_ids=tuple(
                sorted(orphan_closure_ids, key=lambda item: item.value)
            ),
            orphan_diagnostic_refs=orphan_diagnostic_refs,
            analysis_basis_refs=analysis_basis_refs,
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
            population_reconciled=population_reconciled,
            report_reconciled=report_reconciled,
            action_reconciled=action_reconciled,
            regulatory_metadata_clean=not conflict_refs,
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
]
