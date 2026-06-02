"""ETABS Crosscheck tests."""

import pytest
from dataclasses import asdict

from tbdy_engine.design.beams.beam_region_flexure import (
    BeamFlexureRegionDesignResult,
    BeamRegionFlexureResult,
    STATUS_OK as REGION_OK,
)
from tbdy_engine.design.beams.calculators.shear_reinforcement_design import (
    ShearReinforcementDesignResult,
    STATUS_SHEAR_REINFORCEMENT_REQUIRED,
)
from tbdy_engine.verification.beams.etabs_design_output import ETABSDesignOutput
from tbdy_engine.verification.beams.comparison_result import (
    ETABSComparisonItem,
    STATUS_CLOSE,
    STATUS_MODERATE,
    STATUS_LARGE,
    STATUS_INCOMPLETE,
)
from tbdy_engine.verification.beams.etabs_crosscheck import (
    compare_numeric_field,
    compare_flexure_region_to_etabs,
    compare_shear_spacing_to_etabs,
    compare_engine_to_etabs_design_output,
)


# =============================================================================
# Numeric Comparison Tests
# =============================================================================

def test_numeric_close():
    item = compare_numeric_field(field="test", engine_value=100.0, etabs_value=103.0)
    assert item.status == STATUS_CLOSE
    assert item.difference_percent == pytest.approx(3.0)


def test_numeric_moderate():
    item = compare_numeric_field(field="test", engine_value=100.0, etabs_value=115.0)
    assert item.status == STATUS_MODERATE
    assert item.difference_percent == pytest.approx(15.0)


def test_numeric_large():
    item = compare_numeric_field(field="test", engine_value=100.0, etabs_value=130.0)
    assert item.status == STATUS_LARGE
    assert item.difference_percent == pytest.approx(30.0)


def test_numeric_missing_etabs():
    item = compare_numeric_field(field="test", engine_value=100.0, etabs_value=None)
    assert item.status == STATUS_INCOMPLETE


def test_numeric_missing_engine():
    item = compare_numeric_field(field="test", engine_value=None, etabs_value=100.0)
    assert item.status == STATUS_INCOMPLETE


def test_numeric_zero_zero():
    item = compare_numeric_field(field="test", engine_value=0.0, etabs_value=0.0)
    assert item.status == STATUS_CLOSE
    assert item.difference_percent == 0.0


def test_numeric_engine_zero_etabs_nonzero():
    item = compare_numeric_field(field="test", engine_value=0.0, etabs_value=10.0)
    assert item.status == STATUS_LARGE
    assert item.difference_percent is None


# =============================================================================
# Flexure Comparison Tests
# =============================================================================

def _flexure_result():
    return BeamFlexureRegionDesignResult(
        beam_id="B101_S1", label="B101", status="OK",
        regions={
            "top_left": BeamRegionFlexureResult(
                region="top_left", status=REGION_OK, As_design_required_cm2=18.0,
            ),
            "bottom_mid": BeamRegionFlexureResult(
                region="bottom_mid", status=REGION_OK, As_design_required_cm2=14.0,
            ),
            "top_right": BeamRegionFlexureResult(
                region="top_right", status=REGION_OK, As_design_required_cm2=20.0,
            ),
        },
    )


def test_flexure_comparison():
    etabs = ETABSDesignOutput(
        beam_id="B101_S1", label="B101",
        top_left_As_required_cm2=18.5,
        bottom_mid_As_required_cm2=16.0,
        top_right_As_required_cm2=30.0,
    )
    items = compare_flexure_region_to_etabs(_flexure_result(), etabs)

    assert len(items) == 3

    tl = [i for i in items if "top_left" in i.field][0]
    assert tl.status == STATUS_CLOSE

    bm = [i for i in items if "bottom_mid" in i.field][0]
    assert bm.status == STATUS_MODERATE

    tr = [i for i in items if "top_right" in i.field][0]
    assert tr.status == STATUS_LARGE


# =============================================================================
# Shear Comparison Tests
# =============================================================================

def _shear_result():
    return ShearReinforcementDesignResult(
        status=STATUS_SHEAR_REINFORCEMENT_REQUIRED,
        s_required_limited_mm=150.0,
        s_max_mm=200.0,
        governing="shear",
    )


