"""
BeamDemandSet kontrat testleri.
"""

import pytest
from tbdy_engine.design.beams.demand import (
    BeamDemandSet,
    BeamDemandEvidence,
    DemandCombinationMetadata,
    validate_beam_demand_set,
)


# =============================================================================
# Helpers
# =============================================================================

def _valid_evidence():
    return BeamDemandEvidence(
        demand_name="Md_left_neg_kNm",
        combo="Grav_Ult",
        station=0.0,
        raw_value=-250.0,
        rule="max_abs_negative_left_zone",
    )


def _valid_demand_set():
    return BeamDemandSet(
        beam_id="B101_S1",
        label="B101",
        source="etabs_frameforce",
        Md_left_neg_kNm=250.0,
        Md_mid_pos_kNm=80.0,
        Md_right_neg_kNm=300.0,
        Vd_left_kN=120.0,
        Vd_right_kN=150.0,
        N_kN=-200.0,
        torsion_Td_kNm=5.0,
        governing={
            "Md_left_neg_kNm": _valid_evidence(),
        },
        combination_metadata=DemandCombinationMetadata(
            selected_combos=("Grav_Ult", "Cap_SeisX"),
            envelope_mode="multi_combo",
        ),
    )


# =============================================================================
# Test 1: Valid demand set passes
# =============================================================================

def test_valid_demand_set_passes():
    demand = _valid_demand_set()
    assert validate_beam_demand_set(demand) == ()


# =============================================================================
# Test 2: Missing beam_id fails
# =============================================================================

def test_missing_beam_id_fails():
    demand = BeamDemandSet(beam_id="", label="B101")
    errors = validate_beam_demand_set(demand)
    assert "beam_id" in errors


# =============================================================================
# Test 3: Missing label fails
# =============================================================================

def test_missing_label_fails():
    demand = BeamDemandSet(beam_id="B101_S1", label="")
    errors = validate_beam_demand_set(demand)
    assert "label" in errors


# =============================================================================
# Test 4: Unknown source fails
# =============================================================================

def test_unknown_source_fails():
    demand = BeamDemandSet(beam_id="B101_S1", label="B101", source="unknown")
    errors = validate_beam_demand_set(demand)
    assert "source" in errors


# =============================================================================
# Test 5: Governing evidence stores combo/station/rule
# =============================================================================

def test_governing_evidence_fields():
    ev = _valid_evidence()
    assert ev.combo == "Grav_Ult"
    assert ev.station == 0.0
    assert ev.raw_value == -250.0
    assert ev.rule == "max_abs_negative_left_zone"


# =============================================================================
# Test 6: BeamDemandSet has no design calculation fields
# =============================================================================

def test_no_design_calculation_fields():
    """BeamDemandSet tasarım hesabı alanları içermez."""
    demand = _valid_demand_set()
    demand_dict = demand.__dict__

    forbidden = ["As_required", "Mpr", "Ve_capacity"]
    for field in forbidden:
        assert field not in demand_dict, (
            f"BeamDemandSet should not have '{field}' field"
        )


# =============================================================================
# Test 7: Immutability
# =============================================================================

def test_demand_set_is_immutable():
    demand = _valid_demand_set()
    with pytest.raises(Exception):
        demand.Md_left_neg_kNm = 999.0


# =============================================================================
# Test 8: Serialization round-trip
# =============================================================================

def test_serialization_roundtrip():
    import json
    from dataclasses import asdict

    demand = _valid_demand_set()
    d = asdict(demand)
    js = json.dumps(d)
    loaded = json.loads(js)

    assert loaded["beam_id"] == "B101_S1"
    assert loaded["Md_left_neg_kNm"] == 250.0
    assert loaded["N_kN"] == -200.0
    assert loaded["combination_metadata"]["envelope_mode"] == "multi_combo"


# =============================================================================
# Test 9: Torsion is optional
# =============================================================================

def test_torsion_optional():
    demand = BeamDemandSet(
        beam_id="B101_S1",
        label="B101",
        source="etabs_frameforce",
    )
    assert demand.torsion_Td_kNm is None


# =============================================================================
# Test 10: Boundary scan — no forbidden terms
# =============================================================================

def test_demand_no_forbidden_terms():
    """demand.py forbidden terimler içermez (RawFrameForceRow hariç)."""
    import inspect
    import tbdy_engine.design.beams.demand as demand_module

    source = inspect.getsource(demand_module)
    forbidden = [
        "comtypes", "SapModel",
        "As_required", "Mpr", "Ve_capacity",
        "provided_area", "selected_area",
        "ReportingFacade", "CheckAdapter", "streamlit",
    ]
    for term in forbidden:
        assert term not in source, (
            f"Forbidden term '{term}' found in demand.py"
        )
