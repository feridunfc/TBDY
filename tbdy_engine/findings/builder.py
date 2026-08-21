"""Explicit pure Finding projections for F0.6."""
from __future__ import annotations

from tbdy_engine.analysis_basis.contracts import AnalysisBasisCompatibility
from tbdy_engine.checks.result import CheckResult, CheckStatus
from tbdy_engine.regulatory.contracts import (
    ClosureExecutionStatus,
    CompiledClosureRecord,
    RuleClosureOutcome,
    RuleInstanceId,
)
from tbdy_engine.regulatory.kernel import AnalysisBasisStatus

from .contracts import Finding, FindingSourceKind, _finding_identity


def _refs(values: tuple[str, ...], label: str) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise TypeError(f"{label} must be a tuple of strings")
    if any(not isinstance(item, str) for item in values):
        raise TypeError(f"{label} must contain strings only")
    for item in values:
        if not item.strip() or item != item.strip():
            raise ValueError(f"{label} must contain nonblank canonical strings")
    return tuple(values)


def _finding(
    *,
    source_kind: FindingSourceKind,
    source_ref: str,
    source_status: CheckStatus | ClosureExecutionStatus | AnalysisBasisStatus,
    scope_ref: str,
    direction: str | None,
    rule_instance_ref: RuleInstanceId | None,
    code_refs=(),
    regulatory_quantity_keys=(),
    evidence_refs: tuple[str, ...] = (),
    diagnostic_refs=(),
    messages=(),
    provenance_refs: tuple[str, ...] = (),
) -> Finding:
    evidence_refs = _refs(evidence_refs, "evidence_refs")
    provenance_refs = _refs(provenance_refs, "provenance_refs")
    code_refs = tuple(code_refs)
    regulatory_quantity_keys = tuple(regulatory_quantity_keys)
    diagnostic_refs = tuple(diagnostic_refs)
    messages = tuple(messages)
    finding_id = _finding_identity(
        source_kind=source_kind,
        source_ref=source_ref,
        source_status=source_status,
        scope_ref=scope_ref,
        direction=direction,
        rule_instance_ref=rule_instance_ref,
        code_refs=code_refs,
        regulatory_quantity_keys=regulatory_quantity_keys,
        evidence_refs=evidence_refs,
        diagnostic_refs=diagnostic_refs,
        messages=messages,
        provenance_refs=provenance_refs,
    )
    return Finding(
        finding_id=finding_id,
        source_kind=source_kind,
        source_ref=source_ref,
        source_status=source_status,
        scope_ref=scope_ref,
        direction=direction,
        rule_instance_ref=rule_instance_ref,
        code_refs=code_refs,
        regulatory_quantity_keys=regulatory_quantity_keys,
        evidence_refs=evidence_refs,
        diagnostic_refs=diagnostic_refs,
        messages=messages,
        provenance_refs=provenance_refs,
    )


def build_finding_from_check_result(
    *,
    instance_id: RuleInstanceId,
    result: CheckResult,
    evidence_refs: tuple[str, ...] = (),
    provenance_refs: tuple[str, ...] = (),
) -> Finding | None:
    """Project an already-authoritative CheckStatus without re-evaluating engineering."""
    if not isinstance(instance_id, RuleInstanceId):
        raise TypeError("instance_id must be RuleInstanceId")
    if not isinstance(result, CheckResult):
        raise TypeError("result must be canonical CheckResult")
    if result.check_id != instance_id.rule_id.value:
        raise ValueError("CheckResult check_id must match supplied RuleInstanceId rule_id")
    if result.component != instance_id.scope_ref:
        raise ValueError("CheckResult component must match supplied RuleInstanceId scope_ref")
    if result.status in {CheckStatus.OK, CheckStatus.OUT_OF_SCOPE}:
        return None
    if result.status not in {CheckStatus.FAIL, CheckStatus.WARNING, CheckStatus.NO_DATA, CheckStatus.BLOCKED}:
        raise ValueError(f"unsupported canonical CheckStatus: {result.status}")
    return _finding(
        source_kind=FindingSourceKind.CHECK_RESULT,
        source_ref=f"check-result:{instance_id.value}",
        source_status=result.status,
        scope_ref=instance_id.scope_ref,
        direction=instance_id.direction,
        rule_instance_ref=instance_id,
        code_refs=() if not result.code_ref else (result.code_ref,),
        evidence_refs=evidence_refs,
        messages=tuple(result.messages),
        provenance_refs=provenance_refs,
    )


