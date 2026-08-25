from tbdy_engine.design.columns.rebar_layout import (
    ColumnRebarLayoutInputs,
    generate_rectangular_column_rebar_candidates,
)
from tbdy_engine.product_reports.vs6_rebar_layout_report import build_vs6_rebar_layout_report


def test_vs6_rebar_layout_report_is_projection_only_and_labels_candidate_authority():
    population = generate_rectangular_column_rebar_candidates(
        ColumnRebarLayoutInputs(
            width_mm=800.0,
            depth_mm=800.0,
            clear_cover_mm=40.0,
            tie_diameter_mm=10.0,
            aggregate_max_mm=22.0,
            allowed_bar_diameters_mm=(16.0, 20.0, 24.0),
        )
    )
    report = build_vs6_rebar_layout_report(
        component_id="236",
        section_name="Column_80x80",
        population=population,
    ).as_dict()

    assert report["status"] == "PROVEN"
    assert report["component_id"] == "236"
    assert report["presentation_contract"]["engineering_recalculation_allowed"] is False
    assert report["tables"][0]["rows"]
    assert {row["authority"] for row in report["tables"][0]["rows"]} == {"DESIGN_CANDIDATE_ONLY"}
    assert any("not ENGINE_SELECTED_REBAR" in warning for warning in report["warnings"])
