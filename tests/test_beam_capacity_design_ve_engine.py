"""
Capacity Design Ve Engine tests.
"""

import json
from dataclasses import asdict

import pytest

from tbdy_engine.design.beams.calculators.capacity_design import (
    CapacityDesignVeInput,
    capacity_design_ve,
    STATUS_OK,
    STATUS_INVALID_INPUT,
    STATUS_UNSUPPORTED_DIRECTION,
)


# =============================================================================
# Test 1: Import safety
# =============================================================================

def test_import_safety():
    """capacity_design.py imports no external model adapters."""
    import inspect
    import tbdy_engine.design.beams.calculators.capacity_design as cd

    source = inspect.getsource(cd)
    forbidden = [
        "comtypes", "SapModel", "FrameForce", "ETABS",
    ]
    for term in forbidden:
        assert term not in source, f"Forbidden import '{term}' found"


# =============================================================================
# Test 2: Typical case
# =============================================================================

def test_typical_case():
    inp = CapacityDesignVeInput(
        Mpr_left_kNm=600.0,
        Mpr_right_kNm=500.0,
        Vg_kN=100.0,
        Ln_mm=5000.0,
    )
    result = capacity_design_ve(inp)

    assert result.status == STATUS_OK
    # plastic_shear = (600+500)/5 = 220 kN
    assert result.plastic_shear_component_kN == pytest.approx(220.0)
    # Ve = 220 + 100 = 320 kN
    assert result.Ve_capacity_kN == pytest.approx(320.0)
    assert result.direction == "absolute"


# =============================================================================
# Test 3: Zero gravity shear
# =============================================================================

def test_zero_gravity_shear():
    inp = CapacityDesignVeInput(
        Mpr_left_kNm=600.0,
        Mpr_right_kNm=400.0,
        Vg_kN=0.0,
        Ln_mm=5000.0,
    )
    result = capacity_design_ve(inp)

    # plastic_shear = 1000/5 = 200, Ve = 200
    assert result.Ve_capacity_kN == pytest.approx(200.0)


# =============================================================================
# Test 4: Zero moments
# =============================================================================

def test_zero_moments():
    inp = CapacityDesignVeInput(
        Mpr_left_kNm=0.0,
        Mpr_right_kNm=0.0,
        Vg_kN=100.0,
        Ln_mm=5000.0,
    )
    result = capacity_design_ve(inp)

    assert result.plastic_shear_component_kN == 0.0
    assert result.Ve_capacity_kN == pytest.approx(100.0)


# =============================================================================
# Test 5: Monotonic Mpr
# =============================================================================

def test_monotonic_Mpr():
    def ve_for_mpr(mpr):
        inp = CapacityDesignVeInput(
            Mpr_left_kNm=mpr, Mpr_right_kNm=mpr,
            Vg_kN=50.0, Ln_mm=5000.0,
        )
        return capacity_design_ve(inp).Ve_capacity_kN

    assert ve_for_mpr(200) < ve_for_mpr(400) < ve_for_mpr(600)


# =============================================================================
# Test 6: Monotonic Ln (inverse)
# =============================================================================

def test_monotonic_Ln_inverse():
    def ve_for_Ln(Ln):
        inp = CapacityDesignVeInput(
            Mpr_left_kNm=600.0, Mpr_right_kNm=400.0,
            Vg_kN=50.0, Ln_mm=Ln,
        )
        return capacity_design_ve(inp).Ve_capacity_kN

    # Longer span → lower plastic shear → lower Ve
    assert ve_for_Ln(8000) < ve_for_Ln(5000) < ve_for_Ln(3000)


# =============================================================================
# Test 7: Negative Vg absolute contribution
# =============================================================================

def test_negative_Vg_absolute():
    inp = CapacityDesignVeInput(
        Mpr_left_kNm=600.0,
        Mpr_right_kNm=400.0,
        Vg_kN=-100.0,
        Ln_mm=5000.0,
    )
    result = capacity_design_ve(inp)

    # plastic_shear = 1000/5 = 200, Ve = 200 + 100 = 300
    assert result.Ve_capacity_kN == pytest.approx(300.0)


