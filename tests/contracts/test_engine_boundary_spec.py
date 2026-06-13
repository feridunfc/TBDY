from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_engine_boundary_spec_forbids_check_engine_policy_and_provider_access():
    text = (ROOT / "docs" / "ENGINE_BOUNDARY_SPEC_v1.md").read_text(encoding="utf-8")
    for phrase in [
        "CheckEngine must not read table registry",
        "combo policy",
        "design basis",
        "section-state policy",
        "design combo matrix",
        "ETABS table names",
        "combo regex",
        "actual combo names",
        "Excel sheet names",
    ]:
        assert phrase in text


def test_workspace_constitution_documents_source_boundaries():
    text = (ROOT / "docs" / "WORKSPACE_CONSTITUTION_v1.md").read_text(encoding="utf-8")
    assert "ETABS_LIVE" in text
    assert "only production source" in text
    assert "EXCEL_FIXTURE" in text
    assert "never become production input" in text
