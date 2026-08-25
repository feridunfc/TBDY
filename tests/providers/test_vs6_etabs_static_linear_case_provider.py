import pytest

from tbdy_engine.providers.etabs_static_linear_case_provider import (
    EtabsStaticLinearCaseProviderError,
    capture_etabs_static_linear_case,
    capture_etabs_static_linear_cases,
)


class StaticLinear:
    def __init__(self, rows):
        self.rows = rows

    def GetLoads(self, name):
        return self.rows[name]


class LoadPatterns:
    def __init__(self, rows):
        self.rows = rows

    def GetLoadType(self, name):
        return self.rows[name]


def test_provider_preserves_case_load_terms_and_factual_pattern_types():
    case = capture_etabs_static_linear_case(
        StaticLinear({
            "LC_TEST": (3, ("Load", "Load", "Accel"), ("G", "Q", "UX"), (1.0, 0.5, 0.25), 0),
        }),
        LoadPatterns({
            "G": (1, 0),
            "Q": (3, 0),
        }),
        "LC_TEST",
    )

    assert case.status == "PROVEN_FACTUAL_STATIC_LINEAR_CASE_LOADS"
    assert [item.load_name for item in case.loads] == ["G", "Q", "UX"]
    assert [item.scale_factor for item in case.loads] == [1.0, 0.5, 0.25]
    assert case.loads[0].load_pattern.type_name == "DEAD"
    assert case.loads[1].load_pattern.type_name == "LIVE"
    assert case.loads[2].load_pattern is None


def test_unknown_newer_pattern_type_is_preserved_not_guessed():
    case = capture_etabs_static_linear_case(
        StaticLinear({"LC_X": (1, ("Load",), ("X",), (1.0,), 0)}),
        LoadPatterns({"X": (99, 0)}),
        "LC_X",
    )
    assert case.loads[0].load_pattern.type_code == 99
    assert case.loads[0].load_pattern.type_name == "UNKNOWN_99"


def test_nonzero_api_return_fails_closed():
    with pytest.raises(EtabsStaticLinearCaseProviderError, match="failed"):
        capture_etabs_static_linear_case(
            StaticLinear({"BAD": (0, (), (), (), 1)}),
            LoadPatterns({}),
            "BAD",
        )


def test_count_mismatch_and_unknown_load_type_fail_closed():
    with pytest.raises(EtabsStaticLinearCaseProviderError, match="count mismatch"):
        capture_etabs_static_linear_case(
            StaticLinear({"BAD": (2, ("Load",), ("G",), (1.0,), 0)}),
            LoadPatterns({"G": (1, 0)}),
            "BAD",
        )

    with pytest.raises(EtabsStaticLinearCaseProviderError, match="Load or Accel"):
        capture_etabs_static_linear_case(
            StaticLinear({"BAD": (1, ("Mystery",), ("G",), (1.0,), 0)}),
            LoadPatterns({"G": (1, 0)}),
            "BAD",
        )


def test_batch_requires_unique_names_and_preserves_order():
    static = StaticLinear({
        "A": (1, ("Load",), ("G",), (1.0,), 0),
        "B": (1, ("Load",), ("Q",), (1.0,), 0),
    })
    patterns = LoadPatterns({"G": (1, 0), "Q": (3, 0)})
    result = capture_etabs_static_linear_cases(static, patterns, ("B", "A"))
    assert [item.name for item in result] == ["B", "A"]

    with pytest.raises(EtabsStaticLinearCaseProviderError, match="unique"):
        capture_etabs_static_linear_cases(static, patterns, ("A", "A"))
