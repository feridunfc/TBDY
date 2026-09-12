from __future__ import annotations

import pytest

from tbdy_engine.etabs.oapi.contracts import EtabsOAPIError
from tbdy_engine.etabs.oapi.frame_design_procedure import (
    decode_frame_design_procedure_response,
    read_frame_design_procedure,
)


class _FrameObj:
    def __init__(self, value):
        self.value = value
        self.calls = []

    def GetDesignProcedure(self, name):
        self.calls.append(name)
        if isinstance(self.value, Exception):
            raise self.value
        return self.value


def test_decode_design_procedure_preserves_exact_factual_code() -> None:
    fact = decode_frame_design_procedure_response((2, 0), frame_name="F1")
    assert fact.frame_name == "F1"
    assert fact.procedure_code == 2
    assert fact.raw_response == (2, 0)


@pytest.mark.parametrize(
    "raw",
    [
        (2, 1),
        (2, True),
        (True, 0),
        ("2", 0),
        [2, 0],
        (2,),
        (2, 0, 0),
    ],
)
def test_decode_design_procedure_rejects_nonexact_or_failed_abi(raw) -> None:
    with pytest.raises(EtabsOAPIError):
        decode_frame_design_procedure_response(raw, frame_name="F1")


def test_read_design_procedure_calls_exact_requested_frame() -> None:
    frame_obj = _FrameObj((2, 0))
    fact = read_frame_design_procedure(frame_obj, "F2")
    assert frame_obj.calls == ["F2"]
    assert fact.procedure_code == 2


def test_read_design_procedure_wraps_com_failure() -> None:
    frame_obj = _FrameObj(RuntimeError("boom"))
    with pytest.raises(EtabsOAPIError, match="RuntimeError"):
        read_frame_design_procedure(frame_obj, "F2")
