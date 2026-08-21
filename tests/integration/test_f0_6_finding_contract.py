from __future__ import annotations

from dataclasses import FrozenInstanceError, fields, replace
from pathlib import Path

import pytest

from tbdy_engine.analysis_basis.contracts import AnalysisBasisCompatibility
from tbdy_engine.checks.result import CheckResult, CheckStatus
from tbdy_engine.findings import (
    Finding,
    FindingSourceKind,
    build_finding_from_analysis_basis,
    build_finding_from_check_result,
    build_finding_from_rule_closure,
)
from tbdy_engine.regulatory.contracts import (
    ApplicabilityState,
    ClosureExecutionStatus,
    CompiledClosureRecord,
    DependencyKey,
    Grain,
    RuleClosureOutcome,
    RuleId,
    RuleInstanceId,
)
from tbdy_engine.regulatory.kernel import AnalysisBasisStatus


def _instance(rule: str = "TEST_CHECK", scope: str = "C1") -> RuleInstanceId:
    return RuleInstanceId.build(rule_id=RuleId(rule), grain=Grain.COMPONENT, scope_ref=scope)


def _directional_instance(
    rule: str = "TEST_DIRECTIONAL_CHECK",
    scope: str = "C1",
    direction: str = "X",
) -> RuleInstanceId:
    return RuleInstanceId.build(
        rule_id=RuleId(rule),
        grain=Grain.COMPONENT_DIRECTION,
        scope_ref=scope,
        direction=direction,
    )


def _result(status: CheckStatus, *, rule: str = "TEST_CHECK", scope: str = "C1") -> CheckResult:
    return CheckResult(
        check_id=rule,
        component=scope,
        component_type="toy",
        status=status,
        value=999.0 if status is CheckStatus.FAIL else 0.0,
        limit=1.0 if status is CheckStatus.FAIL else 999.0,
        messages=("source-message",),
        code_ref="TBDY-TEST",
    )


def _closure(status: ClosureExecutionStatus) -> tuple[CompiledClosureRecord, RuleClosureOutcome]:
    instance = _instance("TEST_CLOSURE")
    record = CompiledClosureRecord(
        instance_id=instance,
        rule_id=instance.rule_id,
        grain=instance.grain,
        scope_ref=instance.scope_ref,
        mandatory=True,
        applicability=ApplicabilityState.APPLIES,
        declared_dependency_refs=(),
        code_refs=("TBDY-CLOSURE",),
        rule_version="v1",
    )
    outcome = RuleClosureOutcome(
        compiled_record_ref=instance,
        execution_status=status,
        regulatory_quantity_refs=(DependencyKey("Q1"),) if status is ClosureExecutionStatus.BLOCKED else (),
        diagnostic_refs=("diag:closure",),
    )
    return record, outcome


def _compat(status: AnalysisBasisStatus) -> AnalysisBasisCompatibility:
    return AnalysisBasisCompatibility(
        compatibility_id=f"compat:X:{status.value}",
        epoch_ref="epoch:E17",
        structural_zone_ref="SUPERSTRUCTURE",
        direction="X",
        required_basis_ref="policy:X",
        analysis_assumption_ref="assumption:X:E17",
        status=status,
        diagnostic_refs=("diag:basis",),
    )


@pytest.mark.parametrize("status", [CheckStatus.OK, CheckStatus.OUT_OF_SCOPE])
def test_check_result_nonfinding_statuses_return_none(status: CheckStatus) -> None:
    assert build_finding_from_check_result(instance_id=_instance(), result=_result(status)) is None


@pytest.mark.parametrize("status", [CheckStatus.FAIL, CheckStatus.WARNING, CheckStatus.NO_DATA, CheckStatus.BLOCKED])
def test_check_result_adverse_statuses_project_exact_source_status(status: CheckStatus) -> None:
    finding = build_finding_from_check_result(
        instance_id=_instance(),
        result=_result(status),
        evidence_refs=("evidence:explicit",),
        provenance_refs=("provenance:finding",),
    )
    assert finding is not None
    assert finding.source_kind is FindingSourceKind.CHECK_RESULT
    assert finding.source_status is status
    assert finding.rule_instance_ref == _instance()
    assert finding.evidence_refs == ("evidence:explicit",)
    assert finding.messages == ("source-message",)


