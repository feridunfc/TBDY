"""
Beam Design Benchmark Suite.
Golden fixture tests for all beam design kernels, verification, and crosscheck.
"""

import json
from dataclasses import asdict
from pathlib import Path

import pytest

BENCHMARK_DIR = Path(__file__).parent / "benchmarks" / "beams"


# =============================================================================
# Helpers
# =============================================================================

def _load_case(filename: str) -> dict:
    """Load benchmark fixture. Fails if missing."""
    path = BENCHMARK_DIR / filename
    assert path.exists(), f"Benchmark fixture missing: {path}"
    return json.loads(path.read_text(encoding="utf-8"))


def _assert_close(actual, expected, rel=0.001):
    """Assert numeric value within relative tolerance."""
    assert actual == pytest.approx(expected, rel=rel), (
        f"Value {actual} not within {rel*100}% of expected {expected}"
    )


# =============================================================================
# 1. Flexure Md→As Benchmark
# =============================================================================

def test_benchmark_flexure_md_to_as():
    from tbdy_engine.design.beams.calculators.flexure_design import (
        FlexureMdToAsInput,
        flexure_md_to_as,
    )

    case = _load_case("flexure_md_to_as_case_001.json")
    inp = case["input"]
    expected = case["expected"]

    result = flexure_md_to_as(FlexureMdToAsInput(
        Md_kNm=inp["Md_kNm"],
        bw_mm=inp["bw_mm"],
        d_mm=inp["d_mm"],
        fcd_mpa=inp["fcd_mpa"],
        fyd_mpa=inp["fyd_mpa"],
        alpha=inp.get("alpha", 0.85),
        beta=inp.get("beta", 0.85),
    ))

    assert result.status == expected["status"]
    assert expected["As_required_cm2_min"] <= result.As_required_cm2 <= expected["As_required_cm2_max"]
    assert result.Mu_check_kNm >= inp["Md_kNm"]
    assert result.neutral_axis_ratio <= expected["neutral_axis_ratio_max"]
    assert expected["a_mm_min"] <= result.a_mm <= expected["a_mm_max"]
    assert expected["lever_arm_z_mm_min"] <= result.lever_arm_z_mm <= expected["lever_arm_z_mm_max"]


# =============================================================================
# 2. Flexure Limits Benchmark
# =============================================================================

def test_benchmark_flexure_limits():
    from tbdy_engine.design.beams.calculators.flexure_limits import (
        FlexureLimitsInput,
        flexure_limits,
    )

    case = _load_case("flexure_limits_case_001.json")
    inp = case["input"]
    expected = case["expected"]
    tol = case.get("tolerance", {}).get("relative", 0.001)

    result = flexure_limits(FlexureLimitsInput(
        As_required_cm2=inp["As_required_cm2"],
        bw_mm=inp["bw_mm"],
        d_mm=inp["d_mm"],
        fctd_mpa=inp["fctd_mpa"],
        fyd_mpa=inp["fyd_mpa"],
        rho_max=inp["rho_max"],
    ))

    assert result.status == expected["status"]
    assert result.governing == expected["governing"]
    assert result.As_design_required_cm2 == expected["As_design_required_cm2"]
    _assert_close(result.rho_required, expected["rho_required"], rel=tol)
    _assert_close(result.rho_min, expected["rho_min"], rel=tol)
    _assert_close(result.As_min_cm2, expected["As_min_cm2"], rel=tol)
    _assert_close(result.As_max_cm2, expected["As_max_cm2"], rel=tol)


# =============================================================================
# 3. Region Flexure Benchmark
# =============================================================================

