from __future__ import annotations

from dataclasses import FrozenInstanceError, fields, replace
from pathlib import Path

import pytest

from tbdy_engine.analysis_basis import (
    AnalysisBasisCompatibility,
    AnalysisBasisResolutionError,
    AnalysisBasisSnapshot,
    AnalysisSystemAssumption,
    ReviewedDirectionalSystemDeclaration,
    RuleAnalysisBasisRequirement,
    build_analysis_basis_snapshot,
    resolve_rule_targets_for_analysis_basis,
)
from tbdy_engine.features.evidence_epoch import EvidenceEpoch, EvidenceEpochOrigin
from tbdy_engine.regulatory.contracts import Grain, RuleId, RuleInstanceId
from tbdy_engine.regulatory.kernel import AnalysisBasisStatus, RuleScopeTarget


ZONE = "SUPERSTRUCTURE"
RULE = RuleId("TEST_F0_5_RULE")


def _epoch(epoch_id: str = "E17") -> EvidenceEpoch:
    return EvidenceEpoch(
        epoch_id=epoch_id,
        model_fingerprint="fixture:model",
        origin=EvidenceEpochOrigin.FIXTURE_REPLAY,
        source_fingerprint="fixture:source",
        provenance_refs=("fixture:capture",),
    )


def _declaration(direction: str = "X") -> ReviewedDirectionalSystemDeclaration:
    return ReviewedDirectionalSystemDeclaration(
        declaration_id=f"fixture:declaration:{direction}",
        structural_zone_ref=ZONE,
        direction=direction,
        declared_basis_ref=f"fixture:declared:{direction}",
        provenance_refs=(f"fixture:review:{direction}",),
    )


def _assumption(direction: str = "X", epoch_id: str = "E17") -> AnalysisSystemAssumption:
    return AnalysisSystemAssumption(
        assumption_id=f"fixture:assumption:{direction}:{epoch_id}",
        epoch_ref=f"epoch:{epoch_id}",
        structural_zone_ref=ZONE,
        direction=direction,
        observed_basis_ref=f"fixture:observed:{direction}",
        analysis_evidence_refs=(f"fixture:analysis-evidence:{direction}",),
        provenance_refs=(f"fixture:assumption-provenance:{direction}",),
    )


def _compatibility(
    direction: str = "X",
    *,
    epoch_id: str = "E17",
    status: AnalysisBasisStatus = AnalysisBasisStatus.MATCH,
    compatibility_id: str | None = None,
    zone: str = ZONE,
    required_basis_ref: str | None = None,
    assumption_ref: str | None = None,
) -> AnalysisBasisCompatibility:
    assumption = _assumption(direction, epoch_id)
    return AnalysisBasisCompatibility(
        compatibility_id=compatibility_id or f"fixture:compatibility:{direction}:{epoch_id}:{status.value}",
        epoch_ref=f"epoch:{epoch_id}",
        structural_zone_ref=zone,
        direction=direction,
        required_basis_ref=required_basis_ref or f"fixture:policy:{direction}",
        analysis_assumption_ref=assumption_ref or assumption.assumption_id,
        status=status,
        diagnostic_refs=(f"fixture:diagnostic:{direction}",),
        provenance_refs=(f"fixture:compatibility-provenance:{direction}",),
    )


def _target(direction: str = "X") -> RuleScopeTarget:
    return RuleScopeTarget(
        rule_id=RULE,
        grain=Grain.DIRECTION,
        scope_ref=ZONE,
        direction=direction,
        applicability_input=True,
    )


def _requirement(target: RuleScopeTarget, compatibility_ref: str) -> RuleAnalysisBasisRequirement:
    return RuleAnalysisBasisRequirement(
        rule_instance_id=target.instance_id,
        structural_zone_ref=ZONE,
        direction=target.direction or "",
        compatibility_ref=compatibility_ref,
    )


