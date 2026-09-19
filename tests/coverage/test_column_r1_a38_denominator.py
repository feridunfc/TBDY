from __future__ import annotations

from dataclasses import fields
from types import SimpleNamespace

import pytest

from tbdy_engine.application.contracts import (
    ColumnExecutionRequest,
    ProjectExecutionRequest,
)
from tbdy_engine.application.project_execution import ProjectExecutionArtifact
from tbdy_engine.checks.result import CheckResult, CheckStatus
from tbdy_engine.coverage.column_denominator import (
    ColumnDenominatorError,
    ColumnDenominatorLeafIdentity,
    ColumnExpectedLeaf,
    ColumnLeafApplicability,
    ColumnLeafOutcome,
    ColumnLeafOutcomeStatus,
    SupportedColumnDenominator,
    canonical_column_leaf_source_ref,
    compose_supported_column_denominator,
)


def _check(check_id: str, status: CheckStatus, *, direction: str | None = None):
    evidence = [
        "A36:SOURCE",
        "LOCAL_SHEAR_DIRECTION:V2" if direction == "V2" else "LOCAL_SHEAR_DIRECTION:V3",
        "CSI_ETABS_GET_REBAR_COLUMN_LOCAL_TIE_LEGS:Number2DirTieBars->V2|Number3DirTieBars->V3",
    ]
    if direction is not None:
        evidence.append(f"QUALIFIED_VC:{direction}:100kN")
    return CheckResult(
        check_id=check_id,
        component="C1",
        component_type="COLUMN",
        status=status,
        evidence=tuple(evidence),
        code_ref="TEST",
    )


def _shear_direction(direction: str, status: CheckStatus = CheckStatus.OK):
    return SimpleNamespace(
        direction=direction,
        tbdy_brittle_result=_check(
            f"P7_BRITTLE_{direction}",
            status,
            direction=direction,
        ),
        ts500_web_result=_check(
            f"P7_WEB_{direction}",
            CheckStatus.OK,
            direction=direction,
        ),
        source_refs=(f"P7:{direction}",),
    )


