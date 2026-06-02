"""
BeamDemandProcessor testleri.
"""

import json
from dataclasses import asdict

import pytest

from tbdy_engine.design.beams.demand import (
    RawFrameForceRow,
)
from tbdy_engine.design.beams.demand_processor import (
    process_frameforce_rows_to_demand_set,
    BeamDemandProcessorError,
)


# =============================================================================
# Helpers
# =============================================================================

def _make_single_combo_rows():
    return [
        RawFrameForceRow("1", "B35", "Grav_Ult", 0.0,    0.0,  50.0, -100.0, 0.0),
        RawFrameForceRow("1", "B35", "Grav_Ult", 2500.0, 0.0,  20.0,   80.0, 0.0),
        RawFrameForceRow("1", "B35", "Grav_Ult", 5000.0, 0.0, -60.0, -120.0, 0.0),
    ]


def _make_multi_combo_rows():
    return [
        RawFrameForceRow("1", "B35", "Grav_Ult",  0.0,    0.0,  40.0, -100.0, 0.0),
        RawFrameForceRow("1", "B35", "Grav_Ult",  2500.0, 0.0,  15.0,   90.0, 0.0),
        RawFrameForceRow("1", "B35", "Grav_Ult",  5000.0, 0.0, -50.0, -110.0, 0.0),
        RawFrameForceRow("1", "B35", "Cap_SeisX", 0.0,    0.0,  60.0, -180.0, 0.0),
        RawFrameForceRow("1", "B35", "Cap_SeisX", 2500.0, 0.0,  25.0,   70.0, 0.0),
        RawFrameForceRow("1", "B35", "Cap_SeisX", 5000.0, 0.0, -70.0, -140.0, 0.0),
    ]


# =============================================================================
# Test 1: Single Combo Golden
# =============================================================================

def test_single_combo_golden():
    rows = _make_single_combo_rows()
    result = process_frameforce_rows_to_demand_set(
        rows, beam_id="1", label="B35", length_mm=5000,
    )

    assert result.Md_left_neg_kNm == pytest.approx(100.0)
    assert result.Md_mid_pos_kNm == pytest.approx(80.0)
    assert result.Md_right_neg_kNm == pytest.approx(120.0)
    assert result.Vd_left_kN == pytest.approx(50.0)
    assert result.Vd_right_kN == pytest.approx(60.0)
    assert result.N_kN == pytest.approx(0.0)
    assert result.torsion_Td_kNm is None
    assert result.combination_metadata.envelope_mode == "single_combo"

    assert result.governing["Md_left_neg_kNm"].combo == "Grav_Ult"
    assert result.governing["Md_left_neg_kNm"].raw_value == pytest.approx(-100.0)


# =============================================================================
# Test 2: Multi Combo Governing Evidence
# =============================================================================

def test_multi_combo_governing_evidence():
    rows = _make_multi_combo_rows()
    result = process_frameforce_rows_to_demand_set(
        rows, beam_id="1", label="B35", length_mm=5000,
    )

    assert result.Md_left_neg_kNm == pytest.approx(180.0)
    assert result.governing["Md_left_neg_kNm"].combo == "Cap_SeisX"
    assert result.governing["Md_left_neg_kNm"].raw_value == pytest.approx(-180.0)

    assert result.Md_mid_pos_kNm == pytest.approx(90.0)
    assert result.governing["Md_mid_pos_kNm"].combo == "Grav_Ult"
    assert result.governing["Md_mid_pos_kNm"].raw_value == pytest.approx(90.0)

    assert result.Md_right_neg_kNm == pytest.approx(140.0)
    assert result.governing["Md_right_neg_kNm"].combo == "Cap_SeisX"
    assert result.governing["Md_right_neg_kNm"].raw_value == pytest.approx(-140.0)

    assert result.Vd_left_kN == pytest.approx(60.0)
    assert result.governing["Vd_left_kN"].combo == "Cap_SeisX"

    assert result.Vd_right_kN == pytest.approx(70.0)
    assert result.governing["Vd_right_kN"].combo == "Cap_SeisX"

    assert result.combination_metadata.envelope_mode == "multi_combo"
    assert len(result.combination_metadata.selected_combos) == 2


