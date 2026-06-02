"""
Plastic Moment Engine tests.
"""

import json
from dataclasses import asdict

import pytest

from tbdy_engine.design.beams.calculators.plastic_moment import (
    PlasticMomentInput,
    plastic_moment,
    STATUS_OK,
    STATUS_INVALID_INPUT,
    STATUS_NO_REINFORCEMENT,
    STATUS_COMPRESSION_BLOCK_EXCEEDS_SECTION,
)


# =============================================================================
# Test 1: Import safety
# =============================================================================

def test_import_safety():
    """plastic_moment.py imports no external model adapters."""
    import inspect
    import tbdy_engine.design.beams.calculators.plastic_moment as pm

    source = inspect.getsource(pm)
    forbidden = [
        "comtypes", "SapModel", "FrameForce", "ETABS",
    ]
    for term in forbidden:
        assert term not in source, f"Forbidden import '{term}' found"


# =============================================================================
# Test 2: Typical case
# =============================================================================

def test_typical_case():
    inp = PlasticMomentInput(
        As_cm2=20.0,
        bw_mm=600.0,
        d_mm=650.0,
        fcd_mpa=20.0,
        fyk_mpa=420.0,
        steel_overstrength=1.25,
    )
    result = plastic_moment(inp)

    assert result.status == STATUS_OK
    assert result.fs_capacity_mpa == 525.0

    # Yaklaşık el hesabı: Mpr ≈ 628 kNm
    assert 620.0 <= result.Mpr_kNm <= 640.0
    assert 100.0 <= result.a_mm <= 106.0
    assert 595.0 <= result.lever_arm_z_mm <= 602.0
    assert result.c_mm > 0
    assert result.rho > 0
    assert result.neutral_axis_ratio > 0
    assert result.As_mm2 == 2000.0


# =============================================================================
# Test 3: Zero reinforcement
# =============================================================================

def test_zero_reinforcement():
    inp = PlasticMomentInput(
        As_cm2=0.0,
        bw_mm=600.0,
        d_mm=650.0,
        fcd_mpa=20.0,
        fyk_mpa=420.0,
    )
    result = plastic_moment(inp)

    assert result.status == STATUS_NO_REINFORCEMENT
    assert result.Mpr_kNm == 0.0
    assert result.As_mm2 == 0.0


# =============================================================================
# Test 4: Monotonic As
# =============================================================================

def test_monotonic_As():
    def mpr_for_as(As):
        inp = PlasticMomentInput(
            As_cm2=As, bw_mm=600.0, d_mm=650.0,
            fcd_mpa=20.0, fyk_mpa=420.0,
        )
        return plastic_moment(inp).Mpr_kNm

    assert mpr_for_as(10) < mpr_for_as(20) < mpr_for_as(30)


# =============================================================================
# Test 5: Monotonic d
# =============================================================================

def test_monotonic_d():
    def mpr_for_d(d):
        inp = PlasticMomentInput(
            As_cm2=20.0, bw_mm=600.0, d_mm=d,
            fcd_mpa=20.0, fyk_mpa=420.0,
        )
        return plastic_moment(inp).Mpr_kNm

    assert mpr_for_d(500) < mpr_for_d(650) < mpr_for_d(800)


# =============================================================================
# Test 6: Monotonic fyk
# =============================================================================

def test_monotonic_fyk():
    def mpr_for_fyk(fyk):
        inp = PlasticMomentInput(
            As_cm2=20.0, bw_mm=600.0, d_mm=650.0,
            fcd_mpa=20.0, fyk_mpa=fyk,
        )
        return plastic_moment(inp).Mpr_kNm

    assert mpr_for_fyk(365) < mpr_for_fyk(420) < mpr_for_fyk(500)


# =============================================================================
# Test 7: Overstrength effect
# =============================================================================

def test_overstrength_effect():
    def mpr_for_os(os_val):
        inp = PlasticMomentInput(
            As_cm2=20.0, bw_mm=600.0, d_mm=650.0,
            fcd_mpa=20.0, fyk_mpa=420.0,
            steel_overstrength=os_val,
        )
        return plastic_moment(inp).Mpr_kNm

    assert mpr_for_os(1.0) < mpr_for_os(1.25) < mpr_for_os(1.5)