def _column(
    component_id: str = "C1",
    *,
    model: str = "model:sha256:111",
    epoch: str = "epoch:1",
    v2_status: CheckStatus = CheckStatus.OK,
    v3_status: CheckStatus = CheckStatus.OK,
    readiness_status: str = "READY",
    include_downstream: bool = True,
):
    minimum = SimpleNamespace(
        status="OK",
        source_refs=("MIN_ECC",),
    )
    basis = SimpleNamespace(
        status="PROVEN_TS500_SLENDERNESS_BASIS",
        source_refs=("SWAY", "LOCAL_AXES", "END_RESTRAINT", "LK", "M1_M2"),
    )
    slenderness = SimpleNamespace(
        status="OK",
        source_refs=("SLENDERNESS",),
    )
    readiness = SimpleNamespace(
        status=readiness_status,
        analysis_basis_status=(
            "REANALYSIS_REQUIRED"
            if readiness_status == "REANALYSIS_REQUIRED"
            else "MATCH"
        ),
        second_order_treatment=(
            "GENERAL_SECOND_ORDER_ANALYSIS_REQUIRED"
            if readiness_status == "REANALYSIS_REQUIRED"
            else "MOMENT_MAGNIFICATION_APPLIED"
        ),
        stability_sway_status="NONSWAY",
        minimum_eccentricity=minimum,
        slenderness_basis=basis,
        slenderness=slenderness,
        state_slenderness=(),
        moment_magnification_results=(),
        demand_states=(SimpleNamespace(source_identity="A23:STATE:1"),),
        blocked_items=(
            ("A22:REANALYSIS",)
            if readiness_status == "REANALYSIS_REQUIRED"
            else ()
        ),
        source_refs=("FND2:READINESS",),
    )
    execution = SimpleNamespace(readiness=readiness)
    binding = SimpleNamespace(
        readiness_ref="fnd-col-2:C1",
        provenance_refs=("FND2:PLAN",),
    )

    if not include_downstream:
        return SimpleNamespace(
            component_id=component_id,
            model_fingerprint=model,
            evidence_epoch_id=epoch,
            status=readiness_status,
            blockers=(),
            fnd_col_2_execution=execution,
            readiness_binding=binding,
            design_state=None,
            controlled_design_result=None,
            layout_authority=None,
            longitudinal_selection=None,
            longitudinal_runtime=None,
            transverse_confinement=None,
            column_shear_p7=None,
            column_shear_limited=None,
            a23_demand_states=tuple(readiness.demand_states),
        )

    design_state = SimpleNamespace(
        identity_ref=f"design-state:{component_id}",
        parent_analysis_result_ref=f"analysis-result:{component_id}",
        provenance_refs=("DESIGN_STATE:PROOF",),
    )
    design_lineage = SimpleNamespace(
        qualified=True,
        qualification_ref=f"design-lineage:{component_id}",
        provenance_refs=("DESIGN_LINEAGE:PROOF",),
    )
    design_result = SimpleNamespace(
        identity_ref=f"design-result:{component_id}",
        provenance_refs=("DESIGN_RESULT:PROOF",),
    )
    controlled = SimpleNamespace(
        design_state=design_state,
        design_result_identity=design_result,
        design_lineage=design_lineage,
        design_attempt_ref=f"design-attempt:{component_id}",
        design_generation_ref=f"design-generation:{component_id}",
        provenance_refs=("B6:PROOF",),
    )

    requirement = SimpleNamespace(
        source_refs=("FND1:REQUIREMENT",),
        authority_binding_ref="FND1:BINDING",
    )
    layout = SimpleNamespace(
        requirement=requirement,
        status="PROVEN",
        source_refs=("FND1:LAYOUT",),
        authority_binding_ref="FND1:LAYOUT:BINDING",
    )
    adequacy = SimpleNamespace(
        complete=True,
        unresolved_candidate_count=0,
        adequate_candidate_count=1,
        candidate_assessments=(
            SimpleNamespace(
                pmm_decision_ids=("PMM:1", "PMM:2"),
                source_refs=("ADEQUACY:1",),
            ),
        ),
        source_refs=("ADEQUACY:POPULATION",),
    )
    contract = SimpleNamespace(
        etabs_requirement_ids=("ETABS_REQUIRED_REBAR:1",),
        source_refs=("SELECTION_CONTRACT",),
    )
    selected_rebar = SimpleNamespace(
        selected_rebar_ref=f"engine-selected-rebar:{component_id}",
        candidate_adequacy_ref="ADEQUACY:1",
        provenance_refs=("SELECTED:PROOF",),
    )
    selection = SimpleNamespace(
        selected=True,
        status="SELECTED",
        blockers=(),
        selection_contract=contract,
        adequacy_population=adequacy,
        selected_rebar=selected_rebar,
        provenance_refs=("SELECTION:PROOF",),
    )
    detailing = SimpleNamespace(
        status="FINAL_DETAILING_REQUIRED",
        unresolved_items=("ANCHORAGE",),
        source_refs=("A35:DETAILING",),
    )
    bound_basis = SimpleNamespace(
        high_ductility_applies=True,
        limited_ductility_applies=False,
        binding_ref="DESIGN_BASIS:BINDING",
        source_refs=("DESIGN_BASIS:SOURCE",),
    )
    combo = SimpleNamespace(
        reconciled=True,
        source_refs=("COMBO:RECONCILED",),
    )
    runtime = SimpleNamespace(
        bound_design_basis=bound_basis,
        combo_reconciliation=combo,
        layout_authority=layout,
        selection=selection,
        detailing=detailing,
    )

    v2_final = _check(
        "COL_FINAL_SHEAR_VR_DIR2",
        v2_status,
        direction="V2",
    )
    v3_final = _check(
        "COL_FINAL_SHEAR_VR_DIR3",
        v3_status,
        direction="V3",
    )
    transverse = SimpleNamespace(
        checks=(v2_final, v3_final),
        blockers=(),
        source_refs=("VS5:TBDY", "VS5:TS500", "A36:SOURCE"),
    )
    p7 = SimpleNamespace(
        component_id=component_id,
        directions=(
            _shear_direction("V2"),
            _shear_direction("V3"),
        ),
    )

    return SimpleNamespace(
        component_id=component_id,
        model_fingerprint=model,
        evidence_epoch_id=epoch,
        status="SELECTED",
        blockers=(),
        fnd_col_2_execution=execution,
        readiness_binding=binding,
        design_state=design_state,
        controlled_design_result=controlled,
        design_result_identity=design_result,
        design_lineage=design_lineage,
        layout_authority=layout,
        longitudinal_selection=selection,
        longitudinal_runtime=runtime,
        transverse_confinement=transverse,
        column_shear_p7=p7,
        column_shear_limited=None,
        a23_demand_states=tuple(readiness.demand_states),
    )


def _short(component_id: str = "C1", applies: bool = False):
    return SimpleNamespace(
        component_id=component_id,
        short_column_applies=applies,
        review_refs=("REVIEW:SHORT",),
    )


