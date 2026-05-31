from __future__ import annotations

import math
import sys
import types
from pathlib import Path

import pytest

if "tbdy_engine" not in sys.modules:
    tbdy_pkg = types.ModuleType("tbdy_engine")
    tbdy_pkg.__path__ = [str(Path(__file__).resolve().parents[1] / "tbdy_engine")]
    sys.modules["tbdy_engine"] = tbdy_pkg

from tbdy_engine.design.beams.beam_core import evaluate_beam_core


def _benchmark_input(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "beam_id": "B-BENCH-01",
        "story": "+0.00",
        "section_name": "B60x60",
        "bw_mm": 600.0,
        "h_mm": 600.0,
        "d_mm": 550.0,
        "cover_mm": 40.0,
        "Ln_mm": 5000.0,
        "fck_mpa": 30.0,
        "fcd_mpa": 20.0,
        "fctd_mpa": 1.27,
        "fyk_mpa": 420.0,
        "fyd_mpa": 365.0,
        "fywd_mpa": 365.0,
        "Vd_left_kN": 90.0,
        "Ve_left_kN": 107.2,
        "Md_left_neg_kNm": 120.0,
        "Md_mid_pos_kNm": 90.0,
        "Md_right_neg_kNm": 110.0,
        "axial_kN": 0.0,
        "stirrup_legs": 2,
        "stirrup_diameter_mm": 10.0,
        "stirrup_spacing_mm": 100.0,
        "longitudinal_bar_diameter_mm": 16.0,
        # Moment-derived required area must govern; zero is intentionally ignored.
        "top_required_area_cm2": 0.0,
        "top_selected_area_cm2": 10.0,
        "bottom_required_area_cm2": 0.0,
        "bottom_selected_area_cm2": 10.0,
        "missing_inputs": (),
        "source": {"origin": "hand_calc_benchmark"},
    }
    data.update(overrides)
    return data


def _beta1(fck_mpa: float) -> float:
    if fck_mpa <= 30.0:
        return 0.85
    return max(0.65, 0.85 - 0.05 * ((fck_mpa - 30.0) / 7.0))


def _stress_block(*, selected_area_cm2: float, fyd_mpa: float, fcd_mpa: float, bw_mm: float, beta1: float) -> dict[str, float]:
    selected_area_mm2 = selected_area_cm2 * 100.0
    a_mm = selected_area_mm2 * fyd_mpa / (0.85 * fcd_mpa * bw_mm)
    c_mm = a_mm / beta1
    compression_block_kN = 0.85 * fcd_mpa * bw_mm * a_mm / 1000.0
    return {
        "a_mm": a_mm,
        "c_mm": c_mm,
        "compression_block_kN": compression_block_kN,
    }


def _required_area_from_moment_cm2(*, Md_kNm: float, fyd_mpa: float, fcd_mpa: float, bw_mm: float, d_mm: float) -> float:
    # Independent quadratic hand calculation:
    # Mu = As*fyd*(d - a/2)
    # a = As*fyd/(0.85*fcd*bw)
    Mu_Nmm = abs(Md_kNm) * 1_000_000.0
    quadratic_a = (fyd_mpa * fyd_mpa) / (1.7 * fcd_mpa * bw_mm)
    quadratic_b = fyd_mpa * d_mm
    discriminant = quadratic_b * quadratic_b - 4.0 * quadratic_a * Mu_Nmm
    assert discriminant > 0.0
    As_required_mm2 = (quadratic_b - math.sqrt(discriminant)) / (2.0 * quadratic_a)
    return As_required_mm2 / 100.0


def _rho(*, selected_area_cm2: float, bw_mm: float, d_mm: float) -> float:
    return selected_area_cm2 * 100.0 / (bw_mm * d_mm)


def _rho_min(*, fctd_mpa: float, fyd_mpa: float) -> float:
    return max(0.8 * fctd_mpa / fyd_mpa, 0.0015)


def _rho_max() -> float:
    return 0.04


def _plastic_moment(*, selected_area_cm2: float, bw_mm: float, d_mm: float, fcd_mpa: float, fyd_mpa: float) -> dict[str, float]:
    selected_area_mm2 = selected_area_cm2 * 100.0
    a_mm = selected_area_mm2 * fyd_mpa / (0.85 * fcd_mpa * bw_mm)
    lever_arm_mm = d_mm - a_mm / 2.0
    Mp_Nmm = selected_area_mm2 * fyd_mpa * lever_arm_mm
    return {
        "a_mm": a_mm,
        "lever_arm_mm": lever_arm_mm,
        "Mp_Nmm": Mp_Nmm,
        "Mp_kNm": Mp_Nmm / 1_000_000.0,
    }


