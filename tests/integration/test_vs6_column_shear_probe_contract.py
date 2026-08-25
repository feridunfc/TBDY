from tools.probe_vs6_column_shear_sources import decode_get_rebar_column


def _call_result(*, to_be_designed: bool, return_code: int = 0):
    return {
        "success": True,
        "raw": [
            "DefaultRebar_500",
            "DefaultRebar_500",
            1,
            0,
            0.04,
            0,
            3,
            5,
            "20",
            "10",
            0.15,
            3,
            3,
            to_be_designed,
            return_code,
        ],
    }


def test_get_rebar_column_to_be_designed_is_design_intent_only():
    decoded = decode_get_rebar_column(_call_result(to_be_designed=True))

    assert decoded["status"] == "DECODED"
    assert decoded["authority_status"] == "DESIGN_INTENT_ONLY"
    assert decoded["data"]["MatPropLong"] == "DefaultRebar_500"
    assert decoded["data"]["MatPropConfine"] == "DefaultRebar_500"
    assert decoded["data"]["Cover"] == 0.04
    assert decoded["data"]["NumberR3Bars"] == 3
    assert decoded["data"]["NumberR2Bars"] == 5
    assert decoded["data"]["RebarSize"] == "20"
    assert decoded["data"]["TieSize"] == "10"
    assert decoded["data"]["TieSpacingLongit"] == 0.15
    assert decoded["data"]["Number2DirTieBars"] == 3
    assert decoded["data"]["Number3DirTieBars"] == 3
    assert decoded["data"]["ToBeDesigned"] is True


def test_get_rebar_column_check_input_is_not_promoted_to_final_rebar():
    decoded = decode_get_rebar_column(_call_result(to_be_designed=False))

    assert decoded["status"] == "DECODED"
    assert decoded["authority_status"] == "SECTION_REBAR_CHECK_INPUT"
    assert decoded["data"]["ToBeDesigned"] is False


def test_get_rebar_column_nonzero_return_code_is_not_proven():
    decoded = decode_get_rebar_column(
        _call_result(to_be_designed=False, return_code=1)
    )

    assert decoded["status"] == "NONZERO_RETURN_CODE"
    assert decoded["authority_status"] == "NOT_PROVEN"


def test_get_rebar_column_unexpected_shape_fails_closed():
    decoded = decode_get_rebar_column({"success": True, "raw": ["too", "short"]})

    assert decoded["status"] == "UNEXPECTED_SHAPE"
    assert decoded["authority_status"] == "NOT_PROVEN"
    assert decoded["data"] is None
