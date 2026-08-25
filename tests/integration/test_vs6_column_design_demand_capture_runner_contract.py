from __future__ import annotations

import inspect

import tools.run_live_vs6_column_design_demand_capture as runner


def test_vs6_design_demand_capture_runner_is_read_only_and_stops_before_design():
    source = inspect.getsource(runner)
    for forbidden in (
        "RunAnalysis(",
        "StartDesign(",
        "SetPresentUnits(",
        ".Save(",
        "SetRebarColumn(",
        "SetSection(",
        "ENGINE_SELECTED_REBAR",
        "generate_rectangular_column_rebar_candidates(",
        "select_engine_rebar_for_demands(",
    ):
        assert forbidden not in source
    assert "COMPLETE_FACTUAL_COLUMN_DESIGN_DEMAND" in source
    assert "reinforcement_selected\": False" in source
    assert "section_capacity_computed\": False" in source


def test_vs6_design_demand_capture_runner_requires_explicit_units_and_outputs():
    source = inspect.getsource(runner)
    for token in (
        "--outputs",
        "--reviewed-force-unit",
        "--reviewed-moment-unit",
        "--reviewed-length-unit",
        "--reviewed-concrete-fc-unit",
        "--expected-model-fingerprint",
    ):
        assert token in source