# =============================================================================
# Test 3: Axial From Different Combo
# =============================================================================

def test_axial_from_different_combo():
    rows = [
        RawFrameForceRow("1", "B35", "Grav_Ult",  0.0, -50.0, 0.0, 0.0, 0.0),
        RawFrameForceRow("1", "B35", "Grav_Ult",  2500.0, -30.0, 0.0, 0.0, 0.0),
        RawFrameForceRow("1", "B35", "Grav_Ult",  5000.0, -50.0, 0.0, 0.0, 0.0),
        RawFrameForceRow("1", "B35", "Cap_SeisX", 0.0, -200.0, 0.0, 0.0, 0.0),
        RawFrameForceRow("1", "B35", "Cap_SeisX", 2500.0, -100.0, 0.0, 0.0, 0.0),
        RawFrameForceRow("1", "B35", "Cap_SeisX", 5000.0, -200.0, 0.0, 0.0, 0.0),
    ]
    result = process_frameforce_rows_to_demand_set(
        rows, beam_id="1", label="B35", length_mm=5000,
    )

    assert result.N_kN == pytest.approx(-200.0)
    assert result.governing["N_kN"].combo == "Cap_SeisX"
    assert result.governing["N_kN"].raw_value == pytest.approx(-200.0)


# =============================================================================
# Test 4: Torsion Preserved
# =============================================================================

def test_torsion_preserved():
    rows = [
        RawFrameForceRow("1", "B35", "Grav_Ult", 0.0,    0.0, 0.0, 0.0, 5.0),
        RawFrameForceRow("1", "B35", "Grav_Ult", 2500.0, 0.0, 0.0, 0.0, 3.0),
        RawFrameForceRow("1", "B35", "Grav_Ult", 5000.0, 0.0, 0.0, 0.0, 8.0),
    ]
    result = process_frameforce_rows_to_demand_set(
        rows, beam_id="1", label="B35", length_mm=5000,
    )

    assert result.torsion_Td_kNm == pytest.approx(8.0)
    assert result.governing["torsion_Td_kNm"].combo == "Grav_Ult"
    assert result.governing["torsion_Td_kNm"].raw_value == pytest.approx(8.0)


# =============================================================================
# Test 5: Missing Mid Positive
# =============================================================================

def test_missing_mid_positive():
    rows = [
        RawFrameForceRow("1", "B35", "Grav_Ult", 0.0,    0.0, 0.0, -100.0, 0.0),
        RawFrameForceRow("1", "B35", "Grav_Ult", 2500.0, 0.0, 0.0,  -50.0, 0.0),
        RawFrameForceRow("1", "B35", "Grav_Ult", 5000.0, 0.0, 0.0, -120.0, 0.0),
    ]
    result = process_frameforce_rows_to_demand_set(
        rows, beam_id="1", label="B35", length_mm=5000,
    )

    assert result.Md_mid_pos_kNm is None
    assert result.governing["Md_mid_pos_kNm"].rule == "no_positive_moment_in_mid_zone"
    assert result.Md_left_neg_kNm == pytest.approx(100.0)
    assert result.Md_right_neg_kNm == pytest.approx(120.0)


# =============================================================================
# Test 6: Empty Rows
# =============================================================================

def test_empty_rows_fails():
    with pytest.raises(BeamDemandProcessorError) as exc:
        process_frameforce_rows_to_demand_set([], beam_id="1", label="B35")
    assert exc.value.stage == "demand_input_empty"


# =============================================================================
# Test 7: Selected Combo Not Present
# =============================================================================

def test_selected_combo_not_present():
    rows = _make_single_combo_rows()
    with pytest.raises(BeamDemandProcessorError) as exc:
        process_frameforce_rows_to_demand_set(
            rows, beam_id="1", label="B35",
            selected_combos=["MissingCombo"], length_mm=5000,
        )
    assert exc.value.stage == "demand_no_selected_combos"


