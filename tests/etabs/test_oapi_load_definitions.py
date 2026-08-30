from __future__ import annotations

import pytest

from tbdy_engine.etabs.oapi.contracts import EtabsOAPIError
from tbdy_engine.etabs.oapi.load_definitions import read_load_case_type


class _LoadCases:
    def __init__(self, raw: object) -> None:
        self.raw = raw

    def GetTypeOAPI_1(self, _name: str) -> object:
        return self.raw


@pytest.mark.parametrize(
    ("raw", "expected_auto"),
    [
        ([1, 0, 1, 0, 0, 0], 0),
        ([1, 0, 8, 0, 3, 0], 3),
        ([1, 0, 8, 0, 5, 0], 5),
        ([1, 0, 8, 0, 6, 0], 6),
        ([1, 0, 8, 0, 7, 0], 7),
        ([1, 0, 8, 0, 10, 0], 10),
        ([3, 2, 8, 0, 0, 0], 0),
        ([4, 0, 5, 0, 0, 0], 0),
    ],
)
def test_read_load_case_type_accepts_live_csi_auto_codes(
    raw: list[object], expected_auto: int
) -> None:
    fact = read_load_case_type(_LoadCases(raw), "CASE")

    assert fact.auto_flag == expected_auto
    assert fact.raw_response is raw


@pytest.mark.parametrize(
    "raw",
    [
        [1, 0, 1, 0, 0],
        [1, 0, 1, 0, 0, 1],
        [1, 0, 1, 2, 0, 0],
        [1, 0, 1, 0, True, 0],
        [1, 0, 1, 0, 5.5, 0],
        [1, 0, 1, 0, "5", 0],
        [1, 0, 1, 0, "malformed", 0],
    ],
)
def test_read_load_case_type_rejects_invalid_auto_or_abi_contract(raw: list[object]) -> None:
    with pytest.raises(EtabsOAPIError):
        read_load_case_type(_LoadCases(raw), "CASE")