def test_benchmark_region_flexure():
    from tbdy_engine.design.beams.context import (
        BeamGeometryInput,
        BeamMaterialInput,
        BeamMetadata,
        BeamModelContext,
    )
    from tbdy_engine.design.beams.demand import BeamDemandSet
    from tbdy_engine.design.beams.beam_region_flexure import (
        design_beam_region_flexure,
    )

    case = _load_case("region_flexure_case_001.json")
    ctx = case["context"]
    dem = case["demand"]
    expected = case["expected"]

    context = BeamModelContext(
        beam_id=ctx["beam_id"],
        geometry=BeamGeometryInput(**ctx["geometry"]),
        material=BeamMaterialInput(**ctx["material"]),
        metadata=BeamMetadata(**ctx["metadata"]),
    )

    demand = BeamDemandSet(
        beam_id=dem["beam_id"],
        label=dem["label"],
        source=dem["source"],
        Md_left_neg_kNm=dem["Md_left_neg_kNm"],
        Md_mid_pos_kNm=dem["Md_mid_pos_kNm"],
        Md_right_neg_kNm=dem["Md_right_neg_kNm"],
        Vd_left_kN=dem["Vd_left_kN"],
        Vd_right_kN=dem["Vd_right_kN"],
        N_kN=dem.get("N_kN", 0.0),
    )

    result = design_beam_region_flexure(context, demand)

    assert result.status == expected["status"]

    for region_key, exp_region in expected["regions"].items():
        region = result.regions[region_key]
        assert region.status == exp_region["status"]
        assert exp_region["As_design_required_cm2_min"] <= region.As_design_required_cm2 <= exp_region["As_design_required_cm2_max"]


# =============================================================================
# 4. Plastic Moment Benchmark
# =============================================================================

def test_benchmark_plastic_moment():
    from tbdy_engine.design.beams.calculators.plastic_moment import (
        PlasticMomentInput,
        plastic_moment,
    )

    case = _load_case("plastic_moment_case_001.json")
    inp = case["input"]
    expected = case["expected"]
    tol = case.get("tolerance", {}).get("relative", 0.001)

    result = plastic_moment(PlasticMomentInput(
        As_cm2=inp["As_cm2"],
        bw_mm=inp["bw_mm"],
        d_mm=inp["d_mm"],
        fcd_mpa=inp["fcd_mpa"],
        fyk_mpa=inp["fyk_mpa"],
        alpha=inp.get("alpha", 0.85),
        beta=inp.get("beta", 0.85),
        steel_overstrength=inp.get("steel_overstrength", 1.25),
    ))

    assert result.status == expected["status"]
    _assert_close(result.fs_capacity_mpa, expected["fs_capacity_mpa"], rel=tol)
    _assert_close(result.a_mm, expected["a_mm"], rel=tol)
    _assert_close(result.lever_arm_z_mm, expected["lever_arm_z_mm"], rel=tol)
    _assert_close(result.Mpr_kNm, expected["Mpr_kNm"], rel=tol)


# =============================================================================
# 5. Capacity Ve Benchmark
# =============================================================================

def test_benchmark_capacity_ve():
    from tbdy_engine.design.beams.calculators.capacity_design import (
        CapacityDesignVeInput,
        capacity_design_ve,
    )

    case = _load_case("capacity_ve_case_001.json")
    inp = case["input"]
    expected = case["expected"]
    tol = case.get("tolerance", {}).get("relative", 0.001)

    result = capacity_design_ve(CapacityDesignVeInput(
        Mpr_left_kNm=inp["Mpr_left_kNm"],
        Mpr_right_kNm=inp["Mpr_right_kNm"],
        Vg_kN=inp["Vg_kN"],
        Ln_mm=inp["Ln_mm"],
        direction=inp.get("direction", "absolute"),
    ))

    assert result.status == expected["status"]
    _assert_close(result.plastic_shear_component_kN, expected["plastic_shear_component_kN"], rel=tol)
    _assert_close(result.Ve_capacity_kN, expected["Ve_capacity_kN"], rel=tol)


# =============================================================================
# 6. Shear Reinforcement Benchmark
# =============================================================================

def test_benchmark_shear_reinforcement():
    from tbdy_engine.design.beams.calculators.shear_reinforcement_design import (
        ShearReinforcementDesignInput,
        shear_reinforcement_design,
    )

    case = _load_case("shear_reinforcement_case_001.json")
    inp = case["input"]
    expected = case["expected"]
    tol = case.get("tolerance", {}).get("relative", 0.001)

    result = shear_reinforcement_design(ShearReinforcementDesignInput(
        V_design_kN=inp["V_design_kN"],
        bw_mm=inp["bw_mm"],
        d_mm=inp["d_mm"],
        fctd_mpa=inp["fctd_mpa"],
        fywd_mpa=inp["fywd_mpa"],
        stirrup_diameter_mm=inp["stirrup_diameter_mm"],
        stirrup_legs=inp["stirrup_legs"],
        cot_theta=inp.get("cot_theta", 1.0),
        vc_factor=inp.get("vc_factor", 0.65),
        s_max_mm=inp.get("s_max_mm", 200.0),
    ))

    assert result.status == expected["status"]
    _assert_close(result.Vc_kN, expected["Vc_kN"], rel=tol)
    _assert_close(result.Vs_required_kN, expected["Vs_required_kN"], rel=tol)
    _assert_close(result.Asw_per_stirrup_mm2, expected["Asw_per_stirrup_mm2"], rel=tol)
    assert result.s_required_limited_mm == expected["s_required_limited_mm"]
    assert result.governing == expected["governing"]


