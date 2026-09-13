import pytest

from tbdy_engine.design.columns.end_moment_ratio import (
    EndMomentRatioError,
    build_exact_static_end_moment_ratio,
)
from tbdy_engine.design.columns.rebar_selection import ColumnDemandState


def _state(end, m2, m3, *, case="ULS", case_type="DesignStaticLinearExact", step_type=None):
    return ColumnDemandState(
        state_id=f"C1|{case}|{end}|STATIC_LINEAR_EXACT",
        component_id="S1:C1:1",
        output_case=case,
        case_type=case_type,
        step_type=step_type,
        step_number=None,
        station_m=0.0 if end == "I_END" else 3.0,
        end_tag=end,
        nd_compression_n=1_000_000.0,
        m2_nmm=m2,
        m3_nmm=m3,
        source_identity=f"source:{case}:{end}",
    )


def test_ratio_uses_exact_pair_not_independent_axis_envelope():
    result = build_exact_static_end_moment_ratio(
        i_end=_state("I_END", 100.0, 20.0),
        j_end=_state("J_END", 50.0, -10.0),
        axis="M2",
        analysis_result_ref="ANALYSIS_RESULT:B5",
        source_refs=("combo:ULS",),
    )
    assert result.m1_nmm == pytest.approx(50.0)
    assert result.m2_nmm == pytest.approx(100.0)
    assert result.moment_ratio_m1_over_m2 == pytest.approx(0.5)
    assert result.curvature == "SINGLE_CURVATURE"
    assert result.analysis_result_ref == "ANALYSIS_RESULT:B5"
    assert "I_END_STATE:C1|ULS|I_END|STATIC_LINEAR_EXACT" in result.source_refs
    assert "J_END_STATE:C1|ULS|J_END|STATIC_LINEAR_EXACT" in result.source_refs


def test_double_curvature_ratio_is_negative_and_magnitude_ordered():
    result = build_exact_static_end_moment_ratio(
        i_end=_state("I_END", -40.0, 20.0),
        j_end=_state("J_END", 100.0, -10.0),
        axis="M2",
        analysis_result_ref="ANALYSIS_RESULT:B5",
        source_refs=("combo:ULS",),
    )
    assert result.m1_nmm == pytest.approx(-40.0)
    assert result.m2_nmm == pytest.approx(100.0)
    assert result.moment_ratio_m1_over_m2 == pytest.approx(-0.4)
    assert result.curvature == "DOUBLE_CURVATURE"


def test_response_spectrum_permutation_is_rejected_for_actual_ratio():
    with pytest.raises(EndMomentRatioError, match="static-linear"):
        build_exact_static_end_moment_ratio(
            i_end=_state("I_END", 100.0, 20.0, case_type="DesignResponseSpectrumPermutation", step_type="P+1_M2+1_M3+1"),
            j_end=_state("J_END", 50.0, -10.0, case_type="DesignResponseSpectrumPermutation", step_type="P+1_M2+1_M3+1"),
            axis="M2",
            analysis_result_ref="ANALYSIS_RESULT:B5",
            source_refs=("combo:ULS",),
        )


def test_different_combo_identity_is_rejected():
    with pytest.raises(EndMomentRatioError, match="different output_case"):
        build_exact_static_end_moment_ratio(
            i_end=_state("I_END", 100.0, 20.0, case="ULS_A"),
            j_end=_state("J_END", 50.0, -10.0, case="ULS_B"),
            axis="M2",
            analysis_result_ref="ANALYSIS_RESULT:B5",
            source_refs=("combo:ULS",),
        )