def test_reviewed_declaration_is_immutable_directional_and_opaque() -> None:
    declaration = _declaration()
    assert declaration.structural_zone_ref == ZONE
    assert declaration.direction == "X"
    assert declaration.declared_basis_ref == "fixture:declared:X"
    assert declaration.provenance_refs == ("fixture:review:X",)
    with pytest.raises(FrozenInstanceError):
        declaration.direction = "Y"  # type: ignore[misc]
    with pytest.raises(TypeError, match="tuple"):
        ReviewedDirectionalSystemDeclaration(
            declaration_id="d",
            structural_zone_ref=ZONE,
            direction="X",
            declared_basis_ref="basis",
            provenance_refs=["not", "tuple"],  # type: ignore[arg-type]
        )


def test_analysis_assumption_is_epoch_bound_and_has_no_compatibility_decision() -> None:
    assumption = _assumption()
    assert assumption.epoch_ref == "epoch:E17"
    assert assumption.analysis_evidence_refs == ("fixture:analysis-evidence:X",)
    assert assumption.provenance_refs == ("fixture:assumption-provenance:X",)
    assert "status" not in assumption.__dataclass_fields__
    assert "compatibility_status" not in assumption.__dataclass_fields__
    with pytest.raises(FrozenInstanceError):
        assumption.epoch_ref = "epoch:E18"  # type: ignore[misc]


def test_compatibility_reuses_existing_analysis_basis_status_exactly() -> None:
    compatibility = _compatibility(status=AnalysisBasisStatus.REANALYSIS_REQUIRED)
    assert compatibility.status is AnalysisBasisStatus.REANALYSIS_REQUIRED
    assert type(compatibility.status) is AnalysisBasisStatus
    with pytest.raises(TypeError, match="canonical AnalysisBasisStatus"):
        AnalysisBasisCompatibility(
            compatibility_id="c",
            epoch_ref="epoch:E17",
            structural_zone_ref=ZONE,
            direction="X",
            required_basis_ref="policy",
            analysis_assumption_ref="assumption",
            status="MATCH",  # type: ignore[arg-type]
        )


def test_snapshot_is_join_only_immutable_and_forbidden_fields_are_absent() -> None:
    snapshot = build_analysis_basis_snapshot(
        epoch=_epoch(),
        declaration=_declaration(),
        resolved_policy_ref="fixture:policy:X",
        assumption=_assumption(),
        compatibility=_compatibility(),
        analysis_evidence_refs=("fixture:analysis-evidence:X",),
        provenance_refs=("fixture:snapshot-provenance",),
    )
    assert snapshot.snapshot_id.startswith("analysis-basis-snapshot:")
    assert snapshot.epoch_ref == "epoch:E17"
    assert snapshot.compatibility_ref.startswith("fixture:compatibility:X")
    with pytest.raises(FrozenInstanceError):
        snapshot.direction = "Y"  # type: ignore[misc]

    forbidden = {
        "r",
        "r_declared",
        "r_resolved",
        "d",
        "d_declared",
        "d_resolved",
        "dts",
        "bys",
        "bks",
        "system_class",
        "compatibility_status",
        "reanalysis_required",
    }
    actual = {item.name.casefold() for item in fields(AnalysisBasisSnapshot)}
    assert forbidden.isdisjoint(actual)


def test_snapshot_identity_is_deterministic_and_changes_only_with_join_inputs() -> None:
    kwargs = dict(
        epoch=_epoch(),
        declaration=_declaration(),
        resolved_policy_ref="fixture:policy:X",
        assumption=_assumption(),
        compatibility=_compatibility(compatibility_id="fixture:compatibility:X:v1"),
        analysis_evidence_refs=("fixture:analysis-evidence:X",),
        provenance_refs=("fixture:snapshot-provenance",),
    )
    first = build_analysis_basis_snapshot(**kwargs)
    second = build_analysis_basis_snapshot(**kwargs)
    assert first == second
    assert first.snapshot_id == second.snapshot_id

    changed_compatibility = build_analysis_basis_snapshot(
        **{**kwargs, "compatibility": _compatibility(compatibility_id="fixture:compatibility:X:v2")}
    )
    assert changed_compatibility.snapshot_id != first.snapshot_id

    changed_epoch = build_analysis_basis_snapshot(
        epoch=_epoch("E18"),
        declaration=_declaration(),
        resolved_policy_ref="fixture:policy:X",
        assumption=_assumption(epoch_id="E18"),
        compatibility=_compatibility(epoch_id="E18", compatibility_id="fixture:compatibility:X:E18"),
        analysis_evidence_refs=("fixture:analysis-evidence:X",),
        provenance_refs=("fixture:snapshot-provenance",),
    )
    assert changed_epoch.snapshot_id != first.snapshot_id


