from __future__ import annotations

import inspect
import pytest

from tbdy_engine.checks.result import CheckStatus
from tbdy_engine.regulatory.contracts import ApplicabilityState, DependencySourceKind
from tbdy_engine.regulatory.kernel import AnalysisBasisStatus
from tbdy_engine.regulatory import structural_system as ss
from tbdy_engine.regulatory import vs4a_program as vs4a_program_module
from tbdy_engine.regulatory.vs4a_program import compile_vs4a_program, execute_vs4a_program


DECL_REVIEW = ("review:system-declaration",)
DECL_PROV = ("prov:system-declaration",)
ORTHO_REVIEW = ("review:orthogonal-system",)
ORTHO_PROV = ("prov:orthogonal-system",)
SEIS_REVIEW = ("review:dts-bys",)
SEIS_PROV = ("prov:dts-bys",)
ANALYSIS_EVIDENCE = ("analysis:reviewed-basis",)
A16_REVIEW = ("review:a16-roof-connection",)
A16_PROV = ("prov:a16-special-context",)


def _dir(direction: str, row: str) -> ss.ReviewedDirectionalRcSystemDeclaration:
    return ss.ReviewedDirectionalRcSystemDeclaration(
        direction=direction,
        table_4_1_row=row,
        review_refs=DECL_REVIEW,
        provenance_refs=DECL_PROV,
    )


def _declarations(row: str) -> ss.ReviewedOrthogonalRcSystemDeclaration:
    return ss.ReviewedOrthogonalRcSystemDeclaration(
        x=_dir("X", row),
        y=_dir("Y", row),
        review_refs=ORTHO_REVIEW,
        provenance_refs=ORTHO_PROV,
    )


def _seismic(dts: str, bys: int) -> ss.ReviewedSeismicClassificationContext:
    return ss.ReviewedSeismicClassificationContext(
        dts=dts,
        bys=bys,
        review_refs=SEIS_REVIEW,
        provenance_refs=SEIS_PROV,
    )


def _assumptions(row: str, *, x_r: float | None = None, x_d: float | None = None):
    policy = ss.table_4_1_policy(row)
    return (
        ss.DirectionalAnalysisSystemAssumption(
            direction="X",
            assumed_table_4_1_row=row,
            assumed_r=policy.r if x_r is None else x_r,
            assumed_d=policy.d if x_d is None else x_d,
            analysis_evidence_refs=ANALYSIS_EVIDENCE,
        ),
        ss.DirectionalAnalysisSystemAssumption(
            direction="Y",
            assumed_table_4_1_row=row,
            assumed_r=policy.r,
            assumed_d=policy.d,
            analysis_evidence_refs=ANALYSIS_EVIDENCE,
        ),
    )


def _a16_contexts(
    *,
    story_count: int = 1,
    height_m: float = 10.0,
    connection: ss.RoofConnectionCondition = ss.RoofConnectionCondition.PINNED,
):
    return tuple(
        ss.A16SpecialContext(
            direction=direction,
            story_count=story_count,
            building_height_m=height_m,
            roof_connection_condition=connection,
            roof_connection_review_refs=A16_REVIEW,
            provenance_refs=A16_PROV,
        )
        for direction in ("X", "Y")
    )


def _run(row: str, *, dts: str, bys: int, assumptions=None, a16_contexts=()):
    program = compile_vs4a_program(
        declarations=_declarations(row),
        seismic=_seismic(dts, bys),
        analysis_assumptions=_assumptions(row) if assumptions is None else assumptions,
        a16_contexts=a16_contexts,
    )
    return program, execute_vs4a_program(program)


def _quantity(snapshot, rule_id, direction="X"):
    return ss.directional_quantity(snapshot, rule_id, direction).value


def _formal(snapshot, rule_id, direction="X"):
    matches = tuple(
        record.result
        for record in snapshot.formal_results
        if record.instance_id.rule_id == rule_id and record.instance_id.direction == direction
    )
    assert len(matches) == 1
    return matches[0]


