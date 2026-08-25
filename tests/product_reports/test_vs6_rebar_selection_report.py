from tbdy_engine.design.columns.rebar_layout import ColumnRebarLayoutInputs, generate_rectangular_column_rebar_candidates
from tbdy_engine.design.columns.rebar_selection import (
    ColumnDemandBasis,
    ColumnDemandState,
    ColumnRebarSelectionPolicy,
    select_engine_rebar_for_demands,
)
from tbdy_engine.design.columns.section_capacity import ColumnSectionMaterial
from tbdy_engine.product_reports.vs6_rebar_selection_report import build_vs6_rebar_selection_report


def test_selected_rebar_report_keeps_engine_selected_authority_distinct_from_provided_rebar():
    population = generate_rectangular_column_rebar_candidates(
        ColumnRebarLayoutInputs(800, 800, 40, 10, 22, (16, 20, 24))
    )
    demand = ColumnDemandState(
        "D1", "+0.00:C2:236", "ULT", "Combination", "Max", None, 0.0, "I_END",
        1_000_000.0, 20e6, 10e6, "source:D1"
    )
    result = select_engine_rebar_for_demands(
        component_id=demand.component_id,
        width_mm=800,
        depth_mm=800,
        population=population,
        material=ColumnSectionMaterial(35, 23.3333333333, 434.7826086957),
        demands=(demand,),
        basis=ColumnDemandBasis("RESOLVED", "RESOLVED", "RESOLVED", "RESOLVED", ("review:test",)),
        policy=ColumnRebarSelectionPolicy(8, 20.0),
    )
    report = build_vs6_rebar_selection_report(result).as_dict()
    authority = next(field["value"] for field in report["summary_fields"] if field["key"] == "authority")
    assert report["status"] == "PROVEN"
    assert authority == "ENGINE_SELECTED_REBAR"
    assert "USER_PROVIDED_REBAR" in report["warnings"][0]
    assert report["presentation_contract"]["engineering_recalculation_allowed"] is False
