"""
Pure Md→As Flexure Kernel tests.
"""

import json
from dataclasses import asdict

import pytest

from tbdy_engine.design.beams.calculators.flexure_design import (
    FlexureMdToAsInput,
    flexure_md_to_as,
    STATUS_OK,
    STATUS_INVALID_INPUT,
    STATUS_NO_TENSION_REINFORCEMENT,
)


# =============================================================================
# Test 1: Import safety
# =============================================================================

def test_import_safety():
    """flexure_design.py imports no external model adapters."""
    import inspect
    import tbdy_engine.design.beams.calculators.flexure_design as fd

    source = inspect.getsource(fd)
    forbidden = [
        "comtypes", "SapModel", "FrameForce", "ETABS",
    ]
    for term in forbidden:
        assert term not in source, f"Forbidden import '{term}' found"


# =============================================================================
# Test 2: Zero moment
# =============================================================================

def test_zero_moment():
    inp = FlexureMdToAsInput(
        Md_kNm=0.0, bw_mm=600.0, d_mm=650.0,
        fcd_mpa=20.0, fyd_mpa=365.0,
    )
    result = flexure_md_to_as(inp)

    assert result.status == STATUS_NO_TENSION_REINFORCEMENT
    assert result.As_required_mm2 == 0.0
    assert result.As_required_cm2 == 0.0
    assert result.a_mm == 0.0
    assert result.c_mm == 0.0
    assert result.neutral_axis_ratio == 0.0
    assert result.Mu_check_kNm == 0.0


# =============================================================================
# Test 3: Typical reference case
# =============================================================================

def test_typical_reference_case():
    inp = FlexureMdToAsInput(
        Md_kNm=400.0, bw_mm=600.0, d_mm=650.0,
        fcd_mpa=20.0, fyd_mpa=365.0,
    )
    result = flexure_md_to_as(inp)

    assert result.status == STATUS_OK
    assert result.As_required_cm2 > 15.0
    assert result.As_required_cm2 < 22.0
    assert result.Mu_check_kNm >= 400.0
    assert result.a_mm > 0
    assert result.c_mm > 0
    assert result.neutral_axis_ratio > 0
    assert result.neutral_axis_ratio < 0.40
    assert result.lever_arm_z_mm < 650.0
    assert result.lever_arm_z_mm > 500.0
    assert result.rho_required > 0
    assert result.iterations > 0


# =============================================================================
# Test 4: Monotonic Md
# =============================================================================

def test_monotonic_md():
    def as_for_md(md):
        inp = FlexureMdToAsInput(
            Md_kNm=md, bw_mm=600.0, d_mm=650.0,
            fcd_mpa=20.0, fyd_mpa=365.0,
        )
        return flexure_md_to_as(inp).As_required_mm2

    a200 = as_for_md(200)
    a400 = as_for_md(400)
    a600 = as_for_md(600)

    assert a200 < a400 < a600


# =============================================================================
# Test 5: Monotonic d
# =============================================================================

def test_monotonic_d():
    def as_for_d(d):
        inp = FlexureMdToAsInput(
            Md_kNm=400.0, bw_mm=600.0, d_mm=d,
            fcd_mpa=20.0, fyd_mpa=365.0,
        )
        return flexure_md_to_as(inp).As_required_mm2

    a500 = as_for_d(500)
    a650 = as_for_d(650)
    a800 = as_for_d(800)

    assert a500 > a650 > a800


# =============================================================================
# Test 6: Monotonic fyd
# =============================================================================

def test_monotonic_fyd():
    def as_for_fyd(fyd):
        inp = FlexureMdToAsInput(
            Md_kNm=400.0, bw_mm=600.0, d_mm=650.0,
            fcd_mpa=20.0, fyd_mpa=fyd,
        )
        return flexure_md_to_as(inp).As_required_mm2

    a365 = as_for_fyd(365)
    a420 = as_for_fyd(420)
    a500 = as_for_fyd(500)

    assert a365 > a420 > a500


# =============================================================================
# Test 7: Mu_check >= Md (FIX: no pytest.approx with >=)
# =============================================================================