def test_shared_regulatory_quantities_drive_preeligibility_and_formal_checks():
    pre_keys = {dep.key for dep in ss.PREANALYSIS_ELIGIBILITY_SPEC.dependencies}
    assert pre_keys == {
        ss.BYS_ELIGIBILITY_STATE_KEY,
        ss.DTS_ELIGIBILITY_STATE_KEY,
        ss.A31_ELIGIBILITY_STATE_KEY,
        ss.A16_ELIGIBILITY_STATE_KEY,
    }
    assert all(
        dep.source_kind is DependencySourceKind.REGULATORY_QUANTITY
        for dep in ss.PREANALYSIS_ELIGIBILITY_SPEC.dependencies
    )
    for spec, key in (
        (ss.BYS_CHECK_SPEC, ss.BYS_ELIGIBILITY_STATE_KEY),
        (ss.DTS_CHECK_SPEC, ss.DTS_ELIGIBILITY_STATE_KEY),
        (ss.A31_CHECK_SPEC, ss.A31_ELIGIBILITY_STATE_KEY),
        (ss.A16_CHECK_SPEC, ss.A16_ELIGIBILITY_STATE_KEY),
    ):
        state_dep = next(dep for dep in spec.dependencies if dep.key == key)
        assert state_dep.source_kind is DependencySourceKind.REGULATORY_QUANTITY


def test_bys_fail_cannot_yield_resolved_policy_or_match_basis():
    _, snapshot = _run("A11", dts="3", bys=2)
    assert _quantity(snapshot, ss.RC_TABLE_4_1_BYS_ELIGIBILITY_STATE) == "INELIGIBLE"
    assert _formal(snapshot, ss.RC_TABLE_4_1_BYS_ELIGIBILITY).status is CheckStatus.FAIL
    assert _quantity(snapshot, ss.RC_PREANALYSIS_SYSTEM_ELIGIBILITY)["state"] == "INELIGIBLE"
    assert _quantity(snapshot, ss.RC_DIRECTIONAL_BASELINE_SYSTEM_POLICY)["resolution_state"] == "INVALID"
    assert _quantity(snapshot, ss.RC_ANALYSIS_BASIS_COMPATIBILITY) == AnalysisBasisStatus.INVALID.value


def test_dts_fail_cannot_yield_resolved_policy():
    _, snapshot = _run("A32", dts="1a", bys=8)
    assert _quantity(snapshot, ss.RC_TBDY_4_3_4_1_DTS_SYSTEM_ELIGIBILITY_STATE) == "INELIGIBLE"
    assert _formal(snapshot, ss.RC_TBDY_4_3_4_1_DTS_SYSTEM_ELIGIBILITY).status is CheckStatus.FAIL
    assert _quantity(snapshot, ss.RC_DIRECTIONAL_BASELINE_SYSTEM_POLICY)["resolution_state"] == "INVALID"
    assert _quantity(snapshot, ss.RC_ANALYSIS_BASIS_COMPATIBILITY) == AnalysisBasisStatus.INVALID.value


def test_a31_dts_fail_maps_to_invalid():
    _, snapshot = _run("A31", dts="2", bys=8)
    assert _quantity(snapshot, ss.RC_TBDY_4_3_4_3_A31_DTS_ELIGIBILITY_STATE) == "INELIGIBLE"
    assert _formal(snapshot, ss.RC_TBDY_4_3_4_3_A31_DTS_ELIGIBILITY).status is CheckStatus.FAIL
    assert _quantity(snapshot, ss.RC_ANALYSIS_BASIS_COMPATIBILITY) == AnalysisBasisStatus.INVALID.value


def test_a16_fail_maps_to_invalid():
    _, snapshot = _run(
        "A16",
        dts="3",
        bys=8,
        a16_contexts=_a16_contexts(story_count=2),
    )
    assert _quantity(snapshot, ss.RC_TABLE_4_1_A16_SPECIAL_ELIGIBILITY_STATE) == "INELIGIBLE"
    assert _formal(snapshot, ss.RC_TABLE_4_1_A16_SPECIAL_ELIGIBILITY).status is CheckStatus.FAIL
    assert _quantity(snapshot, ss.RC_DIRECTIONAL_BASELINE_SYSTEM_POLICY)["resolution_state"] == "INVALID"
    assert _quantity(snapshot, ss.RC_ANALYSIS_BASIS_COMPATIBILITY) == AnalysisBasisStatus.INVALID.value


