from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[2]
CATALOG_DIR = ROOT / "tbdy_engine" / "catalogs"


def load(name):
    return yaml.safe_load((CATALOG_DIR / name).read_text(encoding="utf-8"))


def test_combo_policy_has_full_canonical_taxonomy_and_aliases():
    data = load("load_combo_policy.yaml")
    families = set(data["combo_families"])
    assert {
        "GRAV_SERVICE", "GRAV_STRENGTH", "DUCTILE_X", "DUCTILE_Y", "CAPACITY_X", "CAPACITY_Y",
        "DISP_X", "DISP_Y", "MODAL", "SOIL", "TEMP_POS", "TEMP_NEG", "NONE",
    } <= families
    assert data["combo_family_aliases"]["DUCTILE_X_OR_Y"]["expands_to"] == ["DUCTILE_X", "DUCTILE_Y"]
    assert data["combo_family_aliases"]["CAPACITY_X_OR_Y"]["expands_to"] == ["CAPACITY_X", "CAPACITY_Y"]
    assert data["combo_family_aliases"]["DISP_X_OR_Y"]["expands_to"] == ["DISP_X", "DISP_Y"]
    assert data["combo_families"]["DISP_X"]["read_only"] is True
    assert data["combo_families"]["DISP_X"]["reinforcement_design_allowed"] is False
    assert data["policy"]["unknown_combo_behavior"] == "diagnostic"


def test_design_combo_matrix_covers_element_purpose_contract():
    rows = {(r["element_type"], r["purpose"]) for r in load("design_combo_matrix.yaml")["design_mappings"]}
    expected = {
        ("beam", "geometry"), ("beam", "flexure"), ("beam", "shear"), ("beam", "capacity_design_shear"),
        ("column", "geometry"), ("column", "pmm"), ("column", "shear"),
        ("story", "drift"), ("story", "torsion_A1"),
        ("global", "modal_mass"), ("global", "base_shear"),
        ("wall", "pier_design"), ("wall", "shear"),
    }
    assert expected <= rows


def test_section_state_policy_maps_every_combo_family():
    families = set(load("load_combo_policy.yaml")["combo_families"])
    mapping = set(load("section_state_policy.yaml")["combo_family_to_section_state"])
    assert families <= mapping


def test_no_forbidden_feature_names_and_user_provided_rebar_role_exists():
    features = load("feature_catalog.yaml")["features"]
    for name in features:
        lowered = name.lower()
        assert not any(term in lowered for term in ["ratio", "status", "pass", "fail", "ok"]), name
    roles = {f["semantic_role"] for f in features.values()}
    assert "USER_PROVIDED_REBAR" in roles
    assert "beam_design_selection_status" not in features


def test_scope_alignment_is_bidirectional():
    checks = set(load("check_catalog.yaml")["checks"])
    reverse = {r["check_catalog_key"] for r in load("check_scope_alignment.yaml")["reverse_mappings"]}
    assert checks <= reverse
