from __future__ import annotations

from pathlib import Path

from tbdy_engine.product.offline_acceptance import build_offline_acceptance_command_plan

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "tbdy_engine" / "features" / "live_etabs_table_discovery.py"
CLI_PATH = ROOT / "tools" / "probe_live_etabs_geometry_tables.py"
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "c13_4_offline_acceptance.yml"
IMPLEMENTATION_PATHS = (MODULE_PATH, CLI_PATH)
FORBIDDEN_ENGINE_SNIPPETS = (
    "CheckResult",
    "MinimalCheckEngine",
    "tbdy_engine.checks.engine",
)
FORBIDDEN_SCOPE_TERMS = (
    "rebar_extraction",
    "capacity_design",
    "PMM",
    "SCWB",
    "drift",
    "modal_mass",
)


def test_no_section_name_dimension_derivation_exists_in_implementation():
    for path in IMPLEMENTATION_PATHS:
        source = path.read_text(encoding="utf-8")
        assert "B40x70" not in source
        assert "C40x50" not in source
        assert "parse_section" not in source
        assert ".split(" not in source


def test_no_unit_conversion_exists_in_implementation():
    for path in IMPLEMENTATION_PATHS:
        source = path.read_text(encoding="utf-8")
        assert "unit_conversion" not in source
        assert "convert" not in source.casefold()


def test_no_checkresult_or_checkengine_appears_in_discovery_module_or_tool():
    for path in IMPLEMENTATION_PATHS:
        source = path.read_text(encoding="utf-8")
        for forbidden in FORBIDDEN_ENGINE_SNIPPETS:
            assert forbidden not in source


def test_no_product_smoke_call_appears_in_discovery_tool():
    source = CLI_PATH.read_text(encoding="utf-8")

    assert "run_geometry_product_smoke" not in source
    assert "product_smoke" not in source


def test_no_forbidden_engineering_scope_terms_in_discovery_module_or_tool():
    for path in IMPLEMENTATION_PATHS:
        source = path.read_text(encoding="utf-8")
        for forbidden in FORBIDDEN_SCOPE_TERMS:
            assert forbidden not in source


def test_forces_term_is_only_a_prefetch_penalty_not_force_extraction():
    source = MODULE_PATH.read_text(encoding="utf-8")

    assert '"forces"' in source
    assert "force_extraction" not in source
    assert "GetTableForDisplayArray(\"Forces" not in source


def test_offline_acceptance_includes_c13_5_p4_and_command_count_is_16(tmp_path: Path):
    plan = build_offline_acceptance_command_plan(output_dir=tmp_path, python_executable="PY")

    assert len(plan) == 16
    assert ("pytest_c13_5_p4", ("PY", "-m", "pytest", "-q", "tests/c13_5_p4")) in plan


def test_p10_workflow_delegates_to_p9_cli_only_and_does_not_mention_c13_5_p4():
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")

    assert "python tools/run_offline_product_acceptance.py" in workflow
    assert "pytest -q" not in workflow
    assert "tests/c13_5_p4" not in workflow


def test_older_p9_tests_use_future_safe_expected_count_constant():
    p9_positive = (ROOT / "tests" / "c13_4_p9" / "test_offline_product_acceptance.py").read_text(encoding="utf-8")
    p9_negative = (ROOT / "tests" / "c13_4_p9" / "test_offline_product_acceptance_negative_cases.py").read_text(encoding="utf-8")

    assert "EXPECTED_COMMAND_COUNT = len(EXPECTED_NAMES)" in p9_positive
    assert "_expected_command_count" in p9_negative
    assert "assert result.command_count == 15" not in p9_positive
    assert "assert result.command_count == 15" not in p9_negative