def test_a16_unreviewed_maps_to_unresolved():
    _, snapshot = _run(
        "A16",
        dts="3",
        bys=8,
        a16_contexts=_a16_contexts(connection=ss.RoofConnectionCondition.UNREVIEWED),
    )
    assert _quantity(snapshot, ss.RC_TABLE_4_1_A16_SPECIAL_ELIGIBILITY_STATE) == "BLOCKED"
    assert _formal(snapshot, ss.RC_TABLE_4_1_A16_SPECIAL_ELIGIBILITY).status is CheckStatus.BLOCKED
    assert _quantity(snapshot, ss.RC_PREANALYSIS_SYSTEM_ELIGIBILITY)["state"] == "BLOCKED"
    assert _quantity(snapshot, ss.RC_DIRECTIONAL_BASELINE_SYSTEM_POLICY)["resolution_state"] == "UNRESOLVED"
    assert _quantity(snapshot, ss.RC_ANALYSIS_BASIS_COMPATIBILITY) == AnalysisBasisStatus.UNRESOLVED.value


def test_empty_reviewed_declaration_refs_rejected():
    with pytest.raises(ValueError, match="review_ref must contain at least one"):
        ss.ReviewedDirectionalRcSystemDeclaration(
            direction="X",
            table_4_1_row="A11",
            review_refs=(),
            provenance_refs=DECL_PROV,
        )


def test_empty_dts_bys_review_refs_rejected():
    with pytest.raises(ValueError, match="review_ref must contain at least one"):
        ss.ReviewedSeismicClassificationContext(
            dts="3",
            bys=8,
            review_refs=(),
            provenance_refs=SEIS_PROV,
        )


def test_empty_a16_roof_review_refs_rejected():
    with pytest.raises(ValueError, match="roof_connection_review_ref must contain at least one"):
        ss.A16SpecialContext(
            direction="X",
            story_count=1,
            building_height_m=10.0,
            roof_connection_condition=ss.RoofConnectionCondition.PINNED,
            roof_connection_review_refs=(),
            provenance_refs=A16_PROV,
        )


def test_baseline_matching_assumption_plus_eligibility_fail_is_not_match():
    assumptions = _assumptions("A11")
    _, snapshot = _run("A11", dts="3", bys=2, assumptions=assumptions)
    assert _quantity(snapshot, ss.RC_ANALYSIS_BASIS_COMPATIBILITY) != AnalysisBasisStatus.MATCH.value
    assert _quantity(snapshot, ss.RC_ANALYSIS_BASIS_COMPATIBILITY) == AnalysisBasisStatus.INVALID.value


def test_baseline_matching_assumption_plus_postqual_pending_is_unresolved():
    _, snapshot = _run("A14", dts="3", bys=8)
    baseline = _quantity(snapshot, ss.RC_DIRECTIONAL_BASELINE_SYSTEM_POLICY)
    assert baseline["preanalysis_eligibility"] == "ELIGIBLE"
    assert baseline["post_analysis_qualification_requirement"] == "REQUIRED"
    assert baseline["resolution_state"] == "PROVISIONAL"
    assert _quantity(snapshot, ss.RC_ANALYSIS_BASIS_COMPATIBILITY) == AnalysisBasisStatus.UNRESOLVED.value


def test_eligible_resolved_exact_assumption_is_match():
    _, snapshot = _run("A11", dts="3", bys=8)
    baseline = _quantity(snapshot, ss.RC_DIRECTIONAL_BASELINE_SYSTEM_POLICY)
    assert baseline["resolution_state"] == "RESOLVED"
    assert _quantity(snapshot, ss.RC_ANALYSIS_BASIS_COMPATIBILITY) == AnalysisBasisStatus.MATCH.value


def test_eligible_resolved_mismatch_requires_reanalysis():
    assumptions = _assumptions("A11", x_r=7.0)
    _, snapshot = _run("A11", dts="3", bys=8, assumptions=assumptions)
    assert _quantity(snapshot, ss.RC_DIRECTIONAL_BASELINE_SYSTEM_POLICY)["resolution_state"] == "RESOLVED"
    assert _quantity(snapshot, ss.RC_ANALYSIS_BASIS_COMPATIBILITY) == AnalysisBasisStatus.REANALYSIS_REQUIRED.value


def test_no_duplicated_orchestration_path():
    assert not hasattr(ss, "compile_vs4a_program")
    assert compile_vs4a_program.__module__ == "tbdy_engine.regulatory.vs4a_program"


def _closure(program, rule_id, direction="X"):
    matches = tuple(
        record
        for record in program.plan.compiled_closure_inventory
        if record.instance_id.rule_id == rule_id
        and record.instance_id.direction == direction
    )
    assert len(matches) == 1
    return matches[0]


def _formal_matches(snapshot, rule_id, direction="X"):
    return tuple(
        record.result
        for record in snapshot.formal_results
        if record.instance_id.rule_id == rule_id
        and record.instance_id.direction == direction
    )


