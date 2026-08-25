from tbdy_engine.design.columns.minimum_eccentricity import apply_ts500_minimum_eccentricity
from tbdy_engine.design.columns.rebar_selection import ColumnDemandState
from tbdy_engine.product_reports.vs6_minimum_eccentricity_report import (
    build_vs6_minimum_eccentricity_report,
)


COMP = "+0.00:C2:236"


def test_minimum_eccentricity_report_projects_canonical_result_only():
    demand = ColumnDemandState(
        state_id="s1",
        component_id=COMP,
        output_case="ULS",
        case_type="DesignStaticLinearExact",
        step_type=None,
        step_number=None,
        station_m=0.0,
        end_tag="I_END",
        nd_compression_n=1_000_000.0,
        m2_nmm=10_000_000.0,
        m3_nmm=20_000_000.0,
        source_identity="fixture",
    )
    result = apply_ts500_minimum_eccentricity(
        component_id=COMP,
        width_mm=500.0,
        depth_mm=800.0,
        demands=(demand,),
    )
    report = build_vs6_minimum_eccentricity_report(result)
    assert report.slice_id == "VS6-P6-TS500-MINIMUM-ECCENTRICITY"
    assert report.status == "PROVEN"
    assert report.component_id == COMP
    assert len(report.tables) == 1
    contract = report.as_dict()["presentation_contract"]
    assert contract["engineering_recalculation_allowed"] is False
    assert contract["renderer_may_change_status"] is False
    assert contract["renderer_may_change_governing_selection"] is False
