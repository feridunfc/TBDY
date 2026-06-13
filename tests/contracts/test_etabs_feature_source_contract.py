from __future__ import annotations

import copy
import json
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "tbdy_engine" / "catalogs" / "etabs_feature_source_contract.yaml"
SCHEMA = ROOT / "tbdy_engine" / "catalogs" / "schemas" / "etabs_feature_source_contract.schema.json"
FEATURE_SNAPSHOT_FIXTURE = ROOT / "tests" / "fixtures" / "feature_snapshot_c8_3_minimal_valid.json"


def _contract() -> dict:
    return yaml.safe_load(CONTRACT.read_text(encoding="utf-8"))


def _schema() -> dict:
    return json.loads(SCHEMA.read_text(encoding="utf-8"))


def _validator() -> Draft202012Validator:
    return Draft202012Validator(_schema())


def _errors(instance: dict):
    return list(_validator().iter_errors(instance))


def _sources() -> list[dict]:
    return list(_contract()["sources"])


def _by_id() -> dict[str, dict]:
    return {row["feature_id"]: row for row in _sources()}


def _current_resolved_feature_ids() -> set[str]:
    doc = json.loads(FEATURE_SNAPSHOT_FIXTURE.read_text(encoding="utf-8"))
    return {
        fid
        for snapshot in doc.get("snapshots", [])
        for fid, feature in (snapshot.get("features") or {}).items()
        if feature.get("status") == "RESOLVED"
    }


def test_etabs_feature_source_contract_exists():
    assert CONTRACT.is_file()
    assert SCHEMA.is_file()


def test_etabs_feature_source_contract_schema_validates():
    errors = _errors(_contract())
    assert not errors, [error.message for error in errors]


def test_all_current_resolved_features_have_source_contract_entry():
    current = _current_resolved_feature_ids()
    contracted = {row["feature_id"] for row in _sources()}
    assert current - contracted == set()
    assert len(current) == 28
    assert len(contracted & current) == 28


def test_no_future_locked_rebar_flexure_shear_capacity_sources_present():
    forbidden_roles = {
        "TBDY_MIN_REQUIRED_REBAR",
        "GOVERNING_REQUIRED_REBAR",
        "ENGINE_SELECTED_REBAR",
        "USER_PROVIDED_REBAR",
        "FINAL_DETAILING_REQUIRED",
    }
    forbidden_scopes = {
        "future_rebar_unlock",
        "future_flexure_unlock",
        "future_shear_unlock",
        "future_capacity_unlock",
        "capacity_design",
    }
    for row in _sources():
        assert row.get("semantic_role") not in forbidden_roles, row["feature_id"]
        assert row.get("source_scope") not in forbidden_scopes, row["feature_id"]
        assert row.get("locked_future_scope") is False


def test_source_contract_rejects_excel_production_source():
    doc = copy.deepcopy(_contract())
    doc["sources"][0]["source_type"] = "excel_production"
    assert _errors(doc)


def test_story_drift_source_requires_display_selection():
    for fid in ["story_drift_value", "story_drift_max_mm", "story_drift_output_case", "story_drift_direction"]:
        row = _by_id()[fid]
        assert row["source_type"] == "display_table"
        assert row["canonical_table_key"] == "story_drifts"
        assert row["etabs_table_name"] == "Story Drifts"
        assert row["display_selection_required"] is True
        assert "Drift" in row["required_columns"]


def test_story_max_over_avg_source_requires_display_selection():
    row = _by_id()["story_torsion_a1_coefficient"]
    assert row["canonical_table_key"] == "story_max_over_avg_drifts"
    assert row["etabs_table_name"] == "Story Max Over Avg Drifts"
    assert row["display_selection_required"] is True
    assert "Ratio" in row["required_columns"]


def test_base_reaction_source_requires_display_selection():
    for fid in ["base_reaction_fx", "base_reaction_fy", "base_reaction_x_kN", "base_reaction_y_kN"]:
        row = _by_id()[fid]
        assert row["canonical_table_key"] == "base_reactions"
        assert row["etabs_table_name"] == "Base Reactions"
        assert row["display_selection_required"] is True
        assert {"FX", "FY"}.issubset(set(row["required_columns"]))


def test_story_base_sources_default_preferred_output_case():
    for fid, row in _by_id().items():
        if row.get("canonical_table_key") in {"story_drifts", "story_max_over_avg_drifts", "base_reactions"}:
            assert row["preferred_output_case_default"] == "Crack_SeisY_UpSoil", fid


def test_base_reaction_source_does_not_require_story_or_component_id():
    for fid in ["base_reaction_fx", "base_reaction_fy", "base_reaction_x_kN", "base_reaction_y_kN"]:
        requirements = _by_id()[fid]["identity_requirements"]
        assert requirements["requires_story"] is False
        assert requirements["requires_component_id"] is False
        rule = "\n".join(_by_id()[fid]["row_selection_rule"])
        assert "do not require Story" in rule
        assert "do not require component_id" in rule


def test_modal_mass_source_uses_max_cumulative_not_fixed_mode_10():
    for fid in ["modal_sum_ux", "modal_sum_uy"]:
        row = _by_id()[fid]
        assert row["semantic_role"] == "MODAL_CUMULATIVE_PARTICIPATION"
        assert row["aggregation"] == "max_cumulative"
        assert "fixed_mode_10_only" in row["forbidden_source"]
        assert any("maximum cumulative" in rule for rule in row["row_selection_rule"])


def test_direct_api_geometry_sources_are_not_section_name_inference():
    for fid in ["beam_width_mm", "beam_depth_mm", "beam_length_mm"]:
        row = _by_id()[fid]
        assert row["source_type"] == "direct_api"
        assert row["api_path"]
        assert row["raw_fields"]
        assert "section_name_inference" in row["forbidden_source"]


def test_manual_ductility_class_source_does_not_infer_from_combo_name():
    contract = _contract()
    assert not any(row["feature_id"] == "ductility_class" for row in contract["sources"])
    not_applicable = contract.get("not_applicable_semantic_items", [])
    assert any(item.get("semantic_item") == "ductility_class" for item in not_applicable)
    text = yaml.safe_dump(contract, sort_keys=True)
    assert "ETABS_combo_name_inference" not in text


def test_source_contract_rejects_check_result_or_verdict_semantics():
    for key, value in [
        ("check_id", "beam_geometry_min_width"),
        ("verdict", "OK"),
        ("engineering_verdict", "FAIL"),
        ("source_status", "OK"),
    ]:
        doc = copy.deepcopy(_contract())
        doc["sources"][0][key] = value
        assert _errors(doc), key


def test_source_contract_rejects_future_scope_unlock():
    doc = copy.deepcopy(_contract())
    doc["sources"][0]["source_scope"] = "future_capacity_unlock"
    assert _errors(doc)
