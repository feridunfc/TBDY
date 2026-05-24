
from tools.inspect_actual_combo_sources_v1 import (
    extract_candidates_from_obj,
    is_combo_key,
    is_combo_value,
    choose_for_row,
    candidate_index,
)

def test_source_inspector_accepts_real_design_combo():
    obj = {"evidence": {"beam_design_summary": {"Combo": "K_E_X"}}}
    found = extract_candidates_from_obj(obj, "final_engine_report_combo_resolved.json.checks[0]")
    assert len(found) == 1
    assert found[0]["candidate"] == "K_E_X"
    assert found[0]["family"] == "K_E"

def test_source_inspector_rejects_metadata_family():
    assert not is_combo_key("combo_family")
    assert not is_combo_value("K_E")
    obj = {"combo_family": "K_E", "raw_combo": "UNEXPOSED_ETABS_COMBO::K_E"}
    assert extract_candidates_from_obj(obj, "final_engine_report_combo_resolved.json.checks[0]") == []

def test_choose_for_row_requires_unique_family_candidate():
    candidates = [
        {"candidate": "K_E_X", "family": "K_E", "field": "Combo", "source": "x", "resolved_by": "alias_exact", "confidence": 0.9},
    ]
    row = {"combo_required_family": "K_E"}
    chosen = choose_for_row(row, candidate_index(candidates))
    assert chosen["candidate"] == "K_E_X"

def test_choose_for_row_does_not_inject_ambiguous_family():
    candidates = [
        {"candidate": "K_E_X", "family": "K_E", "field": "Combo", "source": "x"},
        {"candidate": "K_E_Y", "family": "K_E", "field": "Combo", "source": "x"},
    ]
    row = {"combo_required_family": "K_E"}
    assert choose_for_row(row, candidate_index(candidates)) == {}
