from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CATALOGS = ROOT / "tbdy_engine" / "catalogs"

ALLOWED_VERIFIED = {
    "frame_assignments_summary",
    "concrete_rectangular_frame_sections",
    "modal_participating_mass",
    "story_drifts",
    "story_max_over_avg_drifts",
    "base_reactions",
    "material_list_by_story",
    "concrete_material_properties",
    "rebar_material_properties",
    "frame_section_assignments",
    "frame_section_material_assignments",
    "area_assignments_summary",
    "wall_section_properties",
    "pier_assignments",
    # C13.2-P4 promoted blocked sources and live-proved supporting context.
    "material_properties",
    "story_definitions",
    "pier_section_properties",
    "wall_bays",
    "wall_object_connectivity",
}
LEGACY_COMPATIBILITY_ALIASES = {
    "frame_assignments": "frame_assignments_summary",
    "frame_section_properties": "concrete_rectangular_frame_sections",
    "modal_results": "modal_participating_mass",
    "material_concrete_data": "concrete_material_properties",
    "material_rebar_data": "rebar_material_properties",
    "wall_section_data": "wall_section_properties",
}

FORBIDDEN_CHANGED_PATHS = (
    "tbdy_engine/features/resolver/live_smoke.py",
    "tbdy_engine/checks/engine.py",
    "tools/render_product_report.py",
    "apps/",
    "runtime/",
    "archx/",
    "runner_v2/",
)


def load_yaml(name: str):
    return yaml.safe_load((CATALOGS / name).read_text(encoding="utf-8"))


def table_registry():
    return load_yaml("table_registry.yaml")["tables"]


def test_table_registry_preserves_constitution_version_1_0():
    assert load_yaml("table_registry.yaml")["metadata"]["version"] == "1.0"


def test_c13_2_p1_verified_families_are_represented_in_table_registry():
    tables = table_registry()
    assert ALLOWED_VERIFIED.issubset(tables.keys())


def test_only_allowed_families_are_promoted_verified_live():
    verified = {
        key
        for key, entry in table_registry().items()
        if entry["evidence_status"] == "VERIFIED_LIVE" and not entry.get("compatibility_alias_for")
    }
    assert verified == ALLOWED_VERIFIED


def test_legacy_table_keys_are_preserved_as_compatibility_aliases():
    tables = table_registry()
    for alias_key, target_key in LEGACY_COMPATIBILITY_ALIASES.items():
        assert alias_key in tables
        assert tables[alias_key]["compatibility_alias_for"] == target_key
        assert tables[alias_key]["live_table_name"] == tables[target_key]["live_table_name"]
        assert tables[alias_key]["check_unlock_allowed"] is False


def test_material_properties_promotion_does_not_use_material_list_tables():
    material = table_registry()["material_properties"]
    assert material["evidence_status"] in {"NEEDS_LIVE_PROBE", "VERIFIED_LIVE"}
    assert "Material List" not in material["live_table_name"]
    assert set(material["must_not_use"]) >= {
        "Material List by Story",
        "Material List by Object Type",
        "Material List by Section Prop",
    }


def test_frame_section_source_distinction_is_preserved():
    tables = table_registry()
    material_mapping = tables["frame_section_material_assignments"]
    assignment_context = tables["frame_section_assignments"]
    assert material_mapping["live_table_name"] == "Frame Section Property Definitions - Summary"
    assert "Material" in material_mapping["required_columns"]
    assert material_mapping["source_role"] == "section_property_material_mapping"
    assert assignment_context["live_table_name"] == "Frame Assignments - Section Properties"
    assert "Material" not in assignment_context["required_columns"]
    assert assignment_context["source_role"] == "section_assignment_context_only"


def test_story_definitions_and_pier_section_properties_keep_check_unlock_locked():
    tables = table_registry()
    assert tables["story_definitions"]["evidence_status"] in {"NEEDS_LIVE_PROBE", "VERIFIED_LIVE"}
    assert tables["pier_section_properties"]["evidence_status"] in {"NEEDS_LIVE_PROBE", "VERIFIED_LIVE"}
    assert tables["story_definitions"]["check_unlock_allowed"] is False
    assert tables["pier_section_properties"]["check_unlock_allowed"] is False


