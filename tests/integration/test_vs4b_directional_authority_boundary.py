from __future__ import annotations

from pathlib import Path

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
from tbdy_engine.regulatory.vs4b_program import (
    STATUS_PROVEN_NOT_APPLICABLE,
    STATUS_RESOLVED,
    run_vs4b_a15_direction,
)


def _seismic() -> ReviewedSeismicClassificationContext:
    return ReviewedSeismicClassificationContext(
        dts="2",
        bys=2,
        review_refs=("review:seismic",),
        provenance_refs=("project:seismic",),
    )


def _assumption(direction: str) -> DirectionalAnalysisSystemAssumption:
    return DirectionalAnalysisSystemAssumption(
        direction=direction,
        assumed_table_4_1_row="A15",
        assumed_r=7.0,
        assumed_d=2.5,
        analysis_evidence_refs=(f"analysis:basis:{direction}",),
        provenance_refs=(f"project:analysis:{direction}",),
    )


def _directional_evidence(
    direction: str,
    *,
    case_type: str = "LinRespSpec",
    mapping: tuple[str, ...] = (),
    wall_moment: float = 60.0,
):
    cases = (
        ("~Static+EccRSX", "~Static-EccRSX")
        if direction == "X"
        else ("~Static+EccRSY", "~Static-EccRSY")
    )
    sections = (
        {"Story": "B1", "Pier": "P1", "CGBotZ": -5.15, "AxisAngle": 0.0},
    )
    if direction == "X":
        m2, m3 = 0.0, wall_moment
        mx, my = 0.0, 100.0
    else:
        m2, m3 = wall_moment, 0.0
        mx, my = 100.0, 0.0
    pier = {
        case: (
            {
                "Story": "B1",
                "Pier": "P1",
                "OutputCase": case,
                "CaseType": case_type,
                "Location": "Bottom",
                "M2": m2,
                "M3": m3,
            },
        )
        for case in cases
    }
    story = {
        case: (
            {
                "Story": "B1",
                "OutputCase": case,
                "CaseType": case_type,
                "Location": "Bottom",
                "MX": mx,
                "MY": my,
            },
        )
        for case in cases
    }
    base = {
        case: (
            {
                "OutputCase": case,
                "CaseType": case_type,
                "MX": mx,
                "MY": my,
                "X": 0.0,
                "Y": 0.0,
                "Z": -5.15,
            },
        )
        for case in cases
    }
    return build_directional_mdev_mo_evidence(
        direction=direction,
        evidence_epoch_id=f"epoch:directional:{direction}",
        model_fingerprint=f"etabs:model-identity:sha256:directional:{direction}",
        case_names=cases,
        base_context=ReviewedRegulatoryBaseContext(
            -5.15,
            False,
            ("review:base",),
            ("project:base",),
        ),
        wall_population=ReviewedDirectionalWallPopulation(
            direction,
            ("P1",),
            (f"review:walls:{direction}",),
            (f"project:walls:{direction}",),
        ),
        result_context=ReviewedResultPopulationContext(
            analysis_method=ReviewedAnalysisMethod.MODAL_COMBINATION,
            scaling_state_id=f"reviewed:scaled-final:{direction}",
            result_operator_id=f"reviewed:signed-same-realization:{direction}",
            wall_to_total_sign_factor=1,
            review_refs=(f"review:results:{direction}",),
            provenance_refs=(f"project:results:{direction}",),
            population_mapping_review_refs=mapping,
        ),
        pier_sections=sections,
        pier_force_rows_by_case=pier,
        story_force_rows_by_case=story,
        base_reaction_rows_by_case=base,
    )


def _declaration(direction: str, row: str = "A15"):
    return ReviewedDirectionalRcSystemDeclaration(
        direction=direction,
        table_4_1_row=row,
        review_refs=(f"review:declaration:{direction}:{row}",),
        provenance_refs=(f"project:declaration:{direction}:{row}",),
    )


