from __future__ import annotations

from pathlib import Path
import yaml

from tbdy_engine.features.result_evidence import (
    BASE_REACTION_IDENTITY_FIELDS,
    BASE_REACTION_PAYLOAD_FIELDS,
    PIER_FORCE_IDENTITY_FIELDS,
    PIER_FORCE_PAYLOAD_FIELDS,
    STORY_FORCE_IDENTITY_FIELDS,
    STORY_FORCE_PAYLOAD_FIELDS,
)
from tbdy_engine.providers.table_registry import TableRegistry

ROOT = Path(__file__).resolve().parents[2]
OVERLAY = ROOT / "tbdy_engine/catalogs/table_registry_p2_10_wall_pack_b.yaml"


def test_live_result_source_overlay_preserves_full_capture_but_identity_is_not_payload():
    raw = yaml.safe_load(OVERLAY.read_text(encoding="utf-8"))
    tables = raw["tables"]
    expected = {
        "base_reactions": (BASE_REACTION_IDENTITY_FIELDS, BASE_REACTION_PAYLOAD_FIELDS, 96, "Base Reactions"),
        "pier_forces": (PIER_FORCE_IDENTITY_FIELDS, PIER_FORCE_PAYLOAD_FIELDS, 4416, "Pier Forces"),
        "story_forces": (STORY_FORCE_IDENTITY_FIELDS, STORY_FORCE_PAYLOAD_FIELDS, 392, "Story Forces"),
    }
    for key, (identity, payload, rows, live_name) in expected.items():
        item = tables[key]
        assert item["evidence_status"] == "VERIFIED_LIVE"
        assert item["live_table_name"] == live_name
        assert tuple(item["required_columns"]) == identity + payload
        assert set(identity).isdisjoint(payload)
        assert item["verified_by"]["return_code"] == 0
        assert item["verified_by"]["observed_rows"] == rows
        assert item["verified_by"]["full_capture"] is True
        assert item["check_unlock_allowed"] is False


def test_exact_identity_and_payload_field_sets_are_frozen():
    assert BASE_REACTION_IDENTITY_FIELDS == ("OutputCase", "CaseType", "StepType", "StepNumber")
    assert BASE_REACTION_PAYLOAD_FIELDS == ("FX", "FY", "FZ", "MX", "MY", "MZ", "X", "Y", "Z")
    assert PIER_FORCE_IDENTITY_FIELDS == (
        "Story", "Pier", "OutputCase", "CaseType", "StepType", "StepNumber", "Location"
    )
    assert PIER_FORCE_PAYLOAD_FIELDS == ("P", "V2", "V3", "T", "M2", "M3")
    assert STORY_FORCE_IDENTITY_FIELDS == (
        "Story", "OutputCase", "CaseType", "StepType", "StepNumber", "Location"
    )
    assert STORY_FORCE_PAYLOAD_FIELDS == ("P", "VX", "VY", "T", "MX", "MY")


def test_effective_table_registry_exposes_story_forces_and_pack_b_promotions():
    registry = TableRegistry.from_catalog_dir(ROOT / "tbdy_engine/catalogs")
    assert registry.preferred_actual_name("base_reactions") == "Base Reactions"
    assert registry.preferred_actual_name("pier_forces") == "Pier Forces"
    assert registry.preferred_actual_name("story_forces") == "Story Forces"
    for key in ("base_reactions", "pier_forces", "story_forces"):
        assert registry.tables[key]["evidence_status"] == "VERIFIED_LIVE"


def test_raw_verified_live_is_not_derived_vt_or_ndm_verification():
    text = OVERLAY.read_text(encoding="utf-8")
    assert "derived_quantities_forbidden: [Vt]" in text
    assert "derived_quantities_forbidden: [Ndm]" in text
    assert "check_unlock_allowed: false" in text
    feature_overlay = (ROOT / "tbdy_engine/catalogs/feature_catalog_p2_10_wall_pack_b.yaml").read_text(encoding="utf-8")
    assert "Vt:" not in feature_overlay
    assert "Ndm:" not in feature_overlay
    assert "wall_special_branch_7_6_1_3_applies:" not in feature_overlay
    assert "wall_regulatory_structural_system_classification:" not in feature_overlay


def test_pack_b_does_not_contract_unrequired_result_sources():
    text = OVERLAY.read_text(encoding="utf-8")
    assert "Diaphragm Forces" not in text
    assert "Joint Reactions" not in text
