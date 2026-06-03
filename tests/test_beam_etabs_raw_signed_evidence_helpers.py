from __future__ import annotations

from types import SimpleNamespace

from tbdy_engine.design.beams.etabs_single_beam_frameforce_runner import (
    ETABS_RAW_SIGN_CONVENTION,
    _r21a_raw_signed_action_fields,
    _r21a_raw_signed_governing_evidence,
)


def test_r21a_raw_signed_shear_evidence_helper() -> None:
    envelope = {
        "Vd_left_kN": SimpleNamespace(value=91.057, raw_value=-91.057, combo="Grav_Ult", station=0.0),
        "Ve_left_kN": SimpleNamespace(value=91.057, raw_value=-91.057, combo="Grav_Ult", station=0.0),
    }

    actions = _r21a_raw_signed_action_fields(envelope)
    evidence = _r21a_raw_signed_governing_evidence(envelope)

    assert actions["Vd_left_kN"] == 91.057
    assert actions["Vd_left_raw_signed_kN"] == -91.057
    assert actions["Ve_left_kN"] == 91.057
    assert actions["Ve_left_raw_signed_kN"] == -91.057

    assert evidence["Vd_left_kN"]["etabs_raw_signed_value"] == -91.057
    assert evidence["Vd_left_kN"]["design_demand_magnitude"] == 91.057
    assert evidence["Vd_left_kN"]["etabs_local_axis_component"] == "V2"
    assert evidence["Vd_left_kN"]["sign_convention"] == ETABS_RAW_SIGN_CONVENTION


def test_r21a_raw_signed_moment_evidence_helper() -> None:
    envelope = {
        "Md_left_neg_kNm": SimpleNamespace(value=66.683, raw_value=-66.683, combo="Grav_Ult", station=0.0),
        "Md_mid_pos_kNm": SimpleNamespace(value=84.682, raw_value=84.682, combo="Cap_SeisX", station=3.65),
        "Md_right_neg_kNm": SimpleNamespace(value=116.378, raw_value=-116.378, combo="Grav_Ult", station=7.0),
    }

    actions = _r21a_raw_signed_action_fields(envelope)
    evidence = _r21a_raw_signed_governing_evidence(envelope)

    assert actions["Md_left_neg_kNm"] == 66.683
    assert actions["M3_left_raw_signed_kNm"] == -66.683
    assert actions["M3_mid_raw_signed_kNm"] == 84.682
    assert actions["M3_right_raw_signed_kNm"] == -116.378

    assert evidence["Md_left_neg_kNm"]["etabs_raw_signed_value"] == -66.683
    assert evidence["Md_left_neg_kNm"]["design_demand_magnitude"] == 66.683
    assert evidence["Md_left_neg_kNm"]["etabs_local_axis_component"] == "M3"