def test_snapshot_direct_construction_rejects_format_valid_unrelated_digest() -> None:
    snapshot = build_analysis_basis_snapshot(
        epoch=_epoch(),
        declaration=_declaration(),
        resolved_policy_ref="fixture:policy:X",
        assumption=_assumption(),
        compatibility=_compatibility(compatibility_id="fixture:compatibility:X:integrity"),
        analysis_evidence_refs=("fixture:analysis-evidence:X",),
        provenance_refs=("fixture:snapshot-provenance",),
    )
    with pytest.raises(ValueError, match="canonical stored join fields"):
        AnalysisBasisSnapshot(
            snapshot_id="analysis-basis-snapshot:" + "0" * 64,
            epoch_ref=snapshot.epoch_ref,
            structural_zone_ref=snapshot.structural_zone_ref,
            direction=snapshot.direction,
            reviewed_declaration_ref=snapshot.reviewed_declaration_ref,
            resolved_policy_ref=snapshot.resolved_policy_ref,
            analysis_assumption_ref=snapshot.analysis_assumption_ref,
            compatibility_ref=snapshot.compatibility_ref,
            analysis_evidence_refs=snapshot.analysis_evidence_refs,
            provenance_refs=snapshot.provenance_refs,
        )


@pytest.mark.parametrize(
    "field_name,new_value",
    [
        ("epoch_ref", "epoch:E18"),
        ("structural_zone_ref", "OTHER_ZONE"),
        ("direction", "Y"),
        ("reviewed_declaration_ref", "fixture:declaration:changed"),
        ("resolved_policy_ref", "fixture:policy:changed"),
        ("analysis_assumption_ref", "fixture:assumption:changed"),
        ("compatibility_ref", "fixture:compatibility:changed"),
        ("analysis_evidence_refs", ("fixture:analysis-evidence:changed",)),
        ("provenance_refs", ("fixture:snapshot-provenance:changed",)),
    ],
)
def test_snapshot_rejects_changed_identity_field_with_old_id(field_name: str, new_value: object) -> None:
    snapshot = build_analysis_basis_snapshot(
        epoch=_epoch(),
        declaration=_declaration(),
        resolved_policy_ref="fixture:policy:X",
        assumption=_assumption(),
        compatibility=_compatibility(compatibility_id="fixture:compatibility:X:integrity"),
        analysis_evidence_refs=("fixture:analysis-evidence:X",),
        provenance_refs=("fixture:snapshot-provenance",),
    )
    with pytest.raises(ValueError, match="canonical stored join fields"):
        replace(snapshot, **{field_name: new_value})


def test_snapshot_tuple_order_is_stable_and_identity_bearing() -> None:
    kwargs = dict(
        epoch=_epoch(),
        declaration=_declaration(),
        resolved_policy_ref="fixture:policy:X",
        assumption=_assumption(),
        compatibility=_compatibility(compatibility_id="fixture:compatibility:X:ordering"),
    )
    first = build_analysis_basis_snapshot(
        **kwargs,
        analysis_evidence_refs=("fixture:evidence:1", "fixture:evidence:2"),
        provenance_refs=("fixture:provenance:1", "fixture:provenance:2"),
    )
    same = build_analysis_basis_snapshot(
        **kwargs,
        analysis_evidence_refs=("fixture:evidence:1", "fixture:evidence:2"),
        provenance_refs=("fixture:provenance:1", "fixture:provenance:2"),
    )
    reversed_evidence = build_analysis_basis_snapshot(
        **kwargs,
        analysis_evidence_refs=("fixture:evidence:2", "fixture:evidence:1"),
        provenance_refs=("fixture:provenance:1", "fixture:provenance:2"),
    )
    reversed_provenance = build_analysis_basis_snapshot(
        **kwargs,
        analysis_evidence_refs=("fixture:evidence:1", "fixture:evidence:2"),
        provenance_refs=("fixture:provenance:2", "fixture:provenance:1"),
    )
    assert first.snapshot_id == same.snapshot_id
    assert first.analysis_evidence_refs == ("fixture:evidence:1", "fixture:evidence:2")
    assert first.provenance_refs == ("fixture:provenance:1", "fixture:provenance:2")
    assert reversed_evidence.snapshot_id != first.snapshot_id
    assert reversed_provenance.snapshot_id != first.snapshot_id


