from __future__ import annotations

from pathlib import Path

import apps.streamlit_beam_design_app as app


def test_r24b_live_design_fallback_rows_from_legacy_result(monkeypatch) -> None:
    class FakeSessionState(dict):
        pass

    class FakeStreamlit:
        session_state = FakeSessionState(
            {
                "legacy_beamcore_result": {
                    "summary": {
                        "beams": [
                            {
                                "object_name": "300",
                                "label": "B4",
                                "story": "+14.5",
                                "section": "B40x70",
                                "actions": {
                                    "Md_mid_pos_kNm": 43.7621,
                                    "Vd_left_kN": 50.006,
                                },
                                "governing": {
                                    "Md_mid_pos_kNm": {
                                        "combo": "ENV_CRK",
                                        "station": 2.52,
                                    }
                                },
                                "artifact_paths": {
                                    "json": "_local/streamlit_beam_design/300/engine_report.json",
                                    "xlsx": "_local/streamlit_beam_design/300/engine_report.xlsx",
                                },
                            }
                        ]
                    }
                }
            }
        )

    monkeypatch.setattr(app, "st", FakeStreamlit)

    rows = app._live_beamcore_design_fallback_rows()

    assert rows[0]["object_name"] == "300"
    assert rows[0]["Md_mid_pos_kNm"] == 43.7621
    assert rows[0]["Md_mid_pos_station"] == 2.52
    assert rows[0]["artifact_xlsx"].endswith("engine_report.xlsx")


def test_r24b_live_verification_fallback_rows_from_legacy_result(monkeypatch) -> None:
    class FakeSessionState(dict):
        pass

    class FakeStreamlit:
        session_state = FakeSessionState(
            {
                "legacy_beamcore_result": {
                    "summary": {
                        "beams": [
                            {
                                "object_name": "300",
                                "label": "B4",
                                "story": "+14.5",
                                "beam_core_status": "OK",
                                "check_count": 24,
                                "capacity_design_check_statuses": {
                                    "beam_shear_capacity_design_ve_le_vr": "executed",
                                },
                                "artifact_paths": {
                                    "json": "_local/streamlit_beam_design/300/engine_report.json",
                                    "xlsx": "_local/streamlit_beam_design/300/engine_report.xlsx",
                                },
                            }
                        ]
                    }
                }
            }
        )

    monkeypatch.setattr(app, "st", FakeStreamlit)

    rows = app._live_beamcore_verification_fallback_rows()

    assert rows[0]["object_name"] == "300"
    assert rows[0]["beam_core_status"] == "OK"
    assert rows[0]["check_count"] == 24
    assert rows[0]["capacity_design_check_statuses"]["beam_shear_capacity_design_ve_le_vr"] == "executed"


def test_r24b_source_contract_terms_present() -> None:
    source = Path("apps/streamlit_beam_design_app.py").read_text(encoding="utf-8-sig")

    required = [
        "_live_beamcore_design_fallback_rows",
        "_live_beamcore_verification_fallback_rows",
        "Showing live BeamCore diagnostic design evidence instead",
        "Showing live BeamCore diagnostic verification evidence instead",
        "does not create a BeamDesignResult",
        "Diagnostic fallback only",
    ]

    for text in required:
        assert text in source
