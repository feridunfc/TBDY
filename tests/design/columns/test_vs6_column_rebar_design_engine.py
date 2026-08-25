from tbdy_engine.design.columns.column_rebar_design_engine import (
    ColumnRebarDesignInputs,
    design_column_longitudinal_rebar,
)
from tbdy_engine.design.columns.rebar_catalog import build_rebar_catalog_from_rows
from tbdy_engine.design.columns.rebar_selection import (
    ColumnDemandBasis,
    ColumnDemandState,
    ColumnRebarSelectionPolicy,
)
from tbdy_engine.design.columns.section_capacity import ColumnSectionMaterial


COMP = "+0.00:C2:236"


def _catalog():
    return build_rebar_catalog_from_rows(
        (
            {"Name": "10", "Diameter": 10.0},
            {"Name": "14", "Diameter": 14.0},
            {"Name": "20", "Diameter": 20.0},
            {"Name": "25", "Diameter": 25.0},
        ),
        name_field="Name",
        diameter_field="Diameter",
        diameter_unit="mm",
        source_name="ETABS:Reinforcing Bar Sizes",
    )


def test_engine_preserves_catalog_exclusions_and_blocks_authority_when_basis_is_blocked():
    demand = ColumnDemandState(
        state_id="promoted:1",
        component_id=COMP,
        output_case="ULS_17",
        case_type="DesignStaticLinearExact",
        step_type=None,
        step_number=None,
        station_m=0.0,
        end_tag="I_END",
        nd_compression_n=1_000_000.0,
        m2_nmm=100_000_000.0,
        m3_nmm=50_000_000.0,
        source_identity="fixture",
    )
    inputs = ColumnRebarDesignInputs(
        component_id=COMP,
        width_mm=800.0,
        depth_mm=800.0,
        clear_cover_mm=40.0,
        tie_diameter_mm=10.0,
        aggregate_max_mm=25.0,
        material=ColumnSectionMaterial(fck_mpa=35.0, fcd_mpa=35.0 / 1.5, fyd_mpa=500.0 / 1.15),
        demand_basis=ColumnDemandBasis(
            analysis_order_status="RESOLVED",
            minimum_eccentricity_status="BLOCKED",
            slenderness_status="BLOCKED",
            combination_scope_status="RESOLVED",
            review_refs=("fixture-review",),
        ),
        selection_policy=ColumnRebarSelectionPolicy(angle_count=36, axial_tolerance_n=1_000.0),
    )
    result = design_column_longitudinal_rebar(
        inputs=inputs,
        rebar_catalog=_catalog(),
        promoted_demands=(demand,),
    )
    assert result.status == "BLOCKED_DEMAND_BASIS"
    assert result.authority == "NOT_SELECTED"
    assert result.excluded_catalog_bar_names == ("10",)
    assert result.candidate_population is not None
    assert result.candidate_population.inputs.allowed_bar_diameters_mm == (14.0, 20.0, 25.0)