@pytest.mark.parametrize(
    "mutator,match",
    [
        ("assumption_epoch", "assumption epoch"),
        ("compatibility_epoch", "compatibility epoch"),
        ("zone", "structural_zone_ref mismatch"),
        ("direction", "direction mismatch"),
        ("assumption_ref", "analysis_assumption_ref"),
        ("required_policy", "required_basis_ref"),
    ],
)
def test_snapshot_builder_rejects_structural_incoherence(mutator: str, match: str) -> None:
    epoch = _epoch()
    declaration = _declaration()
    assumption = _assumption()
    compatibility = _compatibility()
    policy = "fixture:policy:X"

    if mutator == "assumption_epoch":
        assumption = _assumption(epoch_id="E18")
    elif mutator == "compatibility_epoch":
        compatibility = _compatibility(epoch_id="E18")
    elif mutator == "zone":
        compatibility = _compatibility(zone="OTHER_ZONE")
    elif mutator == "direction":
        compatibility = AnalysisBasisCompatibility(
            compatibility_id="fixture:compatibility:Y",
            epoch_ref="epoch:E17",
            structural_zone_ref=ZONE,
            direction="Y",
            required_basis_ref=policy,
            analysis_assumption_ref=assumption.assumption_id,
            status=AnalysisBasisStatus.MATCH,
        )
    elif mutator == "assumption_ref":
        compatibility = _compatibility(assumption_ref="fixture:other-assumption")
    elif mutator == "required_policy":
        policy = "fixture:other-policy"

    with pytest.raises(ValueError, match=match):
        build_analysis_basis_snapshot(
            epoch=epoch,
            declaration=declaration,
            resolved_policy_ref=policy,
            assumption=assumption,
            compatibility=compatibility,
        )


def test_snapshot_builder_preserves_inputs_and_contracts_reject_noncanonical_refs() -> None:
    epoch = _epoch()
    declaration = _declaration()
    assumption = _assumption()
    compatibility = _compatibility()
    before = (
        epoch.as_dict(),
        declaration,
        assumption,
        compatibility,
    )
    build_analysis_basis_snapshot(
        epoch=epoch,
        declaration=declaration,
        resolved_policy_ref="fixture:policy:X",
        assumption=assumption,
        compatibility=compatibility,
        analysis_evidence_refs=("fixture:analysis-evidence:X",),
        provenance_refs=("fixture:snapshot-provenance",),
    )
    assert epoch.as_dict() == before[0]
    assert declaration == before[1]
    assert assumption == before[2]
    assert compatibility == before[3]

    with pytest.raises(ValueError, match="direction"):
        ReviewedDirectionalSystemDeclaration(
            declaration_id="fixture:declaration",
            structural_zone_ref=ZONE,
            direction=" ",
            declared_basis_ref="fixture:declared",
        )
    with pytest.raises(ValueError, match="epoch_ref"):
        AnalysisSystemAssumption(
            assumption_id="fixture:assumption",
            epoch_ref="E17",
            structural_zone_ref=ZONE,
            direction="X",
            observed_basis_ref="fixture:observed",
        )
    with pytest.raises(ValueError, match="required_basis_ref"):
        AnalysisBasisCompatibility(
            compatibility_id="fixture:compatibility",
            epoch_ref="epoch:E17",
            structural_zone_ref=ZONE,
            direction="X",
            required_basis_ref=" ",
            analysis_assumption_ref="fixture:assumption",
            status=AnalysisBasisStatus.MATCH,
        )


