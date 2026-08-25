from tbdy_engine.design.columns.design_demand_states import (
    LinearComboConstituent,
    build_linear_combo_design_demands,
)
from tbdy_engine.design.columns.rebar_selection import ColumnDemandState
from tbdy_engine.product_reports.vs6_design_demand_report import build_vs6_design_demand_report


COMP = "+0.00:C2:236"


def _state(case, case_type, end, station, n, m2, m3, step=None):
    return ColumnDemandState(
        state_id=f"{case}:{end}",
        component_id=COMP,
        output_case=case,
        case_type=case_type,
        step_type=step,
        step_number=None,
        station_m=station,
        end_tag=end,
        nd_compression_n=n,
        m2_nmm=m2,
        m3_nmm=m3,
        source_identity=f"src:{case}:{end}",
    )


def test_design_demand_report_is_projection_only_and_exposes_all_permutations():
    rows = (
        _state("G", "LinStatic", "I_END", 0.0, 1000.0, 10.0, 20.0),
        _state("RS", "LinRespSpec", "I_END", 0.0, -100.0, 30.0, 40.0, "Max"),
        _state("G", "LinStatic", "J_END", 4.0, 900.0, -10.0, -20.0),
        _state("RS", "LinRespSpec", "J_END", 4.0, -80.0, 20.0, 25.0, "Max"),
    )
    build = build_linear_combo_design_demands(
        component_id=COMP,
        combo_name="SEIS",
        combo_type="LINEAR_ADD",
        constituents=(LinearComboConstituent("G", 1.0), LinearComboConstituent("RS", 1.0)),
        case_demands=rows,
    )
    report = build_vs6_design_demand_report(build).as_dict()
    assert report["status"] == "PROVEN"
    assert report["presentation_contract"]["engineering_recalculation_allowed"] is False
    states = next(table for table in report["tables"] if table["table_id"] == "vs6_design_demand_states")
    assert len(states["rows"]) == 16
    assert any("not promoted directly" in warning for warning in report["warnings"])
