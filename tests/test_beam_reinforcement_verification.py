"""
Beam Reinforcement Verification tests.
"""

import pytest
from dataclasses import asdict

from tbdy_engine.design.beams.beam_region_flexure import (
    BeamFlexureRegionDesignResult,
    BeamRegionFlexureResult,
    STATUS_OK as REGION_OK,
    STATUS_MISSING_DEMAND,
    STATUS_OVER_REINFORCED,
)
from tbdy_engine.design.beams.calculators.shear_reinforcement_design import (
    ShearReinforcementDesignResult,
    STATUS_SHEAR_REINFORCEMENT_REQUIRED,
)
from tbdy_engine.verification.beams.provided_reinforcement import (
    BeamProvidedReinforcement,
    ProvidedStirrup,
)
from tbdy_engine.verification.beams.verification_result import (
    STATUS_PASS,
    STATUS_FAIL,
    STATUS_UNKNOWN,
    STATUS_NOT_APPLICABLE,
)
from tbdy_engine.verification.beams.reinforcement_verification import (
    verify_flexure_regions,
    verify_stirrup_spacing,
    verify_beam_reinforcement,
)


# =============================================================================
# Helpers
# =============================================================================

def _flexure_result():
    return BeamFlexureRegionDesignResult(
        beam_id="B101_S1",
        label="B101",
        status="OK",
        regions={
            "top_left": BeamRegionFlexureResult(
                region="top_left",
                status=REGION_OK,
                As_design_required_cm2=18.0,
            ),
            "bottom_mid": BeamRegionFlexureResult(
                region="bottom_mid",
                status=REGION_OK,
                As_design_required_cm2=14.0,
            ),
            "top_right": BeamRegionFlexureResult(
                region="top_right",
                status=REGION_OK,
                As_design_required_cm2=20.0,
            ),
        },
    )


def _provided_pass():
    return BeamProvidedReinforcement(
        beam_id="B101_S1", label="B101",
        top_left_As_cm2=20.0, bottom_mid_As_cm2=16.0, top_right_As_cm2=22.0,
        stirrup=ProvidedStirrup(diameter_mm=10.0, legs=2, spacing_mm=100.0),
    )


def _shear_result():
    return ShearReinforcementDesignResult(
        status=STATUS_SHEAR_REINFORCEMENT_REQUIRED,
        V_design_kN=350.0, Vc_kN=320.0, Vs_required_kN=30.0,
        s_required_limited_mm=150.0, s_max_mm=200.0, governing="shear",
    )


# =============================================================================
# Existing tests (1-12)
# =============================================================================

def test_flexure_pass():
    checks = verify_flexure_regions(_flexure_result(), _provided_pass())
    assert len(checks) == 3
    for c in checks:
        assert c.status == STATUS_PASS

    tl = [c for c in checks if "top_left" in c.check_id][0]
    assert tl.utilization == pytest.approx(0.9)


def test_flexure_fail():
    provided = BeamProvidedReinforcement(
        beam_id="B101_S1", label="B101",
        top_left_As_cm2=15.0, bottom_mid_As_cm2=16.0, top_right_As_cm2=22.0,
    )
    checks = verify_flexure_regions(_flexure_result(), provided)
    tl = [c for c in checks if "top_left" in c.check_id][0]
    assert tl.status == STATUS_FAIL


def test_flexure_missing_provided():
    provided = BeamProvidedReinforcement(beam_id="B101_S1", label="B101")
    checks = verify_flexure_regions(_flexure_result(), provided)
    for c in checks:
        assert c.status == STATUS_UNKNOWN


def test_region_missing_demand():
    result = BeamFlexureRegionDesignResult(
        beam_id="B101_S1", label="B101", status="PARTIAL",
        regions={
            "top_left": BeamRegionFlexureResult(region="top_left", status=STATUS_MISSING_DEMAND),
            "bottom_mid": BeamRegionFlexureResult(region="bottom_mid", status=REGION_OK, As_design_required_cm2=14.0),
            "top_right": BeamRegionFlexureResult(region="top_right", status=REGION_OK, As_design_required_cm2=20.0),
        },
    )
    checks = verify_flexure_regions(result, _provided_pass())
    tl = [c for c in checks if "top_left" in c.check_id][0]
    assert tl.status == STATUS_UNKNOWN


def test_region_over_reinforced():
    result = BeamFlexureRegionDesignResult(
        beam_id="B101_S1", label="B101", status="OVER_REINFORCED",
        regions={
            "top_left": BeamRegionFlexureResult(region="top_left", status=STATUS_OVER_REINFORCED, As_design_required_cm2=100.0),
            "bottom_mid": BeamRegionFlexureResult(region="bottom_mid", status=REGION_OK, As_design_required_cm2=14.0),
            "top_right": BeamRegionFlexureResult(region="top_right", status=REGION_OK, As_design_required_cm2=20.0),
        },
    )
    checks = verify_flexure_regions(result, _provided_pass())
    tl = [c for c in checks if "top_left" in c.check_id][0]
    assert tl.status == STATUS_FAIL


