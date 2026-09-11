from __future__ import annotations

import pytest

from tbdy_engine.etabs.oapi.contracts import EtabsOAPIError
from tbdy_engine.etabs.oapi.eq713_response_results import (
    decode_area_strain_shell_response,
)


def _raw(*, ret: int = 0, object_name: str = "A1", case_name: str = "EQX"):
    values = (
        0.001,
        0.002,
        0.003,
        0.004,
        -0.005,
        6.0,
        0.007,
        -0.001,
        -0.002,
        -0.003,
        0.008,
        -0.009,
        -10.0,
        0.011,
        0.012,
        -0.013,
        0.014,
        15.0,
    )
    # NumberResults + Obj/Elm/PointElm/LoadCase/StepType/StepNum + 18 strain arrays + ret.
    return (
        1,
        [object_name],
        ["E1"],
        ["P1"],
        [case_name],
        [""],
        [0.0],
        *([value] for value in values),
        ret,
    )


def test_area_strain_shell_decoder_preserves_exact_documented_fields() -> None:
    fact = decode_area_strain_shell_response(_raw(), area_name="A1", case_name="EQX")
    assert fact.area_name == "A1"
    assert fact.case_name == "EQX"
    assert fact.return_code == 0
    assert fact.source_api == "Results.AreaStrainShell"
    assert fact.evidence_ref == "ETABS:Results.AreaStrainShell:A1:EQX:rows=1"
    row = fact.rows[0]
    assert (row.object_name, row.element_name, row.point_element_name) == ("A1", "E1", "P1")
    assert row.e11_top == 0.001
    assert row.e22_top == 0.002
    assert row.g12_top == 0.003
    assert row.e11_bottom == -0.001
    assert row.e22_bottom == -0.002
    assert row.g12_bottom == -0.003
    assert row.g13_avg == 0.012
    assert row.g23_avg == -0.013
    assert row.gmax_avg == 0.014
    assert row.gangle_avg == 15.0


def test_area_strain_shell_decoder_fails_closed_on_object_or_case_mismatch() -> None:
    with pytest.raises(EtabsOAPIError, match="binding mismatch"):
        decode_area_strain_shell_response(_raw(object_name="OTHER"), area_name="A1", case_name="EQX")
    with pytest.raises(EtabsOAPIError, match="binding mismatch"):
        decode_area_strain_shell_response(_raw(case_name="OTHER"), area_name="A1", case_name="EQX")


def test_area_strain_shell_decoder_rejects_nonzero_return_code() -> None:
    with pytest.raises(EtabsOAPIError, match="nonzero code 1"):
        decode_area_strain_shell_response(_raw(ret=1), area_name="A1", case_name="EQX")
