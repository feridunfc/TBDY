import math

from tbdy_engine.design.columns.effective_length import (
    ColumnEffectiveLengthAxisBasis,
    evaluate_ts500_effective_length_factor,
)
from tbdy_engine.design.columns.slenderness import SWAY_PERMITTED, SWAY_PREVENTED


def _basis(*, axis="M2", sway=SWAY_PREVENTED, a1=1.0, a2=3.0, hinged=False):
    return ColumnEffectiveLengthAxisBasis(
        axis=axis,
        sway_classification=sway,
        alpha_bottom=a1,
        alpha_top=a2,
        one_end_hinged=hinged,
        source_refs=("joint-bottom", "joint-top"),
    )


def test_sway_prevented_eq714_uses_stated_upper_bounds():
    result = evaluate_ts500_effective_length_factor(_basis(a1=1.0, a2=3.0))
    assert result.alpha1 == 1.0
    assert result.alpha2 == 3.0
    assert result.alpha_m == 2.0
    assert math.isclose(result.effective_length_factor_k, 0.90)


def test_sway_permitted_eq715_alpha_m_below_two():
    result = evaluate_ts500_effective_length_factor(
        _basis(sway=SWAY_PERMITTED, a1=0.5, a2=1.5)
    )
    expected = ((20.0 - 1.0) / 20.0) * math.sqrt(2.0)
    assert math.isclose(result.effective_length_factor_k, expected)


def test_sway_permitted_eq715_alpha_m_at_least_two():
    result = evaluate_ts500_effective_length_factor(
        _basis(axis="M3", sway=SWAY_PERMITTED, a1=2.0, a2=4.0)
    )
    assert result.axis == "M3"
    assert math.isclose(result.effective_length_factor_k, 0.9 * math.sqrt(4.0))


def test_sway_permitted_one_end_hinged_uses_special_expression():
    result = evaluate_ts500_effective_length_factor(
        _basis(sway=SWAY_PERMITTED, a1=0.0, a2=4.0, hinged=True)
    )
    assert math.isclose(result.effective_length_factor_k, 3.2)
