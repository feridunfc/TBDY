from __future__ import annotations

from dataclasses import dataclass

from tbdy_engine.checks.result import CheckResult
from tbdy_engine.coverage.column_denominator import (
    ColumnDenominatorLeafIdentity,
    ColumnExpectedLeaf,
    ColumnLeafApplicability,
    ColumnLeafOutcome,
    ColumnLeafOutcomeStatus,
    SupportedColumnDenominator,
    canonical_column_leaf_source_ref,
)
from tbdy_engine.coverage.project_reconciliation import (
    ProjectCoverageReconciler,
)
from tbdy_engine.regulatory.contracts import (
    ApplicabilityBinding,
    ApplicabilityState,
    CheckEvaluatorBinding,
    CheckSpec,
    Grain,
    RuleId,
)
from tbdy_engine.regulatory.kernel import (
    AnalysisBasisStatus,
    RegulatoryCompileInputs,
    RegulatoryCompiler,
    RegulatoryStoreSnapshot,
    RuleScopeTarget,
)
from tbdy_engine.regulatory.registry import RegulatoryRegistry


MODEL = "model:a39"
EPOCH = "epoch:a39"
COMPONENT = "C1"


@dataclass(frozen=True, slots=True)
class _AppInput:
    state: ApplicabilityState = ApplicabilityState.PROVEN_NOT_APPLICABLE


def _app(value: _AppInput) -> ApplicabilityState:
    return value.state


def _program_and_snapshot():
    rule = "F0_A39_SENTINEL"
    registry = RegulatoryRegistry(
        checks=(
            CheckSpec(
                rule_id=RuleId(rule),
                code_refs=("TEST",),
                rule_version="v1",
                formal_result_type=CheckResult,
                dependencies=(),
                applicability=ApplicabilityBinding(
                    "app:a39",
                    _AppInput,
                    _app,
                ),
                evaluator=CheckEvaluatorBinding(
                    "eval:a39",
                    object,
                    lambda _: None,
                ),
            ),
        )
    )
    program = RegulatoryCompiler.compile(
        registry,
        RegulatoryCompileInputs(
            rule_targets=(
                RuleScopeTarget(
                    rule_id=RuleId(rule),
                    grain=Grain.COMPONENT,
                    scope_ref="A39:F0",
                    mandatory=True,
                    applicability_input=_AppInput(),
                ),
            )
        ),
    )
    snapshot = RegulatoryStoreSnapshot(
        plan_identity=program.plan.plan_identity,
        regulatory_quantities=(),
        formal_results=(),
        closure_outcomes=(),
        diagnostics=(),
    )
    return program, snapshot


def _identity(key: str, *, direction: str | None = None):
    return ColumnDenominatorLeafIdentity.build(
        component_id=COMPONENT,
        leaf_key=key,
        model_fingerprint=MODEL,
        evidence_epoch_id=EPOCH,
        direction=direction,
    )


def _leaf(
    key: str,
    *,
    applicability: ColumnLeafApplicability = ColumnLeafApplicability.MANDATORY,
):
    identity = _identity(key)
    return ColumnExpectedLeaf(
        identity=identity,
        family=key,
        applicability=applicability,
    )


def _outcome(
    leaf: ColumnExpectedLeaf,
    status: ColumnLeafOutcomeStatus,
    *,
    deferred_owner: str | None = None,
    dependency_refs: tuple[str, ...] = (),
    analysis_basis_ref: str | None = None,
):
    return ColumnLeafOutcome(
        identity=leaf.identity,
        status=status,
        source_ref=canonical_column_leaf_source_ref(leaf.identity),
        evidence_refs=(f"EVIDENCE:{leaf.identity.leaf_key}",),
        blocker_refs=(
            (f"BLOCKER:{leaf.identity.leaf_key}",)
            if status
            in {
                ColumnLeafOutcomeStatus.BLOCKED,
                ColumnLeafOutcomeStatus.NO_DATA,
                ColumnLeafOutcomeStatus.EXPLICIT_UNRESOLVED,
                ColumnLeafOutcomeStatus.REANALYSIS_REQUIRED,
            }
            else ()
        ),
        analysis_basis_ref=analysis_basis_ref,
        dependency_refs=dependency_refs,
        deferred_owner=deferred_owner,
    )


def _full_denominator():
    pass_leaf = _leaf("PASS")
    fail_leaf = _leaf("FAIL")
    pna_leaf = _leaf(
        "PNA",
        applicability=ColumnLeafApplicability.PROVEN_NOT_APPLICABLE,
    )
    blocked_leaf = _leaf("BLOCKED")
    no_data_leaf = _leaf("NO_DATA")
    reanalysis_leaf = _leaf("REANALYSIS")
    deferred_leaf = _leaf("SCWB")

    expected = (
        pass_leaf,
        fail_leaf,
        pna_leaf,
        blocked_leaf,
        no_data_leaf,
        reanalysis_leaf,
        deferred_leaf,
    )
    outcomes = (
        _outcome(pass_leaf, ColumnLeafOutcomeStatus.EXECUTED_PASS),
        _outcome(fail_leaf, ColumnLeafOutcomeStatus.EXECUTED_FAIL),
        _outcome(
            pna_leaf,
            ColumnLeafOutcomeStatus.PROVEN_NOT_APPLICABLE,
        ),
        _outcome(blocked_leaf, ColumnLeafOutcomeStatus.BLOCKED),
        _outcome(no_data_leaf, ColumnLeafOutcomeStatus.NO_DATA),
        _outcome(
            reanalysis_leaf,
            ColumnLeafOutcomeStatus.REANALYSIS_REQUIRED,
            analysis_basis_ref=AnalysisBasisStatus.REANALYSIS_REQUIRED.value,
        ),
        _outcome(
            deferred_leaf,
            ColumnLeafOutcomeStatus.EXPLICIT_UNRESOLVED,
            deferred_owner="BEAM_DOMAIN",
            dependency_refs=("CANONICAL_BEAM_CAPACITY_AUTHORITY",),
        ),
    )
    return SupportedColumnDenominator(expected, outcomes)


