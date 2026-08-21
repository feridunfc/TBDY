from __future__ import annotations

from dataclasses import FrozenInstanceError, fields, replace
from pathlib import Path

import pytest

from tbdy_engine.analysis_basis.basis_report import build_analysis_basis_report, build_analysis_basis_report_row
from tbdy_engine.analysis_basis.contracts import (
    AnalysisBasisCompatibility,
    AnalysisSystemAssumption,
    ReviewedDirectionalSystemDeclaration,
    build_analysis_basis_snapshot,
)
from tbdy_engine.features.evidence_epoch import EvidenceEpoch, EvidenceEpochOrigin
from tbdy_engine.findings import Finding, build_finding_from_analysis_basis
from tbdy_engine.regulatory.kernel import AnalysisBasisStatus
from tbdy_engine.remediation import RemediationClass, RemediationPlan, build_remediation_plan


ZONE = "SUPERSTRUCTURE"


def _compat(direction: str, status: AnalysisBasisStatus) -> AnalysisBasisCompatibility:
    return AnalysisBasisCompatibility(
        compatibility_id=f"compatibility:{direction}:{status.value}",
        epoch_ref="epoch:E17",
        structural_zone_ref=ZONE,
        direction=direction,
        required_basis_ref=f"policy:{direction}",
        analysis_assumption_ref=f"assumption:{direction}:E17",
        status=status,
        diagnostic_refs=(f"diag:{direction}",),
    )


def _finding(direction: str = "Y", status: AnalysisBasisStatus = AnalysisBasisStatus.REANALYSIS_REQUIRED) -> Finding:
    finding = build_finding_from_analysis_basis(
        compatibility=_compat(direction, status),
        provenance_refs=(f"finding-provenance:{direction}",),
    )
    assert finding is not None
    return finding


def test_remediation_enum_is_exactly_bounded() -> None:
    assert {item.value for item in RemediationClass} == {
        "NO_MUTATION_REQUIRED",
        "DETERMINISTIC_FIX_AVAILABLE",
        "USER_ACTION_REQUIRED",
        "ENGINEERING_DECISION_REQUIRED",
        "ENGINEERING_REDESIGN_REQUIRED",
        "UNSUPPORTED_AUTOMATION",
    }


@pytest.mark.parametrize(
    "classification,authorization,reanalysis,redesign",
    [
        (RemediationClass.NO_MUTATION_REQUIRED, False, False, False),
        (RemediationClass.NO_MUTATION_REQUIRED, False, True, False),
        (RemediationClass.DETERMINISTIC_FIX_AVAILABLE, True, True, False),
        (RemediationClass.USER_ACTION_REQUIRED, False, True, False),
        (RemediationClass.ENGINEERING_DECISION_REQUIRED, False, False, False),
        (RemediationClass.ENGINEERING_REDESIGN_REQUIRED, False, False, True),
        (RemediationClass.UNSUPPORTED_AUTOMATION, False, False, False),
    ],
)
def test_valid_explicit_remediation_matrix(
    classification: RemediationClass,
    authorization: bool,
    reanalysis: bool,
    redesign: bool,
) -> None:
    plan = build_remediation_plan(
        findings=(_finding(),),
        remediation_class=classification,
        proposed_action_refs=("action:user-review-required",),
        user_authorization_required=authorization,
        reanalysis_required=reanalysis,
        redesign_required=redesign,
    )
    assert plan.remediation_class is classification
    assert plan.user_authorization_required is authorization
    assert plan.reanalysis_required is reanalysis
    assert plan.redesign_required is redesign


@pytest.mark.parametrize(
    "classification,authorization,redesign,match",
    [
        (RemediationClass.DETERMINISTIC_FIX_AVAILABLE, False, False, "explicit user authorization"),
        (RemediationClass.NO_MUTATION_REQUIRED, True, False, "user_authorization_required=False"),
        (RemediationClass.ENGINEERING_REDESIGN_REQUIRED, False, False, "redesign_required=True"),
    ],
)
def test_required_lifecycle_invariants_reject_invalid_combinations(
    classification: RemediationClass,
    authorization: bool,
    redesign: bool,
    match: str,
) -> None:
    with pytest.raises(ValueError, match=match):
        build_remediation_plan(
            findings=(_finding(),),
            remediation_class=classification,
            user_authorization_required=authorization,
            reanalysis_required=False,
            redesign_required=redesign,
        )


def test_builder_requires_canonical_nonduplicate_findings() -> None:
    finding = _finding()
    with pytest.raises(ValueError, match="at least one"):
        build_remediation_plan(
            findings=(),
            remediation_class=RemediationClass.USER_ACTION_REQUIRED,
            user_authorization_required=False,
            reanalysis_required=False,
            redesign_required=False,
        )
    with pytest.raises(ValueError, match="duplicate finding"):
        build_remediation_plan(
            findings=(finding, finding),
            remediation_class=RemediationClass.USER_ACTION_REQUIRED,
            user_authorization_required=False,
            reanalysis_required=False,
            redesign_required=False,
        )
    with pytest.raises(TypeError, match="Finding"):
        build_remediation_plan(
            findings=(object(),),  # type: ignore[arg-type]
            remediation_class=RemediationClass.USER_ACTION_REQUIRED,
            user_authorization_required=False,
            reanalysis_required=False,
            redesign_required=False,
        )