def test_check_result_builder_observes_status_only_not_numeric_fields() -> None:
    assert build_finding_from_check_result(instance_id=_instance(), result=_result(CheckStatus.FAIL)) is not None
    assert build_finding_from_check_result(instance_id=_instance(), result=_result(CheckStatus.OK)) is None


@pytest.mark.parametrize(
    "status,creates",
    [
        (ClosureExecutionStatus.EXECUTED, False),
        (ClosureExecutionStatus.PROVEN_NOT_APPLICABLE, False),
        (ClosureExecutionStatus.NOT_EXECUTED, True),
        (ClosureExecutionStatus.BLOCKED, True),
        (ClosureExecutionStatus.NO_DATA, True),
        (ClosureExecutionStatus.MISSING, True),
        (ClosureExecutionStatus.DUPLICATE, True),
        (ClosureExecutionStatus.INVALID, True),
    ],
)
def test_rule_closure_matrix_preserves_exact_status(status: ClosureExecutionStatus, creates: bool) -> None:
    record, outcome = _closure(status)
    finding = build_finding_from_rule_closure(compiled_record=record, outcome=outcome)
    assert (finding is not None) is creates
    if finding is not None:
        assert finding.source_kind is FindingSourceKind.RULE_CLOSURE
        assert finding.source_status is status
        assert finding.code_refs == record.code_refs
        assert finding.regulatory_quantity_keys == outcome.regulatory_quantity_refs
        assert finding.diagnostic_refs == outcome.diagnostic_refs


def test_rule_closure_builder_rejects_mismatched_identity() -> None:
    record, outcome = _closure(ClosureExecutionStatus.BLOCKED)
    wrong = RuleClosureOutcome(compiled_record_ref=_instance("OTHER"), execution_status=ClosureExecutionStatus.BLOCKED)
    with pytest.raises(ValueError, match="must match"):
        build_finding_from_rule_closure(compiled_record=record, outcome=wrong)


@pytest.mark.parametrize(
    "status,creates",
    [
        (AnalysisBasisStatus.MATCH, False),
        (AnalysisBasisStatus.REANALYSIS_REQUIRED, True),
        (AnalysisBasisStatus.UNRESOLVED, True),
        (AnalysisBasisStatus.INVALID, True),
    ],
)
def test_analysis_basis_matrix_preserves_exact_status(status: AnalysisBasisStatus, creates: bool) -> None:
    compatibility = _compat(status)
    finding = build_finding_from_analysis_basis(compatibility=compatibility)
    assert (finding is not None) is creates
    if finding is not None:
        assert finding.source_kind is FindingSourceKind.ANALYSIS_BASIS_COMPATIBILITY
        assert finding.source_status is status
        assert finding.rule_instance_ref is None
        assert finding.diagnostic_refs == compatibility.diagnostic_refs


def test_finding_identity_is_content_bound_deterministic_and_immutable() -> None:
    first = build_finding_from_check_result(instance_id=_instance(), result=_result(CheckStatus.FAIL), provenance_refs=("p:1",))
    second = build_finding_from_check_result(instance_id=_instance(), result=_result(CheckStatus.FAIL), provenance_refs=("p:1",))
    changed = build_finding_from_check_result(instance_id=_instance(), result=_result(CheckStatus.FAIL), provenance_refs=("p:2",))
    assert first == second
    assert first is not None and changed is not None
    assert first.finding_id == second.finding_id
    assert changed.finding_id != first.finding_id
    with pytest.raises(ValueError, match="canonical stored semantic fields"):
        replace(first, finding_id="finding:" + "0" * 64)
    with pytest.raises(ValueError, match="canonical stored semantic fields"):
        replace(first, source_ref="check-result:changed")
    with pytest.raises(FrozenInstanceError):
        first.scope_ref = "OTHER"  # type: ignore[misc]


