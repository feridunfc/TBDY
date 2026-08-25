from tbdy_engine.design.columns.sway_stability import (
    LOAD_BASIS_AUTHORITY,
    STORY_STABILITY_INPUT_AUTHORITY,
    TS500_LOAD_GQE,
    TS500_LOAD_GQW,
    UNCRACKED_SECTION_BASIS_AUTHORITY,
    StoryStabilityIndexEvidence,
    resolve_ts500_story_sway_from_stability_indices,
)
from tbdy_engine.product_reports.vs6_sway_stability_report import (
    build_vs6_sway_stability_report,
)


def _evidence(load_basis: str, drift_mm: float):
    return StoryStabilityIndexEvidence(
        story="+0.00",
        direction="X",
        load_basis=load_basis,
        story_height_mm=3000.0,
        relative_story_displacement_mm=drift_mm,
        story_shear_n=1_000_000.0,
        sum_column_axial_design_force_n=10_000_000.0,
        input_authority=STORY_STABILITY_INPUT_AUTHORITY,
        load_basis_authority=LOAD_BASIS_AUTHORITY,
        stiffness_basis="UNCRACKED",
        stiffness_basis_authority=UNCRACKED_SECTION_BASIS_AUTHORITY,
        source_refs=(f"fixture:{load_basis}",),
    )


def test_report_projects_resolved_kernel_without_recalculation():
    result = resolve_ts500_story_sway_from_stability_indices(
        (_evidence(TS500_LOAD_GQE, 6.0), _evidence(TS500_LOAD_GQW, 9.0)),
        story="+0.00",
        direction="X",
    )
    report = build_vs6_sway_stability_report(result)
    assert report.status == "PROVEN"
    assert report.component_id == "+0.00:X"
    assert report.tables[0].rows[1]["phi"] == result.load_results[1].phi
    presentation = report.as_dict()["presentation_contract"]
    assert presentation["engineering_recalculation_allowed"] is False
    assert presentation["renderer_may_change_status"] is False


def test_report_keeps_incomplete_stability_proof_blocked_not_failed():
    result = resolve_ts500_story_sway_from_stability_indices(
        (_evidence(TS500_LOAD_GQE, 6.0),),
        story="+0.00",
        direction="X",
    )
    report = build_vs6_sway_stability_report(result)
    assert report.status == "BLOCKED"
    assert report.warnings