# =============================================================================
# 7. Verification Benchmark
# =============================================================================

def test_benchmark_verification():
    from tbdy_engine.design.beams.beam_region_flexure import (
        BeamFlexureRegionDesignResult,
        BeamRegionFlexureResult,
        STATUS_OK as REGION_OK,
    )
    from tbdy_engine.design.beams.calculators.shear_reinforcement_design import (
        ShearReinforcementDesignResult,
    )
    from tbdy_engine.verification.beams.provided_reinforcement import (
        BeamProvidedReinforcement,
        ProvidedStirrup,
    )
    from tbdy_engine.verification.beams.reinforcement_verification import (
        verify_beam_reinforcement,
    )

    case = _load_case("verification_case_001.json")
    req = case["required"]
    prov = case["provided"]
    expected = case["expected"]

    flexure_result = BeamFlexureRegionDesignResult(
        beam_id="B101_S1", label="B101", status="OK",
        regions={
            "top_left": BeamRegionFlexureResult(
                region="top_left", status=REGION_OK,
                As_design_required_cm2=req["top_left_As_cm2"],
            ),
            "bottom_mid": BeamRegionFlexureResult(
                region="bottom_mid", status=REGION_OK,
                As_design_required_cm2=req["bottom_mid_As_cm2"],
            ),
            "top_right": BeamRegionFlexureResult(
                region="top_right", status=REGION_OK,
                As_design_required_cm2=req["top_right_As_cm2"],
            ),
        },
    )

    shear_result = ShearReinforcementDesignResult(
        status="SHEAR_REINFORCEMENT_REQUIRED",
        s_required_limited_mm=req["shear_spacing_required_mm"],
        s_max_mm=200.0,
        governing="shear",
    )

    provided = BeamProvidedReinforcement(
        beam_id=prov["beam_id"],
        label=prov["label"],
        top_left_As_cm2=prov["top_left_As_cm2"],
        bottom_mid_As_cm2=prov["bottom_mid_As_cm2"],
        top_right_As_cm2=prov["top_right_As_cm2"],
        stirrup=ProvidedStirrup(
            diameter_mm=prov["stirrup"]["diameter_mm"],
            legs=prov["stirrup"]["legs"],
            spacing_mm=prov["stirrup"]["spacing_mm"],
        ),
    )

    verification = verify_beam_reinforcement(
        beam_id="B101_S1", label="B101",
        provided=provided,
        flexure_region_result=flexure_result,
        shear_result=shear_result,
    )

    assert verification.status == expected["status"]
    assert len(verification.checks) == expected["check_count"]
    for check in verification.checks:
        assert check.status == "PASS"


# =============================================================================
# 8. ETABS Crosscheck Benchmark
# =============================================================================

