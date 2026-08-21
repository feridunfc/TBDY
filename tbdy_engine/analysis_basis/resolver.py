"""Pure F0.5 kernel-front mapping from compatibility artifacts to existing target readiness."""
from __future__ import annotations

from dataclasses import replace
from typing import Sequence

from tbdy_engine.features.evidence_epoch import EvidenceEpoch
from tbdy_engine.regulatory.kernel import AnalysisBasisStatus, RuleScopeTarget

from .contracts import (
    AnalysisBasisCompatibility,
    RuleAnalysisBasisRequirement,
    evidence_epoch_ref,
)


class AnalysisBasisResolutionError(ValueError):
    """Fail-closed structural input error for F0.5 target preparation."""


def resolve_rule_targets_for_analysis_basis(
    *,
    epoch: EvidenceEpoch,
    rule_targets: Sequence[RuleScopeTarget],
    requirements: Sequence[RuleAnalysisBasisRequirement],
    compatibilities: Sequence[AnalysisBasisCompatibility],
) -> tuple[RuleScopeTarget, ...]:
    """Return deterministic immutable targets using the existing F0 analysis-basis status."""

    if not isinstance(epoch, EvidenceEpoch):
        raise TypeError("epoch must be EvidenceEpoch")
    targets = tuple(rule_targets)
    reqs = tuple(requirements)
    comps = tuple(compatibilities)
    if any(not isinstance(item, RuleScopeTarget) for item in targets):
        raise TypeError("rule_targets must contain RuleScopeTarget")
    if any(not isinstance(item, RuleAnalysisBasisRequirement) for item in reqs):
        raise TypeError("requirements must contain RuleAnalysisBasisRequirement")
    if any(not isinstance(item, AnalysisBasisCompatibility) for item in comps):
        raise TypeError("compatibilities must contain AnalysisBasisCompatibility")

    target_by_id = {}
    for target in targets:
        if target.analysis_basis_status is not AnalysisBasisStatus.MATCH:
            raise AnalysisBasisResolutionError(
                "incoming RuleScopeTarget must be pre-resolution MATCH to avoid double-owned basis status"
            )
        if target.instance_id in target_by_id:
            raise AnalysisBasisResolutionError(
                f"duplicate rule target: {target.instance_id.value}"
            )
        target_by_id[target.instance_id] = target

    requirement_by_id = {}
    for requirement in reqs:
        instance_id = requirement.rule_instance_id
        if instance_id in requirement_by_id:
            raise AnalysisBasisResolutionError(
                f"duplicate analysis-basis requirement: {instance_id.value}"
            )
        target = target_by_id.get(instance_id)
        if target is None:
            raise AnalysisBasisResolutionError(
                f"analysis-basis requirement references unknown target: {instance_id.value}"
            )
        if requirement.direction != target.direction:
            raise AnalysisBasisResolutionError(
                f"requirement direction mismatch for target: {instance_id.value}"
            )
        requirement_by_id[instance_id] = requirement

    compatibility_by_id = {}
    for compatibility in comps:
        if compatibility.compatibility_id in compatibility_by_id:
            raise AnalysisBasisResolutionError(
                f"duplicate compatibility_id: {compatibility.compatibility_id}"
            )
        compatibility_by_id[compatibility.compatibility_id] = compatibility

    current_epoch_ref = evidence_epoch_ref(epoch)
    resolved: list[RuleScopeTarget] = []
    for target in sorted(targets, key=lambda item: item.sort_key):
        requirement = requirement_by_id.get(target.instance_id)
        status = AnalysisBasisStatus.MATCH
        if requirement is not None:
            compatibility = compatibility_by_id.get(requirement.compatibility_ref)
            if compatibility is None:
                status = AnalysisBasisStatus.UNRESOLVED
            else:
                if compatibility.structural_zone_ref != requirement.structural_zone_ref:
                    raise AnalysisBasisResolutionError(
                        f"compatibility structural_zone_ref mismatch: {compatibility.compatibility_id}"
                    )
                if compatibility.direction != requirement.direction:
                    raise AnalysisBasisResolutionError(
                        f"compatibility direction mismatch: {compatibility.compatibility_id}"
                    )
                if compatibility.epoch_ref != current_epoch_ref:
                    status = AnalysisBasisStatus.UNRESOLVED
                else:
                    status = compatibility.status
        resolved.append(replace(target, analysis_basis_status=status))
    return tuple(resolved)


__all__ = [
    "AnalysisBasisResolutionError",
    "resolve_rule_targets_for_analysis_basis",
]
