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
    ):
        assert forbidden not in source

    assert "capture_etabs_combo_definitions" in source
    assert "capture_etabs_rebar_catalog_evidence" in source
    assert "promote_etabs_rebar_catalog" in source
    assert "evaluate_column_design" in source


def test_combination_scope_is_engine_derived_not_cli_authorized():
    source = inspect.getsource(runner)
    assert "--combination-scope-status" not in source
    assert 'combination_scope_status="BLOCKED"' in source
    assert '"combination_scope_status": "ENGINE_DERIVED"' in source


def test_bar_library_is_factual_etabs_catalog_not_cli_diameter_list():
    source = inspect.getsource(runner)
    assert "--reviewed-bar-diameters-mm" not in source
    assert "--rebar-name-field" in source
    assert "--rebar-diameter-field" in source
    assert "--rebar-diameter-unit" in source


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
