from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "c13_4_offline_acceptance.yml"
P9_COMMAND = "python tools/run_offline_product_acceptance.py --out local_out/c13_4_ci_offline_acceptance"
LOWER_PYTEST_COMMANDS = (
    "pytest -q tests/c13_4_p1",
    "pytest -q tests/c13_4_p2",
    "pytest -q tests/c13_4_p3",
    "pytest -q tests/c13_4_p4",
    "pytest -q tests/c13_4_p5",
    "pytest -q tests/c13_4_p6",
    "pytest -q tests/c13_4_p7",
    "pytest -q tests/c13_4_p8",
    "pytest -q tests/c13_4_p9",
)
DIRECT_PRODUCT_COMMANDS = (
    "tools/run_geometry_product_smoke.py",
    "tools/validate_geometry_product_bundle.py",
    "tools/run_geometry_golden_regression.py",
)
FORBIDDEN_WORKFLOW_TERMS = (
    "ETABS",
    "Excel production",
    "excel production",
    "Streamlit",
    "streamlit",
    "final building compliance",
    "Final building compliance",
)


def _workflow_text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_workflow_file_exists():
    assert WORKFLOW.is_file()


def test_workflow_name_is_exact():
    assert _workflow_text().splitlines()[0] == "name: C13.4 Offline Product Acceptance"


def test_workflow_triggers_pull_request_and_push_to_main():
    text = _workflow_text()

    assert "on:\n" in text
    assert "  pull_request:\n" in text
    assert "  push:\n" in text
    assert text.count("      - main") == 2


def test_workflow_has_single_offline_acceptance_job_on_ubuntu_latest():
    text = _workflow_text()

    assert "jobs:\n" in text
    assert "  offline-acceptance:\n" in text
    assert text.count("offline-acceptance:") == 1
    assert "    runs-on: ubuntu-latest\n" in text


def test_required_steps_are_present_in_order():
    text = _workflow_text()
    markers = [
        "      - name: Checkout",
        "      - name: Setup Python",
        "      - name: Install dependencies",
        "      - name: Run offline acceptance gate",
        "      - name: Upload acceptance artifacts",
    ]

    positions = [text.index(marker) for marker in markers]
    assert positions == sorted(positions)


def test_workflow_uses_checkout_and_setup_python():
    text = _workflow_text()

    assert "uses: actions/checkout@v4" in text
    assert "uses: actions/setup-python@v5" in text


def test_python_version_is_311():
    text = _workflow_text()

    assert 'python-version: "3.11"' in text


def test_workflow_runs_exactly_the_p9_cli_command():
    text = _workflow_text()

    assert f"run: {P9_COMMAND}" in text
    assert text.count(P9_COMMAND) == 1


def test_workflow_does_not_duplicate_lower_level_pytest_commands():
    text = _workflow_text()

    for command in LOWER_PYTEST_COMMANDS:
        assert command not in text


def test_workflow_does_not_directly_call_product_smoke_validator_or_golden_regression():
    text = _workflow_text()

    for command in DIRECT_PRODUCT_COMMANDS:
        assert command not in text


def test_artifact_upload_contract():
    text = _workflow_text()

    assert "if: always()" in text
    assert "uses: actions/upload-artifact@v4" in text
    assert "name: c13-4-offline-acceptance" in text
    assert "path: local_out/c13_4_ci_offline_acceptance" in text


def test_dependency_install_strategy_is_minimal_explicit_test_runtime():
    text = _workflow_text()

    assert "python -m pip install --upgrade pip" in text
    assert "python -m pip install pytest pyyaml jsonschema" in text


def test_workflow_contains_no_forbidden_scope_terms():
    text = _workflow_text()

    for forbidden_term in FORBIDDEN_WORKFLOW_TERMS:
        assert forbidden_term not in text
