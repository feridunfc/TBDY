"""
Beam Region Flexure Mapping tests.
"""

import json
from dataclasses import asdict

import pytest

from tbdy_engine.design.beams.context import (
    BeamGeometryInput,
    BeamMaterialInput,
    BeamMetadata,
    BeamModelContext,
)
from tbdy_engine.design.beams.demand import (
    BeamDemandSet,
    BeamDemandEvidence,
    DemandCombinationMetadata,
)
from tbdy_engine.design.beams.beam_region_flexure import (
    design_beam_region_flexure,
    BeamFlexureRegionDesignResult,
    BeamRegionFlexureResult,
    STATUS_OK,
    STATUS_MIN_REINFORCEMENT_GOVERNS,
    STATUS_OVER_REINFORCED,
    STATUS_MISSING_DEMAND,
    STATUS_INVALID_INPUT,
    STATUS_PARTIAL,
)


# =============================================================================
# Helpers
# =============================================================================

def _valid_context(beam_id="B101_S1", label="B101"):
    return BeamModelContext(
        beam_id=beam_id,
        geometry=BeamGeometryInput(
            bw_mm=600.0,
            h_mm=700.0,
            d_mm=650.0,
            cover_mm=50.0,
            Ln_mm=5000.0,
        ),
        material=BeamMaterialInput(
            fck_mpa=30.0,
            fcd_mpa=20.0,
            fctd_mpa=1.27,
            fyk_mpa=420.0,
            fyd_mpa=365.0,
            fywd_mpa=365.0,
        ),
        metadata=BeamMetadata(
            label=label,
            story="S1",
            section_name="B60x70",
            source="test",
        ),
    )


def _valid_demand(beam_id="B101_S1", label="B101"):
    return BeamDemandSet(
        beam_id=beam_id,
        label=label,
        source="test_fixture",
        Md_left_neg_kNm=400.0,
        Md_mid_pos_kNm=300.0,
        Md_right_neg_kNm=500.0,
        Vd_left_kN=120.0,
        Vd_right_kN=150.0,
        N_kN=-200.0,
        governing={
            "Md_left_neg_kNm": BeamDemandEvidence(
                demand_name="Md_left_neg_kNm",
                combo="Cap_SeisX",
                station=0.0,
                raw_value=-400.0,
                rule="max_abs_negative_left_zone",
            ),
            "Md_mid_pos_kNm": BeamDemandEvidence(
                demand_name="Md_mid_pos_kNm",
                combo="Grav_Ult",
                station=2500.0,
                raw_value=300.0,
                rule="max_positive_mid_zone",
            ),
            "Md_right_neg_kNm": BeamDemandEvidence(
                demand_name="Md_right_neg_kNm",
                combo="Cap_SeisX",
                station=5000.0,
                raw_value=-500.0,
                rule="max_abs_negative_right_zone",
            ),
        },
        combination_metadata=DemandCombinationMetadata(
            selected_combos=("Grav_Ult", "Cap_SeisX"),
            envelope_mode="multi_combo",
        ),
    )


# =============================================================================
# Test 1: Import safety
# =============================================================================

def test_import_safety():
    """beam_region_flexure.py imports no external model adapters."""
    import inspect
    import tbdy_engine.design.beams.beam_region_flexure as brf

    source = inspect.getsource(brf)
    forbidden = [
        "comtypes", "SapModel", "FrameForce", "ETABS",
    ]
    for term in forbidden:
        assert term not in source, f"Forbidden import '{term}' found"


# =============================================================================
# Test 2: Basic three-region mapping
# =============================================================================

def test_basic_three_region_mapping():
    context = _valid_context()
    demand = _valid_demand()

    result = design_beam_region_flexure(context, demand)

    assert result.beam_id == "B101_S1"
    assert result.label == "B101"
    assert result.status == STATUS_OK

    assert "top_left" in result.regions
    assert "bottom_mid" in result.regions
    assert "top_right" in result.regions

    tl = result.regions["top_left"]
    assert tl.demand_name == "Md_left_neg_kNm"
    assert tl.Md_kNm == 400.0
    assert tl.As_design_required_cm2 > 0
    assert tl.status == STATUS_OK

    bm = result.regions["bottom_mid"]
    assert bm.demand_name == "Md_mid_pos_kNm"
    assert bm.Md_kNm == 300.0
    assert bm.As_design_required_cm2 > 0

    tr = result.regions["top_right"]
    assert tr.demand_name == "Md_right_neg_kNm"
    assert tr.Md_kNm == 500.0
    assert tr.As_design_required_cm2 > 0


# =============================================================================
# Test 3: Demand evidence preserved
# =============================================================================

def test_demand_evidence_preserved():
    context = _valid_context()
    demand = _valid_demand()

    result = design_beam_region_flexure(context, demand)

    tl = result.regions["top_left"]
    assert tl.demand_evidence["combo"] == "Cap_SeisX"
    assert tl.demand_evidence["station"] == 0.0
    assert tl.demand_evidence["raw_value"] == -400.0
    assert tl.demand_evidence["rule"] == "max_abs_negative_left_zone"

    bm = result.regions["bottom_mid"]
    assert bm.demand_evidence["combo"] == "Grav_Ult"

    tr = result.regions["top_right"]
    assert tr.demand_evidence["combo"] == "Cap_SeisX"