def _shear_hand_calc(data: dict[str, object]) -> dict[str, float]:
    stirrup_legs = float(data["stirrup_legs"])
    stirrup_diameter_mm = float(data["stirrup_diameter_mm"])
    fywd_mpa = float(data["fywd_mpa"])
    d_mm = float(data["d_mm"])
    stirrup_spacing_mm = float(data["stirrup_spacing_mm"])
    fcd_mpa = float(data["fcd_mpa"])
    fctd_mpa = float(data["fctd_mpa"])
    bw_mm = float(data["bw_mm"])

    Asw_mm2 = stirrup_legs * math.pi * stirrup_diameter_mm**2 / 4.0
    Asw_cm2 = Asw_mm2 / 100.0
    Vc_kN = 0.0
    Vw_kN = Asw_mm2 * fywd_mpa * d_mm / stirrup_spacing_mm / 1000.0
    Vr_kN = Vc_kN + Vw_kN
    Vmax_kN = 0.85 * 0.22 * fcd_mpa * bw_mm * d_mm / 1000.0
    Asw_min_mm2 = 0.3 * fctd_mpa * bw_mm * stirrup_spacing_mm / fywd_mpa
    Asw_min_cm2 = Asw_min_mm2 / 100.0
    return {
        "Asw_mm2": Asw_mm2,
        "Asw_cm2": Asw_cm2,
        "Vc_kN": Vc_kN,
        "Vw_kN": Vw_kN,
        "Vr_kN": Vr_kN,
        "Vmax_kN": Vmax_kN,
        "Asw_min_mm2": Asw_min_mm2,
        "Asw_min_cm2": Asw_min_cm2,
    }


def _candidate_bar_area_cm2(diameter_mm: float, legs: int) -> float:
    return math.pi * diameter_mm * diameter_mm / 4.0 / 100.0 * legs


def _expected_selected_bar(*, required_area_cm2: float, bw_mm: float, d_mm: float, rho_min: float, rho_max: float) -> dict[str, float | int]:
    target_area_cm2 = max(required_area_cm2, rho_min * bw_mm * d_mm / 100.0)
    candidates: list[dict[str, float | int]] = []
    for diameter_mm in (12.0, 14.0, 16.0, 18.0, 20.0, 22.0, 25.0, 28.0, 32.0):
        for legs in range(2, 13):
            area_cm2 = _candidate_bar_area_cm2(diameter_mm, legs)
            candidates.append(
                {
                    "diameter_mm": diameter_mm,
                    "legs": legs,
                    "area_cm2": area_cm2,
                }
            )
    for candidate in sorted(candidates, key=lambda item: (item["area_cm2"], item["legs"], item["diameter_mm"])):
        area_cm2 = float(candidate["area_cm2"])
        rho = area_cm2 * 100.0 / (bw_mm * d_mm)
        if area_cm2 >= target_area_cm2 and rho <= rho_max:
            return {
                "diameter_mm": float(candidate["diameter_mm"]),
                "legs": int(candidate["legs"]),
                "area_cm2": area_cm2,
                "rho": rho,
            }
    raise AssertionError("No deterministic hand-calculated bar candidate found")


def _capacity_design_hand_calc(*, top_mp_kNm: float, bottom_mp_kNm: float, Ln_mm: float, Vd_left_kN: float, Vmax_kN: float) -> dict[str, float]:
    Ve_capacity_kN = (top_mp_kNm + bottom_mp_kNm) / (Ln_mm / 1000.0) + abs(Vd_left_kN)
    return {
        "Ve_capacity_kN": Ve_capacity_kN,
        "capacity_design_vmax_limit_kN": 0.85 * Vmax_kN,
    }


def _checks_by_name(checks: tuple[object, ...]) -> dict[str, object]:
    return {check.name: check for check in checks}


