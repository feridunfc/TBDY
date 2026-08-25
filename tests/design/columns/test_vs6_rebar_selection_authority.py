from tbdy_engine.design.columns.rebar_layout import ColumnRebarLayoutInputs, generate_rectangular_column_rebar_candidates
from tbdy_engine.design.columns.rebar_selection import ColumnDemandBasis, ColumnDemandState, ColumnRebarSelectionPolicy
from tbdy_engine.design.columns.rebar_selection_authority import select_engine_rebar_from_authorized_demands
from tbdy_engine.design.columns.section_capacity import ColumnSectionMaterial


COMP = "+0.00:C2:236"


def _basis():
    return ColumnDemandBasis("RESOLVED", "RESOLVED", "RESOLVED", "RESOLVED", ("review:test",))


def _population():
    return generate_rectangular_column_rebar_candidates(
        ColumnRebarLayoutInputs(800, 800, 40, 10, 22, (16, 20, 24))
    )


def _material():
    return ColumnSectionMaterial(35, 23.3333333333, 434.7826086957)


def _demand(case_type):
    return ColumnDemandState(
        state_id="D1",
        component_id=COMP,
        output_case="ULT",
        case_type=case_type,
        step_type=None,
        step_number=None,
        station_m=0.0,
        end_tag="I_END",
        nd_compression_n=1_000_000.0,
        m2_nmm=20e6,
        m3_nmm=10e6,
        source_identity="source:D1",
    )


def test_raw_etabs_combination_row_cannot_reach_engine_selected_rebar():
    result = select_engine_rebar_from_authorized_demands(
        component_id=COMP,
        width_mm=800,
        depth_mm=800,
        population=_population(),
        material=_material(),
        demands=(_demand("Combination"),),
        basis=_basis(),
        policy=ColumnRebarSelectionPolicy(8, 20.0),
    )
    assert result.status == "BLOCKED_UNPROMOTED_DEMAND_STATES"
    assert result.authority == "NOT_SELECTED"
    assert result.selected_candidate is None


def test_promoted_static_design_state_may_reach_selection_kernel():
    result = select_engine_rebar_from_authorized_demands(
        component_id=COMP,
        width_mm=800,
        depth_mm=800,
        population=_population(),
        material=_material(),
        demands=(_demand("DesignStaticLinearExact"),),
        basis=_basis(),
        policy=ColumnRebarSelectionPolicy(8, 20.0),
    )
    assert result.status == "SELECTED"
    assert result.authority == "ENGINE_SELECTED_REBAR"