def test_nonapplicable_formal_checks_are_compile_time_proven_not_applicable():
    program, snapshot = _run("A11", dts="3", bys=8)
    assert _closure(program, ss.RC_TABLE_4_1_BYS_ELIGIBILITY).applicability is ApplicabilityState.APPLIES
    for rule_id in (
        ss.RC_TBDY_4_3_4_1_DTS_SYSTEM_ELIGIBILITY,
        ss.RC_TBDY_4_3_4_3_A31_DTS_ELIGIBILITY,
        ss.RC_TABLE_4_1_A16_SPECIAL_ELIGIBILITY,
    ):
        assert _closure(program, rule_id).applicability is ApplicabilityState.PROVEN_NOT_APPLICABLE
        assert _formal_matches(snapshot, rule_id) == ()
    assert _quantity(snapshot, ss.RC_TBDY_4_3_4_1_DTS_SYSTEM_ELIGIBILITY_STATE) == "ELIGIBLE"
    assert _quantity(snapshot, ss.RC_TBDY_4_3_4_3_A31_DTS_ELIGIBILITY_STATE) == "NOT_APPLICABLE"
    assert _quantity(snapshot, ss.RC_TABLE_4_1_A16_SPECIAL_ELIGIBILITY_STATE) == "NOT_APPLICABLE"


def test_a31_formal_applicability_is_compile_time_scoped():
    program, snapshot = _run("A31", dts="3", bys=8)
    for rule_id in (
        ss.RC_TABLE_4_1_BYS_ELIGIBILITY,
        ss.RC_TBDY_4_3_4_1_DTS_SYSTEM_ELIGIBILITY,
        ss.RC_TBDY_4_3_4_3_A31_DTS_ELIGIBILITY,
    ):
        assert _closure(program, rule_id).applicability is ApplicabilityState.APPLIES
    assert _closure(program, ss.RC_TABLE_4_1_A16_SPECIAL_ELIGIBILITY).applicability is ApplicabilityState.PROVEN_NOT_APPLICABLE
    assert _formal_matches(snapshot, ss.RC_TABLE_4_1_A16_SPECIAL_ELIGIBILITY) == ()


def test_a16_formal_applicability_is_compile_time_scoped():
    program, snapshot = _run(
        "A16",
        dts="3",
        bys=8,
        a16_contexts=_a16_contexts(),
    )
    assert _closure(program, ss.RC_TABLE_4_1_A16_SPECIAL_ELIGIBILITY).applicability is ApplicabilityState.APPLIES
    for rule_id in (
        ss.RC_TABLE_4_1_BYS_ELIGIBILITY,
        ss.RC_TBDY_4_3_4_1_DTS_SYSTEM_ELIGIBILITY,
        ss.RC_TBDY_4_3_4_3_A31_DTS_ELIGIBILITY,
    ):
        assert _closure(program, rule_id).applicability is ApplicabilityState.PROVEN_NOT_APPLICABLE
        assert _formal_matches(snapshot, rule_id) == ()



def test_formal_applicability_evaluators_are_reviewed_structural_system_code():
    for spec in (
        ss.BYS_CHECK_SPEC,
        ss.DTS_CHECK_SPEC,
        ss.A31_CHECK_SPEC,
        ss.A16_CHECK_SPEC,
    ):
        assert spec.applicability.evaluator.__module__ == "tbdy_engine.regulatory.structural_system"
        assert spec.applicability.input_type.__module__ == "tbdy_engine.regulatory.structural_system"


def test_vs4a_program_contains_no_regulatory_formal_applicability_branching():
    source = inspect.getsource(vs4a_program_module)
    assert "_formal_check_applies" not in source
    assert 'table_4_1_row == "A16"' not in source
    assert 'table_4_1_row != "A16"' not in source
    assert "ss.formal_check_applicability_input(" in source
    assert "ss.requires_a16_special_context(" in source


def test_4_3_4_1_high_mixed_limited_applicability_boundaries_are_exact():
    for row, policy in ss.TABLE_4_1_A_SERIES.items():
        actual = ss.evaluate_dts_4_3_4_1_formal_applicability(
            ss.Dts4341FormalApplicabilityInput(row)
        )
        expected = (
            ApplicabilityState.PROVEN_NOT_APPLICABLE
            if policy.ductility is ss.RcDuctilityLevel.HIGH
            else ApplicabilityState.APPLIES
        )
        assert actual is expected, row
