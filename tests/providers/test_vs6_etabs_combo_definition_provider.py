import pytest

from tbdy_engine.providers.etabs_combo_definition_provider import (
    EtabsComboDefinitionProviderError,
    capture_etabs_combo_definition,
    capture_etabs_combo_definitions,
)


class FakeRespCombo:
    def __init__(self):
        self.types = {
            "TOP": [0, 0],
            "SUB": (1, 0),
        }
        self.lists = {
            "TOP": [2, [0, 1], ["LC_G", "SUB"], [1.0, 0.5], 0],
            "SUB": (1, (0,), ("RSX",), (1.0,), 0),
        }

    def GetTypeCombo(self, name):
        return self.types[name]

    def GetCaseList(self, name):
        return self.lists[name]


def test_provider_decodes_generated_com_list_and_tuple_shapes_without_design_classification():
    result = capture_etabs_combo_definition(FakeRespCombo(), "TOP")

    assert result.name == "TOP"
    assert result.combo_type == "LINEAR_ADD"
    assert [item.cname_type for item in result.constituents] == ["LOAD_CASE", "LOAD_COMBO"]
    assert [item.name for item in result.constituents] == ["LC_G", "SUB"]
    assert len(result.nested_combos) == 1
    assert result.nested_combos[0].name == "SUB"
    assert result.nested_combos[0].combo_type == "ENVELOPE"
    assert "GetTypeCombo" not in result.status
    assert "concurrency" not in str(result.as_dict()).lower()


def test_provider_requires_unique_requested_names():
    with pytest.raises(EtabsComboDefinitionProviderError, match="unique"):
        capture_etabs_combo_definitions(FakeRespCombo(), ("TOP", "TOP"))


def test_provider_fails_closed_on_recursive_combo_cycle():
    class Cyclic:
        def GetTypeCombo(self, name):
            return [0, 0]

        def GetCaseList(self, name):
            child = "B" if name == "A" else "A"
            return [1, [1], [child], [1.0], 0]

    with pytest.raises(EtabsComboDefinitionProviderError, match="recursive"):
        capture_etabs_combo_definition(Cyclic(), "A")