def test_requirement_is_exact_rule_instance_binding_and_validates_scope_direction() -> None:
    target = _target("X")
    requirement = _requirement(target, "fixture:compatibility:X")
    assert requirement.rule_instance_id == target.instance_id
    assert requirement.direction == "X"
    wrong_direction = RuleInstanceId.build(
        rule_id=RULE,
        grain=Grain.DIRECTION,
        scope_ref=ZONE,
        direction="Y",
    )
    with pytest.raises(ValueError, match="direction"):
        RuleAnalysisBasisRequirement(
            rule_instance_id=wrong_direction,
            structural_zone_ref=ZONE,
            direction="X",
            compatibility_ref="fixture:compatibility:X",
        )


def test_resolver_maps_match_reanalysis_missing_stale_and_invalid_without_mutating_inputs() -> None:
    x = _target("X")
    y = _target("Y")
    x_comp = _compatibility("X", status=AnalysisBasisStatus.MATCH)
    y_comp = _compatibility("Y", status=AnalysisBasisStatus.REANALYSIS_REQUIRED)
    requirements = (
        _requirement(x, x_comp.compatibility_id),
        _requirement(y, y_comp.compatibility_id),
    )
    before_targets = (x, y)
    resolved = resolve_rule_targets_for_analysis_basis(
        epoch=_epoch(),
        rule_targets=tuple(reversed(before_targets)),
        requirements=tuple(reversed(requirements)),
        compatibilities=(y_comp, x_comp),
    )
    by_direction = {item.direction: item for item in resolved}
    assert by_direction["X"].analysis_basis_status is AnalysisBasisStatus.MATCH
    assert by_direction["Y"].analysis_basis_status is AnalysisBasisStatus.REANALYSIS_REQUIRED
    assert before_targets[0].analysis_basis_status is AnalysisBasisStatus.MATCH
    assert before_targets[1].analysis_basis_status is AnalysisBasisStatus.MATCH
    assert resolved == tuple(sorted(resolved, key=lambda item: item.sort_key))

    missing = resolve_rule_targets_for_analysis_basis(
        epoch=_epoch(),
        rule_targets=(x,),
        requirements=(_requirement(x, "fixture:missing"),),
        compatibilities=(),
    )
    assert missing[0].analysis_basis_status is AnalysisBasisStatus.UNRESOLVED

    stale = resolve_rule_targets_for_analysis_basis(
        epoch=_epoch("E18"),
        rule_targets=(x, y),
        requirements=(_requirement(x, x_comp.compatibility_id),),
        compatibilities=(x_comp,),
    )
    stale_by_direction = {item.direction: item for item in stale}
    assert stale_by_direction["X"].analysis_basis_status is AnalysisBasisStatus.UNRESOLVED
    assert stale_by_direction["Y"].analysis_basis_status is AnalysisBasisStatus.MATCH

    invalid_comp = _compatibility("X", status=AnalysisBasisStatus.INVALID)
    invalid = resolve_rule_targets_for_analysis_basis(
        epoch=_epoch(),
        rule_targets=(x,),
        requirements=(_requirement(x, invalid_comp.compatibility_id),),
        compatibilities=(invalid_comp,),
    )
    assert invalid[0].analysis_basis_status is AnalysisBasisStatus.INVALID


