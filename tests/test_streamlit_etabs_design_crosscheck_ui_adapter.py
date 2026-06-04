from __future__ import annotations

from types import SimpleNamespace

from tbdy_engine.design.beams.streamlit_etabs_ui_adapter import summarize_etabs_design_crosscheck_rows


def test_summarize_etabs_design_crosscheck_rows_from_objects() -> None:
    rows = [
        SimpleNamespace(
            story="+14.5",
            label="B4",
            unique_name="300",
            section="B40x70",
            location="End-I",
            region="left",
            status="DIAGNOSTIC",
            etabs_negative_moment_kNm=-49.7361,
            beamcore_negative_moment_kNm=26.1939,
            negative_moment_delta_kNm=23.5422,
            etabs_positive_moment_kNm=24.868,
            beamcore_positive_moment_kNm=None,
            positive_moment_delta_kNm=None,
            etabs_as_top_cm2=2.62,
            beamcore_top_required_cm2=1.3104,
            top_as_delta_cm2=1.3096,
            etabs_as_bot_cm2=1.41,
            beamcore_bottom_required_cm2=None,
            bottom_as_delta_cm2=None,
            message="Diagnostic comparison only",
        )
    ]

    result = summarize_etabs_design_crosscheck_rows(rows)

    assert result == [
        {
            "story": "+14.5",
            "label": "B4",
            "unique_name": "300",
            "section": "B40x70",
            "location": "End-I",
            "region": "left",
            "status": "DIAGNOSTIC",
            "etabs_negative_moment_kNm": -49.7361,
            "beamcore_negative_moment_kNm": 26.1939,
            "negative_moment_delta_kNm": 23.5422,
            "etabs_positive_moment_kNm": 24.868,
            "beamcore_positive_moment_kNm": None,
            "positive_moment_delta_kNm": None,
            "etabs_as_top_cm2": 2.62,
            "beamcore_top_required_cm2": 1.3104,
            "top_as_delta_cm2": 1.3096,
            "etabs_as_bot_cm2": 1.41,
            "beamcore_bottom_required_cm2": None,
            "bottom_as_delta_cm2": None,
            "message": "Diagnostic comparison only",
        }
    ]


def test_summarize_etabs_design_crosscheck_rows_from_dicts() -> None:
    rows = [
        {
            "story": "+14.5",
            "label": "B4",
            "unique_name": "300",
            "section": "B40x70",
            "location": "Middle",
            "region": "middle",
            "status": "DIAGNOSTIC",
            "etabs_as_bot_cm2": 2.25,
            "beamcore_bottom_required_cm2": 2.4431,
        }
    ]

    result = summarize_etabs_design_crosscheck_rows(rows)

    assert result[0]["location"] == "Middle"
    assert result[0]["region"] == "middle"
    assert result[0]["etabs_as_bot_cm2"] == 2.25
    assert result[0]["beamcore_bottom_required_cm2"] == 2.4431