def test_shear_comparison():
    etabs = ETABSDesignOutput(
        beam_id="B101_S1", label="B101",
        shear_spacing_required_mm=155.0,
    )
    items = compare_shear_spacing_to_etabs(_shear_result(), etabs)

    assert len(items) == 1
    assert items[0].status == STATUS_CLOSE
    assert items[0].difference_percent == pytest.approx(5.0 / 150.0 * 100, rel=0.1)


# =============================================================================
# Combined Runner Tests
# =============================================================================

def test_combined_runner():
    etabs = ETABSDesignOutput(
        beam_id="B101_S1", label="B101",
        top_left_As_required_cm2=18.5,
        bottom_mid_As_required_cm2=16.0,
        top_right_As_required_cm2=30.0,
    )
    result = compare_engine_to_etabs_design_output(
        beam_id="B101_S1", label="B101",
        etabs_output=etabs,
        flexure_region_result=_flexure_result(),
    )
    assert result.status == STATUS_LARGE  # top_right farkı LARGE


def test_identity_mismatch():
    etabs = ETABSDesignOutput(beam_id="B999_S1", label="B999")
    result = compare_engine_to_etabs_design_output(
        beam_id="B101_S1", label="B101",
        etabs_output=etabs,
    )
    assert result.status == STATUS_INCOMPLETE
    assert result.items == ()
    assert "identity mismatch" in str(result.evidence.get("invalid_inputs", ""))


def test_no_inputs():
    etabs = ETABSDesignOutput(beam_id="B101_S1", label="B101")
    result = compare_engine_to_etabs_design_output(
        beam_id="B101_S1", label="B101",
        etabs_output=etabs,
    )
    assert result.status == STATUS_INCOMPLETE
    assert result.items == ()


# =============================================================================
# Immutability Tests
# =============================================================================

def test_does_not_mutate_flexure_result():
    flexure_before = _flexure_result()
    flexure_dict_before = asdict(flexure_before)

    etabs = ETABSDesignOutput(
        beam_id="B101_S1", label="B101",
        top_left_As_required_cm2=50.0,  # LARGE difference
    )
    compare_engine_to_etabs_design_output(
        beam_id="B101_S1", label="B101",
        etabs_output=etabs,
        flexure_region_result=flexure_before,
    )

    assert asdict(flexure_before) == flexure_dict_before


def test_does_not_mutate_shear_result():
    shear_before = _shear_result()
    shear_dict_before = asdict(shear_before)

    etabs = ETABSDesignOutput(
        beam_id="B101_S1", label="B101",
        shear_spacing_required_mm=500.0,  # LARGE difference
    )
    compare_engine_to_etabs_design_output(
        beam_id="B101_S1", label="B101",
        etabs_output=etabs,
        shear_result=shear_before,
    )

    assert asdict(shear_before) == shear_dict_before


# =============================================================================
# Crosscheck Does Not Affect Verification Test
# =============================================================================

def test_etabs_disagreement_does_not_mutate_verification():
    """ETABS LARGE disagreement does not change verification PASS."""
    from tbdy_engine.verification.beams.provided_reinforcement import (
        BeamProvidedReinforcement,
    )
    from tbdy_engine.verification.beams.reinforcement_verification import (
        verify_beam_reinforcement,
    )

    provided = BeamProvidedReinforcement(
        beam_id="B101_S1", label="B101",
        top_left_As_cm2=20.0, bottom_mid_As_cm2=16.0, top_right_As_cm2=22.0,
    )
    verification_before = verify_beam_reinforcement(
        beam_id="B101_S1", label="B101",
        provided=provided,
        flexure_region_result=_flexure_result(),
    )
    assert verification_before.status == "PASS"

    # Run crosscheck with LARGE differences
    etabs = ETABSDesignOutput(
        beam_id="B101_S1", label="B101",
        top_left_As_required_cm2=50.0,
        bottom_mid_As_required_cm2=50.0,
        top_right_As_required_cm2=50.0,
    )
    comparison = compare_engine_to_etabs_design_output(
        beam_id="B101_S1", label="B101",
        etabs_output=etabs,
        flexure_region_result=_flexure_result(),
    )
    assert comparison.status == STATUS_LARGE

    # Verification result unchanged
    verification_after = asdict(verification_before)
    assert verification_after["status"] == "PASS"
