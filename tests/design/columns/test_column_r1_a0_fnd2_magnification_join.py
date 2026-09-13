import pytest

from tbdy_engine.design.columns.column_design_demand_engine import ColumnComboDefinition
from tbdy_engine.design.columns.column_design_readiness import (
    BLOCKED,
    READY,
    SECOND_ORDER_MOMENT_MAGNIFICATION_APPLIED,
    SECOND_ORDER_MOMENT_MAGNIFICATION_REQUIRED,
    resolve_column_design_demand_readiness,
)
from tbdy_engine.design.columns.combo_pattern_engine import ComboPatternConstituent
from tbdy_engine.design.columns.moment_magnification import (
    ColumnMomentMagnificationAxisBasis,
    STIFFNESS_METHOD_EQ_7_21,
)
from tbdy_engine.design.columns.rebar_selection import ColumnDemandState
from tbdy_engine.design.columns.slenderness import (
    ColumnSlendernessAxisBasis,
    ColumnSlendernessBasis,
    SWAY_PREVENTED,
)


COMP = "+0.00:C2:236"


def _state(end, station, nd, m2, m3):
    return ColumnDemandState(
        state_id=f"G:{end}",
        component_id=COMP,
        output_case="G",
        case_type="LinStatic",
        step_type=None,
        step_number=None,
        station_m=station,
        end_tag=end,
        nd_compression_n=nd,
        m2_nmm=m2,
        m3_nmm=m3,
        source_identity=f"B5:G:{end}",
    )


def _resolve(*, magnification=()):
    combo = (
        ColumnComboDefinition(
            name="ULS",
            combo_type="LINEAR_ADD",
            constituents=(ComboPatternConstituent("G", 1.0),),
        ),
    )
    demands = (
        _state("I_END", 0.0, 1_000_000.0, -100_000_000.0, 80_000_000.0),
        _state("J_END", 3.0, 900_000.0, 70_000_000.0, -60_000_000.0),
    )
    slenderness = ColumnSlendernessBasis(
        component_id=COMP,
        m2=ColumnSlendernessAxisBasis(
            axis="M2",
            section_dimension_mm=500.0,
            free_length_ln_mm=6000.0,
            effective_length_factor_k=1.0,
            sway_classification=SWAY_PREVENTED,
            moment_ratio_m1_over_m2=1.0,
            source_refs=("reviewed:M2",),
        ),
        m3=ColumnSlendernessAxisBasis(
            axis="M3",
            section_dimension_mm=800.0,
            free_length_ln_mm=3000.0,
            effective_length_factor_k=1.0,
            sway_classification=SWAY_PREVENTED,
            moment_ratio_m1_over_m2=0.0,
            source_refs=("reviewed:M3",),
        ),
        source_refs=("reviewed:slenderness",),
    )
    return resolve_column_design_demand_readiness(
        component_id=COMP,
        combo_definitions=combo,
        constituent_case_demands=demands,
        width_mm=500.0,
        depth_mm=800.0,
        slenderness_basis=slenderness,
        moment_magnification_bases=magnification,
    )


def test_fnd2_only_enters_magnification_after_slenderness_decision_and_only_on_required_axis():
    blocked = _resolve()
    assert blocked.status == BLOCKED
    assert blocked.second_order_treatment == SECOND_ORDER_MOMENT_MAGNIFICATION_REQUIRED
    assert blocked.slenderness.m2.status == "MOMENT_MAGNIFICATION_REQUIRED"
    assert blocked.slenderness.m3.status == "SLENDERNESS_EFFECTS_NEGLIGIBLE"

    bases = tuple(
        ColumnMomentMagnificationAxisBasis(
            demand_state_id=state.state_id,
            axis="M2",
            sway_classification=SWAY_PREVENTED,
            nd_compression_n=state.nd_compression_n,
            m1_over_m2=1.0,
            effective_length_lk_mm=blocked.slenderness.m2.effective_length_lk_mm,
            radius_i_mm=blocked.slenderness.m2.radius_of_gyration_i_mm,
            ec_mpa=30_000.0,
            ic_mm4=12.0e9,
            creep_ratio_rm=0.20,
            stiffness_method=STIFFNESS_METHOD_EQ_7_21,
            source_refs=(f"A0:{state.state_id}:M2",),
        )
        for state in blocked.minimum_eccentricity.states
    )

    ready = _resolve(magnification=bases)
    assert ready.status == READY
    assert ready.second_order_treatment == SECOND_ORDER_MOMENT_MAGNIFICATION_APPLIED
    assert len(ready.moment_magnification_results) == len(ready.demand_states)

    before = {state.state_id: state for state in blocked.minimum_eccentricity.states}
    after = {state.state_id: state for state in ready.demand_states}
    assert set(before) == set(after)
    for state_id in before:
        assert after[state_id].nd_compression_n == pytest.approx(before[state_id].nd_compression_n)
        assert abs(after[state_id].m2_nmm) >= abs(before[state_id].m2_nmm)
        assert after[state_id].m3_nmm == pytest.approx(before[state_id].m3_nmm)
        assert "TS500_MAGNIFIED" in after[state_id].source_identity