def test_complete_expected_denominator_is_deterministic_and_has_exact_accounting():
    column = _column()
    first = compose_supported_column_denominator(
        (column,),
        short_column_contexts=(_short(),),
    )
    second = compose_supported_column_denominator(
        (column,),
        short_column_contexts=(_short(),),
    )

    assert first.to_json() == second.to_json()
    assert first.expected_column_count == 1
    assert first.expected_instance_count == len(first.outcomes)
    assert first.expected_leaf_count > 40
    assert first.silent_missing_count == 0
    assert first.duplicate_count == 0
    assert first.orphan_count == 0
    assert first.population_reconciled is True

    keys = {item.identity.leaf_key for item in first.expected_leaves}
    assert {
        "COLUMN_IDENTITY_TOPOLOGY",
        "TBDY_AXIAL",
        "TS500_AXIAL",
        "FND_COL_2_READINESS",
        "B6_CONTROLLED_DESIGN",
        "ETABS_REQUIRED_REBAR",
        "PMM_SECTION_CAPACITY",
        "ENGINE_SELECTED_REBAR",
        "TRANSVERSE_CONFINEMENT",
        "P7_OR_LIMITED_FINAL_SHEAR",
        "VC",
        "ASW_D_MAPPING",
        "VE_LE_VR",
        "SCWB",
        "BEAM_COLUMN_JOINT",
    }.issubset(keys)


def test_pass_and_fail_are_distinct_executed_outcomes_not_missing():
    denominator = compose_supported_column_denominator(
        (_column(v2_status=CheckStatus.FAIL, v3_status=CheckStatus.OK),),
        short_column_contexts=(_short(),),
    )
    assert (
        denominator.outcome("C1", "VE_LE_VR", "V2").status
        is ColumnLeafOutcomeStatus.EXECUTED_FAIL
    )
    assert (
        denominator.outcome("C1", "VE_LE_VR", "V3").status
        is ColumnLeafOutcomeStatus.EXECUTED_PASS
    )
    assert denominator.silent_missing_count == 0


def test_short_column_pna_requires_positive_ordinary_proof():
    ordinary = compose_supported_column_denominator(
        (_column(),),
        short_column_contexts=(_short(applies=False),),
    )
    leaf = ordinary.outcome("C1", "SHORT_COLUMN_SHEAR", "V2")
    assert leaf.status is ColumnLeafOutcomeStatus.PROVEN_NOT_APPLICABLE

    unresolved = compose_supported_column_denominator((_column(),))
    leaf = unresolved.outcome("C1", "SHORT_COLUMN_SHEAR", "V2")
    assert leaf.status is ColumnLeafOutcomeStatus.EXPLICIT_UNRESOLVED
    expected = next(
        item
        for item in unresolved.expected_leaves
        if item.identity.value == leaf.identity.value
    )
    assert expected.applicability is ColumnLeafApplicability.CONDITIONAL


def test_short_column_true_executes_existing_short_p7_identity():
    denominator = compose_supported_column_denominator(
        (_column(),),
        short_column_contexts=(_short(applies=True),),
    )
    assert (
        denominator.outcome("C1", "SHORT_COLUMN_SHEAR", "V2").status
        is ColumnLeafOutcomeStatus.EXECUTED_PASS
    )


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (CheckStatus.BLOCKED, ColumnLeafOutcomeStatus.BLOCKED),
        (CheckStatus.NO_DATA, ColumnLeafOutcomeStatus.NO_DATA),
    ],
)
def test_blocked_and_no_data_remain_distinct(status, expected):
    denominator = compose_supported_column_denominator(
        (_column(v2_status=status),),
        short_column_contexts=(_short(),),
    )
    assert denominator.outcome("C1", "VE_LE_VR", "V2").status is expected


def test_reanalysis_required_is_preserved_not_collapsed_to_blocked():
    denominator = compose_supported_column_denominator(
        (
            _column(
                readiness_status="REANALYSIS_REQUIRED",
                include_downstream=False,
            ),
        ),
        short_column_contexts=(_short(),),
    )
    assert (
        denominator.outcome(
            "C1",
            "MOMENT_MAGNIFICATION_OR_REANALYSIS",
        ).status
        is ColumnLeafOutcomeStatus.REANALYSIS_REQUIRED
    )
    assert (
        denominator.outcome("C1", "FND_COL_2_READINESS").status
        is ColumnLeafOutcomeStatus.REANALYSIS_REQUIRED
    )


