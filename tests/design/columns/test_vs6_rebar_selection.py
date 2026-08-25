import pytest

from tbdy_engine.design.columns.rebar_layout import ColumnRebarLayoutInputs, generate_rectangular_column_rebar_candidates
from tbdy_engine.design.columns.rebar_selection import (
    ColumnDemandBasis,
    ColumnDemandState,
    ColumnRebarSelectionPolicy,
    ETABS_AXIAL_SIGN_NEGATIVE_COMPRESSION,
    normalize_etabs_column_end_demands,
    select_engine_rebar_for_demands,
)
from tbdy_engine.design.columns.section_capacity import ColumnSectionMaterial


def _basis(resolved=True):
    status = "RESOLVED" if resolved else "BLOCKED"
    return ColumnDemandBasis(
        analysis_order_status=status,
        minimum_eccentricity_status=status,
        slenderness_status=status,
        combination_scope_status=status,
        review_refs=("review:test",),
    )


def _population():
    return generate_rectangular_column_rebar_candidates(
        ColumnRebarLayoutInputs(
            width_mm=800.0,
            depth_mm=800.0,
            clear_cover_mm=40.0,
            tie_diameter_mm=10.0,
            aggregate_max_mm=22.0,
            allowed_bar_diameters_mm=(16.0, 20.0, 24.0),
        )
    )


def _material():
    return ColumnSectionMaterial(fck_mpa=35.0, fcd_mpa=23.3333333333, fyd_mpa=434.7826086957)


def test_exact_etabs_end_rows_are_normalized_without_governing_collapse():
    rows = (
        {"Story":"+0.00","Column":"C2","UniqueName":"236","OutputCase":"EX","CaseType":"LinRespSpec","StepType":"Max","StepNumber":None,"Station":"0","P":"-3000","M2":"100","M3":"50","Element":"236-1","ElemStation":"0"},
        {"Story":"+0.00","Column":"C2","UniqueName":"236","OutputCase":"EX","CaseType":"LinRespSpec","StepType":"Min","StepNumber":None,"Station":"0","P":"-3200","M2":"-90","M3":"-40","Element":"236-1","ElemStation":"0"},
        {"Story":"+0.00","Column":"C2","UniqueName":"236","OutputCase":"EX","CaseType":"LinRespSpec","StepType":"Max","StepNumber":None,"Station":"2.225","P":"-3100","M2":"20","M3":"10","Element":"236-1","ElemStation":"2.225"},
        {"Story":"+0.00","Column":"C2","UniqueName":"236","OutputCase":"EX","CaseType":"LinRespSpec","StepType":"Max","StepNumber":None,"Station":"4.45","P":"-2900","M2":"-110","M3":"60","Element":"236-1","ElemStation":"4.45"},
    )
    demands = normalize_etabs_column_end_demands(
        rows,
        unique_name="236",
        component_id="+0.00:C2:236",
        reviewed_force_unit="kN",
        reviewed_moment_unit="kN-m",
        axial_sign_policy=ETABS_AXIAL_SIGN_NEGATIVE_COMPRESSION,
    )
    assert len(demands) == 3
    assert {item.end_tag for item in demands} == {"I_END", "J_END"}
    assert all(item.nd_compression_n > 0 for item in demands)
    assert not any(item.station_m == pytest.approx(2.225) for item in demands)


def test_selection_is_blocked_when_any_demand_basis_item_is_unresolved():
    result = select_engine_rebar_for_demands(
        component_id="+0.00:C2:236",
        width_mm=800.0,
        depth_mm=800.0,
        population=_population(),
        material=_material(),
        demands=(),
        basis=_basis(False),
        policy=ColumnRebarSelectionPolicy(angle_count=8, axial_tolerance_n=20.0),
    )
    assert result.status == "BLOCKED_DEMAND_BASIS"
    assert result.authority == "NOT_SELECTED"
    assert result.selected_candidate is None


def test_low_demand_selects_smallest_eligible_candidate_and_promotes_only_engine_authority():
    demand = ColumnDemandState(
        state_id="D1",
        component_id="+0.00:C2:236",
        output_case="ULT",
        case_type="Combination",
        step_type="",
        step_number=None,
        station_m=0.0,
        end_tag="I_END",
        nd_compression_n=1_000_000.0,
        m2_nmm=20e6,
        m3_nmm=10e6,
        source_identity="source:D1",
    )
    result = select_engine_rebar_for_demands(
        component_id=demand.component_id,
        width_mm=800.0,
        depth_mm=800.0,
        population=_population(),
        material=_material(),
        demands=(demand,),
        basis=_basis(True),
        policy=ColumnRebarSelectionPolicy(angle_count=8, axial_tolerance_n=20.0),
    )
    assert result.status == "SELECTED"
    assert result.authority == "ENGINE_SELECTED_REBAR"
    assert result.selected_candidate == _population().candidates[0]
    assert result.required_as_in_candidate_family_mm2 == pytest.approx(result.selected_candidate.as_total_mm2)
    assert result.governing_utilization is not None
    assert result.governing_utilization <= 1.0