def test_finding_rejects_source_kind_status_type_mismatch() -> None:
    instance = _instance()
    base = dict(
        finding_id="finding:" + "0" * 64,
        source_ref="source",
        scope_ref="C1",
        direction=None,
        rule_instance_ref=instance,
    )
    with pytest.raises(TypeError, match="CheckStatus"):
        Finding(source_kind=FindingSourceKind.CHECK_RESULT, source_status=ClosureExecutionStatus.BLOCKED, **base)
    with pytest.raises(TypeError, match="ClosureExecutionStatus"):
        Finding(source_kind=FindingSourceKind.RULE_CLOSURE, source_status=CheckStatus.FAIL, **base)
    with pytest.raises(TypeError, match="AnalysisBasisStatus"):
        Finding(source_kind=FindingSourceKind.ANALYSIS_BASIS_COMPATIBILITY, source_status=CheckStatus.BLOCKED, **base)


def test_finding_has_no_verdict_remediation_or_framework_escape_hatch() -> None:
    names = {item.name.casefold() for item in fields(Finding)}
    forbidden = {
        "finding_status",
        "finding_verdict",
        "severity",
        "remediation_class",
        "fix",
        "suggested_fix",
        "mutation",
        "action",
        "approved",
        "reanalysis_required",
        "redesign_required",
        "metadata",
        "payload",
        "full_tbdy_compliance_status",
    }
    assert forbidden.isdisjoint(names)

    import tbdy_engine.findings.builder as builder_module
    import tbdy_engine.findings.contracts as contracts_module
    source = Path(builder_module.__file__).read_text(encoding="utf-8") + Path(contracts_module.__file__).read_text(encoding="utf-8")
    for token in (
        "tbdy_engine.etabs",
        "etabs_gateway",
        "product_reports",
        "checks.engine",
        "MinimalCheckEngine",
        "member_geometry",
        "result_evidence",
        "contracts.runtime_catalog",
        "contracts.migrator",
        "FindingEngine",
        "FindingAggregator",
        "SeverityEngine",
    ):
        assert token not in source


def test_direct_check_result_finding_requires_rule_instance_ref() -> None:
    with pytest.raises(ValueError, match="requires rule_instance_ref"):
        Finding(
            finding_id="finding:" + "0" * 64,
            source_kind=FindingSourceKind.CHECK_RESULT,
            source_ref="check-result:missing-instance",
            source_status=CheckStatus.FAIL,
            scope_ref="C1",
            direction=None,
            rule_instance_ref=None,
        )


def test_direct_check_result_finding_rejects_scope_mismatch() -> None:
    instance = _instance()
    with pytest.raises(ValueError, match="scope_ref must match"):
        Finding(
            finding_id="finding:" + "0" * 64,
            source_kind=FindingSourceKind.CHECK_RESULT,
            source_ref=f"check-result:{instance.value}",
            source_status=CheckStatus.FAIL,
            scope_ref="OTHER",
            direction=instance.direction,
            rule_instance_ref=instance,
        )


def test_direct_check_result_finding_rejects_direction_mismatch() -> None:
    instance = _directional_instance(direction="X")
    with pytest.raises(ValueError, match="direction must match"):
        Finding(
            finding_id="finding:" + "0" * 64,
            source_kind=FindingSourceKind.CHECK_RESULT,
            source_ref=f"check-result:{instance.value}",
            source_status=CheckStatus.FAIL,
            scope_ref=instance.scope_ref,
            direction="Y",
            rule_instance_ref=instance,
        )


def test_direct_check_result_finding_rejects_wrong_source_ref() -> None:
    instance = _instance()
    with pytest.raises(ValueError, match="source_ref"):
        Finding(
            finding_id="finding:" + "0" * 64,
            source_kind=FindingSourceKind.CHECK_RESULT,
            source_ref=f"rule-closure:{instance.value}",
            source_status=CheckStatus.FAIL,
            scope_ref=instance.scope_ref,
            direction=instance.direction,
            rule_instance_ref=instance,
        )


def test_direct_rule_closure_finding_rejects_scope_mismatch() -> None:
    instance = _instance("TEST_CLOSURE")
    with pytest.raises(ValueError, match="scope_ref must match"):
        Finding(
            finding_id="finding:" + "0" * 64,
            source_kind=FindingSourceKind.RULE_CLOSURE,
            source_ref=f"rule-closure:{instance.value}",
            source_status=ClosureExecutionStatus.BLOCKED,
            scope_ref="OTHER",
            direction=instance.direction,
            rule_instance_ref=instance,
        )


