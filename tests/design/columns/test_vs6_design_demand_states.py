import pytest

from tbdy_engine.design.columns.design_demand_states import (
    ColumnDesignDemandError,
    DESIGN_AUTHORITY_RESPONSE_SPECTRUM,
    DESIGN_AUTHORITY_STATIC,
    LinearComboConstituent,
    build_linear_combo_design_demands,
    verify_observed_combo_rows_are_generated_subset,
)
from tbdy_engine.design.columns.rebar_selection import ColumnDemandState


COMP = "+0.00:C2:236"


def _state(case, case_type, end, station, n, m2, m3, step=None):
    return ColumnDemandState(
        state_id=f"{case}:{end}:{step}",
        component_id=COMP,
        output_case=case,
        case_type=case_type,
        step_type=step,
        step_number=None,
        station_m=station,
        end_tag=end,
        nd_compression_n=n,
        m2_nmm=m2,
        m3_nmm=m3,
        source_identity=f"src:{case}:{end}:{step}",
    )


def test_static_linear_combo_produces_one_exact_state_per_end():
    rows = (
        _state("D", "LinStatic", "I_END", 0.0, 1000.0, 10.0, 20.0),
        _state("L", "LinStatic", "I_END", 0.0, 200.0, -5.0, 2.0),
        _state("D", "LinStatic", "J_END", 4.0, 900.0, -8.0, 15.0),
        _state("L", "LinStatic", "J_END", 4.0, 150.0, 4.0, -3.0),
    )
    result = build_linear_combo_design_demands(
        component_id=COMP,
        combo_name="ULT",
        combo_type="LINEAR_ADD",
        constituents=(LinearComboConstituent("D", 1.4), LinearComboConstituent("L", 1.6)),
        case_demands=rows,
    )
    assert result.status == "PROVEN_DESIGN_DEMAND_STATES"
    assert result.authority == DESIGN_AUTHORITY_STATIC
    assert len(result.states) == 2
    i = next(item for item in result.states if item.end_tag == "I_END")
    assert i.case_type == "DesignStaticLinearExact"
    assert i.nd_compression_n == pytest.approx(1720.0)
    assert i.m2_nmm == pytest.approx(6.0)
    assert i.m3_nmm == pytest.approx(31.2)


def test_response_spectrum_combo_expands_independent_p_m2_m3_signs():
    rows = (
        _state("G", "LinStatic", "I_END", 0.0, 1000.0, 10.0, 20.0),
        _state("RSX", "LinRespSpec", "I_END", 0.0, -70.0, 20.0, 30.0, "Max"),
        _state("RSY", "LinRespSpec", "I_END", 0.0, -100.0, 40.0, 50.0, "Max"),
        _state("G", "LinStatic", "J_END", 4.0, 900.0, -10.0, -20.0),
        _state("RSX", "LinRespSpec", "J_END", 4.0, -60.0, 15.0, 25.0, "Max"),
        _state("RSY", "LinRespSpec", "J_END", 4.0, -80.0, 35.0, 45.0, "Max"),
    )
    result = build_linear_combo_design_demands(
        component_id=COMP,
        combo_name="SEIS_X",
        combo_type="LINEAR_ADD",
        constituents=(
            LinearComboConstituent("G", 1.0),
            LinearComboConstituent("RSX", 1.0),
            LinearComboConstituent("RSY", 0.3),
        ),
        case_demands=rows,
    )
    assert result.authority == DESIGN_AUTHORITY_RESPONSE_SPECTRUM
    assert len(result.states) == 16
    i_states = [item for item in result.states if item.end_tag == "I_END"]
    assert len(i_states) == 8
    assert len({(item.nd_compression_n, item.m2_nmm, item.m3_nmm) for item in i_states}) == 8

    # I-end static base = (1000, 10, 20); factored spectrum magnitudes
    # = (100, 32, 45).  All eight independent sign permutations must exist.
    assert any(
        item.nd_compression_n == pytest.approx(900.0)
        and item.m2_nmm == pytest.approx(42.0)
        and item.m3_nmm == pytest.approx(65.0)
        for item in i_states
    )
    assert any(
        item.nd_compression_n == pytest.approx(1100.0)
        and item.m2_nmm == pytest.approx(-22.0)
        and item.m3_nmm == pytest.approx(-25.0)
        for item in i_states
    )


def test_etabs_display_max_min_rows_can_be_proven_as_subset_without_becoming_authority():
    rows = (
        _state("G", "LinStatic", "I_END", 0.0, 1000.0, 10.0, 20.0),
        _state("RS", "LinRespSpec", "I_END", 0.0, -100.0, 30.0, 40.0, "Max"),
        _state("G", "LinStatic", "J_END", 4.0, 900.0, -10.0, -20.0),
        _state("RS", "LinRespSpec", "J_END", 4.0, -80.0, 20.0, 25.0, "Max"),
    )
    generated = build_linear_combo_design_demands(
        component_id=COMP,
        combo_name="SEIS",
        combo_type="LINEAR_ADD",
        constituents=(LinearComboConstituent("G", 1.0), LinearComboConstituent("RS", 1.0)),
        case_demands=rows,
    )
    observed = (
        _state("SEIS", "Combination", "I_END", 0.0, 900.0, 40.0, 60.0, "Max"),
        _state("SEIS", "Combination", "I_END", 0.0, 1100.0, -20.0, -20.0, "Min"),
        _state("SEIS", "Combination", "J_END", 4.0, 820.0, 10.0, 5.0, "Max"),
        _state("SEIS", "Combination", "J_END", 4.0, 980.0, -30.0, -45.0, "Min"),
    )
    proof = verify_observed_combo_rows_are_generated_subset(
        generated=generated,
        observed_combo_demands=observed,
        force_tolerance_n=1e-9,
        moment_tolerance_nmm=1e-9,
    )
    assert proof.status == "PROVEN_OBSERVED_ROWS_SUBSET_OF_DESIGN_PERMUTATIONS"
    assert proof.observed_state_count == 4
    assert proof.matched_state_count == 4
    assert proof.unmatched_observed_state_ids == ()
    # The generated design set remains the wider eight-per-end permutation set.
    assert len(generated.states) == 16


def test_nested_combo_constituent_fails_closed():
    rows = (
        _state("D", "LinStatic", "I_END", 0.0, 1.0, 1.0, 1.0),
        _state("D", "LinStatic", "J_END", 4.0, 1.0, 1.0, 1.0),
    )
    with pytest.raises(ColumnDesignDemandError, match="flattened LOAD_CASE"):
        build_linear_combo_design_demands(
            component_id=COMP,
            combo_name="X",
            combo_type="LINEAR_ADD",
            constituents=(LinearComboConstituent("D", 1.0, cname_type="LOAD_COMBO"),),
            case_demands=rows,
        )