# =============================================================================
# Test 8: Compression block exceeds section
# =============================================================================

def test_compression_block_exceeds_section():
    inp = PlasticMomentInput(
        As_cm2=300.0,  # çok büyük
        bw_mm=600.0,
        d_mm=650.0,
        fcd_mpa=20.0,
        fyk_mpa=420.0,
    )
    result = plastic_moment(inp)

    assert result.status == STATUS_COMPRESSION_BLOCK_EXCEEDS_SECTION


# =============================================================================
# Test 9: Invalid inputs
# =============================================================================

@pytest.mark.parametrize("kwargs,expected_field", [
    ({"As_cm2": -1.0}, "As_cm2 < 0"),
    ({"bw_mm": 0.0}, "bw_mm <= 0"),
    ({"d_mm": 0.0}, "d_mm <= 0"),
    ({"fcd_mpa": 0.0}, "fcd_mpa <= 0"),
    ({"fyk_mpa": 0.0}, "fyk_mpa <= 0"),
    ({"alpha": 0.0}, "alpha <= 0"),
    ({"beta": 0.0}, "beta <= 0"),
    ({"steel_overstrength": 0.0}, "steel_overstrength <= 0"),
])
def test_invalid_inputs(kwargs, expected_field):
    defaults = {
        "As_cm2": 20.0, "bw_mm": 600.0, "d_mm": 650.0,
        "fcd_mpa": 20.0, "fyk_mpa": 420.0,
    }
    defaults.update(kwargs)
    inp = PlasticMomentInput(**defaults)
    result = plastic_moment(inp)

    assert result.status == STATUS_INVALID_INPUT
    evidence = dict(result.evidence)
    assert "invalid_inputs" in evidence
    assert expected_field in evidence["invalid_inputs"]


# =============================================================================
# Test 10: Determinism
# =============================================================================

def test_determinism():
    inp = PlasticMomentInput(
        As_cm2=20.0, bw_mm=600.0, d_mm=650.0,
        fcd_mpa=20.0, fyk_mpa=420.0,
    )
    first = asdict(plastic_moment(inp))
    for _ in range(100):
        again = asdict(plastic_moment(inp))
        assert again == first


# =============================================================================
# Test 11: No leakage (Ve_capacity, provided_area forbidden)
# =============================================================================

def test_no_leakage():
    """plastic_moment.py contains no postprocessing or Ve_capacity terms."""
    import inspect
    import tbdy_engine.design.beams.calculators.plastic_moment as pm

    source = inspect.getsource(pm)
    forbidden = [
        "provided_area", "selected_area",
        "Ve_capacity",
        "ReportingFacade", "CheckAdapter",
        "BeamEvaluationPackage", "streamlit",
    ]
    for term in forbidden:
        assert term not in source, f"Forbidden term '{term}' found"


# =============================================================================
# Test 12: Evidence contains steel_overstrength and formulas
# =============================================================================

def test_evidence_contains_policy():
    inp = PlasticMomentInput(
        As_cm2=20.0, bw_mm=600.0, d_mm=650.0,
        fcd_mpa=20.0, fyk_mpa=420.0,
    )
    result = plastic_moment(inp)
    evidence = dict(result.evidence)

    assert evidence.get("steel_overstrength") == 1.25
    assert evidence.get("alpha") == 0.85
    assert evidence.get("beta") == 0.85
    assert "formula_fs_capacity" in evidence
    assert "formula_a" in evidence
    assert "formula_z" in evidence
    assert "formula_Mpr" in evidence
    assert "policy_note" in evidence


# =============================================================================
# Test 13: Serialization round-trip
# =============================================================================

def test_serialization_roundtrip():
    inp = PlasticMomentInput(
        As_cm2=20.0, bw_mm=600.0, d_mm=650.0,
        fcd_mpa=20.0, fyk_mpa=420.0,
    )
    result = plastic_moment(inp)

    d = asdict(result)
    js = json.dumps(d)
    loaded = json.loads(js)

    assert loaded["status"] == STATUS_OK
    assert loaded["Mpr_kNm"] > 600.0
    assert loaded["evidence"]["steel_overstrength"] == 1.25
