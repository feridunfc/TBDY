from __future__ import annotations

from tbdy_engine.features.etabs_mdev_mo_evidence import (
    BLOCKED_ANALYSIS_METHOD_RESULT_POPULATION_MISMATCH,
    ReviewedAnalysisMethod,
    ReviewedDirectionalWallPopulation,
    ReviewedRegulatoryBaseContext,
    ReviewedResultPopulationContext,
    build_directional_mdev_mo_evidence,
)
from tbdy_engine.regulatory.kernel import AnalysisBasisStatus
from tbdy_engine.regulatory.structural_system import (
    DirectionalAnalysisSystemAssumption,
    ReviewedDirectionalRcSystemDeclaration,
    ReviewedSeismicClassificationContext,
)
from tbdy_engine.regulatory.vs4b_program import STATUS_RESOLVED, run_vs4b_a15_direction


CASES = ("~Static+EccRSX", "~Static-EccRSX")


def _reviewed_inputs(*, assumed_row="A15", r=7.0, d=2.5, bys=2):
    declaration = ReviewedDirectionalRcSystemDeclaration(
        direction="X",
        table_4_1_row="A15",
        review_refs=("review:declaration:X",),
        provenance_refs=("project:declaration:X",),
    )
    seismic = ReviewedSeismicClassificationContext(
        dts="2",
        bys=bys,
        review_refs=("review:seismic",),
        provenance_refs=("project:seismic",),
    )
    assumption = DirectionalAnalysisSystemAssumption(
        direction="X",
        assumed_table_4_1_row=assumed_row,
        assumed_r=r,
        assumed_d=d,
        analysis_evidence_refs=("analysis:basis:X",),
        provenance_refs=("project:analysis:X",),
    )
    return declaration, seismic, assumption


def _evidence(*, case_type="LinRespSpec", wall_each=30.0, mapping=()):
    sections = (
        {"Story": "B1", "Pier": "P1", "CGBotZ": -5.15, "AxisAngle": 0.0},
        {"Story": "B1", "Pier": "P2", "CGBotZ": -5.15, "AxisAngle": 0.0},
    )
    pier = {}
    story = {}
    base = {}
    for case in CASES:
        pier[case] = (
            {"Story": "B1", "Pier": "P1", "OutputCase": case, "CaseType": case_type,
             "Location": "Bottom", "M2": 0.0, "M3": wall_each},
            {"Story": "B1", "Pier": "P2", "OutputCase": case, "CaseType": case_type,
             "Location": "Bottom", "M2": 0.0, "M3": wall_each},
        )
        story[case] = (
            {"Story": "B1", "OutputCase": case, "CaseType": case_type,
             "Location": "Bottom", "MX": 0.0, "MY": 100.0},
        )
        base[case] = (
            {"OutputCase": case, "CaseType": case_type, "MX": 0.0, "MY": 100.0,
             "X": 0.0, "Y": 0.0, "Z": -5.15},
        )
    return build_directional_mdev_mo_evidence(
        direction="X",
        evidence_epoch_id="epoch:integration",
        model_fingerprint="etabs:model-identity:sha256:integration",
        case_names=CASES,
        base_context=ReviewedRegulatoryBaseContext(
            -5.15, False, ("review:base",), ("project:base",)
        ),
        wall_population=ReviewedDirectionalWallPopulation(
            "X", ("P1", "P2"), ("review:walls:X",), ("project:walls:X",)
        ),
        result_context=ReviewedResultPopulationContext(
            analysis_method=ReviewedAnalysisMethod.MODAL_COMBINATION,
            scaling_state_id="reviewed:scaled-final",
            result_operator_id="reviewed:signed-same-realization",
            wall_to_total_sign_factor=1,
            review_refs=("review:results",),
            provenance_refs=("project:results",),
            population_mapping_review_refs=tuple(mapping),
        ),
        pier_sections=sections,
        pier_force_rows_by_case=pier,
        story_force_rows_by_case=story,
        base_reaction_rows_by_case=base,
    )


def test_modal_nominal_evidence_executes_existing_f0_kernel_and_resolves_match():
    declaration, seismic, assumption = _reviewed_inputs()
    run = run_vs4b_a15_direction(
        declaration=declaration,
        seismic=seismic,
        analysis_assumption=assumption,
        evidence=_evidence(wall_each=30.0),
    )
    assert run.status == STATUS_RESOLVED
    assert run.program is not None and run.store is not None
    assert run.effective_policy["qualification_branch"] == "NOMINAL"
    assert run.effective_policy["declared_system_row"] == "A15"
    assert run.analysis_basis_status is AnalysisBasisStatus.MATCH
    assert len(run.store.regulatory_quantities) == 2


def test_modal_upper_evidence_keeps_a15_declaration_and_requires_reanalysis_from_r7_basis():
    declaration, seismic, assumption = _reviewed_inputs()
    run = run_vs4b_a15_direction(
        declaration=declaration,
        seismic=seismic,
        analysis_assumption=assumption,
        evidence=_evidence(wall_each=40.0),
    )
    assert run.status == STATUS_RESOLVED
    assert run.effective_policy["qualification_branch"] == "UPPER"
    assert run.effective_policy["declared_system_row"] == "A15"
    assert run.effective_policy["effective_parameter_basis"] == "A13"
    assert run.effective_policy["effective_r"] == 6.0
    assert run.effective_policy["effective_d"] == 2.5
    assert run.analysis_basis_status is AnalysisBasisStatus.REANALYSIS_REQUIRED


def test_linstat_rows_do_not_compile_under_modal_authority_without_reviewed_mapping():
    declaration, seismic, assumption = _reviewed_inputs()
    factual = _evidence(case_type="LinStatic")
    assert factual.blocking_status == BLOCKED_ANALYSIS_METHOD_RESULT_POPULATION_MISMATCH
    run = run_vs4b_a15_direction(
        declaration=declaration,
        seismic=seismic,
        analysis_assumption=assumption,
        evidence=factual,
    )
    assert run.status == BLOCKED_ANALYSIS_METHOD_RESULT_POPULATION_MISMATCH
    assert run.program is None
    assert run.store is None
    assert run.effective_policy is None
    assert run.analysis_basis_status is None
    rendered = str(run.as_dict())
    assert "qualification_branch" not in rendered
    assert "alpha_m" not in rendered


def test_explicit_reviewed_linstat_to_modal_population_mapping_is_required_before_compile():
    declaration, seismic, assumption = _reviewed_inputs()
    factual = _evidence(
        case_type="LinStatic",
        mapping=("review:etabs-linstatic-is-reviewed-modal-decomposition",),
    )
    assert factual.regulatory_ready is True
    run = run_vs4b_a15_direction(
        declaration=declaration,
        seismic=seismic,
        analysis_assumption=assumption,
        evidence=factual,
    )
    assert run.status == STATUS_RESOLVED
    assert run.effective_policy["qualification_branch"] == "NOMINAL"


def test_lower_branch_existing_bys2_is_invalid_after_postanalysis_resolution():
    declaration, seismic, assumption = _reviewed_inputs(bys=2)
    run = run_vs4b_a15_direction(
        declaration=declaration,
        seismic=seismic,
        analysis_assumption=assumption,
        evidence=_evidence(wall_each=20.0),
    )
    assert run.status == STATUS_RESOLVED
    assert run.effective_policy["qualification_branch"] == "LOWER"
    assert run.effective_policy["effective_bys_policy"] == 3
    assert run.analysis_basis_status is AnalysisBasisStatus.INVALID
