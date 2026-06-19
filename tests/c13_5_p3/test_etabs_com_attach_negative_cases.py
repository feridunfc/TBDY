from __future__ import annotations

from pathlib import Path

from tbdy_engine.product.offline_acceptance import build_offline_acceptance_command_plan

ROOT = Path(__file__).resolve().parents[2]
ATTACH_MODULE_PATH = ROOT / "tbdy_engine" / "features" / "etabs_com_attach.py"
LIVE_PROBE_PATH = ROOT / "tbdy_engine" / "features" / "live_etabs_geometry_probe.py"
CLI_PATH = ROOT / "tools" / "probe_live_etabs_geometry_snapshot.py"
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "c13_4_offline_acceptance.yml"
IMPLEMENTATION_PATHS = (ATTACH_MODULE_PATH, CLI_PATH)
PROBE_BOUNDARY_PATHS = (ATTACH_MODULE_PATH, LIVE_PROBE_PATH, CLI_PATH)
FORBIDDEN_ENGINE_SNIPPETS = (
    "CheckResult",
    "MinimalCheckEngine",
    "tbdy_engine.checks.engine",
)
FORBIDDEN_SCOPE_TERMS = (
    "force",
    "rebar",
    "capacity",
    "PMM",
    "SCWB",
    "drift",
    "modal",
)


def test_probe_boundary_does_not_emit_checkresult_or_import_check_engine():
    for path in PROBE_BOUNDARY_PATHS:
        source = path.read_text(encoding="utf-8")
        for forbidden in FORBIDDEN_ENGINE_SNIPPETS:
            assert forbidden not in source


def test_new_attach_implementation_does_not_add_engineering_scope_terms():
    for path in IMPLEMENTATION_PATHS:
        source = path.read_text(encoding="utf-8")
        for forbidden in FORBIDDEN_SCOPE_TERMS:
            assert forbidden not in source


def test_attach_failure_contract_does_not_expose_raw_com_object_values():
    source = LIVE_PROBE_PATH.read_text(encoding="utf-8")
    start = source.index("def write_com_attach_failure_probe_outputs")
    end = source.index("def load_mapping_provider_from_json")
    failure_source = source[start:end]

    assert "etabs_object" not in failure_source
    assert "sap_model" not in failure_source


def test_offline_acceptance_includes_c13_5_p3_and_command_count_is_15(tmp_path: Path):
    plan = build_offline_acceptance_command_plan(output_dir=tmp_path, python_executable="PY")

    assert len(plan) == 15
    assert ("pytest_c13_5_p3", ("PY", "-m", "pytest", "-q", "tests/c13_5_p3")) in plan


def test_p10_workflow_delegates_to_p9_cli_only_and_does_not_mention_c13_5_p3():
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")

    assert "python tools/run_offline_product_acceptance.py" in workflow
    assert "pytest -q" not in workflow
    assert "tests/c13_5_p3" not in workflow


def test_cli_failure_path_does_not_run_product_smoke():
    source = CLI_PATH.read_text(encoding="utf-8")

    assert "run_geometry_product_smoke" not in source
    assert "product_smoke" not in source


def test_live_probe_boundary_keeps_existing_geometry_extraction_table_list_bounded():
    source = LIVE_PROBE_PATH.read_text(encoding="utf-8")

    assert "def _candidate_live_table_names" in source
    assert "return preferred[:max_candidate_tables]" in source
    assert "Registry" not in source