def test_cross_domain_leaves_are_explicit_deferred_not_pass():
    denominator = compose_supported_column_denominator(
        (_column(),),
        short_column_contexts=(_short(),),
    )
    for key in ("SCWB", "BEAM_COLUMN_JOINT"):
        outcome = denominator.outcome("C1", key)
        assert outcome.status is ColumnLeafOutcomeStatus.EXPLICIT_UNRESOLVED
        assert outcome.deferred_owner
        assert outcome.dependency_refs


def test_multiple_columns_have_independent_exact_identities():
    left = _column("C1", model="model:A", epoch="epoch:A")
    right = _column("C2", model="model:A", epoch="epoch:A")
    denominator = compose_supported_column_denominator(
        (right, left),
        short_column_contexts=(_short("C2"), _short("C1")),
    )
    assert denominator.expected_column_count == 2
    assert denominator.expected_instance_count == 2 * denominator.expected_leaf_count
    c1 = denominator.outcome("C1", "ENGINE_SELECTED_REBAR")
    c2 = denominator.outcome("C2", "ENGINE_SELECTED_REBAR")
    assert c1.identity.value != c2.identity.value


def test_duplicate_missing_and_orphan_populations_are_rejected_before_fcr():
    denominator = compose_supported_column_denominator(
        (_column(),),
        short_column_contexts=(_short(),),
    )

    with pytest.raises(ColumnDenominatorError, match="duplicate runtime"):
        SupportedColumnDenominator(
            denominator.expected_leaves,
            (*denominator.outcomes, denominator.outcomes[0]),
        )

    with pytest.raises(ColumnDenominatorError, match="silent missing"):
        SupportedColumnDenominator(
            denominator.expected_leaves,
            denominator.outcomes[:-1],
        )

    identity = ColumnDenominatorLeafIdentity.build(
        component_id="C1",
        leaf_key="ORPHAN",
        model_fingerprint="model:sha256:111",
        evidence_epoch_id="epoch:1",
    )
    orphan = ColumnLeafOutcome(
        identity=identity,
        status=ColumnLeafOutcomeStatus.BLOCKED,
        source_ref=canonical_column_leaf_source_ref(identity),
        blocker_refs=("ORPHAN",),
    )
    with pytest.raises(ColumnDenominatorError, match="orphan"):
        SupportedColumnDenominator(
            denominator.expected_leaves,
            (*denominator.outcomes, orphan),
        )


def test_fnd2_only_cannot_masquerade_as_full_resolved_column_product():
    denominator = compose_supported_column_denominator(
        (_column(include_downstream=False),),
        short_column_contexts=(_short(),),
    )
    assert denominator.expected_leaf_count > 40
    assert denominator.population_reconciled is True
    assert denominator.fully_resolved is False
    assert (
        denominator.outcome("C1", "ENGINE_SELECTED_REBAR").status
        is ColumnLeafOutcomeStatus.BLOCKED
    )
    assert (
        denominator.outcome("C1", "TRANSVERSE_CONFINEMENT").status
        is ColumnLeafOutcomeStatus.BLOCKED
    )


def test_denominator_truth_is_not_in_request_dtos_and_project_artifact_has_projection():
    forbidden = {
        "denominator_pass",
        "expected_check_results",
        "column_denominator",
        "fcr_results",
        "report_status",
    }
    assert forbidden.isdisjoint(
        {item.name for item in fields(ColumnExecutionRequest)}
    )
    assert forbidden.isdisjoint(
        {item.name for item in fields(ProjectExecutionRequest)}
    )
    assert "column_denominator" in {
        item.name for item in fields(ProjectExecutionArtifact)
    }

def test_a38_runtime_outcome_vocabulary_is_exactly_the_canonical_seven():
    assert {item.value for item in ColumnLeafOutcomeStatus} == {
        "EXECUTED/PASS",
        "EXECUTED/FAIL",
        "PROVEN_NOT_APPLICABLE",
        "BLOCKED",
        "NO_DATA",
        "EXPLICIT_UNRESOLVED",
        "REANALYSIS_REQUIRED",
    }


def test_cross_domain_deferral_is_metadata_on_explicit_unresolved():
    denominator = compose_supported_column_denominator(
        (_column(),),
        short_column_contexts=(_short(),),
    )
    outcome = denominator.outcome("C1", "SCWB")
    assert outcome.status is ColumnLeafOutcomeStatus.EXPLICIT_UNRESOLVED
    assert outcome.deferred_owner == "BEAM_DOMAIN"
    assert outcome.dependency_refs == ("CANONICAL_BEAM_CAPACITY_AUTHORITY",)