def test_x_a15_executes_without_any_y_wall_or_case_input():
    evidence = _directional_evidence("X")
    assert all("RSY" not in case.case_name for case in evidence.cases)
    run = run_vs4b_a15_direction(
        declaration=_declaration("X"),
        seismic=_seismic(),
        analysis_assumption=_assumption("X"),
        evidence=evidence,
    )
    assert run.status == STATUS_RESOLVED
    assert run.effective_policy["qualification_branch"] == "NOMINAL"
    assert run.effective_policy["declared_system_row"] == "A15"
    assert run.analysis_basis_status is AnalysisBasisStatus.MATCH


def test_y_a15_executes_without_any_x_wall_or_case_input():
    evidence = _directional_evidence("Y")
    assert all("RSX" not in case.case_name for case in evidence.cases)
    run = run_vs4b_a15_direction(
        declaration=_declaration("Y"),
        seismic=_seismic(),
        analysis_assumption=_assumption("Y"),
        evidence=evidence,
    )
    assert run.status == STATUS_RESOLVED
    assert run.effective_policy["qualification_branch"] == "NOMINAL"
    assert run.effective_policy["declared_system_row"] == "A15"
    assert run.analysis_basis_status is AnalysisBasisStatus.MATCH


def test_non_a15_reviewed_declaration_is_proven_not_applicable_and_never_compiles_a15():
    run = run_vs4b_a15_direction(
        declaration=_declaration("X", "A14"),
        seismic=_seismic(),
        analysis_assumption=_assumption("X"),
        evidence=_directional_evidence("X"),
    )
    assert run.status == STATUS_PROVEN_NOT_APPLICABLE
    assert run.program is None
    assert run.store is None
    assert run.effective_policy is None
    assert run.analysis_basis_status is None
    rendered = str(run.as_dict())
    assert "qualification_branch" not in rendered
    assert "alpha_m" not in rendered


def test_linstat_modal_without_reviewed_mapping_remains_blocked_before_regulatory_compile():
    evidence = _directional_evidence("X", case_type="LinStatic")
    assert evidence.blocking_status == BLOCKED_ANALYSIS_METHOD_RESULT_POPULATION_MISMATCH
    run = run_vs4b_a15_direction(
        declaration=_declaration("X"),
        seismic=_seismic(),
        analysis_assumption=_assumption("X"),
        evidence=evidence,
    )
    assert run.status == BLOCKED_ANALYSIS_METHOD_RESULT_POPULATION_MISMATCH
    assert run.program is None
    assert run.store is None
    assert run.effective_policy is None
    assert run.analysis_basis_status is None
    rendered = str(run.as_dict())
    assert "qualification_branch" not in rendered
    assert "alpha_m" not in rendered


def test_upper_keeps_declared_a15_but_uses_a13_parameter_basis_and_requires_reanalysis():
    run = run_vs4b_a15_direction(
        declaration=_declaration("X"),
        seismic=_seismic(),
        analysis_assumption=_assumption("X"),
        evidence=_directional_evidence("X", wall_moment=80.0),
    )
    assert run.status == STATUS_RESOLVED
    assert run.effective_policy["qualification_branch"] == "UPPER"
    assert run.effective_policy["declared_system_row"] == "A15"
    assert run.effective_policy["effective_parameter_basis"] == "A13"
    assert run.effective_policy["effective_r"] == 6.0
    assert run.effective_policy["effective_d"] == 2.5
    assert run.effective_policy["effective_bys_policy"] == 2
    assert run.analysis_basis_status is AnalysisBasisStatus.REANALYSIS_REQUIRED


def test_live_runner_never_manufactures_a15_and_exposes_only_directional_inputs():
    source = Path("tools/run_live_vs4b_a15.py").read_text(encoding="utf-8")
    assert 'table_4_1_row="A15"' not in source
    assert "table_4_1_row=args.declared_row" in source
    for required in ("--direction", "--declared-row", "--piers", "--cases"):
        assert required in source
    for forbidden in ("--x-piers", "--y-piers", "--x-cases", "--y-cases"):
        assert forbidden not in source
