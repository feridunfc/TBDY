from __future__ import annotations

from pathlib import Path

import apps.streamlit_beam_design_app as app


def test_r23d_pdf_report_action_returns_coming_soon(tmp_path: Path) -> None:
    result = app._run_report_action("pdf_report", tmp_path)

    assert result["kind"] == "pdf_report"
    assert result["status"] == "COMING_SOON"
    assert result["files"] == {}
    assert "PDF Report" in result["message"]


def test_r23d_unknown_report_action_returns_unknown(tmp_path: Path) -> None:
    result = app._run_report_action("unknown", tmp_path)

    assert result["kind"] == "unknown"
    assert result["status"] == "UNKNOWN_ACTION"
    assert result["files"] == {}
    assert "Unknown report action" in result["message"]


def test_r23d_standard_report_action_result_preserves_files() -> None:
    result = app._standard_report_action_result(
        "etabs_design_crosscheck",
        {
            "status": "OK",
            "files": {
                "json": "etabs_design_crosscheck.json",
                "xlsx": "etabs_design_crosscheck.xlsx",
            },
        },
    )

    assert result["kind"] == "etabs_design_crosscheck"
    assert result["status"] == "OK"
    assert result["files"]["json"] == "etabs_design_crosscheck.json"
    assert "does not validate BeamCore" in result["claim_boundary"]


def test_r23d_etabs_design_crosscheck_action_no_data(tmp_path: Path, monkeypatch) -> None:
    class FakeSessionState(dict):
        pass

    class FakeStreamlit:
        session_state = FakeSessionState()

    monkeypatch.setattr(app, "st", FakeStreamlit)

    result = app._run_report_action("etabs_design_crosscheck", tmp_path)

    assert result["kind"] == "etabs_design_crosscheck"
    assert result["status"] == "NO_DATA"
    assert result["files"] == {}


def test_r23d_source_contract_terms_present() -> None:
    source = Path("apps/streamlit_beam_design_app.py").read_text(encoding="utf-8-sig")

    required = [
        "_run_report_action",
        "_standard_report_action_result",
        "Run Selected Report Action",
        "last_report_action_result",
        "UNKNOWN_ACTION",
        "COMING_SOON",
    ]

    for text in required:
        assert text in source


def test_r23d_no_validation_claims() -> None:
    source = Path("apps/streamlit_beam_design_app.py").read_text(encoding="utf-8-sig")

    forbidden = [
        "ETABS validation passed",
        "TBDY compliance proven",
        "production-ready report",
    ]

    for text in forbidden:
        assert text not in source