def test_direct_rule_closure_finding_rejects_wrong_source_ref() -> None:
    instance = _instance("TEST_CLOSURE")
    with pytest.raises(ValueError, match="source_ref"):
        Finding(
            finding_id="finding:" + "0" * 64,
            source_kind=FindingSourceKind.RULE_CLOSURE,
            source_ref=f"check-result:{instance.value}",
            source_status=ClosureExecutionStatus.BLOCKED,
            scope_ref=instance.scope_ref,
            direction=instance.direction,
            rule_instance_ref=instance,
        )


def test_direct_analysis_basis_finding_rejects_rule_instance_ref() -> None:
    instance = _instance()
    with pytest.raises(ValueError, match="rule_instance_ref=None"):
        Finding(
            finding_id="finding:" + "0" * 64,
            source_kind=FindingSourceKind.ANALYSIS_BASIS_COMPATIBILITY,
            source_ref="analysis-basis-compatibility:compat:X",
            source_status=AnalysisBasisStatus.INVALID,
            scope_ref="SUPERSTRUCTURE",
            direction="X",
            rule_instance_ref=instance,
        )


def test_direct_analysis_basis_finding_requires_direction() -> None:
    with pytest.raises(ValueError, match="requires direction"):
        Finding(
            finding_id="finding:" + "0" * 64,
            source_kind=FindingSourceKind.ANALYSIS_BASIS_COMPATIBILITY,
            source_ref="analysis-basis-compatibility:compat:X",
            source_status=AnalysisBasisStatus.INVALID,
            scope_ref="SUPERSTRUCTURE",
            direction=None,
            rule_instance_ref=None,
        )


def test_direct_analysis_basis_finding_rejects_wrong_source_ref_prefix() -> None:
    with pytest.raises(ValueError, match="analysis-basis-compatibility"):
        Finding(
            finding_id="finding:" + "0" * 64,
            source_kind=FindingSourceKind.ANALYSIS_BASIS_COMPATIBILITY,
            source_ref="compatibility:compat:X",
            source_status=AnalysisBasisStatus.INVALID,
            scope_ref="SUPERSTRUCTURE",
            direction="X",
            rule_instance_ref=None,
        )


def test_direct_analysis_basis_finding_rejects_blank_source_ref_suffix() -> None:
    with pytest.raises(ValueError, match="analysis_basis_compatibility_id"):
        Finding(
            finding_id="finding:" + "0" * 64,
            source_kind=FindingSourceKind.ANALYSIS_BASIS_COMPATIBILITY,
            source_ref="analysis-basis-compatibility:",
            source_status=AnalysisBasisStatus.INVALID,
            scope_ref="SUPERSTRUCTURE",
            direction="X",
            rule_instance_ref=None,
        )


def test_all_three_existing_builders_create_source_coherent_findings() -> None:
    check_instance = _instance()
    check_finding = build_finding_from_check_result(
        instance_id=check_instance,
        result=_result(CheckStatus.FAIL),
    )
    record, outcome = _closure(ClosureExecutionStatus.BLOCKED)
    closure_finding = build_finding_from_rule_closure(
        compiled_record=record,
        outcome=outcome,
    )
    compatibility = _compat(AnalysisBasisStatus.REANALYSIS_REQUIRED)
    basis_finding = build_finding_from_analysis_basis(compatibility=compatibility)

    assert check_finding is not None
    assert check_finding.source_ref == f"check-result:{check_instance.value}"
    assert check_finding.scope_ref == check_instance.scope_ref
    assert check_finding.direction == check_instance.direction
    assert check_finding.rule_instance_ref == check_instance

    assert closure_finding is not None
    assert closure_finding.source_ref == f"rule-closure:{record.instance_id.value}"
    assert closure_finding.scope_ref == record.instance_id.scope_ref
    assert closure_finding.direction == record.instance_id.direction
    assert closure_finding.rule_instance_ref == record.instance_id

    assert basis_finding is not None
    assert basis_finding.source_ref == (
        f"analysis-basis-compatibility:{compatibility.compatibility_id}"
    )
    assert basis_finding.scope_ref == compatibility.structural_zone_ref
    assert basis_finding.direction == compatibility.direction
    assert basis_finding.rule_instance_ref is None


