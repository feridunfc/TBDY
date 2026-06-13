from pathlib import Path
import json
import yaml

ROOT = Path(__file__).resolve().parents[2]
CATALOG_DIR = ROOT / "tbdy_engine" / "catalogs"


def load_yaml(name):
    return yaml.safe_load((CATALOG_DIR / name).read_text(encoding="utf-8"))


def load_json(name):
    return json.loads((CATALOG_DIR / "examples" / name).read_text(encoding="utf-8"))


def test_workspace_contract_source_rules_are_production_safe():
    data = load_yaml("workspace_contract.yaml")
    sources = data["allowed_source_types"]
    assert sources["ETABS_LIVE"]["production_allowed"] is True
    for source_type in ["FAKE_PROVIDER", "EXCEL_FIXTURE", "JSON_FIXTURE"]:
        assert sources[source_type]["production_allowed"] is False
    assert data["source_rules"]["production_source"] == "ETABS_LIVE"
    assert data["source_rules"]["excel_never_production_input"] is True


def test_workspace_state_example_has_no_check_result_objects_and_valid_report_state():
    state = load_json("workspace_state.example.json")
    assert "check_results" not in state
    assert "CheckResult" not in state
    assert state["report_state"]["status"] == "COMPLETE"
    assert state["check_results_json"]