def test_remediation_identity_is_deterministic_sorted_content_bound_and_immutable() -> None:
    first_finding = _finding("X", AnalysisBasisStatus.UNRESOLVED)
    second_finding = _finding("Y", AnalysisBasisStatus.REANALYSIS_REQUIRED)
    kwargs = dict(
        remediation_class=RemediationClass.USER_ACTION_REQUIRED,
        proposed_action_refs=("action:user-review-required",),
        user_authorization_required=False,
        reanalysis_required=True,
        redesign_required=False,
        provenance_refs=("plan:provenance",),
    )
    first = build_remediation_plan(findings=(first_finding, second_finding), **kwargs)
    reversed_plan = build_remediation_plan(findings=(second_finding, first_finding), **kwargs)
    assert first == reversed_plan
    assert first.finding_refs == tuple(sorted(first.finding_refs))

    changed_class = build_remediation_plan(
        findings=(first_finding, second_finding),
        **{**kwargs, "remediation_class": RemediationClass.ENGINEERING_DECISION_REQUIRED},
    )
    changed_reanalysis = build_remediation_plan(
        findings=(first_finding, second_finding),
        **{**kwargs, "reanalysis_required": False},
    )
    assert changed_class.plan_id != first.plan_id
    assert changed_reanalysis.plan_id != first.plan_id
    with pytest.raises(ValueError, match="canonical stored semantic fields"):
        replace(first, plan_id="remediation-plan:" + "0" * 64)
    with pytest.raises(FrozenInstanceError):
        first.reanalysis_required = False  # type: ignore[misc]


def test_end_to_end_neutral_basis_report_finding_and_explicit_plan_do_not_mutate_sources() -> None:
    epoch = EvidenceEpoch(
        epoch_id="E17",
        model_fingerprint="fixture:model",
        origin=EvidenceEpochOrigin.FIXTURE_REPLAY,
        source_fingerprint="fixture:source",
        provenance_refs=("fixture:capture",),
    )
    source_before = epoch.as_dict()
    rows = []
    compatibilities = {}
    for direction, status in (("X", AnalysisBasisStatus.MATCH), ("Y", AnalysisBasisStatus.REANALYSIS_REQUIRED)):
        declaration = ReviewedDirectionalSystemDeclaration(
            declaration_id=f"declaration:{direction}",
            structural_zone_ref=ZONE,
            direction=direction,
            declared_basis_ref=f"declared:{direction}",
        )
        assumption = AnalysisSystemAssumption(
            assumption_id=f"assumption:{direction}:E17",
            epoch_ref="epoch:E17",
            structural_zone_ref=ZONE,
            direction=direction,
            observed_basis_ref=f"observed:{direction}",
        )
        compatibility = _compat(direction, status)
        compatibilities[direction] = compatibility
        snapshot = build_analysis_basis_snapshot(
            epoch=epoch,
            declaration=declaration,
            resolved_policy_ref=f"policy:{direction}",
            assumption=assumption,
            compatibility=compatibility,
        )
        rows.append(build_analysis_basis_report_row(snapshot=snapshot, compatibility=compatibility))

    report = build_analysis_basis_report(rows=tuple(reversed(rows)))
    assert [(row.direction, row.compatibility_status) for row in report.rows] == [
        ("X", AnalysisBasisStatus.MATCH),
        ("Y", AnalysisBasisStatus.REANALYSIS_REQUIRED),
    ]
    assert build_finding_from_analysis_basis(compatibility=compatibilities["X"]) is None
    y_finding = build_finding_from_analysis_basis(compatibility=compatibilities["Y"])
    assert y_finding is not None
    plan = build_remediation_plan(
        findings=(y_finding,),
        remediation_class=RemediationClass.USER_ACTION_REQUIRED,
        proposed_action_refs=("action:user-review-required",),
        user_authorization_required=False,
        reanalysis_required=True,
        redesign_required=False,
    )
    assert plan.reanalysis_required is True
    assert epoch.as_dict() == source_before


def test_remediation_contract_has_no_execution_or_regulatory_verdict_surface() -> None:
    names = {item.name.casefold() for item in fields(RemediationPlan)}
    forbidden = {
        "pass", "fail", "status", "check_status", "compatibility_status", "ratio", "capacity",
        "callable", "function", "handler", "api_method", "etabs_method", "arguments", "payload",
        "patch", "script", "approved", "executed", "mutation",
    }
    assert forbidden.isdisjoint(names)

    import tbdy_engine.remediation.contracts as module
    source = Path(module.__file__).read_text(encoding="utf-8")
    for token in (
        "RegulatoryCompiler",
        "RegulatoryEngine",
        "tbdy_engine.etabs",
        "etabs_gateway",
        "MutationExecutor",
        "MutationJournal",
        "execute_plan",
        "apply_remediation",
        "rerun_analysis",
        "reacquire_model",
    ):
        assert token not in source
