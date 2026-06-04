from __future__ import annotations

from pathlib import Path

import apps.streamlit_beam_design_app as app


def test_r23c_report_action_registry_lists_known_actions() -> None:
    actions = app._report_action_registry()
    kinds = {action["kind"] for action in actions}

    assert "offline_demo_bundle" in kinds
    assert "etabs_design_crosscheck" in kinds
    assert "pdf_report" in kinds


def test_r23c_pdf_report_action_is_coming_soon_disabled() -> None:
    actions = app._report_action_registry()
    pdf = next(action for action in actions if action["kind"] == "pdf_report")

    assert pdf["enabled"] is False
    assert pdf["status"] == "COMING_SOON"
    assert "PDF Report — coming soon" in pdf["claim_boundary"]


def test_r23c_etabs_design_crosscheck_requires_data() -> None:
    actions = app._report_action_registry()
    crosscheck = next(action for action in actions if action["kind"] == "etabs_design_crosscheck")

    assert crosscheck["enabled"] is True
    assert crosscheck["requires_data"] is True
    assert crosscheck["required_session_key"] == "r22c_etabs_design_crosscheck_rows"
    assert "does not validate BeamCore" in crosscheck["claim_boundary"]


def test_r23c_report_action_display_rows_are_compact() -> None:
    actions = app._report_action_registry()
    rows = app._report_action_display_rows(actions)

    assert len(rows) == len(actions)
    assert set(rows[0]) == {
        "status",
        "label",
        "kind",
        "enabled",
        "requires_data",
        "required_session_key",
        "claim_boundary",
    }


def test_r23c_report_action_status_no_data(monkeypatch) -> None:
    class FakeSessionState(dict):
        pass

    class FakeStreamlit:
        session_state = FakeSessionState()

    monkeypatch.setattr(app, "st", FakeStreamlit)

    action = next(
        action for action in app._report_action_registry()
        if action["kind"] == "etabs_design_crosscheck"
    )

    assert app._report_action_status(action) == "NO_DATA"


def test_r23c_report_action_status_ready_when_data_exists(monkeypatch) -> None:
    class FakeSessionState(dict):
        pass

    class FakeStreamlit:
        session_state = FakeSessionState(
            {"r22c_etabs_design_crosscheck_rows": [{"label": "B4"}]}
        )

    monkeypatch.setattr(app, "st", FakeStreamlit)

    action = next(
        action for action in app._report_action_registry()
        if action["kind"] == "etabs_design_crosscheck"
    )

    assert app._report_action_status(action) == "READY"


def test_r23c_report_action_status_pdf_coming_soon(monkeypatch) -> None:
    class FakeSessionState(dict):
        pass

    class FakeStreamlit:
        session_state = FakeSessionState()

    monkeypatch.setattr(app, "st", FakeStreamlit)

    action = next(
        action for action in app._report_action_registry()
        if action["kind"] == "pdf_report"
    )

    assert app._report_action_status(action) == "COMING_SOON"


def test_r23c_source_contract_terms_present() -> None:
    source = Path("apps/streamlit_beam_design_app.py").read_text(encoding="utf-8-sig")

    required = [
        "Report Actions",
        "R23C action registry",
        "_report_action_registry",
        "_report_action_display_rows",
        "_report_action_status",
        "Generate Offline Demo Report Bundle",
        "Generate ETABS Design Crosscheck Report",
        "Generate PDF Report",
    ]

    for text in required:
        assert text in source


def test_r23c_no_validation_claims() -> None:
    source = Path("apps/streamlit_beam_design_app.py").read_text(encoding="utf-8-sig")

    forbidden = [
        "ETABS design validates BeamCore",
        "TBDY compliance proven",
        "production-ready report",
    ]

    for text in forbidden:
        assert text not in source
