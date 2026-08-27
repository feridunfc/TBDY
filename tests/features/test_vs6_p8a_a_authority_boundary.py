from __future__ import annotations

import importlib.util
import inspect

from tbdy_engine.design.columns import column_rebar_design_engine
from tbdy_engine.features import column_design_rebar_evidence


def test_p8a_a_exposes_factual_rebar_evidence_not_engine_selected_rebar():
    source = inspect.getsource(column_design_rebar_evidence)
    assert "ENGINE_SELECTED_REBAR" not in source
    assert hasattr(column_design_rebar_evidence, "promote_etabs_required_rebar")
    assert hasattr(column_design_rebar_evidence, "EtabsRequiredRebarEvidence")


def test_p8a_shortcut_selection_wrapper_is_removed():
    assert not hasattr(
        column_rebar_design_engine,
        "design_column_longitudinal_rebar_from_etabs_requirement",
    )
    source = inspect.getsource(column_rebar_design_engine)
    assert "EtabsRequiredRebarComponent" not in source
    assert "GoverningRequiredRebar" not in source
    assert "tdby_min_required_as_mm2" not in source


def test_p8a_unreviewed_governing_requirement_module_is_quarantined():
    assert importlib.util.find_spec("tbdy_engine.design.columns.rebar_requirement") is None