def test_v1_canonical_beamcore_matches_independent_hand_calculation_benchmark() -> None:
    data = _benchmark_input()
    result = evaluate_beam_core(data)

    assert result.status == "OK"
    assert result.geometry is not None
    assert result.geometry.status == "OK"
    assert result.flexure is not None
    assert result.flexure.status == "OK"
    assert result.shear is not None
    assert result.shear.status == "OK"

    geometry_checks = _checks_by_name(result.geometry.checks)
    assert geometry_checks["beam_geometry_min_width"].status == ("OK" if data["bw_mm"] >= 250.0 else "FAIL")
    assert geometry_checks["beam_geometry_min_depth"].status == ("OK" if data["h_mm"] >= 300.0 else "FAIL")
    assert geometry_checks["beam_geometry_span_depth_ratio"].status == ("OK" if data["Ln_mm"] / data["h_mm"] >= 4.0 else "FAIL")
    assert geometry_checks["beam_geometry_depth_width_ratio"].status == ("OK" if data["h_mm"] / data["bw_mm"] <= 3.5 else "FAIL")
    assert geometry_checks["beam_geometry_span_depth_ratio"].demand == pytest.approx(data["Ln_mm"] / data["h_mm"])
    assert geometry_checks["beam_geometry_depth_width_ratio"].demand == pytest.approx(data["h_mm"] / data["bw_mm"])

    beta1 = _beta1(float(data["fck_mpa"]))
    expected_top_required = _required_area_from_moment_cm2(
        Md_kNm=120.0,
        fyd_mpa=float(data["fyd_mpa"]),
        fcd_mpa=float(data["fcd_mpa"]),
        bw_mm=float(data["bw_mm"]),
        d_mm=float(data["d_mm"]),
    )
    expected_bottom_required = _required_area_from_moment_cm2(
        Md_kNm=90.0,
        fyd_mpa=float(data["fyd_mpa"]),
        fcd_mpa=float(data["fcd_mpa"]),
        bw_mm=float(data["bw_mm"]),
        d_mm=float(data["d_mm"]),
    )
    top_block = _stress_block(
        selected_area_cm2=float(data["top_selected_area_cm2"]),
        fyd_mpa=float(data["fyd_mpa"]),
        fcd_mpa=float(data["fcd_mpa"]),
        bw_mm=float(data["bw_mm"]),
        beta1=beta1,
    )
    bottom_block = _stress_block(
        selected_area_cm2=float(data["bottom_selected_area_cm2"]),
        fyd_mpa=float(data["fyd_mpa"]),
        fcd_mpa=float(data["fcd_mpa"]),
        bw_mm=float(data["bw_mm"]),
        beta1=beta1,
    )
    rho_min = _rho_min(fctd_mpa=float(data["fctd_mpa"]), fyd_mpa=float(data["fyd_mpa"]))
    rho_max = _rho_max()
    top_rho = _rho(selected_area_cm2=float(data["top_selected_area_cm2"]), bw_mm=float(data["bw_mm"]), d_mm=float(data["d_mm"]))
    bottom_rho = _rho(selected_area_cm2=float(data["bottom_selected_area_cm2"]), bw_mm=float(data["bw_mm"]), d_mm=float(data["d_mm"]))
    top_plastic = _plastic_moment(
        selected_area_cm2=float(data["top_selected_area_cm2"]),
        bw_mm=float(data["bw_mm"]),
        d_mm=float(data["d_mm"]),
        fcd_mpa=float(data["fcd_mpa"]),
        fyd_mpa=float(data["fyd_mpa"]),
    )
    bottom_plastic = _plastic_moment(
        selected_area_cm2=float(data["bottom_selected_area_cm2"]),
        bw_mm=float(data["bw_mm"]),
        d_mm=float(data["d_mm"]),
        fcd_mpa=float(data["fcd_mpa"]),
        fyd_mpa=float(data["fyd_mpa"]),
    )
    expected_top_bar = _expected_selected_bar(
        required_area_cm2=expected_top_required,
        bw_mm=float(data["bw_mm"]),
        d_mm=float(data["d_mm"]),
        rho_min=rho_min,
        rho_max=rho_max,
    )
    expected_bottom_bar = _expected_selected_bar(
        required_area_cm2=expected_bottom_required,
        bw_mm=float(data["bw_mm"]),
        d_mm=float(data["d_mm"]),
        rho_min=rho_min,
        rho_max=rho_max,
    )

    assert result.flexure.beta1 == pytest.approx(beta1)
    assert result.flexure.top_stress_block_a_mm == pytest.approx(top_block["a_mm"])
    assert result.flexure.top_neutral_axis_c_mm == pytest.approx(top_block["c_mm"])
    assert result.flexure.top_compression_block_kN == pytest.approx(top_block["compression_block_kN"])
    assert result.flexure.bottom_stress_block_a_mm == pytest.approx(bottom_block["a_mm"])
    assert result.flexure.bottom_neutral_axis_c_mm == pytest.approx(bottom_block["c_mm"])
    assert result.flexure.bottom_compression_block_kN == pytest.approx(bottom_block["compression_block_kN"])

    assert result.flexure.top_required_area_from_moment_cm2 == pytest.approx(expected_top_required)
    assert result.flexure.bottom_required_area_from_moment_cm2 == pytest.approx(expected_bottom_required)
    assert result.flexure.required_top_area_cm2 == pytest.approx(expected_top_required)
    assert result.flexure.required_bottom_area_cm2 == pytest.approx(expected_bottom_required)
    assert result.flexure.top_required_area_source == "moment_derived"
    assert result.flexure.bottom_required_area_source == "moment_derived"

    assert result.flexure.rho_min == pytest.approx(rho_min)
    assert result.flexure.rho_max == pytest.approx(rho_max)
    assert result.flexure.top_rho == pytest.approx(top_rho)
    assert result.flexure.bottom_rho == pytest.approx(bottom_rho)

    assert result.flexure.top_plastic_moment_a_mm == pytest.approx(top_plastic["a_mm"])
    assert result.flexure.top_plastic_moment_lever_arm_mm == pytest.approx(top_plastic["lever_arm_mm"])
    assert result.flexure.top_plastic_moment_kNm == pytest.approx(top_plastic["Mp_kNm"])
    assert result.flexure.bottom_plastic_moment_a_mm == pytest.approx(bottom_plastic["a_mm"])
    assert result.flexure.bottom_plastic_moment_lever_arm_mm == pytest.approx(bottom_plastic["lever_arm_mm"])
    assert result.flexure.bottom_plastic_moment_kNm == pytest.approx(bottom_plastic["Mp_kNm"])

    assert result.flexure.top_selected_bar_diameter_mm == pytest.approx(expected_top_bar["diameter_mm"])
    assert result.flexure.top_selected_bar_legs == expected_top_bar["legs"]
    assert result.flexure.top_selected_bar_area_cm2 == pytest.approx(expected_top_bar["area_cm2"])
    assert result.flexure.bottom_selected_bar_diameter_mm == pytest.approx(expected_bottom_bar["diameter_mm"])
    assert result.flexure.bottom_selected_bar_legs == expected_bottom_bar["legs"]
    assert result.flexure.bottom_selected_bar_area_cm2 == pytest.approx(expected_bottom_bar["area_cm2"])

    flexure_checks = _checks_by_name(result.flexure.checks)
    assert flexure_checks["beam_flexure_top_area_provided_ge_required"].status == "OK"
    assert flexure_checks["beam_flexure_bottom_area_provided_ge_required"].status == "OK"
    assert flexure_checks["beam_flexure_top_rho_ge_rho_min"].status == "OK"
    assert flexure_checks["beam_flexure_bottom_rho_ge_rho_min"].status == "OK"
    assert flexure_checks["beam_flexure_top_rho_le_rho_max"].status == "OK"
    assert flexure_checks["beam_flexure_bottom_rho_le_rho_max"].status == "OK"
    assert flexure_checks["beam_flexure_top_bar_selection"].status == "OK"
    assert flexure_checks["beam_flexure_bottom_bar_selection"].status == "OK"
    assert flexure_checks["beam_flexure_top_plastic_moment_available"].status == "OK"
    assert flexure_checks["beam_flexure_bottom_plastic_moment_available"].status == "OK"

    shear = _shear_hand_calc(data)
    assert result.shear.Asw_mm2 == pytest.approx(shear["Asw_mm2"])
    assert result.shear.Asw_cm2 == pytest.approx(shear["Asw_cm2"])
    assert result.shear.Vc_kN == pytest.approx(shear["Vc_kN"])
    assert result.shear.Vw_kN == pytest.approx(shear["Vw_kN"])
    assert result.shear.Vr_kN == pytest.approx(shear["Vr_kN"])
    assert result.shear.Vmax_kN == pytest.approx(shear["Vmax_kN"])
    assert result.shear.Asw_min_mm2 == pytest.approx(shear["Asw_min_mm2"])
    assert result.shear.Asw_min_cm2 == pytest.approx(shear["Asw_min_cm2"])

    shear_checks = _checks_by_name(result.shear.checks)
    assert shear_checks["beam_shear_ve_le_vr"].status == "OK"
    assert shear_checks["beam_shear_ve_le_vr"].demand == pytest.approx(float(data["Ve_left_kN"]))
    assert shear_checks["beam_shear_ve_le_vr"].capacity == pytest.approx(shear["Vr_kN"])
    assert shear_checks["beam_shear_ve_le_085_vmax"].status == "OK"
    assert shear_checks["beam_shear_ve_le_085_vmax"].capacity == pytest.approx(0.85 * shear["Vmax_kN"])
    assert shear_checks["beam_shear_spacing_le_d_over_4"].status == "OK"
    assert shear_checks["beam_shear_spacing_le_150"].status == "OK"
    assert shear_checks["beam_shear_spacing_le_8_longitudinal_diameter"].status == "OK"
    assert shear_checks["beam_shear_stirrup_diameter_ge_8"].status == "OK"
    assert shear_checks["beam_shear_stirrup_legs_ge_2"].status == "OK"
    assert shear_checks["beam_shear_asw_ge_asw_min"].status == "OK"

    capacity = _capacity_design_hand_calc(
        top_mp_kNm=top_plastic["Mp_kNm"],
        bottom_mp_kNm=bottom_plastic["Mp_kNm"],
        Ln_mm=float(data["Ln_mm"]),
        Vd_left_kN=float(data["Vd_left_kN"]),
        Vmax_kN=shear["Vmax_kN"],
    )
    cd_vr = shear_checks["beam_shear_capacity_design_ve_le_vr"]
    cd_vmax = shear_checks["beam_shear_capacity_design_ve_le_085_vmax"]

    assert cd_vr.status == "OK"
    assert cd_vr.demand == pytest.approx(capacity["Ve_capacity_kN"])
    assert cd_vr.capacity == pytest.approx(shear["Vr_kN"])
    assert cd_vr.ratio == pytest.approx(capacity["Ve_capacity_kN"] / shear["Vr_kN"])
    assert cd_vr.evidence["formula_capacity_check"] == "Ve_capacity_kN <= Vr_kN"

    assert cd_vmax.status == "OK"
    assert cd_vmax.demand == pytest.approx(capacity["Ve_capacity_kN"])
    assert cd_vmax.capacity == pytest.approx(capacity["capacity_design_vmax_limit_kN"])
    assert cd_vmax.ratio == pytest.approx(capacity["Ve_capacity_kN"] / capacity["capacity_design_vmax_limit_kN"])
    assert cd_vmax.evidence["formula_capacity_check"] == "Ve_capacity_kN <= 0.85 * Vmax_kN"

    core_check_names = {check.name for check in result.core_checks}
    for expected_name in (
        "beam_shear_ve_le_vr",
        "beam_shear_ve_le_085_vmax",
        "beam_shear_capacity_design_ve_le_vr",
        "beam_shear_capacity_design_ve_le_085_vmax",
        "beam_flexure_top_plastic_moment_available",
        "beam_flexure_bottom_plastic_moment_available",
    ):
        assert expected_name in core_check_names