def _unsafe_denominator(expected, outcomes):
    value = object.__new__(SupportedColumnDenominator)
    object.__setattr__(value, "expected_leaves", tuple(expected))
    object.__setattr__(value, "outcomes", tuple(outcomes))
    return value


def _reconcile(denominator):
    program, snapshot = _program_and_snapshot()
    return ProjectCoverageReconciler.reconcile(
        compiled_program=program,
        store_snapshot=snapshot,
        column_denominator=denominator,
    )


def test_full_a38_denominator_feeds_existing_fcr_with_exact_truthful_partition():
    reconciliation = _reconcile(_full_denominator())

    assert reconciliation.column_expected_instance_count == 7
    assert reconciliation.column_accounted_instance_count == 7
    assert reconciliation.column_executed_pass_count == 1
    assert reconciliation.column_executed_fail_count == 1
    assert reconciliation.column_proven_not_applicable_count == 1
    assert reconciliation.column_blocked_count == 1
    assert reconciliation.column_no_data_count == 1
    assert reconciliation.column_explicit_unresolved_count == 1
    assert reconciliation.column_reanalysis_required_count == 1
    assert reconciliation.column_deferred_cross_domain_count == 1

    assert reconciliation.column_silent_missing_count == 0
    assert reconciliation.column_duplicate_count == 0
    assert reconciliation.column_orphan_count == 0
    assert reconciliation.column_partition_complete is True
    assert reconciliation.column_population_reconciled is True
    assert reconciliation.population_reconciled is True

    payload = reconciliation.as_dict()
    product = payload["column_denominator_reconciliation"]
    assert product["summary"]["silent_missing_count"] == 0
    assert product["summary"]["duplicate_count"] == 0
    assert product["summary"]["orphan_count"] == 0


def test_fail_blocked_no_data_and_pna_are_accounted_not_reclassified_missing():
    reconciliation = _reconcile(_full_denominator())

    assert reconciliation.column_executed_fail_count == 1
    assert reconciliation.column_blocked_count == 1
    assert reconciliation.column_no_data_count == 1
    assert reconciliation.column_proven_not_applicable_count == 1
    assert reconciliation.column_silent_missing_count == 0
    assert reconciliation.column_population_reconciled is True


def test_reanalysis_required_survives_through_analysis_basis_refs():
    reconciliation = _reconcile(_full_denominator())

    product_ids = {
        item.value
        for item in reconciliation.reanalysis_required_instance_ids
        if isinstance(item, ColumnDenominatorLeafIdentity)
    }
    expected = next(
        item.value
        for item in reconciliation.column_reanalysis_required_leaf_ids
    )
    assert expected in product_ids

    refs = {
        item.instance_id.value: item
        for item in reconciliation.analysis_basis_refs
        if isinstance(item.instance_id, ColumnDenominatorLeafIdentity)
    }
    assert refs[expected].status is AnalysisBasisStatus.REANALYSIS_REQUIRED


def test_deferred_cross_domain_remains_visible_and_is_not_pass():
    reconciliation = _reconcile(_full_denominator())

    assert reconciliation.column_deferred_cross_domain_count == 1
    deferred_id = reconciliation.column_deferred_cross_domain_leaf_ids[0]
    assert deferred_id in reconciliation.column_explicit_unresolved_leaf_ids
    assert deferred_id not in reconciliation.column_executed_pass_leaf_ids


def test_missing_expected_column_outcome_becomes_silent_missing():
    valid = _full_denominator()
    malformed = _unsafe_denominator(
        valid.expected_leaves,
        valid.outcomes[:-1],
    )

    reconciliation = _reconcile(malformed)
    assert reconciliation.column_silent_missing_count == 1
    assert reconciliation.column_partition_complete is False
    assert reconciliation.column_population_reconciled is False
    assert reconciliation.population_reconciled is False


def test_unexpected_column_outcome_becomes_orphan():
    valid = _full_denominator()
    orphan_leaf = _leaf("ORPHAN")
    orphan = _outcome(
        orphan_leaf,
        ColumnLeafOutcomeStatus.BLOCKED,
    )
    malformed = _unsafe_denominator(
        valid.expected_leaves,
        (*valid.outcomes, orphan),
    )

    reconciliation = _reconcile(malformed)
    assert reconciliation.column_orphan_count == 1
    assert reconciliation.column_population_reconciled is False
    assert reconciliation.population_reconciled is False


def test_duplicate_column_outcome_is_detected_without_becoming_missing():
    valid = _full_denominator()
    duplicate = valid.outcomes[0]
    malformed = _unsafe_denominator(
        valid.expected_leaves,
        (*valid.outcomes, duplicate),
    )

    reconciliation = _reconcile(malformed)
    assert reconciliation.column_duplicate_count == 1
    assert reconciliation.column_silent_missing_count == 0
    assert reconciliation.column_partition_complete is False
    assert reconciliation.column_population_reconciled is False
    assert reconciliation.population_reconciled is False


def test_a39_reconciliation_is_deterministic_and_does_not_change_a38_truth():
    denominator = _full_denominator()
    before = denominator.to_json()

    first = _reconcile(denominator)
    second = _reconcile(denominator)

    assert first.to_json() == second.to_json()
    assert denominator.to_json() == before
    assert first.column_population_reconciled is True
