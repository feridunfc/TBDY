from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[2]
CHECK_CATALOG = ROOT / "tbdy_engine" / "catalogs" / "check_catalog.yaml"


def test_check_catalog_does_not_leak_etabs_table_names_or_combo_regex():
    text = CHECK_CATALOG.read_text(encoding="utf-8")
    forbidden = [
        "Frame Assignments - Summary",
        "Concrete Beam Design Summary",
        "Element Forces - Beams",
        "Frame Section Property Definitions",
        "include_patterns",
        "exclude_patterns",
        "combo_regex",
    ]
    for token in forbidden:
        assert token not in text


def test_c1_check_catalog_is_contract_only_no_engine_formulas():
    data = yaml.safe_load(CHECK_CATALOG.read_text(encoding="utf-8"))
    assert data["policy"]["c1_no_engine_formulas"] is True
    for check in data["checks"].values():
        assert "formula" not in check
        assert check["formula_ref"] == "contract_only_no_formula_in_C1"
        assert check["readiness"]["status"] in {"ready", "partial", "missing_features"}
