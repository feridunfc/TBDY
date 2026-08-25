from tbdy_engine.design.columns.combo_pattern_engine import (
    ComboPatternConstituent,
    PATTERN_STATIC_LINEAR,
    PATTERN_STATIC_PLUS_RESPONSE_SPECTRUM,
    PATTERN_UNSUPPORTED,
    classify_combo_pattern,
)


def test_combo_name_has_no_engineering_semantics():
    terms = (
        ComboPatternConstituent("D", 1.0),
        ComboPatternConstituent("RSX", 1.0),
        ComboPatternConstituent("RSY", 0.3),
    )
    case_types = {"D": "LinStatic", "RSX": "LinRespSpec", "RSY": "LinRespSpec"}
    a = classify_combo_pattern(
        combo_name="Crack_SeisX",
        combo_type="LINEAR_ADD",
        constituents=terms,
        case_types=case_types,
    )
    b = classify_combo_pattern(
        combo_name="ULS_17",
        combo_type="LINEAR_ADD",
        constituents=terms,
        case_types=case_types,
    )
    assert a.pattern == b.pattern == PATTERN_STATIC_PLUS_RESPONSE_SPECTRUM
    assert a.supported and b.supported


def test_static_linear_pattern_is_supported():
    result = classify_combo_pattern(
        combo_name="ANY_NAME",
        combo_type="LINEAR_ADD",
        constituents=(ComboPatternConstituent("D", 1.4), ComboPatternConstituent("L", 1.6)),
        case_types={"D": "LinStatic", "L": "LinStatic"},
    )
    assert result.pattern == PATTERN_STATIC_LINEAR
    assert result.status == "PROVEN_SUPPORTED_COMBO_PATTERN"


def test_unsupported_case_type_fails_closed():
    result = classify_combo_pattern(
        combo_name="Crack_SeisX",
        combo_type="LINEAR_ADD",
        constituents=(ComboPatternConstituent("TH", 1.0),),
        case_types={"TH": "NonlinearStatic"},
    )
    assert result.pattern == PATTERN_UNSUPPORTED
    assert not result.supported
    assert result.status == "BLOCKED_UNSUPPORTED_COMBO_PATTERN"
    assert result.unsupported_case_names == ("TH",)


def test_nested_combo_fails_closed_even_with_familiar_name():
    result = classify_combo_pattern(
        combo_name="Crack_SeisX",
        combo_type="LINEAR_ADD",
        constituents=(ComboPatternConstituent("SUB", 1.0, cname_type="LOAD_COMBO"),),
        case_types={"SUB": "LinStatic"},
    )
    assert result.pattern == PATTERN_UNSUPPORTED
    assert not result.supported
