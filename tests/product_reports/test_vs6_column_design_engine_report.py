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
from tbdy_engine.design.columns.slenderness import (
    ColumnSlendernessAxisBasis,
    ColumnSlendernessBasis,
    SWAY_PREVENTED,
)
from tbdy_engine.design.columns.slenderness_basis import (
    ColumnSlendernessAxisEvidence,
    ColumnSlendernessEvidence,
    FACTUAL_CLEAR_LENGTH_CANDIDATE_AUTHORITY,
    REGULATORY_FREE_LENGTH_AUTHORITY,
)
from tbdy_engine.design.columns.stability_stiffness_basis import (
    AssignedFrameBendingModifierEvidence,
    STATUS_REANALYSIS_REQUIRED,
    assess_ts500_eq713_stiffness_basis,
)
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


def _catalog():
    return build_rebar_catalog_from_rows(
        ({"Name": "14", "Diameter": 14.0}, {"Name": "20", "Diameter": 20.0}),
        name_field="Name",
        diameter_field="Diameter",
        diameter_unit="mm",
        source_name="fixture",
    )


def _inputs():
    return ColumnRebarDesignInputs(
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
    )


def _slenderness_basis():
    def axis(name):
        return ColumnSlendernessAxisBasis(
            axis=name,
            section_dimension_mm=800.0,
            free_length_ln_mm=3000.0,
            effective_length_factor_k=1.0,
            sway_classification=SWAY_PREVENTED,
            moment_ratio_m1_over_m2=0.0,
            source_refs=(f"fixture:{name}",),
        )

    return ColumnSlendernessBasis(
        component_id=COMP,
        m2=axis("M2"),
        m3=axis("M3"),
        source_refs=("fixture:slenderness",),
    )


def _slenderness_evidence_without_sway():
    def axis(name):
        return ColumnSlendernessAxisEvidence(
            axis=name,
            section_dimension_mm=800.0,
            factual_clear_length_candidate_mm=3000.0,
            factual_clear_length_source_ref=f"fixture:{name}:candidate",
            factual_clear_length_authority=FACTUAL_CLEAR_LENGTH_CANDIDATE_AUTHORITY,
            regulatory_free_length_ln_mm=3000.0,
            regulatory_free_length_source_ref=f"fixture:{name}:ln",
            regulatory_free_length_authority=REGULATORY_FREE_LENGTH_AUTHORITY,
        )

    return ColumnSlendernessEvidence(
        component_id=COMP,
        m2=axis("M2"),
        m3=axis("M3"),
        source_refs=("fixture:slenderness",),
    )


def _stiffness_reanalysis():
    return assess_ts500_eq713_stiffness_basis(
        (
            AssignedFrameBendingModifierEvidence(
                section_name="Column_80x80",
                member_kind="COLUMN",
                i2_modifier=0.7,
                i3_modifier=0.7,
                source_refs=("fixture:Column_80x80",),
            ),
        )
    )


def test_integrated_report_is_projection_only_and_includes_demand_eccentricity_layout_selection_details():
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
        rebar_catalog=_catalog(),
        rebar_inputs=_inputs(),
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


def test_integrated_report_marks_legacy_design_candidate_only_as_partial():
    result = evaluate_column_design(
        component_id=COMP,
        combo_definitions=(
            ColumnComboDefinition(
                name="ANY",
                combo_type="LINEAR_ADD",
                constituents=(
                    ComboPatternConstituent("D", 1.0),
                ),
            ),
        ),
        constituent_case_demands=(
            _state("I_END", 0.0),
            _state("J_END", 4.0),
        ),
        rebar_catalog=_catalog(),
        rebar_inputs=_inputs(),
        slenderness_basis=_slenderness_basis(),
    )

    assert (
        result.status
        == "SELECTED_DESIGN_CANDIDATE_ONLY"
    )
    assert (
        result.rebar_design.authority
        == "DESIGN_CANDIDATE_ONLY"
    )

    reports = build_vs6_column_design_engine_reports(
        result,
        section_name="Column_80x80",
    )

    composite = reports[0]
    assert composite.status == "PARTIAL"

    summary = {
        field.key: field.value
        for field in composite.summary_fields
    }

    assert (
        summary["rebar_design_status"]
        == "SELECTED_DESIGN_CANDIDATE_ONLY"
    )
    assert (
        summary["rebar_authority"]
        == "DESIGN_CANDIDATE_ONLY"
    )

    selection_report = next(
        item
        for item in reports
        if item.slice_id
        == "VS6-P6-COLUMN-REBAR-SELECTION"
    )

    assert selection_report.status == "PARTIAL"

    selection_summary = {
        field.key: field.value
        for field in selection_report.summary_fields
    }

    assert (
        selection_summary["authority"]
        == "DESIGN_CANDIDATE_ONLY"
    )

    assert any(
        "not ENGINE_SELECTED_REBAR" in warning
        for warning in selection_report.warnings
    )


def test_integrated_report_projects_reanalysis_required_and_stiffness_source_status():
    stiffness = _stiffness_reanalysis()
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
        rebar_catalog=_catalog(),
        rebar_inputs=_inputs(),
        slenderness_evidence=_slenderness_evidence_without_sway(),
        stability_stiffness_basis=stiffness,
    )

    assert result.status == "REANALYSIS_REQUIRED"
    assert stiffness.status == STATUS_REANALYSIS_REQUIRED
    reports = build_vs6_column_design_engine_reports(result, section_name="Column_80x80")
    composite = reports[0]
    assert composite.status == "REANALYSIS_REQUIRED"
    summary = {field.key: field.value for field in composite.summary_fields}
    assert summary["engine_status"] == "REANALYSIS_REQUIRED"
    assert summary["stability_stiffness_basis_status"] == STATUS_REANALYSIS_REQUIRED
    assert any(
        item.slice_id == "VS6-P6-TS500-STABILITY-STIFFNESS-BASIS"
        and item.status == "REANALYSIS_REQUIRED"
        for item in reports
    )
    assert result.rebar_design.authority == "NOT_SELECTED"
