from dataclasses import replace

import pytest

from tbdy_engine.design.columns.column_rebar_design_engine import ColumnRebarDesignInputs, design_column_longitudinal_rebar_from_etabs_requirement
from tbdy_engine.design.columns.column_shear_demand import CAPACITY_PROVEN, resolve_exact_column_end_moment_capacity
from tbdy_engine.design.columns.rebar_catalog import build_rebar_catalog_from_rows
from tbdy_engine.design.columns.rebar_layout import ColumnRebarLayoutInputs, generate_rectangular_column_rebar_candidates
from tbdy_engine.design.columns.rebar_requirement import build_governing_required_rebar
from tbdy_engine.design.columns.rebar_selection import ColumnDemandBasis, ColumnDemandState, ColumnRebarSelectionPolicy
from tbdy_engine.design.columns.section_capacity import ColumnSectionMaterial
from tbdy_engine.features.column_design_rebar_evidence import ColumnDesignRebarIdentity, build_column_design_rebar_evidence, resolve_etabs_required_rebar
from tbdy_engine.regulatory.units import UNIT_MM

COMP = "+0.00:C2:236"
SECTION = "C80x80"
MATERIAL = ColumnSectionMaterial(fck_mpa=35.0, fcd_mpa=35.0 / 1.5, fyd_mpa=500.0 / 1.15)


def _catalog():
    return build_rebar_catalog_from_rows(({"Name":"14","Diameter":14.0},{"Name":"20","Diameter":20.0},{"Name":"25","Diameter":25.0}), name_field="Name", diameter_field="Diameter", diameter_unit="mm", source_name="ETABS:Reinforcing Bar Sizes")


def _basis():
    return ColumnDemandBasis(analysis_order_status="RESOLVED", minimum_eccentricity_status="RESOLVED", slenderness_status="RESOLVED", combination_scope_status="RESOLVED", review_refs=("review:p8a",))


def _inputs(*, preferred=None, refs=()):
    return ColumnRebarDesignInputs(component_id=COMP, width_mm=800.0, depth_mm=800.0, clear_cover_mm=40.0, tie_diameter_mm=10.0, aggregate_max_mm=25.0, material=MATERIAL, demand_basis=_basis(), selection_policy=ColumnRebarSelectionPolicy(angle_count=36, axial_tolerance_n=1000.0), section_identity=SECTION, preferred_bar_diameter_mm=preferred, candidate_preference_refs=refs)


def _demand():
    return ColumnDemandState(state_id="promoted:1", component_id=COMP, output_case="ULS_17", case_type="DesignStaticLinearExact", step_type=None, step_number=None, station_m=0.0, end_tag="I_END", nd_compression_n=1_000_000.0, m2_nmm=20_000_000.0, m3_nmm=10_000_000.0, source_identity="promoted:fixture")


def _required(area=7000.0):
    identity = ColumnDesignRebarIdentity(component_id=COMP, story="+0.00", object_name="C2", label="C2", unique_name="236", section_identity=SECTION)
    evidence = build_column_design_rebar_evidence(model_fingerprint="model:1", identity=identity, rows=({"FrameName":"C2","MyOption":2,"Location":0.0,"PMMCombo":"ULS_17","PMMArea":area,"PMMRatio":0.0,"ErrorSummary":"","WarningSummary":""},), source_length_unit=UNIT_MM, unit_provenance_refs=("CSI:GetPresentUnits_2",))
    return resolve_etabs_required_rebar(evidence, expected_model_fingerprint="model:1", expected_component_id=COMP, expected_section_identity=SECTION)


def test_etabs_requirement_does_not_become_selected_state_automatically():
    required = _required()
    result = design_column_longitudinal_rebar_from_etabs_requirement(inputs=_inputs(), rebar_catalog=_catalog(), promoted_demands=(), etabs_required_rebar=required)
    assert required.authority == "ETABS_REQUIRED_REBAR"
    assert result.authority == "NOT_SELECTED"
    assert result.status == "NO_DATA"


def test_governing_requirement_preserves_source_roles():
    ledger = build_governing_required_rebar(etabs_required=_required(), width_mm=800.0, depth_mm=800.0, tdby_rho_min=0.01, tdby_source_refs=("TBDY:min",))
    assert {item.role for item in ledger.states} == {"ETABS_REQUIRED_REBAR", "TBDY_MIN_REQUIRED_REBAR"}
    assert ledger.governing_required_as_mm2 == pytest.approx(7000.0)
    assert ledger.governing_roles == ("ETABS_REQUIRED_REBAR",)