def test_shear_spacing_pass():
    provided = BeamProvidedReinforcement(
        beam_id="B101_S1", label="B101",
        stirrup=ProvidedStirrup(diameter_mm=10.0, legs=2, spacing_mm=100.0),
    )
    checks = verify_stirrup_spacing(_shear_result(), provided)
    assert checks[0].status == STATUS_PASS


def test_shear_spacing_fail():
    provided = BeamProvidedReinforcement(
        beam_id="B101_S1", label="B101",
        stirrup=ProvidedStirrup(diameter_mm=10.0, legs=2, spacing_mm=200.0),
    )
    checks = verify_stirrup_spacing(_shear_result(), provided)
    assert checks[0].status == STATUS_FAIL


def test_shear_missing_stirrup():
    provided = BeamProvidedReinforcement(beam_id="B101_S1", label="B101")
    checks = verify_stirrup_spacing(_shear_result(), provided)
    assert checks[0].status == STATUS_UNKNOWN


def test_overall_status_fail():
    provided = BeamProvidedReinforcement(
        beam_id="B101_S1", label="B101",
        top_left_As_cm2=10.0, bottom_mid_As_cm2=16.0, top_right_As_cm2=22.0,
    )
    verification = verify_beam_reinforcement(
        beam_id="B101_S1", label="B101",
        provided=provided, flexure_region_result=_flexure_result(),
    )
    assert verification.status == STATUS_FAIL


def test_overall_status_pass():
    verification = verify_beam_reinforcement(
        beam_id="B101_S1", label="B101",
        provided=_provided_pass(),
        flexure_region_result=_flexure_result(),
        shear_result=_shear_result(),
    )
    assert verification.status == STATUS_PASS


def test_no_checks_not_applicable():
    verification = verify_beam_reinforcement(
        beam_id="B101_S1", label="B101",
        provided=BeamProvidedReinforcement(beam_id="B101_S1", label="B101"),
    )
    assert verification.status == STATUS_NOT_APPLICABLE


def test_design_result_immutability():
    flexure_before = _flexure_result()
    shear_before = _shear_result()
    flexure_dict_before = asdict(flexure_before)
    shear_dict_before = asdict(shear_before)

    verify_beam_reinforcement(
        beam_id="B101_S1", label="B101",
        provided=_provided_pass(),
        flexure_region_result=flexure_before,
        shear_result=shear_before,
    )

    assert asdict(flexure_before) == flexure_dict_before
    assert asdict(shear_before) == shear_dict_before


# =============================================================================
# NEW: Identity mismatch tests
# =============================================================================

def test_identity_mismatch_beam_id():
    verification = verify_beam_reinforcement(
        beam_id="B999_S1",  # wrong
        label="B101",
        provided=_provided_pass(),
        flexure_region_result=_flexure_result(),
    )
    assert verification.status == STATUS_UNKNOWN
    assert verification.checks == ()
    assert "invalid_inputs" in verification.evidence
    assert "identity mismatch" in str(verification.evidence["invalid_inputs"])


def test_identity_mismatch_label():
    verification = verify_beam_reinforcement(
        beam_id="B101_S1",
        label="B999",  # wrong
        provided=_provided_pass(),
        flexure_region_result=_flexure_result(),
    )
    assert verification.status == STATUS_UNKNOWN
    assert verification.checks == ()
    assert "identity mismatch" in str(verification.evidence.get("invalid_inputs", ""))


# =============================================================================
# NEW: Zero provided value tests
# =============================================================================

def test_flexure_zero_provided():
    provided = BeamProvidedReinforcement(
        beam_id="B101_S1", label="B101",
        top_left_As_cm2=0.0, bottom_mid_As_cm2=16.0, top_right_As_cm2=22.0,
    )
    checks = verify_flexure_regions(_flexure_result(), provided)
    tl = [c for c in checks if "top_left" in c.check_id][0]
    assert tl.status == STATUS_FAIL
    assert tl.message == "provided reinforcement must be positive"
    assert tl.utilization is None


def test_shear_zero_provided_spacing():
    provided = BeamProvidedReinforcement(
        beam_id="B101_S1", label="B101",
        stirrup=ProvidedStirrup(diameter_mm=10.0, legs=2, spacing_mm=0.0),
    )
    checks = verify_stirrup_spacing(_shear_result(), provided)
    assert checks[0].status == STATUS_FAIL
    assert "must be positive" in checks[0].message