def test_mu_check_ge_md():
    for md in [50, 100, 200, 400, 800, 1200]:
        inp = FlexureMdToAsInput(
            Md_kNm=md, bw_mm=600.0, d_mm=650.0,
            fcd_mpa=20.0, fyd_mpa=365.0,
        )
        result = flexure_md_to_as(inp)
        assert result.Mu_check_kNm >= md, (
            f"Md={md}: Mu_check={result.Mu_check_kNm} < Md"
        )


# =============================================================================
# Test 8: Invalid inputs
# =============================================================================

@pytest.mark.parametrize("kwargs,expected_field", [
    ({"Md_kNm": -100.0}, "Md_kNm < 0"),
    ({"bw_mm": 0.0}, "bw_mm <= 0"),
    ({"bw_mm": -10.0}, "bw_mm <= 0"),
    ({"d_mm": 0.0}, "d_mm <= 0"),
    ({"fcd_mpa": 0.0}, "fcd_mpa <= 0"),
    ({"fyd_mpa": 0.0}, "fyd_mpa <= 0"),
    ({"alpha": 0.0}, "alpha <= 0"),
    ({"beta": 0.0}, "beta <= 0"),
])
def test_invalid_inputs(kwargs, expected_field):
    defaults = {
        "Md_kNm": 400.0, "bw_mm": 600.0, "d_mm": 650.0,
        "fcd_mpa": 20.0, "fyd_mpa": 365.0,
        "alpha": 0.85, "beta": 0.85,
    }
    defaults.update(kwargs)
    inp = FlexureMdToAsInput(**defaults)
    result = flexure_md_to_as(inp)

    assert result.status == STATUS_INVALID_INPUT
    evidence = dict(result.evidence)
    assert "invalid_inputs" in evidence
    assert expected_field in evidence["invalid_inputs"]


# =============================================================================
# Test 9: Determinism
# =============================================================================

def test_determinism():
    inp = FlexureMdToAsInput(
        Md_kNm=400.0, bw_mm=600.0, d_mm=650.0,
        fcd_mpa=20.0, fyd_mpa=365.0,
    )
    first = asdict(flexure_md_to_as(inp))
    for _ in range(100):
        again = asdict(flexure_md_to_as(inp))
        assert again == first


# =============================================================================
# Test 10: Evidence contains coefficients
# =============================================================================

def test_evidence_contains_coefficients():
    inp = FlexureMdToAsInput(
        Md_kNm=400.0, bw_mm=600.0, d_mm=650.0,
        fcd_mpa=20.0, fyd_mpa=365.0,
    )
    result = flexure_md_to_as(inp)
    evidence = dict(result.evidence)

    assert evidence.get("alpha") == 0.85
    assert evidence.get("beta") == 0.85
    assert evidence.get("method") == "binary_search_single_reinforced_rectangular"
    assert evidence.get("Mu_ge_Md") is True
    assert "formula_Mu" in evidence
    assert "formula_a" in evidence
    assert "formula_c" in evidence


# =============================================================================
# Test 11: No postprocessing leakage in production code
# =============================================================================

def test_no_postprocessing_leakage():
    """flexure_design.py contains no postprocessing dependencies."""
    import inspect
    import tbdy_engine.design.beams.calculators.flexure_design as fd

    source = inspect.getsource(fd)
    forbidden = [
        "provided_area", "selected_area",
        "Mpr", "Ve_capacity",
        "ReportingFacade", "CheckAdapter",
        "BeamEvaluationPackage", "streamlit",
    ]
    for term in forbidden:
        assert term not in source, f"Forbidden term '{term}' found"


# =============================================================================
# Test 12: Serialization round-trip
# =============================================================================

def test_serialization_roundtrip():
    inp = FlexureMdToAsInput(
        Md_kNm=400.0, bw_mm=600.0, d_mm=650.0,
        fcd_mpa=20.0, fyd_mpa=365.0,
    )
    result = flexure_md_to_as(inp)

    d = asdict(result)
    js = json.dumps(d)
    loaded = json.loads(js)

    assert loaded["status"] == STATUS_OK
    assert loaded["As_required_mm2"] > 0
    assert loaded["Mu_check_kNm"] >= 400.0
    assert loaded["evidence"]["alpha"] == 0.85
