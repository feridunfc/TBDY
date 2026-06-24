import pytest

from etabs_gateway.contracts import ETABSModelContext
from etabs_gateway.model_context import build_model_context


def test_no_model_context_carries_no_stale_model_values() -> None:
    context = build_model_context(
        raw_model_path="",
        raw_is_locked=True,
        present_units_code=6,
    )

    assert context == ETABSModelContext(
        has_open_model=False,
        model_path=None,
        is_locked=None,
        units=None,
    )


def test_open_model_context_preserves_raw_unit_code() -> None:
    context = build_model_context(
        raw_model_path=r"C:\models\sample.edb",
        raw_is_locked=1,
        present_units_code=6,
        present_units_name="kN_m_C",
    )

    assert context.has_open_model is True
    assert context.model_name == "sample.edb"
    assert context.is_locked is True
    assert context.units is not None
    assert context.units.present_units_code == 6


def test_contract_rejects_stale_values_without_open_model() -> None:
    with pytest.raises(ValueError, match="model_path must be None"):
        ETABSModelContext(
            has_open_model=False,
            model_path="stale.edb",
            is_locked=None,
            units=None,
        )