def test_resolver_rejects_double_owned_unknown_duplicate_and_mismatched_inputs() -> None:
    x = _target("X")
    x_comp = _compatibility("X")
    req = _requirement(x, x_comp.compatibility_id)

    pre_resolved = RuleScopeTarget(
        rule_id=x.rule_id,
        grain=x.grain,
        scope_ref=x.scope_ref,
        direction=x.direction,
        applicability_input=x.applicability_input,
        analysis_basis_status=AnalysisBasisStatus.UNRESOLVED,
    )
    with pytest.raises(AnalysisBasisResolutionError, match="double-owned"):
        resolve_rule_targets_for_analysis_basis(
            epoch=_epoch(),
            rule_targets=(pre_resolved,),
            requirements=(),
            compatibilities=(),
        )

    unknown_target = _target("Y")
    unknown_req = _requirement(unknown_target, "fixture:compatibility:Y")
    with pytest.raises(AnalysisBasisResolutionError, match="unknown target"):
        resolve_rule_targets_for_analysis_basis(
            epoch=_epoch(),
            rule_targets=(x,),
            requirements=(unknown_req,),
            compatibilities=(),
        )

    with pytest.raises(AnalysisBasisResolutionError, match="duplicate analysis-basis requirement"):
        resolve_rule_targets_for_analysis_basis(
            epoch=_epoch(),
            rule_targets=(x,),
            requirements=(req, req),
            compatibilities=(x_comp,),
        )

    duplicate_comp = AnalysisBasisCompatibility(
        compatibility_id=x_comp.compatibility_id,
        epoch_ref=x_comp.epoch_ref,
        structural_zone_ref=x_comp.structural_zone_ref,
        direction=x_comp.direction,
        required_basis_ref=x_comp.required_basis_ref,
        analysis_assumption_ref=x_comp.analysis_assumption_ref,
        status=AnalysisBasisStatus.INVALID,
    )
    with pytest.raises(AnalysisBasisResolutionError, match="duplicate compatibility_id"):
        resolve_rule_targets_for_analysis_basis(
            epoch=_epoch(),
            rule_targets=(x,),
            requirements=(req,),
            compatibilities=(x_comp, duplicate_comp),
        )

    wrong_zone = _compatibility(
        "X",
        compatibility_id=x_comp.compatibility_id,
        zone="OTHER_ZONE",
    )
    with pytest.raises(AnalysisBasisResolutionError, match="structural_zone_ref mismatch"):
        resolve_rule_targets_for_analysis_basis(
            epoch=_epoch(),
            rule_targets=(x,),
            requirements=(req,),
            compatibilities=(wrong_zone,),
        )

    wrong_direction = AnalysisBasisCompatibility(
        compatibility_id=x_comp.compatibility_id,
        epoch_ref="epoch:E17",
        structural_zone_ref=ZONE,
        direction="Y",
        required_basis_ref="fixture:policy:Y",
        analysis_assumption_ref="fixture:assumption:Y:E17",
        status=AnalysisBasisStatus.MATCH,
    )
    with pytest.raises(AnalysisBasisResolutionError, match="direction mismatch"):
        resolve_rule_targets_for_analysis_basis(
            epoch=_epoch(),
            rule_targets=(x,),
            requirements=(req,),
            compatibilities=(wrong_direction,),
        )


def test_production_analysis_basis_modules_have_no_forbidden_architecture_imports_or_rc_fields() -> None:
    import tbdy_engine.analysis_basis.contracts as contracts_module
    import tbdy_engine.analysis_basis.resolver as resolver_module

    sources = (
        Path(contracts_module.__file__).read_text(encoding="utf-8"),
        Path(resolver_module.__file__).read_text(encoding="utf-8"),
    )
    forbidden_import_tokens = (
        "tbdy_engine.etabs",
        "etabs_gateway",
        "product_reports",
        "checks.engine",
        "MinimalCheckEngine",
        "member_geometry",
        "result_evidence",
        "contracts.runtime_catalog",
        "contracts.migrator",
    )
    for source in sources:
        for token in forbidden_import_tokens:
            assert token not in source

    forbidden_fields = {
        "r",
        "r_declared",
        "r_resolved",
        "r_analysed",
        "d",
        "d_declared",
        "d_resolved",
        "d_analysed",
        "i",
        "dts",
        "bys",
        "bks",
        "system_class",
        "compatibility_status",
        "reanalysis_required",
        "basis_invalid",
        "global_basis_status",
    }
    for cls in (
        ReviewedDirectionalSystemDeclaration,
        AnalysisSystemAssumption,
        AnalysisBasisCompatibility,
        AnalysisBasisSnapshot,
        RuleAnalysisBasisRequirement,
    ):
        actual = {item.name.casefold() for item in fields(cls)}
        assert forbidden_fields.isdisjoint(actual)
