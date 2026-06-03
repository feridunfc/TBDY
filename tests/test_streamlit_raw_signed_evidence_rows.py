from __future__ import annotations

from tbdy_engine.design.beams.streamlit_etabs_ui_adapter import shape_result_rows_for_ui


def test_r21a_streamlit_rows_show_raw_signed_values_when_present() -> None:
    rows = shape_result_rows_for_ui(
        {
            "beams": [
                {
                    "object_name": "297",
                    "label": "B1",
                    "section": "B40x70",
                    "beam_core_status": "OK",
                    "actions": {
                        "Vd_left_kN": 91.057,
                        "Vd_left_raw_signed_kN": -91.057,
                        "Ve_left_kN": 91.057,
                        "Ve_left_raw_signed_kN": -91.057,
                        "Md_left_neg_kNm": 66.683,
                        "M3_left_raw_signed_kNm": -66.683,
                    },
                    "governing": {
                        "Ve_left_kN": {
                            "combo": "Grav_Ult",
                            "station": 0.0,
                            "etabs_raw_signed_value": -91.057,
                            "design_demand_magnitude": 91.057,
                            "etabs_local_axis_component": "V2",
                            "sign_convention": "ETABS raw signed local force is preserved; design/check demand uses positive magnitude.",
                        }
                    },
                    "artifact_paths": {},
                }
            ]
        }
    )

    row = rows[0]
    assert row["Vd_left_kN"] == 91.057
    assert row["Vd_left_raw_signed_kN"] == -91.057
    assert row["Ve_left_raw_signed_kN"] == -91.057
    assert row["M3_left_raw_signed_kNm"] == -66.683
    assert row["Ve_left_raw_evidence"] == -91.057
    assert "ETABS raw signed local force is preserved" in row["sign_convention"]
