import pytest

from tbdy_engine.providers.etabs_column_rebar_intent_provider import (
    REBAR_INTENT_DESIGN_ONLY,
    REBAR_INTENT_SECTION_CHECK_INPUT,
    EtabsColumnRebarIntentProviderError,
    capture_etabs_column_rebar_intent,
)


class FakePropFrame:
    def __init__(self, *, to_be_designed=True, as_list=True):
        values = (
            "DefaultRebar_500",  # MatPropLong
            "DefaultRebar_500",  # MatPropConfine
            1,                    # Pattern
            0,                    # ConfineType
            0.04,                 # Cover, reviewed m
            0,                    # NumberCBars
            3,                    # NumberR3Bars
            5,                    # NumberR2Bars
            "20",                 # RebarSize
            "10",                 # TieSize
            0.15,                 # TieSpacingLongit, reviewed m
            3,                    # Number2DirTieBars
            3,                    # Number3DirTieBars
            to_be_designed,       # ToBeDesigned
            0,                    # return code
        )
        self.raw = list(values) if as_list else values

    def GetRebarColumn(self, name):
        assert name == "Column_80x80"
        return self.raw


def test_generated_com_list_shape_preserves_api_r3_then_r2_order_and_design_intent_authority():
    result = capture_etabs_column_rebar_intent(
        FakePropFrame(to_be_designed=True, as_list=True),
        "Column_80x80",
        reviewed_length_unit="m",
    )

    assert result.status == "PROVEN_ETABS_COLUMN_REBAR_INTENT"
    assert result.authority == REBAR_INTENT_DESIGN_ONLY
    assert result.number_r3_bars == 3
    assert result.number_r2_bars == 5
    assert result.rebar_size_name == "20"
    assert result.tie_size_name == "10"
    assert result.cover_mm == pytest.approx(40.0)
    assert result.tie_spacing_longit_mm == pytest.approx(150.0)
    assert result.as_dict()["final_or_provided_rebar_authority"] is False


def test_tuple_shape_with_to_be_designed_false_is_section_check_input_not_final_rebar():
    result = capture_etabs_column_rebar_intent(
        FakePropFrame(to_be_designed=False, as_list=False),
        "Column_80x80",
        reviewed_length_unit="m",
    )
    assert result.authority == REBAR_INTENT_SECTION_CHECK_INPUT
    assert result.to_be_designed is False
    assert result.as_dict()["final_or_provided_rebar_authority"] is False


def test_mm_length_contract_does_not_rescale_cover_or_spacing():
    class MillimeterPropFrame(FakePropFrame):
        def __init__(self):
            super().__init__()
            self.raw[4] = 40.0
            self.raw[10] = 150.0

    result = capture_etabs_column_rebar_intent(
        MillimeterPropFrame(),
        "Column_80x80",
        reviewed_length_unit="mm",
    )
    assert result.cover_mm == pytest.approx(40.0)
    assert result.tie_spacing_longit_mm == pytest.approx(150.0)


def test_non_boolean_to_be_designed_fails_closed():
    fake = FakePropFrame()
    fake.raw[13] = 1
    with pytest.raises(EtabsColumnRebarIntentProviderError, match="non-boolean"):
        capture_etabs_column_rebar_intent(
            fake,
            "Column_80x80",
            reviewed_length_unit="m",
        )


def test_unexpected_api_shape_fails_closed():
    class BadShape:
        def GetRebarColumn(self, name):
            return ["too", "short", 0]

    with pytest.raises(EtabsColumnRebarIntentProviderError, match="expected 15"):
        capture_etabs_column_rebar_intent(
            BadShape(),
            "Column_80x80",
            reviewed_length_unit="m",
        )