def test_benchmark_etabs_crosscheck():
    from tbdy_engine.design.beams.beam_region_flexure import (
        BeamFlexureRegionDesignResult,
        BeamRegionFlexureResult,
        STATUS_OK as REGION_OK,
    )
    from tbdy_engine.design.beams.calculators.shear_reinforcement_design import (
        ShearReinforcementDesignResult,
    )
    from tbdy_engine.verification.beams.etabs_design_output import ETABSDesignOutput
    from tbdy_engine.verification.beams.etabs_crosscheck import (
        compare_engine_to_etabs_design_output,
    )

    case = _load_case("etabs_crosscheck_case_001.json")
    eng = case["engine"]
    etabs_data = case["etabs"]
    expected = case["expected"]

    flexure_result = BeamFlexureRegionDesignResult(
        beam_id="B101_S1", label="B101", status="OK",
        regions={
            "top_left": BeamRegionFlexureResult(
                region="top_left", status=REGION_OK,
                As_design_required_cm2=eng["top_left_As_cm2"],
            ),
            "bottom_mid": BeamRegionFlexureResult(
                region="bottom_mid", status=REGION_OK,
                As_design_required_cm2=eng["bottom_mid_As_cm2"],
            ),
            "top_right": BeamRegionFlexureResult(
                region="top_right", status=REGION_OK,
                As_design_required_cm2=eng["top_right_As_cm2"],
            ),
        },
    )

    shear_result = ShearReinforcementDesignResult(
        status="SHEAR_REINFORCEMENT_REQUIRED",
        s_required_limited_mm=eng["shear_spacing_required_mm"],
        s_max_mm=200.0,
        governing="shear",
    )

    etabs_output = ETABSDesignOutput(
        beam_id=etabs_data["beam_id"],
        label=etabs_data["label"],
        top_left_As_required_cm2=etabs_data["top_left_As_required_cm2"],
        bottom_mid_As_required_cm2=etabs_data["bottom_mid_As_required_cm2"],
        top_right_As_required_cm2=etabs_data["top_right_As_required_cm2"],
        shear_spacing_required_mm=etabs_data["shear_spacing_required_mm"],
    )

    result = compare_engine_to_etabs_design_output(
        beam_id="B101_S1", label="B101",
        etabs_output=etabs_output,
        flexure_region_result=flexure_result,
        shear_result=shear_result,
    )

    assert result.status == expected["status"]
    assert len(result.items) == expected["item_count"]

    for item in result.items:
        expected_status = expected["statuses"].get(item.field)
        assert expected_status is not None, f"Unexpected field {item.field}"
        assert item.status == expected_status, (
            f"Field {item.field}: expected {expected_status}, got {item.status}"
        )


# =============================================================================
# 9. Determinism
# =============================================================================

def test_benchmark_determinism():
    """All benchmark fixtures produce identical results on repeated runs."""
    from tbdy_engine.design.beams.calculators.flexure_design import (
        FlexureMdToAsInput, flexure_md_to_as,
    )
    from tbdy_engine.design.beams.calculators.flexure_limits import (
        FlexureLimitsInput, flexure_limits,
    )
    from tbdy_engine.design.beams.calculators.plastic_moment import (
        PlasticMomentInput, plastic_moment,
    )
    from tbdy_engine.design.beams.calculators.capacity_design import (
        CapacityDesignVeInput, capacity_design_ve,
    )
    from tbdy_engine.design.beams.calculators.shear_reinforcement_design import (
        ShearReinforcementDesignInput, shear_reinforcement_design,
    )

    # Flexure
    case = _load_case("flexure_md_to_as_case_001.json")["input"]
    inp = FlexureMdToAsInput(**{k: case[k] for k in ["Md_kNm","bw_mm","d_mm","fcd_mpa","fyd_mpa"]})
    first = asdict(flexure_md_to_as(inp))
    for _ in range(50):
        assert asdict(flexure_md_to_as(inp)) == first

    # Limits
    case = _load_case("flexure_limits_case_001.json")["input"]
    inp = FlexureLimitsInput(**case)
    first = asdict(flexure_limits(inp))
    for _ in range(50):
        assert asdict(flexure_limits(inp)) == first

    # Plastic moment
    case = _load_case("plastic_moment_case_001.json")["input"]
    inp = PlasticMomentInput(**case)
    first = asdict(plastic_moment(inp))
    for _ in range(50):
        assert asdict(plastic_moment(inp)) == first

    # Capacity Ve
    case = _load_case("capacity_ve_case_001.json")["input"]
    inp = CapacityDesignVeInput(**case)
    first = asdict(capacity_design_ve(inp))
    for _ in range(50):
        assert asdict(capacity_design_ve(inp)) == first

    # Shear reinforcement
    case = _load_case("shear_reinforcement_case_001.json")["input"]
    inp = ShearReinforcementDesignInput(**case)
    first = asdict(shear_reinforcement_design(inp))
    for _ in range(50):
        assert asdict(shear_reinforcement_design(inp)) == first


# =============================================================================
# 10. Missing fixture must fail
# =============================================================================

def test_missing_fixture_fails():
    """Missing benchmark fixture must raise AssertionError, not skip."""
    with pytest.raises(AssertionError, match="Benchmark fixture missing"):
        _load_case("nonexistent_fixture.json")