# =============================================================================
# Test 4: Missing mid demand
# =============================================================================

def test_missing_mid_demand():
    context = _valid_context()
    demand = BeamDemandSet(
        beam_id="B101_S1",
        label="B101",
        source="test",
        Md_left_neg_kNm=400.0,
        Md_mid_pos_kNm=None,  # missing
        Md_right_neg_kNm=500.0,
        Vd_left_kN=120.0,
        Vd_right_kN=150.0,
    )

    result = design_beam_region_flexure(context, demand)

    assert result.status == STATUS_PARTIAL

    assert result.regions["top_left"].status == STATUS_OK
    assert result.regions["bottom_mid"].status == STATUS_MISSING_DEMAND
    assert result.regions["bottom_mid"].Md_kNm is None
    assert result.regions["bottom_mid"].As_design_required_cm2 == 0.0
    assert result.regions["top_right"].status == STATUS_OK


# =============================================================================
# Test 5: Minimum reinforcement governs
# =============================================================================

def test_minimum_reinforcement_governs():
    context = _valid_context()
    demand = BeamDemandSet(
        beam_id="B101_S1",
        label="B101",
        source="test",
        Md_left_neg_kNm=10.0,  # very small
        Md_mid_pos_kNm=5.0,
        Md_right_neg_kNm=10.0,
        Vd_left_kN=50.0,
        Vd_right_kN=50.0,
    )

    result = design_beam_region_flexure(context, demand)

    for region_key in ("top_left", "bottom_mid", "top_right"):
        region = result.regions[region_key]
        assert region.status == STATUS_MIN_REINFORCEMENT_GOVERNS
        assert region.As_design_required_cm2 == region.As_min_cm2
        assert region.As_design_required_cm2 > region.As_required_cm2

    assert result.status == STATUS_MIN_REINFORCEMENT_GOVERNS


# =============================================================================
# Test 6: Over-reinforced propagates
# =============================================================================

def test_over_reinforced_propagates():
    context = _valid_context()
    demand = BeamDemandSet(
        beam_id="B101_S1",
        label="B101",
        source="test",
        Md_left_neg_kNm=2000.0,  # very large
        Md_mid_pos_kNm=300.0,
        Md_right_neg_kNm=500.0,
        Vd_left_kN=200.0,
        Vd_right_kN=200.0,
    )

    result = design_beam_region_flexure(context, demand)

    assert result.regions["top_left"].status == STATUS_OVER_REINFORCED
    assert result.status == STATUS_OVER_REINFORCED


# =============================================================================
# Test 7: Beam id / label mismatch
# =============================================================================

def test_beam_id_mismatch():
    context = _valid_context(beam_id="B101_S1", label="B101")
    demand = _valid_demand(beam_id="B102_S1", label="B102")

    result = design_beam_region_flexure(context, demand)

    assert result.status == STATUS_INVALID_INPUT
    assert result.regions == {}


def test_label_mismatch():
    context = _valid_context(beam_id="B101_S1", label="B101")
    demand = _valid_demand(beam_id="B101_S1", label="B999")

    result = design_beam_region_flexure(context, demand)

    assert result.status == STATUS_INVALID_INPUT
    assert "label mismatch" in str(result.evidence.get("invalid_inputs", ""))


# =============================================================================
# Test 8: Determinism
# =============================================================================

def test_determinism():
    context = _valid_context()
    demand = _valid_demand()

    first = asdict(design_beam_region_flexure(context, demand))
    for _ in range(100):
        again = asdict(design_beam_region_flexure(context, demand))
        assert again == first


# =============================================================================
# Test 9: No postprocessing leakage
# =============================================================================

def test_no_postprocessing_leakage():
    """beam_region_flexure.py contains no postprocessing dependencies."""
    import inspect
    import tbdy_engine.design.beams.beam_region_flexure as brf

    source = inspect.getsource(brf)
    forbidden = [
        "provided_area", "selected_area",
        "Mpr", "Ve_capacity",
        "ReportingFacade", "CheckAdapter",
        "BeamEvaluationPackage", "streamlit",
        "demand_processor",
    ]
    for term in forbidden:
        assert term not in source, f"Forbidden term '{term}' found"


# =============================================================================
# Test 10: Serialization round-trip
# =============================================================================

def test_serialization_roundtrip():
    context = _valid_context()
    demand = _valid_demand()

    result = design_beam_region_flexure(context, demand)

    d = asdict(result)
    js = json.dumps(d)
    loaded = json.loads(js)

    assert loaded["beam_id"] == "B101_S1"
    assert loaded["status"] == STATUS_OK
    assert "top_left" in loaded["regions"]
    assert loaded["regions"]["top_left"]["demand_evidence"]["combo"] == "Cap_SeisX"