def build_finding_from_rule_closure(
    *,
    compiled_record: CompiledClosureRecord,
    outcome: RuleClosureOutcome,
    evidence_refs: tuple[str, ...] = (),
    provenance_refs: tuple[str, ...] = (),
) -> Finding | None:
    """Project an existing closure status without deriving closure reasons."""
    if not isinstance(compiled_record, CompiledClosureRecord):
        raise TypeError("compiled_record must be CompiledClosureRecord")
    if not isinstance(outcome, RuleClosureOutcome):
        raise TypeError("outcome must be RuleClosureOutcome")
    if compiled_record.instance_id != outcome.compiled_record_ref:
        raise ValueError("compiled_record.instance_id must match outcome.compiled_record_ref")
    if outcome.execution_status in {ClosureExecutionStatus.EXECUTED, ClosureExecutionStatus.PROVEN_NOT_APPLICABLE}:
        return None
    if outcome.execution_status not in {
        ClosureExecutionStatus.NOT_EXECUTED,
        ClosureExecutionStatus.BLOCKED,
        ClosureExecutionStatus.NO_DATA,
        ClosureExecutionStatus.MISSING,
        ClosureExecutionStatus.DUPLICATE,
        ClosureExecutionStatus.INVALID,
    }:
        raise ValueError(f"unsupported canonical ClosureExecutionStatus: {outcome.execution_status}")
    return _finding(
        source_kind=FindingSourceKind.RULE_CLOSURE,
        source_ref=f"rule-closure:{compiled_record.instance_id.value}",
        source_status=outcome.execution_status,
        scope_ref=compiled_record.scope_ref,
        direction=compiled_record.instance_id.direction,
        rule_instance_ref=compiled_record.instance_id,
        code_refs=compiled_record.code_refs,
        regulatory_quantity_keys=outcome.regulatory_quantity_refs,
        evidence_refs=evidence_refs,
        diagnostic_refs=outcome.diagnostic_refs,
        provenance_refs=provenance_refs,
    )


def build_finding_from_analysis_basis(
    *,
    compatibility: AnalysisBasisCompatibility,
    evidence_refs: tuple[str, ...] = (),
    provenance_refs: tuple[str, ...] = (),
) -> Finding | None:
    """Project an already-resolved analysis-basis status without calculating compatibility."""
    if not isinstance(compatibility, AnalysisBasisCompatibility):
        raise TypeError("compatibility must be AnalysisBasisCompatibility")
    if compatibility.status is AnalysisBasisStatus.MATCH:
        return None
    if compatibility.status not in {
        AnalysisBasisStatus.REANALYSIS_REQUIRED,
        AnalysisBasisStatus.UNRESOLVED,
        AnalysisBasisStatus.INVALID,
    }:
        raise ValueError(f"unsupported canonical AnalysisBasisStatus: {compatibility.status}")
    return _finding(
        source_kind=FindingSourceKind.ANALYSIS_BASIS_COMPATIBILITY,
        source_ref=f"analysis-basis-compatibility:{compatibility.compatibility_id}",
        source_status=compatibility.status,
        scope_ref=compatibility.structural_zone_ref,
        direction=compatibility.direction,
        rule_instance_ref=None,
        evidence_refs=evidence_refs,
        diagnostic_refs=compatibility.diagnostic_refs,
        provenance_refs=provenance_refs,
    )


__all__ = [
    "build_finding_from_check_result",
    "build_finding_from_rule_closure",
    "build_finding_from_analysis_basis",
]
