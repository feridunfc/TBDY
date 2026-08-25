import inspect

import tools.run_live_vs6_column_rebar_selection as runner


def test_live_rebar_selection_runner_is_read_only_and_has_explicit_basis_gates():
    source = inspect.getsource(runner)
    forbidden = (
        "RunAnalysis(",
        "StartDesign(",
        "SetPresentUnits(",
        ".Save(",
        "SetRebarColumn(",
        "SetSection(",
    )
    assert all(token not in source for token in forbidden)
    assert "analysis-order-status" in source
    assert "minimum-eccentricity-status" in source
    assert "slenderness-status" in source
    assert "combination-scope-status" in source
    assert "ENGINE_SELECTED_REBAR" in source
    assert "final_or_provided_rebar_count\": 0" in source


def test_live_rebar_selection_runner_requires_explicit_project_specific_layout_inputs():
    source = inspect.getsource(runner)
    for token in (
        "--reviewed-clear-cover-mm",
        "--reviewed-layout-tie-diameter-mm",
        "--reviewed-aggregate-max-mm",
        "--reviewed-bar-diameters-mm",
        "--reviewed-fcd-mpa",
        "--reviewed-fyd-mpa",
        "--angle-count",
        "--axial-tolerance-kn",
    ):
        assert token in source
