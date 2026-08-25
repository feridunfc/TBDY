from tbdy_engine.design.columns.column_design_demand_engine import ColumnComboDefinition
from tbdy_engine.design.columns.column_design_engine import evaluate_column_design
from tbdy_engine.design.columns.column_rebar_design_engine import ColumnRebarDesignInputs
from tbdy_engine.design.columns.combo_pattern_engine import ComboPatternConstituent
from tbdy_engine.design.columns.rebar_catalog import build_rebar_catalog_from_rows
from tbdy_engine.design.columns.rebar_selection import (
    ColumnDemandBasis,
    ColumnDemandState,
    ColumnRebarSelectionPolicy,
)
from tbdy_engine.design.columns.section_capacity import ColumnSectionMaterial
from tbdy_engine.product_reports.vs6_column_design_engine_report import (
    build_vs6_column_design_engine_reports,
)


COMP = "+0.00:C2:236"


def _state(end, station):
    return ColumnDemandState(
        state_id=f"D:{end}",
        component_id=COMP,
        output_case="D",
        case_type="LinStatic",
        step_type=None,
        step_number=None,
        station_m=station,
        end_tag=end,
        nd_compression_n=1000.0,
        m2_nmm=10.0,
        m3_nmm=20.0,
        source_identity=f"src:{end}",
    )


def test_integrated_report_is_projection_only_and_includes_demand_eccentricity_layout_selection_details():
    catalog = build_rebar_catalog_from_rows(
        ({"Name": "14", "Diameter": 14.0}, {"Name": "20", "Diameter": 20.0}),
        name_field="Name",
        diameter_field="Diameter",
        diameter_unit="mm",
        source_name="fixture",
    )
    result = evaluate_column_design(
        component_id=COMP,
        combo_definitions=(
            ColumnComboDefinition(
                name="ANY",
                combo_type="LINEAR_ADD",
                constituents=(ComboPatternConstituent("D", 1.0),),
            ),
        ),
        constituent_case_demands=(_state("I_END", 0.0), _state("J_END", 4.0)),
        rebar_catalog=catalog,
        rebar_inputs=ColumnRebarDesignInputs(
            component_id=COMP,
            width_mm=800.0,
            depth_mm=800.0,
            clear_cover_mm=40.0,
            tie_diameter_mm=10.0,
            aggregate_max_mm=25.0,
            material=ColumnSectionMaterial(
                fck_mpa=35.0,
                fcd_mpa=35.0 / 1.5,
                fyd_mpa=500.0 / 1.15,
            ),
            demand_basis=ColumnDemandBasis(
                analysis_order_status="RESOLVED",
                minimum_eccentricity_status="BLOCKED",
                slenderness_status="BLOCKED",
                combination_scope_status="BLOCKED",
                review_refs=("fixture",),
            ),
            selection_policy=ColumnRebarSelectionPolicy(angle_count=36, axial_tolerance_n=1000.0),
        ),
    )

    reports = build_vs6_column_design_engine_reports(result, section_name="Column_80x80")
    assert reports[0].slice_id == "VS6-P4-P6-COLUMN-DESIGN-ENGINE"
    assert reports[0].status == "BLOCKED"
    assert any(item.slice_id == "VS6-P6-COLUMN-DESIGN-DEMAND-STATES" for item in reports)
    assert any(item.slice_id == "VS6-P6-TS500-MINIMUM-ECCENTRICITY" for item in reports)
    assert any(item.slice_id == "VS6-P4-COLUMN-REBAR-CANDIDATES" for item in reports)
    assert any(item.slice_id == "VS6-P6-COLUMN-REBAR-SELECTION" for item in reports)
    for report in reports:
        contract = report.as_dict()["presentation_contract"]
        assert contract["engineering_recalculation_allowed"] is False
        assert contract["renderer_may_change_status"] is False
        assert contract["renderer_may_change_governing_selection"] is False
