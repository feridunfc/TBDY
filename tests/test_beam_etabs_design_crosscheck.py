from __future__ import annotations

from tbdy_engine.verification.beams.etabs_design_crosscheck import (
    LOCATION_TO_REGION,
    crosscheck_etabs_design_output_row,
    crosscheck_etabs_design_output_rows,
    crosscheck_row_to_report_dict,
)
from tbdy_engine.verification.beams.etabs_design_output import normalize_etabs_beam_design_output_row


def test_location_to_region_contract() -> None:
    assert LOCATION_TO_REGION["End-I"] == "left"
    assert LOCATION_TO_REGION["Middle"] == "middle"
    assert LOCATION_TO_REGION["End-J"] == "right"


def test_end_i_maps_negative_moment_and_top_as() -> None:
    etabs = normalize_etabs_beam_design_output_row(
        {
            "Story": "+14.5",
            "Beam": "B4",
            "UniqueName": "300",
            "Section": "B40x70",
            "Location": "End-I",
            "-ve Moment": -49.7361,
            "As Top": 0.000262,
            "+ve Moment": 24.868,
            "As Bot": 0.000141,
        }
    )

    result = crosscheck_etabs_design_output_row(
        etabs,
        beamcore_actions={"Md_left_neg_kNm": 26.193888203152845},
        beamcore_flexure={"top_required_area_cm2": 1.310387385383232},
    )

    assert result.region == "left"
    assert result.etabs_negative_moment_kNm == -49.7361
    assert result.beamcore_negative_moment_kNm == 26.193888203152845
    assert result.negative_moment_delta_kNm == abs(49.7361 - 26.193888203152845)
    assert result.etabs_as_top_cm2 == 2.62
    assert result.beamcore_top_required_cm2 == 1.310387385383232
    assert result.top_as_delta_cm2 == abs(2.62 - 1.310387385383232)
    assert result.status == "DIAGNOSTIC"


def test_middle_maps_positive_moment_and_bottom_as() -> None:
    etabs = normalize_etabs_beam_design_output_row(
        {
            "Location": "Middle",
            "+ve Moment": 43.7621,
            "As Bot": 0.000225,
        }
    )

    result = crosscheck_etabs_design_output_row(
        etabs,
        beamcore_actions={"Md_mid_pos_kNm": 48.65543620177891},
        beamcore_flexure={"bottom_required_area_cm2": 2.44310001537692},
    )

    assert result.region == "middle"
    assert result.beamcore_positive_moment_kNm == 48.65543620177891
    assert result.positive_moment_delta_kNm == abs(43.7621 - 48.65543620177891)
    assert result.etabs_as_bot_cm2 == 2.25
    assert result.beamcore_bottom_required_cm2 == 2.44310001537692
    assert result.bottom_as_delta_cm2 == abs(2.25 - 2.44310001537692)


def test_end_j_maps_negative_moment_to_right_region() -> None:
    etabs = normalize_etabs_beam_design_output_row(
        {
            "Location": "End-J",
            "-ve Moment": -63.2114,
            "As Top": 0.000324,
        }
    )

    result = crosscheck_etabs_design_output_row(
        etabs,
        beamcore_actions={"Md_right_neg_kNm": 13.537957010315958},
        beamcore_flexure={"top_required_area_cm2": 1.310387385383232},
    )

    assert result.region == "right"
    assert result.beamcore_negative_moment_kNm == 13.537957010315958
    assert result.negative_moment_delta_kNm == abs(63.2114 - 13.537957010315958)
    assert result.etabs_as_top_cm2 == 3.24


def test_unknown_location_is_diagnostic_not_crash() -> None:
    etabs = normalize_etabs_beam_design_output_row(
        {
            "Location": "Support-2",
            "-ve Moment": -10.0,
        }
    )

    result = crosscheck_etabs_design_output_row(
        etabs,
        beamcore_actions={},
        beamcore_flexure={},
    )

    assert result.status == "DIAGNOSTIC"
    assert result.region == ""
    assert "Unknown ETABS design output location" in result.message


def test_crosscheck_rows_to_report_dicts() -> None:
    etabs = normalize_etabs_beam_design_output_row(
        {
            "Story": "+14.5",
            "Beam": "B4",
            "UniqueName": "300",
            "Section": "B40x70",
            "Location": "Middle",
            "+ve Moment": 43.7621,
            "As Bot": 0.000225,
        }
    )

    rows = crosscheck_etabs_design_output_rows(
        [etabs],
        beamcore_actions={"Md_mid_pos_kNm": 48.65543620177891},
        beamcore_flexure={"bottom_required_area_cm2": 2.44310001537692},
    )

    report = crosscheck_row_to_report_dict(rows[0])

    assert report["story"] == "+14.5"
    assert report["label"] == "B4"
    assert report["unique_name"] == "300"
    assert report["region"] == "middle"
    assert report["status"] == "DIAGNOSTIC"
    assert report["etabs_as_bot_cm2"] == 2.25
