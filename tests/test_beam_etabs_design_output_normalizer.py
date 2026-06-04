from __future__ import annotations

from tbdy_engine.verification.beams.etabs_design_output import (
    M2_TO_CM2,
    normalize_etabs_beam_design_output_row,
    normalize_etabs_beam_design_output_rows,
    normalize_location,
    row_to_report_dict,
)


def test_normalize_etabs_beam_design_output_row_preserves_identity_fields() -> None:
    row = normalize_etabs_beam_design_output_row(
        {
            "Story": "+14.5",
            "Beam": "B4",
            "UniqueName": "300",
            "Section": "B40x70",
            "Location": "End-I",
        }
    )

    assert row.story == "+14.5"
    assert row.label == "B4"
    assert row.unique_name == "300"
    assert row.section == "B40x70"
    assert row.location == "End-I"
    assert row.location_is_known is True


def test_normalize_etabs_beam_design_output_row_converts_as_m2_to_cm2() -> None:
    row = normalize_etabs_beam_design_output_row(
        {
            "As Top": 0.000262,
            "As Bot": "0.000141",
        }
    )

    assert row.as_top_m2 == 0.000262
    assert row.as_top_cm2 == 0.000262 * M2_TO_CM2
    assert row.as_bot_m2 == 0.000141
    assert row.as_bot_cm2 == 0.000141 * M2_TO_CM2


def test_normalize_etabs_beam_design_output_row_preserves_moment_and_combo_fields() -> None:
    row = normalize_etabs_beam_design_output_row(
        {
            "-ve Moment Combo": "Crack_SeisX_Soil",
            "-ve Moment": "-49.7361",
            "+ve Moment Combo": "Crack_SeisX_Soil",
            "+ve Moment": 24.868,
            "Status": "",
        }
    )

    assert row.negative_moment_combo == "Crack_SeisX_Soil"
    assert row.negative_moment_kNm == -49.7361
    assert row.positive_moment_combo == "Crack_SeisX_Soil"
    assert row.positive_moment_kNm == 24.868
    assert row.status is None


def test_normalize_locations() -> None:
    assert normalize_location("End-I") == ("End-I", True)
    assert normalize_location("Middle") == ("Middle", True)
    assert normalize_location("End-J") == ("End-J", True)
    assert normalize_location("left") == ("End-I", True)
    assert normalize_location("mid") == ("Middle", True)
    assert normalize_location("right") == ("End-J", True)


def test_unknown_location_is_preserved_but_marked_diagnostic() -> None:
    row = normalize_etabs_beam_design_output_row({"Location": "Support-2"})

    assert row.location == "Support-2"
    assert row.location_is_known is False


def test_normalize_rows_and_report_dicts() -> None:
    rows = normalize_etabs_beam_design_output_rows(
        [
            {
                "Story": "+14.5",
                "Beam": "B4",
                "UniqueName": "300",
                "Section": "B40x70",
                "Location": "End-J",
                "-ve Moment": -63.2114,
                "As Top": 0.000324,
                "+ve Moment": 47.1527,
                "As Bot": 0.000242,
            }
        ]
    )

    assert len(rows) == 1

    report = row_to_report_dict(rows[0])

    assert report["story"] == "+14.5"
    assert report["label"] == "B4"
    assert report["unique_name"] == "300"
    assert report["location"] == "End-J"
    assert report["negative_moment_kNm"] == -63.2114
    assert report["as_top_cm2"] == 3.24
    assert report["positive_moment_kNm"] == 47.1527
    assert report["as_bot_cm2"] == 2.42
