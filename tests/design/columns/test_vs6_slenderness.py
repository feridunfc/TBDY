import pytest

from tbdy_engine.design.columns.slenderness import (
    ColumnSlendernessAxisBasis,
    ColumnSlendernessBasis,
    ColumnSlendernessError,
    SWAY_PERMITTED,
    SWAY_PREVENTED,
    evaluate_ts500_column_slenderness,
)


COMP = "+0.00:C2:236"


def _axis(axis, *, h=800.0, ln=3000.0, k=1.0, sway=SWAY_PREVENTED, ratio=0.0):
    return ColumnSlendernessAxisBasis(
        axis=axis,
        section_dimension_mm=h,
        free_length_ln_mm=ln,
        effective_length_factor_k=k,
        sway_classification=sway,
        moment_ratio_m1_over_m2=ratio,
        source_refs=(f"fixture:{axis}",),
    )


def _basis(m2=None, m3=None):
    return ColumnSlendernessBasis(
        component_id=COMP,
        m2=m2 or _axis("M2"),
        m3=m3 or _axis("M3"),
        source_refs=("fixture:basis",),
    )


def test_missing_regulatory_basis_fails_closed():
    result = evaluate_ts500_column_slenderness(component_id=COMP, basis=None)
    assert result.status == "BLOCKED_SLENDERNESS_BASIS"
    assert not result.resolved
    assert result.m2.status == "BLOCKED_MISSING_REGULATORY_BASIS"
    assert result.m3.status == "BLOCKED_MISSING_REGULATORY_BASIS"


def test_rectangular_radius_and_braced_limit_follow_ts500_7_17():
    # i=0.30h=240 mm, lk=3000 mm, lambda=12.5.
    result = evaluate_ts500_column_slenderness(component_id=COMP, basis=_basis())
    assert result.status == "PROVEN_SLENDERNESS_EFFECTS_NEGLIGIBLE"
    assert result.m2.radius_of_gyration_i_mm == pytest.approx(240.0)
    assert result.m2.effective_length_lk_mm == pytest.approx(3000.0)
    assert result.m2.slenderness_ratio_lk_over_i == pytest.approx(12.5)
    assert result.m2.neglect_limit == pytest.approx(34.0)


def test_sway_prevented_limit_is_capped_at_40():
    result = evaluate_ts500_column_slenderness(
        component_id=COMP,
        basis=_basis(
            m2=_axis("M2", ratio=-1.0),
            m3=_axis("M3", ratio=-1.0),
        ),
    )
    assert result.m2.neglect_limit == pytest.approx(40.0)
    assert result.m3.neglect_limit == pytest.approx(40.0)


def test_sway_permitted_uses_22_limit_and_does_not_require_moment_ratio():
    axis = ColumnSlendernessAxisBasis(
        axis="M2",
        section_dimension_mm=800.0,
        free_length_ln_mm=4000.0,
        effective_length_factor_k=1.0,
        sway_classification=SWAY_PERMITTED,
        moment_ratio_m1_over_m2=None,
        source_refs=("fixture:M2",),
    )
    result = evaluate_ts500_column_slenderness(
        component_id=COMP,
        basis=_basis(m2=axis, m3=ColumnSlendernessAxisBasis(
            axis="M3",
            section_dimension_mm=800.0,
            free_length_ln_mm=4000.0,
            effective_length_factor_k=1.0,
            sway_classification=SWAY_PERMITTED,
            moment_ratio_m1_over_m2=None,
            source_refs=("fixture:M3",),
        )),
    )
    assert result.m2.neglect_limit == pytest.approx(22.0)
    assert result.status == "PROVEN_SLENDERNESS_EFFECTS_NEGLIGIBLE"


def test_axis_over_neglect_limit_requires_moment_magnification_not_fail():
    result = evaluate_ts500_column_slenderness(
        component_id=COMP,
        basis=_basis(
            m2=_axis("M2", ln=6000.0, h=500.0, ratio=1.0),
            m3=_axis("M3", ln=3000.0, h=800.0, ratio=0.0),
        ),
    )
    assert result.m2.slenderness_ratio_lk_over_i == pytest.approx(40.0)
    assert result.m2.neglect_limit == pytest.approx(22.0)
    assert result.m2.status == "MOMENT_MAGNIFICATION_REQUIRED"
    assert result.status == "REQUIRES_MOMENT_MAGNIFICATION"
    assert result.requires_moment_magnification


def test_lambda_above_100_requires_general_second_order_analysis():
    result = evaluate_ts500_column_slenderness(
        component_id=COMP,
        basis=_basis(
            m2=_axis("M2", ln=16000.0, h=500.0, k=1.0, ratio=0.0),
            m3=_axis("M3"),
        ),
    )
    assert result.m2.slenderness_ratio_lk_over_i > 100.0
    assert result.m2.status == "GENERAL_SECOND_ORDER_ANALYSIS_REQUIRED"
    assert result.status == "GENERAL_SECOND_ORDER_ANALYSIS_REQUIRED"


def test_sway_prevented_requires_source_bound_m1_m2_ratio():
    with pytest.raises(ColumnSlendernessError, match="moment_ratio_m1_over_m2"):
        ColumnSlendernessAxisBasis(
            axis="M2",
            section_dimension_mm=800.0,
            free_length_ln_mm=3000.0,
            effective_length_factor_k=1.0,
            sway_classification=SWAY_PREVENTED,
            moment_ratio_m1_over_m2=None,
            source_refs=("fixture",),
        )


def test_factual_clear_length_candidate_cannot_masquerade_as_regulatory_free_length():
    with pytest.raises(ColumnSlendernessError, match="free length has not been promoted"):
        ColumnSlendernessAxisBasis(
            axis="M2",
            section_dimension_mm=800.0,
            free_length_ln_mm=4450.0,
            effective_length_factor_k=1.0,
            sway_classification=SWAY_PREVENTED,
            moment_ratio_m1_over_m2=0.0,
            source_refs=("column_shear_topology:analysis_clear_length_candidate_m",),
            free_length_authority="FACTUAL_ANALYSIS_CLEAR_LENGTH_CANDIDATE",
        )