# =============================================================================
# Test 8: Invalid inputs
# =============================================================================

@pytest.mark.parametrize("kwargs,expected_field", [
    ({"Mpr_left_kNm": -1.0}, "Mpr_left_kNm < 0"),
    ({"Mpr_right_kNm": -1.0}, "Mpr_right_kNm < 0"),
    ({"Ln_mm": 0.0}, "Ln_mm <= 0"),
    ({"Ln_mm": -100.0}, "Ln_mm <= 0"),
])
def test_invalid_inputs(kwargs, expected_field):
    defaults = {
        "Mpr_left_kNm": 600.0, "Mpr_right_kNm": 500.0,
        "Vg_kN": 100.0, "Ln_mm": 5000.0,
    }
    defaults.update(kwargs)
    inp = CapacityDesignVeInput(**defaults)
    result = capacity_design_ve(inp)

    assert result.status == STATUS_INVALID_INPUT
    evidence = dict(result.evidence)
    assert "invalid_inputs" in evidence
    assert expected_field in evidence["invalid_inputs"]


# =============================================================================
# Test 9: Unsupported direction
# =============================================================================

def test_unsupported_direction():
    inp = CapacityDesignVeInput(
        Mpr_left_kNm=600.0,
        Mpr_right_kNm=500.0,
        Vg_kN=100.0,
        Ln_mm=5000.0,
        direction="left",
    )
    result = capacity_design_ve(inp)

    assert result.status == STATUS_UNSUPPORTED_DIRECTION


# =============================================================================
# Test 10: Determinism
# =============================================================================

def test_determinism():
    inp = CapacityDesignVeInput(
        Mpr_left_kNm=600.0, Mpr_right_kNm=500.0,
        Vg_kN=100.0, Ln_mm=5000.0,
    )
    first = asdict(capacity_design_ve(inp))
    for _ in range(100):
        again = asdict(capacity_design_ve(inp))
        assert again == first


# =============================================================================
# Test 11: No leakage (Asw_required, Vr forbidden)
# =============================================================================

def test_no_leakage():
    """capacity_design.py contains no shear design or postprocessing terms."""
    import inspect
    import tbdy_engine.design.beams.calculators.capacity_design as cd

    source = inspect.getsource(cd)
    forbidden = [
        "Asw_required", "Vr", "s_required",
        "provided_area", "selected_area",
        "ReportingFacade", "CheckAdapter",
        "BeamEvaluationPackage", "streamlit",
    ]
    for term in forbidden:
        assert term not in source, f"Forbidden term '{term}' found"


# =============================================================================
# Test 12: Evidence contains Ln conversion and direction policy
# =============================================================================

def test_evidence_contains_policy():
    inp = CapacityDesignVeInput(
        Mpr_left_kNm=600.0, Mpr_right_kNm=500.0,
        Vg_kN=100.0, Ln_mm=5000.0,
    )
    result = capacity_design_ve(inp)
    evidence = dict(result.evidence)

    assert evidence.get("Ln_m") == 5.0
    assert "formula_plastic_shear" in evidence
    assert "formula_Ve" in evidence
    assert evidence.get("direction_policy") == "absolute scalar capacity demand"
    assert "policy_note" in evidence


# =============================================================================
# Test 13: Serialization round-trip
# =============================================================================

def test_serialization_roundtrip():
    inp = CapacityDesignVeInput(
        Mpr_left_kNm=600.0, Mpr_right_kNm=500.0,
        Vg_kN=100.0, Ln_mm=5000.0,
    )
    result = capacity_design_ve(inp)

    d = asdict(result)
    js = json.dumps(d)
    loaded = json.loads(js)

    assert loaded["status"] == STATUS_OK
    assert loaded["Ve_capacity_kN"] == pytest.approx(320.0)
    assert loaded["evidence"]["Ln_m"] == 5.0