def test_v1_negative_benchmark_capacity_design_ve_exceeds_vr_by_hand_calculation() -> None:
    data = _benchmark_input(stirrup_spacing_mm=300.0)
    result = evaluate_beam_core(data)

    assert result.status == "FAIL"
    assert result.shear is not None
    assert result.flexure is not None

    top_plastic = _plastic_moment(
        selected_area_cm2=float(data["top_selected_area_cm2"]),
        bw_mm=float(data["bw_mm"]),
        d_mm=float(data["d_mm"]),
        fcd_mpa=float(data["fcd_mpa"]),
        fyd_mpa=float(data["fyd_mpa"]),
    )
    bottom_plastic = _plastic_moment(
        selected_area_cm2=float(data["bottom_selected_area_cm2"]),
        bw_mm=float(data["bw_mm"]),
        d_mm=float(data["d_mm"]),
        fcd_mpa=float(data["fcd_mpa"]),
        fyd_mpa=float(data["fyd_mpa"]),
    )
    shear = _shear_hand_calc(data)
    capacity = _capacity_design_hand_calc(
        top_mp_kNm=top_plastic["Mp_kNm"],
        bottom_mp_kNm=bottom_plastic["Mp_kNm"],
        Ln_mm=float(data["Ln_mm"]),
        Vd_left_kN=float(data["Vd_left_kN"]),
        Vmax_kN=shear["Vmax_kN"],
    )

    assert capacity["Ve_capacity_kN"] > shear["Vr_kN"]

    shear_checks = _checks_by_name(result.shear.checks)
    cd_vr = shear_checks["beam_shear_capacity_design_ve_le_vr"]

    assert cd_vr.status == "FAIL"
    assert cd_vr.demand == pytest.approx(capacity["Ve_capacity_kN"])
    assert cd_vr.capacity == pytest.approx(shear["Vr_kN"])
    assert cd_vr.ratio == pytest.approx(capacity["Ve_capacity_kN"] / shear["Vr_kN"])
    assert cd_vr.ratio > 1.0

    # The Vmax capacity-design limit is intentionally still OK in this negative case;
    # the failure target is independently hand-calculated as Ve_capacity > Vr.
    cd_vmax = shear_checks["beam_shear_capacity_design_ve_le_085_vmax"]
    assert cd_vmax.status == "OK"
    assert cd_vmax.capacity == pytest.approx(capacity["capacity_design_vmax_limit_kN"])