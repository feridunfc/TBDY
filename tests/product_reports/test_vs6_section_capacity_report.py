from tbdy_engine.design.columns.rebar_layout import ColumnRebarLayoutInputs, generate_rectangular_column_rebar_candidates
from tbdy_engine.design.columns.section_capacity import ColumnSectionMaterial, build_interaction_envelope_at_axial_force
from tbdy_engine.product_reports.vs6_section_capacity_report import build_vs6_section_capacity_report


def test_capacity_report_projects_already_resolved_states_without_compliance_verdict():
    candidate = generate_rectangular_column_rebar_candidates(
        ColumnRebarLayoutInputs(
            width_mm=800.0,
            depth_mm=800.0,
            clear_cover_mm=40.0,
            tie_diameter_mm=10.0,
            aggregate_max_mm=22.0,
            allowed_bar_diameters_mm=(20.0,),
        )
    ).candidates[0]
    envelope = build_interaction_envelope_at_axial_force(
        width_mm=800.0,
        depth_mm=800.0,
        bars=candidate.bars,
        material=ColumnSectionMaterial(fck_mpa=35.0, fcd_mpa=23.3333333333, fyd_mpa=434.7826086957),
        target_n_compression_n=3_000_000.0,
        angle_count=8,
        axial_tolerance_n=10.0,
    )
    report = build_vs6_section_capacity_report(
        component_id="236",
        candidate_id=candidate.candidate_id,
        envelope=envelope,
    ).as_dict()

    assert report["status"] == "PROVEN"
    assert report["tables"][0]["rows"]
    assert report["presentation_contract"]["renderer_may_change_status"] is False
    assert all("status" not in row for row in report["tables"][0]["rows"])
