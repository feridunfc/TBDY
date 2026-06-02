"""
Shear Reinforcement Design Engine tests.
"""

import json
from dataclasses import asdict

import pytest

from tbdy_engine.design.beams.calculators.shear_reinforcement_design import (
    ShearReinforcementDesignInput,
    shear_reinforcement_design,
    STATUS_INVALID_INPUT,
    STATUS_MIN_SHEAR_REINFORCEMENT_GOVERNS,
    STATUS_SHEAR_REINFORCEMENT_REQUIRED,
)


# =============================================================================
# Helpers
# =============================================================================

def _default_input(**kwargs):
    defaults = {
        "V_design_kN": 350.0,
        "bw_mm": 600.0,
        "d_mm": 650.0,
        "fctd_mpa": 1.27,
        "fywd_mpa": 365.0,
        "stirrup_diameter_mm": 10.0,
        "stirrup_legs": 2,
    }
    defaults.update(kwargs)
    return ShearReinforcementDesignInput(**defaults)


# =============================================================================
# Test 1: Import safety
# =============================================================================

def test_import_safety():
    """shear_reinforcement_design.py imports no external model adapters."""
    import inspect
    import tbdy_engine.design.beams.calculators.shear_reinforcement_design as srd

    source = inspect.getsource(srd)
    forbidden = [
        "comtypes", "SapModel", "FrameForce", "ETABS",
    ]
    for term in forbidden:
        assert term not in source, f"Forbidden import '{term}' found"


# =============================================================================
# Test 2: Typical shear required
# =============================================================================

def test_typical_shear_required():
    inp = _default_input(V_design_kN=350.0)
    result = shear_reinforcement_design(inp)

    assert result.status == STATUS_SHEAR_REINFORCEMENT_REQUIRED

    # Vc ≈ 0.65 * 1.27 * 600 * 650 / 1000 ≈ 321.9 kN
    assert 315.0 <= result.Vc_kN <= 330.0

    # Vs ≈ 350 - 322 ≈ 28 kN
    assert 25.0 <= result.Vs_required_kN <= 35.0

    # bar_area = π*10²/4 = 78.54 mm², Asw = 2*78.54 = 157.08 mm²
    assert result.bar_area_mm2 == pytest.approx(78.54, rel=0.01)
    assert result.Asw_per_stirrup_mm2 == pytest.approx(157.08, rel=0.01)

    # s ≈ 157.08*365*650*1.0/28050 ≈ 1327 mm → limited = 200 mm
    assert result.s_required_mm is not None
    assert result.s_required_mm > 1000.0
    assert result.s_required_limited_mm == 200.0
    assert result.governing == "s_max"


# =============================================================================
# Test 3: Minimum shear reinforcement governs
# =============================================================================

def test_minimum_governs():
    inp = _default_input(V_design_kN=200.0)  # < Vc
    result = shear_reinforcement_design(inp)

    assert result.status == STATUS_MIN_SHEAR_REINFORCEMENT_GOVERNS
    assert result.Vs_required_kN == 0.0
    assert result.s_required_mm is None
    assert result.s_required_limited_mm == 200.0
    assert result.governing == "s_max"


# =============================================================================
# Test 4: High shear requires tight spacing
# =============================================================================

def test_high_shear_tight_spacing():
    inp = _default_input(V_design_kN=900.0)
    result = shear_reinforcement_design(inp)

    assert result.status == STATUS_SHEAR_REINFORCEMENT_REQUIRED
    assert result.Vs_required_kN > 500.0
    assert result.s_required_mm is not None
    assert result.s_required_mm < 200.0
    assert result.s_required_limited_mm == result.s_required_mm
    assert result.governing == "shear"


# =============================================================================
# Test 5: Monotonic V — higher V → smaller s
# =============================================================================

def test_monotonic_V():
    def s_for_v(v):
        inp = _default_input(V_design_kN=v)
        return shear_reinforcement_design(inp).s_required_mm

    s350 = s_for_v(350)
    s500 = s_for_v(500)
    s700 = s_for_v(700)

    assert s350 is not None
    assert s500 is not None
    assert s700 is not None
    assert s350 > s500 > s700