def test_direct_check_result_finding_rejects_ok_status() -> None:
    instance = _instance()
    with pytest.raises(ValueError, match="not Finding-eligible"):
        Finding(
            finding_id="finding:" + "0" * 64,
            source_kind=FindingSourceKind.CHECK_RESULT,
            source_ref=f"check-result:{instance.value}",
            source_status=CheckStatus.OK,
            scope_ref=instance.scope_ref,
            direction=instance.direction,
            rule_instance_ref=instance,
        )


def test_direct_check_result_finding_rejects_out_of_scope_status() -> None:
    instance = _instance()
    with pytest.raises(ValueError, match="not Finding-eligible"):
        Finding(
            finding_id="finding:" + "0" * 64,
            source_kind=FindingSourceKind.CHECK_RESULT,
            source_ref=f"check-result:{instance.value}",
            source_status=CheckStatus.OUT_OF_SCOPE,
            scope_ref=instance.scope_ref,
            direction=instance.direction,
            rule_instance_ref=instance,
        )


def test_direct_rule_closure_finding_rejects_executed_status() -> None:
    instance = _instance("TEST_CLOSURE")
    with pytest.raises(ValueError, match="not Finding-eligible"):
        Finding(
            finding_id="finding:" + "0" * 64,
            source_kind=FindingSourceKind.RULE_CLOSURE,
            source_ref=f"rule-closure:{instance.value}",
            source_status=ClosureExecutionStatus.EXECUTED,
            scope_ref=instance.scope_ref,
            direction=instance.direction,
            rule_instance_ref=instance,
        )


def test_direct_rule_closure_finding_rejects_proven_not_applicable_status() -> None:
    instance = _instance("TEST_CLOSURE")
    with pytest.raises(ValueError, match="not Finding-eligible"):
        Finding(
            finding_id="finding:" + "0" * 64,
            source_kind=FindingSourceKind.RULE_CLOSURE,
            source_ref=f"rule-closure:{instance.value}",
            source_status=ClosureExecutionStatus.PROVEN_NOT_APPLICABLE,
            scope_ref=instance.scope_ref,
            direction=instance.direction,
            rule_instance_ref=instance,
        )


def test_direct_analysis_basis_finding_rejects_match_status() -> None:
    compatibility = _compat(AnalysisBasisStatus.MATCH)
    with pytest.raises(ValueError, match="not Finding-eligible"):
        Finding(
            finding_id="finding:" + "0" * 64,
            source_kind=FindingSourceKind.ANALYSIS_BASIS_COMPATIBILITY,
            source_ref=f"analysis-basis-compatibility:{compatibility.compatibility_id}",
            source_status=AnalysisBasisStatus.MATCH,
            scope_ref=compatibility.structural_zone_ref,
            direction=compatibility.direction,
            rule_instance_ref=None,
        )


def test_replace_valid_findings_rejects_noneligible_status_before_identity_check() -> None:
    check_finding = build_finding_from_check_result(
        instance_id=_instance(),
        result=_result(CheckStatus.FAIL),
    )
    record, outcome = _closure(ClosureExecutionStatus.BLOCKED)
    closure_finding = build_finding_from_rule_closure(
        compiled_record=record,
        outcome=outcome,
    )
    basis_finding = build_finding_from_analysis_basis(
        compatibility=_compat(AnalysisBasisStatus.REANALYSIS_REQUIRED),
    )
    assert check_finding is not None
    assert closure_finding is not None
    assert basis_finding is not None

    for finding, noneligible_status in (
        (check_finding, CheckStatus.OK),
        (closure_finding, ClosureExecutionStatus.EXECUTED),
        (basis_finding, AnalysisBasisStatus.MATCH),
    ):
        with pytest.raises(ValueError, match="not Finding-eligible"):
            replace(finding, source_status=noneligible_status)
