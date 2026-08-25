import inspect

import tools.run_live_vs6_column_design_engine as runner
from tbdy_engine.providers.etabs_combo_definition_provider import (
    EtabsComboConstituentEvidence,
    EtabsComboDefinitionEvidence,
)


def test_integrated_live_runner_is_read_only_and_uses_production_engines():
    source = inspect.getsource(runner)
    for forbidden in (
        "RunAnalysis(",
        "StartDesign(",
        "SetPresentUnits(",
        ".Save(",
        "SetRebarColumn(",
        "SetSection(",
        "build_linear_combo_design_demands(",
        "verify_observed_combo_rows_are_generated_subset(",
        "generate_rectangular_column_rebar_candidates(",
        "select_engine_rebar_for_demands(",
        "apply_ts500_minimum_eccentricity(",
        "evaluate_ts500_column_slenderness(",
    ):
        assert forbidden not in source

    assert "capture_etabs_combo_definitions" in source
    assert "capture_etabs_rebar_catalog_evidence" in source
    assert "promote_live_proven_etabs_rebar_catalog" in source
    assert "evaluate_column_design" in source
    assert "build_vs6_column_design_engine_reports" in source
    assert '"report_contributions"' in source


def test_combination_scope_is_engine_derived_not_cli_authorized():
    source = inspect.getsource(runner)
    assert "--combination-scope-status" not in source
    assert 'combination_scope_status="BLOCKED"' in source
    assert '"combination_scope_status": "ENGINE_DERIVED"' in source


def test_minimum_eccentricity_is_engine_derived_not_cli_authorized():
    source = inspect.getsource(runner)
    assert "--minimum-eccentricity-status" not in source
    assert 'minimum_eccentricity_status="BLOCKED"' in source
    assert '"minimum_eccentricity_status": "ENGINE_DERIVED_TS500_6.3.10"' in source


def test_slenderness_is_engine_derived_not_cli_authorized_or_factual_length_promoted_here():
    source = inspect.getsource(runner)
    assert "--slenderness-status" not in source
    assert 'slenderness_status="BLOCKED"' in source
    assert '"slenderness_status": "ENGINE_DERIVED_TS500_7.6_BLOCKED_PENDING_REGULATORY_BASIS"' in source
    assert "analysis_clear_length_candidate_m" not in source
    assert "slenderness_basis=" not in source


def test_bar_library_uses_live_proven_factual_etabs_schema_not_cli_field_or_diameter_lists():
    source = inspect.getsource(runner)
    assert "--reviewed-bar-diameters-mm" not in source
    assert "--rebar-name-field" not in source
    assert "--rebar-diameter-field" not in source
    assert "--rebar-diameter-unit" not in source
    assert "promote_live_proven_etabs_rebar_catalog" in source
    assert 'reviewed_length_unit=args.reviewed_length_unit' in source


def test_factual_combo_traversal_collects_recursive_load_cases_without_classifying_them():
    child = EtabsComboDefinitionEvidence(
        name="SUB",
        combo_type_code=1,
        combo_type="ENVELOPE",
        constituents=(EtabsComboConstituentEvidence(0, 0, "LOAD_CASE", "RSX", 1.0),),
        nested_combos=(),
        raw_get_type_combo="raw",
        raw_get_case_list="raw",
    )
    top = EtabsComboDefinitionEvidence(
        name="TOP",
        combo_type_code=0,
        combo_type="LINEAR_ADD",
        constituents=(
            EtabsComboConstituentEvidence(0, 0, "LOAD_CASE", "G", 1.0),
            EtabsComboConstituentEvidence(1, 1, "LOAD_COMBO", "SUB", 1.0),
        ),
        nested_combos=(child,),
        raw_get_type_combo="raw",
        raw_get_case_list="raw",
    )

    assert runner._all_load_case_names((top,)) == ("G", "RSX")
    definition = runner._engine_definition(top)
    assert definition.name == "TOP"
    assert definition.constituents[1].cname_type == "LOAD_COMBO"