# =============================================================================
# Test 8: Station Out of Range
# =============================================================================

def test_station_out_of_range():
    rows = [
        RawFrameForceRow("1", "B35", "Grav_Ult", -100.0, 0.0, 0.0, 0.0, 0.0),
    ]
    with pytest.raises(BeamDemandProcessorError) as exc:
        process_frameforce_rows_to_demand_set(
            rows, beam_id="1", label="B35", length_mm=5000,
        )
    assert exc.value.stage == "demand_station_range"


# =============================================================================
# Test 9: Station Origin Normalization (FIX)
# =============================================================================

def test_station_origin_normalization():
    """ETABS station 0'dan başlamasa bile doğru zone'lama yapılır."""
    rows = [
        RawFrameForceRow("1", "B35", "Grav_Ult", 1000.0, 0.0,  50.0, -100.0, 0.0),
        RawFrameForceRow("1", "B35", "Grav_Ult", 3500.0, 0.0,  20.0,   80.0, 0.0),
        RawFrameForceRow("1", "B35", "Grav_Ult", 6000.0, 0.0, -60.0, -120.0, 0.0),
    ]
    result = process_frameforce_rows_to_demand_set(
        rows, beam_id="1", label="B35", length_mm=None,
    )

    # length inferred = 6000 - 1000 = 5000
    # relative stations: 0, 2500, 5000 → left/mid/right doğru
    assert result.Md_left_neg_kNm == pytest.approx(100.0)
    assert result.Md_mid_pos_kNm == pytest.approx(80.0)
    assert result.Md_right_neg_kNm == pytest.approx(120.0)
    assert result.Vd_left_kN == pytest.approx(50.0)
    assert result.Vd_right_kN == pytest.approx(60.0)


# =============================================================================
# Test 10: Selected Combos Order Preserved
# =============================================================================

def test_selected_combos_order_preserved():
    rows = _make_multi_combo_rows()
    result = process_frameforce_rows_to_demand_set(
        rows, beam_id="1", label="B35", length_mm=5000,
        selected_combos=["Cap_SeisX", "Grav_Ult"],
    )

    assert result.combination_metadata.selected_combos == ("Cap_SeisX", "Grav_Ult")


# =============================================================================
# Test 11: Determinism
# =============================================================================

def test_determinism():
    rows = _make_multi_combo_rows()
    first = asdict(process_frameforce_rows_to_demand_set(
        rows, beam_id="1", label="B35", length_mm=5000,
    ))
    for _ in range(100):
        again = asdict(process_frameforce_rows_to_demand_set(
            rows, beam_id="1", label="B35", length_mm=5000,
        ))
        assert again == first


# =============================================================================
# Test 12: Boundary Scan — Forbidden Imports
# =============================================================================

def test_demand_processor_no_forbidden_imports():
    """demand_processor.py forbidden modülleri import etmez."""
    import inspect
    import tbdy_engine.design.beams.demand_processor as dp

    source = inspect.getsource(dp)
    forbidden = [
        "comtypes", "SapModel", "read_etabs_table_on_demand",
        "ReportingFacade", "CheckAdapter", "BeamEvaluationPackage",
        "streamlit",
    ]
    for term in forbidden:
        assert term not in source, f"Forbidden term '{term}' found in demand_processor.py"


# =============================================================================
# Test 13: No Calculation Leak
# =============================================================================

def test_demand_processor_no_calculation():
    """DemandProcessor design calculation yapmaz."""
    rows = _make_multi_combo_rows()
    result = process_frameforce_rows_to_demand_set(
        rows, beam_id="1", label="B35", length_mm=5000,
    )
    result_dict = asdict(result)
    result_str = json.dumps(result_dict)

    forbidden = ["As_required", "Mpr", "Ve_capacity", "provided_area"]
    for term in forbidden:
        assert term not in result_str, f"Term '{term}' leaked into BeamDemandSet"
