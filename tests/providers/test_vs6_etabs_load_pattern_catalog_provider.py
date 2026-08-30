import pytest

from tbdy_engine.providers.etabs_load_pattern_catalog_provider import (
    capture_etabs_load_pattern_catalog,
)
from tbdy_engine.providers.etabs_static_linear_case_provider import (
    EtabsStaticLinearCaseProviderError,
)


class LoadPatterns:
    def __init__(self, names, types, ret=0):
        self.names = names
        self.types = types
        self.ret = ret

    def GetNameList(self):
        return (len(self.names), tuple(self.names), self.ret)

    def GetLoadType(self, name):
        return (self.types[name], 0)


def test_catalog_enumerates_all_patterns_and_preserves_type_order():
    result = capture_etabs_load_pattern_catalog(
        LoadPatterns(
            ["G", "Q", "EX", "WX"],
            {"G": 1, "Q": 3, "EX": 5, "WX": 6},
        )
    )
    assert result.status == "PROVEN_FACTUAL_LOAD_PATTERN_CATALOG"
    assert [item.name for item in result.patterns] == ["G", "Q", "EX", "WX"]
    assert [item.type_name for item in result.patterns] == ["DEAD", "LIVE", "QUAKE", "WIND"]


def test_catalog_rejects_count_mismatch_and_duplicates():
    class BadCount(LoadPatterns):
        def GetNameList(self):
            return (2, ("G",), 0)

    with pytest.raises(EtabsStaticLinearCaseProviderError, match="count mismatch"):
        capture_etabs_load_pattern_catalog(BadCount(["G"], {"G": 1}))

    with pytest.raises(EtabsStaticLinearCaseProviderError, match="duplicate names"):
        capture_etabs_load_pattern_catalog(
            LoadPatterns(["G", "G"], {"G": 1})
        )


def test_catalog_nonzero_return_fails_closed():
    with pytest.raises(EtabsStaticLinearCaseProviderError, match="failed"):
        capture_etabs_load_pattern_catalog(LoadPatterns(["G"], {"G": 1}, ret=1))