# =============================================================================
# Test 6: Monotonic fywd — higher fywd → larger s
# =============================================================================

def test_monotonic_fywd():
    def s_for_fywd(fywd):
        inp = _default_input(fywd_mpa=fywd)
        return shear_reinforcement_design(inp).s_required_mm

    assert s_for_fywd(365) < s_for_fywd(420) < s_for_fywd(500)


# =============================================================================
# Test 7: Monotonic legs — more legs → larger s
# =============================================================================

def test_monotonic_legs():
    def s_for_legs(legs):
        inp = _default_input(stirrup_legs=legs)
        return shear_reinforcement_design(inp).s_required_mm

    assert s_for_legs(2) < s_for_legs(4) < s_for_legs(6)


# =============================================================================
# Test 8: Monotonic diameter — larger diameter → larger s
# =============================================================================

def test_monotonic_diameter():
    def s_for_dia(dia):
        inp = _default_input(stirrup_diameter_mm=dia)
        return shear_reinforcement_design(inp).s_required_mm

    assert s_for_dia(8) < s_for_dia(10) < s_for_dia(12)


# =============================================================================
# Test 9: Invalid inputs
# =============================================================================

@pytest.mark.parametrize("kwargs,expected_field", [
    ({"V_design_kN": -1.0}, "V_design_kN < 0"),
    ({"bw_mm": 0.0}, "bw_mm <= 0"),
    ({"d_mm": 0.0}, "d_mm <= 0"),
    ({"fctd_mpa": 0.0}, "fctd_mpa <= 0"),
    ({"fywd_mpa": 0.0}, "fywd_mpa <= 0"),
    ({"stirrup_diameter_mm": 0.0}, "stirrup_diameter_mm <= 0"),
    ({"stirrup_legs": 0}, "stirrup_legs <= 0"),
    ({"cot_theta": 0.0}, "cot_theta <= 0"),
    ({"vc_factor": -0.1}, "vc_factor < 0"),
    ({"s_max_mm": 0.0}, "s_max_mm <= 0"),
])
def test_invalid_inputs(kwargs, expected_field):
    inp = _default_input(**kwargs)
    result = shear_reinforcement_design(inp)

    assert result.status == STATUS_INVALID_INPUT
    evidence = dict(result.evidence)
    assert "invalid_inputs" in evidence
    assert expected_field in evidence["invalid_inputs"]


# =============================================================================
# Test 10: Determinism
# =============================================================================

def test_determinism():
    inp = _default_input()
    first = asdict(shear_reinforcement_design(inp))
    for _ in range(100):
        again = asdict(shear_reinforcement_design(inp))
        assert again == first


# =============================================================================
# Test 11: No leakage
# =============================================================================

def test_no_leakage():
    """shear_reinforcement_design.py contains no postprocessing terms."""
    import inspect
    import tbdy_engine.design.beams.calculators.shear_reinforcement_design as srd

    source = inspect.getsource(srd)
    forbidden = [
        "provided_area", "selected_area",
        "Mpr", "Ve_capacity",
        "ReportingFacade", "CheckAdapter",
        "BeamEvaluationPackage", "streamlit",
    ]
    for term in forbidden:
        assert term not in source, f"Forbidden term '{term}' found"


# =============================================================================
# Test 12: Evidence contains policy parameters
# =============================================================================

def test_evidence_contains_policy():
    inp = _default_input()
    result = shear_reinforcement_design(inp)
    evidence = dict(result.evidence)

    assert evidence.get("vc_factor") == 0.65
    assert evidence.get("cot_theta") == 1.0
    assert "formula_Vc" in evidence
    assert "formula_spacing" in evidence
    assert "policy_note" in evidence


# =============================================================================
# Test 13: Serialization round-trip
# =============================================================================

def test_serialization_roundtrip():
    inp = _default_input(V_design_kN=900.0)
    result = shear_reinforcement_design(inp)

    d = asdict(result)
    js = json.dumps(d)
    loaded = json.loads(js)

    assert loaded["status"] == STATUS_SHEAR_REINFORCEMENT_REQUIRED
    assert loaded["Vs_required_kN"] > 0
    assert loaded["governing"] == "shear"
    assert loaded["evidence"]["vc_factor"] == 0.65