def test_pier_forces_remain_semantic_review_and_locked():
    pier_forces = table_registry()["pier_forces"]
    assert pier_forces["evidence_status"] == "SEMANTIC_REVIEW"
    assert pier_forces["check_unlock_allowed"] is False


def test_all_source_contract_entries_have_check_unlock_allowed_false():
    for key, entry in table_registry().items():
        assert entry["check_unlock_allowed"] is False, key
    sources = load_yaml("etabs_feature_source_contract.yaml")["sources"]
    for source in sources:
        assert source["check_unlock_allowed"] is False, source["feature_id"]


def test_feature_ids_do_not_contain_result_terms():
    forbidden = ("pass", "fail", "ok", "verdict", "check_result")
    sources = load_yaml("etabs_feature_source_contract.yaml")["sources"]
    for source in sources:
        feature_id = source["feature_id"].lower()
        assert all(term not in feature_id for term in forbidden), source["feature_id"]


def test_forbidden_runtime_files_not_in_changed_manifest():
    manifest = (ROOT / "c13_2_p2_changed_files.txt").read_text(encoding="utf-8")
    for forbidden in FORBIDDEN_CHANGED_PATHS:
        assert forbidden not in manifest


def test_validation_tool_passes():
    result = subprocess.run(
        [sys.executable, "tools/validate_c13_2_p2_verified_source_contracts.py"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert '"safe_to_implement_checks_now": false' in result.stdout


def test_etabs_feature_source_contract_preserves_legacy_source_entry_shape():
    sources = load_yaml("etabs_feature_source_contract.yaml")["sources"]
    required = {
        "source_type",
        "source_owner",
        "row_selection_rule",
        "evidence_required",
        "display_selection_required",
    }
    for source in sources:
        assert required.issubset(source.keys()), source["feature_id"]
        assert source["source_type"] in {"display_table", "direct_api"}
        assert source["source_owner"] == "ETABS"
        assert source["evidence_required"] is True


def test_etabs_feature_source_ids_exist_in_feature_catalog():
    feature_catalog = CATALOGS / "feature_catalog.yaml"
    if not feature_catalog.exists():
        # Package-local validation may not include unchanged legacy catalogs.
        return
    features = set(load_yaml("feature_catalog.yaml")["features"])
    sources = load_yaml("etabs_feature_source_contract.yaml")["sources"]
    unknown = sorted(source["feature_id"] for source in sources if source["feature_id"] not in features)
    assert unknown == []



def test_legacy_constitution_specific_source_contract_rules_are_preserved():
    sources = {row["feature_id"]: row for row in load_yaml("etabs_feature_source_contract.yaml")["sources"]}
    for fid in ["story_drift_value", "story_drift_max_mm", "story_drift_output_case", "story_drift_direction"]:
        row = sources[fid]
        assert row["canonical_table_key"] == "story_drifts"
        assert row["display_selection_required"] is True
        assert row["preferred_output_case_default"] == "Crack_SeisY_UpSoil"

    for fid in ["base_reaction_fx", "base_reaction_fy", "base_reaction_x_kN", "base_reaction_y_kN"]:
        row = sources[fid]
        assert row["canonical_table_key"] == "base_reactions"
        assert row["display_selection_required"] is True
        assert row["identity_requirements"] == {"requires_story": False, "requires_component_id": False}

    for fid in ["modal_sum_ux", "modal_sum_uy"]:
        row = sources[fid]
        assert row["aggregation"] == "max_cumulative"
        assert "fixed_mode_10_only" in set(row["forbidden_source"])

    for fid in ["beam_width_mm", "beam_depth_mm", "beam_length_mm"]:
        row = sources[fid]
        assert row["source_type"] == "direct_api"
        assert "section_name_inference" in set(row["forbidden_source"])


def test_direct_api_sources_preserve_legacy_api_path_and_raw_fields_schema():
    sources = {row["feature_id"]: row for row in load_yaml("etabs_feature_source_contract.yaml")["sources"]}
    for fid in ["beam_width_mm", "beam_depth_mm", "beam_length_mm"]:
        row = sources[fid]
        assert row["source_type"] == "direct_api"
        assert isinstance(row.get("api_path"), list) and row["api_path"]
        assert isinstance(row.get("raw_fields"), list) and row["raw_fields"]