def test_required_area_gate_rejects_small_candidates_and_selects_real_coordinates():
    result = design_column_longitudinal_rebar_from_etabs_requirement(inputs=_inputs(), rebar_catalog=_catalog(), promoted_demands=(_demand(),), etabs_required_rebar=_required())
    assert result.status == "SELECTED_ENGINE_REBAR"
    assert result.authority == "ENGINE_SELECTED_REBAR"
    assert any(item.status == "REJECTED_INSUFFICIENT_AS" for item in result.area_gate_trials)
    selected = result.selection.selected_candidate
    assert selected.as_total_mm2 >= 7000.0
    assert selected.bar_count == len(selected.bars)
    assert len({(bar.x2_mm, bar.x3_mm) for bar in selected.bars}) == selected.bar_count


def test_preference_is_search_input_only_and_requires_provenance():
    result = design_column_longitudinal_rebar_from_etabs_requirement(inputs=_inputs(preferred=25.0, refs=("PROJECT_PREF:D25",)), rebar_catalog=_catalog(), promoted_demands=(_demand(),), etabs_required_rebar=_required())
    assert result.status == "SELECTED_ENGINE_REBAR"
    assert result.candidate_preference_refs == ("PROJECT_PREF:D25",)
    assert result.governing_required_rebar.governing_required_as_mm2 == pytest.approx(7000.0)
    blocked = design_column_longitudinal_rebar_from_etabs_requirement(inputs=_inputs(preferred=25.0), rebar_catalog=_catalog(), promoted_demands=(_demand(),), etabs_required_rebar=_required())
    assert blocked.status == "BLOCKED_CANDIDATE_PREFERENCE_PROVENANCE"


def test_no_feasible_candidate_and_missing_evidence_fail_closed():
    no_layout = design_column_longitudinal_rebar_from_etabs_requirement(inputs=_inputs(), rebar_catalog=_catalog(), promoted_demands=(_demand(),), etabs_required_rebar=_required(30000.0))
    assert no_layout.status == "NO_FEASIBLE_LAYOUT_REQUIRED_AS"
    assert no_layout.authority == "NOT_SELECTED"
    missing = design_column_longitudinal_rebar_from_etabs_requirement(inputs=_inputs(), rebar_catalog=_catalog(), promoted_demands=(_demand(),), etabs_required_rebar=None)
    assert missing.status == "NO_DATA_ETABS_REQUIRED_REBAR"
    assert missing.authority == "NOT_SELECTED"


def test_wrong_section_identity_fails_closed():
    result = design_column_longitudinal_rebar_from_etabs_requirement(inputs=replace(_inputs(), section_identity="OTHER"), rebar_catalog=_catalog(), promoted_demands=(_demand(),), etabs_required_rebar=_required())
    assert result.status == "BLOCKED_REQUIRED_REBAR_IDENTITY"


def test_existing_physical_spacing_and_fit_kernel_remains_authority():
    population = generate_rectangular_column_rebar_candidates(ColumnRebarLayoutInputs(width_mm=180.0, depth_mm=180.0, clear_cover_mm=50.0, tie_diameter_mm=12.0, aggregate_max_mm=32.0, allowed_bar_diameters_mm=(25.0,)))
    assert population.status == "NO_FEASIBLE_LAYOUT"


def test_selected_coordinates_feed_existing_p7_capacity_adapter_directly():
    result = design_column_longitudinal_rebar_from_etabs_requirement(inputs=_inputs(), rebar_catalog=_catalog(), promoted_demands=(_demand(),), etabs_required_rebar=_required())
    selected = result.selection.selected_candidate
    p7 = resolve_exact_column_end_moment_capacity(component_id=COMP, end_tag="BOTTOM", direction="V2", moment_sign=1, nd_compression_kn=1000.0, width_mm=800.0, depth_mm=800.0, bars=selected.bars, material=MATERIAL, source_refs=("ENGINE_SELECTED_REBAR:" + selected.candidate_id,), angle_count=36)
    assert p7.status == CAPACITY_PROVEN
    assert p7.moment_axis == "M3"


def test_repeated_selection_is_identical():
    kwargs = dict(inputs=_inputs(), rebar_catalog=_catalog(), promoted_demands=(_demand(),), etabs_required_rebar=_required())
    assert design_column_longitudinal_rebar_from_etabs_requirement(**kwargs) == design_column_longitudinal_rebar_from_etabs_requirement(**kwargs)
