from __future__ import annotations

from pathlib import Path


APP_SOURCE = Path("apps/streamlit_beam_design_app.py")
ADAPTER_SOURCE = Path("tbdy_engine/design/beams/streamlit_etabs_ui_adapter.py")


def _source() -> str:
    return APP_SOURCE.read_text(encoding="utf-8-sig")


def test_r20_reports_evidence_sections_visible() -> None:
    source = _source()

    required = [
        "Reports/Evidence",
        "Evidence",
        "Generated Reports",
        "Claim Boundaries",
        "Workspace Evidence",
        "Canonical Units",
        "ETABS Units Evidence",
        "Report Output Settings",
        "PDF Report — coming soon",
    ]

    for text in required:
        assert text in source


def test_r20_report_file_rows_helper_exists() -> None:
    source = _source()

    assert "def _report_file_rows" in source
    assert "story_beam_batch_summary.json" in source
    assert "story_beam_batch_summary.md" in source
    assert "streamlit_single_combo_summary.json" in source
    assert "streamlit_single_combo_summary.md" in source
    assert "failure_diagnosis_summary.json" in source
    assert "failure_diagnosis_summary.md" in source


def test_r20_workspace_evidence_helper_exists() -> None:
    source = _source()

    assert "def _current_workspace_evidence" in source
    assert "workspace_analysis_source" in source
    assert "workspace_element_type" in source
    assert "workspace_last_run_status" in source
    assert "etabs_connection_state" in source


def test_r20_reporting_preserves_claim_boundaries() -> None:
    source = _source()

    assert "not TBDY compliance proof" in source
    assert "not production-ready" in source
    assert "Evidence only" in source


def test_r20_no_forbidden_ui_formulas() -> None:
    combined = _source() + "\n" + ADAPTER_SOURCE.read_text(encoding="utf-8-sig")

    forbidden = [
        "rho_min =",
        "As_required =",
        "Mpr =",
        "Ve_capacity =",
        "s = Asw",
    ]

    for term in forbidden:
        assert term not in combined


def test_r20_no_top_level_com_imports() -> None:
    combined = _source() + "\n" + ADAPTER_SOURCE.read_text(encoding="utf-8-sig")

    forbidden = [
        "import comtypes",
        "from comtypes",
        "import pythoncom",
        "from pythoncom",
    ]

    for term in forbidden:
        assert term not in combined
