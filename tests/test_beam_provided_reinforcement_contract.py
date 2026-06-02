"""
BeamProvidedReinforcement kontrat testleri.
"""

import pytest
from tbdy_engine.verification.beams.provided_reinforcement import (
    BeamProvidedReinforcement,
    ProvidedStirrup,
    validate_beam_provided_reinforcement,
)


# =============================================================================
# Helpers
# =============================================================================

def _valid_provided():
    return BeamProvidedReinforcement(
        beam_id="B101_S1",
        label="B101",
        source="etabs_rebar_schedule",
        top_left_As_cm2=6.0,
        bottom_mid_As_cm2=4.0,
        top_right_As_cm2=5.0,
        stirrup=ProvidedStirrup(
            diameter_mm=8.0,
            legs=2,
            spacing_mm=200.0,
        ),
    )


# =============================================================================
# Test 1: Valid provided reinforcement passes
# =============================================================================

def test_valid_provided_passes():
    reinf = _valid_provided()
    assert validate_beam_provided_reinforcement(reinf) == ()


# =============================================================================
# Test 2: Missing beam_id fails
# =============================================================================

def test_missing_beam_id_fails():
    reinf = BeamProvidedReinforcement(beam_id="", label="B101")
    errors = validate_beam_provided_reinforcement(reinf)
    assert "beam_id" in errors


# =============================================================================
# Test 3: Missing label fails
# =============================================================================

def test_missing_label_fails():
    reinf = BeamProvidedReinforcement(beam_id="B101_S1", label="")
    errors = validate_beam_provided_reinforcement(reinf)
    assert "label" in errors


# =============================================================================
# Test 4: Unknown source fails
# =============================================================================

def test_unknown_source_fails():
    reinf = BeamProvidedReinforcement(
        beam_id="B101_S1", label="B101", source="unknown",
    )
    errors = validate_beam_provided_reinforcement(reinf)
    assert "source" in errors


# =============================================================================
# Test 5: Provided reinforcement is separate from BeamModelContext
# =============================================================================

def test_separate_from_context():
    """BeamProvidedReinforcement, BeamModelContext'ten bağımsızdır."""
    from tbdy_engine.design.beams.context import BeamModelContext

    # BeamModelContext reinforcement alanları içermemeli
    ctx_fields = set(BeamModelContext.__dataclass_fields__.keys())
    assert "top_left_As_cm2" not in ctx_fields
    assert "bottom_mid_As_cm2" not in ctx_fields
    assert "top_right_As_cm2" not in ctx_fields
    assert "stirrup" not in ctx_fields

    # BeamProvidedReinforcement kendi alanlarına sahip
    reinf_fields = set(BeamProvidedReinforcement.__dataclass_fields__.keys())
    assert "top_left_As_cm2" in reinf_fields
    assert "bottom_mid_As_cm2" in reinf_fields
    assert "top_right_As_cm2" in reinf_fields
    assert "stirrup" in reinf_fields


# =============================================================================
# Test 6: Immutability
# =============================================================================

def test_provided_is_immutable():
    reinf = _valid_provided()
    with pytest.raises(Exception):
        reinf.top_As_cm2 = 999.0


# =============================================================================
# Test 7: Serialization round-trip
# =============================================================================

def test_serialization_roundtrip():
    import json
    from dataclasses import asdict

    reinf = _valid_provided()
    d = asdict(reinf)
    js = json.dumps(d)
    loaded = json.loads(js)

    assert loaded["beam_id"] == "B101_S1"
    assert loaded["top_left_As_cm2"] == 6.0
    assert loaded["stirrup"]["diameter_mm"] == 8.0
    assert loaded["stirrup"]["legs"] == 2
