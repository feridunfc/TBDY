import ast
import json
from collections import Counter
from pathlib import Path

from jsonschema import Draft202012Validator

from tests.golden.c7_golden_builder import build_golden_documents

GOLDEN_DIR = Path(__file__).parent
CHECK_RESULTS_PATH = GOLDEN_DIR / "c7_minimal_check_results.golden.json"
COVERAGE_PATH = GOLDEN_DIR / "c7_minimal_coverage_matrix.golden.json"
SNAPSHOT_PATH = GOLDEN_DIR / "c7_minimal_feature_snapshot.golden.json"

UPPER_BOUND_RULES = {"demand_over_capacity", "required_over_selected", "value_over_maximum", "value_over_limit"}
LOWER_BOUND_RULES = {"actual_over_minimum", "selected_over_required", "value_over_minimum", "actual_over_required"}
FORBIDDEN_CHECK_IMPORTS = [
    "providers",
    "table_registry",
    "load_combo_policy",
    "design_combo_matrix",
    "section_state_policy",
    "features.resolver",
    "etabs",
    "runner_v2",
    "runtime",
    "archx",
    "beam_module",
    "beam_checks",
]


def _json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _results():
    return _json(CHECK_RESULTS_PATH)["check_results"]


def _coverage_checks():
    return _json(COVERAGE_PATH)["checks"]


def _find_result(check_id: str, component: str):
    matches = [r for r in _results() if r["check_id"] == check_id and r["component"] == component]
    assert len(matches) == 1
    return matches[0]


def _find_coverage(check_id: str, component_id: str):
    matches = [r for r in _coverage_checks() if r["check_id"] == check_id and r["component_id"] == component_id]
    assert len(matches) == 1
    return matches[0]


def test_c7_golden_json_schema_valid():
    check_schema = _json(Path("tbdy_engine/catalogs/schemas/check_result.schema.json"))
    coverage_schema = _json(Path("tbdy_engine/catalogs/schemas/coverage_matrix.schema.json"))

    check_validator = Draft202012Validator(check_schema)
    for result in _results():
        check_validator.validate(result)

    Draft202012Validator(coverage_schema).validate(_json(COVERAGE_PATH))
    assert _json(SNAPSHOT_PATH)["snapshots"]


def test_c7_golden_json_contains_ok_fail_no_data():
    counts = Counter(result["status"] for result in _results())
    assert counts["OK"] >= 1
    assert counts["FAIL"] >= 1
    assert counts["NO_DATA"] >= 1
    assert counts["WARNING"] >= 1


def test_c7_story_drift_above_limit_fails():
    result = _find_result("story_drift_ratio", "S_DRIFT_FAIL")
    assert result["ratio"] == 1.2
    assert result["ratio_type"] == "value_over_maximum"
    assert result["status"] == "FAIL"


def test_c7_beam_width_below_minimum_fails():
    result = _find_result("beam_geometry_min_width", "B_WIDTH_FAIL")
    assert result["ratio_type"] == "actual_over_minimum"
    assert result["ratio"] == 0.8
    assert result["status"] == "FAIL"


def test_c7_modal_mass_above_threshold_ok():
    result = _find_result("modal_mass_sumux_ge_threshold", "GLOBAL_MODAL_OK")
    assert result["ratio_type"] == "value_over_minimum"
    assert result["ratio"] > 1.0
    assert result["status"] == "OK"


def test_c7_missing_feature_returns_no_data():
    result = _find_result("required_feature_missing_no_data", "B_MISSING")
    assert result["status"] == "NO_DATA"
    assert result["status"] != "OK"
    assert result["status"] != "FAIL"


def test_c7_blocked_coverage_never_ok():
    coverage = _find_coverage("required_feature_missing_no_data", "B_MISSING")
    result = _find_result("required_feature_missing_no_data", "B_MISSING")
    assert coverage["coverage_status"] == "BLOCKED"
    assert result["status"] == "NO_DATA"
    assert result["status"] != "OK"


def test_c7_partial_coverage_never_silent_ok():
    coverage = _find_coverage("beam_geometry_min_width", "B_PARTIAL")
    result = _find_result("beam_geometry_min_width", "B_PARTIAL")
    assert coverage["coverage_status"] == "PARTIAL"
    assert result["status"] in {"WARNING", "NO_DATA"}
    assert result["status"] != "OK"


def test_c7_no_ratio_pass_rule_contradictions():
    for result in _results():
        rule = result["pass_rule"] or result["ratio_type"]
        ratio = result["ratio"]
        if rule in UPPER_BOUND_RULES and ratio is not None and ratio > 1.0:
            assert result["status"] != "OK", result
        if rule in LOWER_BOUND_RULES and ratio is not None and ratio < 1.0:
            assert result["status"] != "OK", result
        if rule in UPPER_BOUND_RULES | LOWER_BOUND_RULES and ratio is None:
            assert result["status"] != "OK", result


def test_c7_evidence_and_code_ref_are_propagated():
    for result in _results():
        assert result["code_ref"]
        assert isinstance(result["evidence"], list)
        if result["status"] in {"OK", "FAIL"}:
            assert result["evidence"], result


def test_c7_golden_output_is_deterministic():
    docs = build_golden_documents()
    expected = {
        "c7_minimal_feature_snapshot.golden.json": docs["feature_snapshot"],
        "c7_minimal_coverage_matrix.golden.json": docs["coverage_matrix"],
        "c7_minimal_check_results.golden.json": docs["check_results"],
    }
    for filename, payload in expected.items():
        actual_text = (GOLDEN_DIR / filename).read_text(encoding="utf-8")
        rebuilt_text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
        assert actual_text == rebuilt_text


def _imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return names


def test_c7_checkengine_forbidden_imports_still_clean():
    imported_text = "\n".join(
        _imports(Path("tbdy_engine/checks/engine.py"))
        + _imports(Path("tbdy_engine/checks/__init__.py"))
        + _imports(Path("tbdy_engine/checks/pass_rules.py"))
    )
    for forbidden in FORBIDDEN_CHECK_IMPORTS:
        assert forbidden not in imported_text

    engine_source = Path("tbdy_engine/checks/engine.py").read_text(encoding="utf-8")
    for forbidden in ["GetTableForDisplayArray", "table_registry", "load_combo_policy", "design_combo_matrix", "section_state_policy"]:
        assert forbidden not in engine_source
