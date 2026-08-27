from __future__ import annotations

from decimal import Decimal

from tbdy_engine.design.columns.column_rebar_design_engine import (
    ColumnRebarDesignInputs,
    design_column_longitudinal_rebar_from_etabs_requirement,
)
from tbdy_engine.design.columns.rebar_catalog import build_rebar_catalog_from_rows
from tbdy_engine.design.columns.rebar_requirement import (
    build_governing_required_rebar,
    evaluate_candidate_requirement_states,
)
from tbdy_engine.design.columns.rebar_selection import (
    ColumnDemandBasis,
    ColumnDemandState,
    ColumnRebarSelectionPolicy,
)
from tbdy_engine.design.columns.section_capacity import ColumnSectionMaterial
from tbdy_engine.features.column_design_rebar_evidence import (
    EtabsRequiredRebarComponent,
    EtabsRequiredRebarEvidence,
)


COMP = "Story1:C1:U1"


def _required(requirement_id, area, combo, location):
    return EtabsRequiredRebarEvidence(
        requirement_id=requirement_id,
        component_id=COMP,
        unique_name="U1",
        story="Story1",
        label="C1",
        assigned_section="ASSIGNED",
        design_section="DESIGN",
        design_combo_identity=("Strength", combo),
        location_mm=Decimal(str(location)),
        required_as_mm2=Decimal(str(area)),
        source_row_id=f"source:{requirement_id}",
        model_fingerprint="model:1",
        evidence_epoch_id="epoch:1",
        source_refs=(f"source-ref:{requirement_id}",),
    )


def _etabs_required():
    requirements = (
        _required("r1", 7000, "ULS1", 0),
        _required("r2", 8000, "ULS2", 3000),
    )
    return EtabsRequiredRebarComponent(
        component_id=COMP,
        unique_name="U1",
        story="Story1",
        label="C1",
        assigned_section="ASSIGNED",
        design_section="DESIGN",
        requirements=requirements,
        source_design_row_count=2,
        promoted_requirement_count=2,
        model_fingerprint="model:1",
        evidence_epoch_id="epoch:1",
        source_refs=("etabs-required:component",),
    )


def _catalog():
    return build_rebar_catalog_from_rows(
        (
            {"Name": "14", "Diameter": 14.0},
            {"Name": "20", "Diameter": 20.0},
            {"Name": "25", "Diameter": 25.0},
        ),
        name_field="Name",
        diameter_field="Diameter",
        diameter_unit="mm",
        source_name="ETABS:Reinforcing Bar Sizes:fixture",
    )


def _inputs(*, model="model:1", epoch="epoch:1", section="DESIGN"):
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
            minimum_eccentricity_status="RESOLVED",
            slenderness_status="RESOLVED",
            combination_scope_status="RESOLVED",
            review_refs=("demand-basis:fixture",),
        ),
        selection_policy=ColumnRebarSelectionPolicy(
            angle_count=36,
            axial_tolerance_n=1000.0,
        ),
        section_identity=section,
        model_fingerprint=model,
        evidence_epoch_id=epoch,
    )


def _demand():
    return ColumnDemandState(
        state_id="promoted:demand:1",
        component_id=COMP,
        output_case="ULS1",
        case_type="DesignStaticLinearExact",
        step_type=None,
        step_number=None,
        station_m=0.0,
        end_tag="I_END",
        nd_compression_n=500_000.0,
        m2_nmm=20_000_000.0,
        m3_nmm=10_000_000.0,
        source_identity="fixture",
    )


def test_governing_requirement_preserves_every_etabs_row_and_tdby_role_without_scalar_max():
    governing = build_governing_required_rebar(
        etabs_required=_etabs_required(),
        tdby_min_required_as_mm2=6400,
        tdby_min_source_refs=("TBDY_MIN_REQUIRED_REBAR:fixture",),
    )
    assert governing.authority == "GOVERNING_REQUIRED_REBAR"
    assert [item.role for item in governing.states].count("ETABS_REQUIRED_REBAR") == 2
    assert [item.role for item in governing.states].count("TBDY_MIN_REQUIRED_REBAR") == 1
    assert not hasattr(governing, "governing_required_as_mm2")

    trials = evaluate_candidate_requirement_states(
        candidate_id="candidate:7500",
        candidate_as_mm2=7500,
        requirements=governing,
    )
    by_id = {item.requirement_id: item.status for item in trials}
    assert by_id["r1"] == "SATISFIED"
    assert by_id["r2"] == "NOT_SATISFIED"
    assert by_id[f"tdby-min-required-rebar:{COMP}"] == "SATISFIED"


def test_design_informed_path_selects_only_after_all_source_distinct_area_requirements():
    result = design_column_longitudinal_rebar_from_etabs_requirement(
        inputs=_inputs(),
        rebar_catalog=_catalog(),
        promoted_demands=(_demand(),),
        etabs_required_rebar=_etabs_required(),
        tdby_min_required_as_mm2=6400,
        tdby_min_source_refs=("TBDY_MIN_REQUIRED_REBAR:fixture",),
    )
    assert result.status == "SELECTED_ENGINE_REBAR"
    assert result.authority == "ENGINE_SELECTED_REBAR"
    assert result.selection is not None
    assert result.selection.selected_candidate is not None
    selected_area = result.selection.selected_candidate.as_total_mm2
    assert selected_area >= 7000
    assert selected_area >= 8000
    assert selected_area >= 6400
    assert result.governing_required_rebar is not None
    assert result.requirement_trials


def test_model_epoch_or_design_section_mismatch_blocks_before_engine_selection():
    for inputs, expected in (
        (_inputs(model="other"), "BLOCKED_REQUIRED_REBAR_EVIDENCE_EPOCH"),
        (_inputs(epoch="other"), "BLOCKED_REQUIRED_REBAR_EVIDENCE_EPOCH"),
        (_inputs(section="OTHER"), "BLOCKED_REQUIRED_REBAR_SECTION"),
    ):
        result = design_column_longitudinal_rebar_from_etabs_requirement(
            inputs=inputs,
            rebar_catalog=_catalog(),
            promoted_demands=(_demand(),),
            etabs_required_rebar=_etabs_required(),
            tdby_min_required_as_mm2=6400,
            tdby_min_source_refs=("TBDY_MIN_REQUIRED_REBAR:fixture",),
        )
        assert result.status == expected
        assert result.authority == "NOT_SELECTED"
