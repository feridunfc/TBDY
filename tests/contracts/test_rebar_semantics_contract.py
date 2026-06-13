from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[2]
FEATURE_CATALOG = ROOT / "tbdy_engine" / "catalogs" / "feature_catalog.yaml"


def test_rebar_canonical_flow_is_present_and_ordered():
    data = yaml.safe_load(FEATURE_CATALOG.read_text(encoding="utf-8"))
    assert data["rebar_semantics"]["canonical_flow"] == [
        "ETABS_REQUIRED_REBAR",
        "TBDY_MIN_REQUIRED_REBAR",
        "GOVERNING_REQUIRED_REBAR",
        "ENGINE_SELECTED_REBAR",
        "DESIGN_SELECTION",
        "USER_PROVIDED_REBAR",
        "FINAL_DETAILING_REQUIRED",
    ]


def test_rebar_features_do_not_claim_verified_provided_rebar():
    data = yaml.safe_load(FEATURE_CATALOG.read_text(encoding="utf-8"))
    features_text = yaml.safe_dump(data["features"])
    assert "VERIFIED_PROVIDED_REBAR" not in features_text
    assert "AS_BUILT_REBAR" not in features_text
    roles = {feature.get("semantic_role") for feature in data["features"].values()}
    assert "ETABS_REQUIRED_REBAR" in roles
    assert "TBDY_MIN_REQUIRED_REBAR" in roles
    assert "GOVERNING_REQUIRED_REBAR" in roles
    assert "ENGINE_SELECTED_REBAR" in roles
