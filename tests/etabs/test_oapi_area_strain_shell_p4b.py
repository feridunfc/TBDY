from __future__ import annotations

import pytest

from tbdy_engine.etabs.oapi.contracts import EtabsOAPIError
from tbdy_engine.etabs.oapi.eq713_response_results import (
    AreaStrainShellRowIdentityProjection,
    decode_area_strain_shell_response,
)


_VALUES = (
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


def _raw(
    *,
    ret: int = 0,
    object_name: str = "A1",
    case_name: str = "EQX",
    count: int = 1,
    identity: str = "complete",
    truncate_numeric: int | None = None,
):
    if identity == "complete":
        obj = [object_name] * count
        elm = ["E1"] * count
        point_elm = ["P1"] * count
    elif identity == "unavailable":
        obj = []
        elm = []
        point_elm = []
    elif identity == "mixed":
        obj = [object_name] * count
        elm = []
        point_elm = []
    elif identity == "partial":
        partial_count = max(count - 1, 0)
        obj = [object_name] * partial_count
        elm = ["E1"] * partial_count
        point_elm = ["P1"] * partial_count
    else:
        raise ValueError(identity)

    numeric = [[value] * count for value in _VALUES]
    if truncate_numeric is not None:
        numeric[truncate_numeric] = numeric[truncate_numeric][:-1]

    return (
        count,
        obj,
        elm,
        point_elm,
        [case_name] * count,
        [""] * count,
        [0.0] * count,
        *numeric,
        ret,
    )


def test_area_strain_shell_decoder_preserves_exact_documented_fields() -> None:
    fact = decode_area_strain_shell_response(
        _raw(),
        area_name="A1",
        case_name="EQX",
    )

    assert fact.area_name == "A1"
    assert fact.case_name == "EQX"
    assert fact.return_code == 0
    assert fact.source_api == "Results.AreaStrainShell"
    assert fact.row_identity_projection is (
        AreaStrainShellRowIdentityProjection.RETURNED_ROW_IDENTITY_AVAILABLE
    )
    assert fact.evidence_ref == "ETABS:Results.AreaStrainShell:A1:EQX:rows=1"

    row = fact.rows[0]
    assert (row.object_name, row.element_name, row.point_element_name) == (
        "A1",
        "E1",
        "P1",
    )
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


def test_area_strain_shell_decoder_accepts_exact_live_absent_row_identity() -> None:
    fact = decode_area_strain_shell_response(
        _raw(identity="unavailable"),
        area_name="A1",
        case_name="EQX",
    )

    assert fact.area_name == "A1"
    assert fact.case_name == "EQX"
    assert fact.return_code == 0
    assert fact.row_identity_projection is (
        AreaStrainShellRowIdentityProjection.RETURNED_ROW_IDENTITY_UNAVAILABLE
    )
    assert fact.evidence_ref == (
        "ETABS:Results.AreaStrainShell:A1:EQX:rows=1:"
        "row_identity=UNAVAILABLE"
    )

    row = fact.rows[0]
    assert row.object_name is None
    assert row.element_name is None
    assert row.point_element_name is None
    assert row.load_case == "EQX"
    assert row.e11_top == 0.001
    assert row.g23_avg == -0.013


def test_area_strain_shell_decoder_fails_closed_on_complete_object_or_case_mismatch() -> None:
    with pytest.raises(EtabsOAPIError, match="binding mismatch"):
        decode_area_strain_shell_response(
            _raw(object_name="OTHER"),
            area_name="A1",
            case_name="EQX",
        )

    with pytest.raises(EtabsOAPIError, match="binding mismatch"):
        decode_area_strain_shell_response(
            _raw(case_name="OTHER"),
            area_name="A1",
            case_name="EQX",
        )


def test_area_strain_shell_case3_still_requires_returned_case_binding() -> None:
    with pytest.raises(EtabsOAPIError, match="binding mismatch"):
        decode_area_strain_shell_response(
            _raw(identity="unavailable", case_name="OTHER"),
            area_name="A1",
            case_name="EQX",
        )


@pytest.mark.parametrize(
    ("identity", "count"),
    (("mixed", 1), ("partial", 2)),
)
def test_area_strain_shell_decoder_rejects_partial_or_mixed_identity_projection(
    identity: str,
    count: int,
) -> None:
    with pytest.raises(
        EtabsOAPIError,
        match="partial/mixed row identity projection",
    ):
        decode_area_strain_shell_response(
            _raw(identity=identity, count=count),
            area_name="A1",
            case_name="EQX",
        )


def test_area_strain_shell_decoder_rejects_nonzero_return_code() -> None:
    with pytest.raises(EtabsOAPIError, match="nonzero code 1"):
        decode_area_strain_shell_response(
            _raw(ret=1, identity="unavailable"),
            area_name="A1",
            case_name="EQX",
        )


def test_area_strain_shell_decoder_rejects_zero_population() -> None:
    with pytest.raises(EtabsOAPIError, match="returned no rows"):
        decode_area_strain_shell_response(
            _raw(count=0, identity="unavailable"),
            area_name="A1",
            case_name="EQX",
        )


def test_area_strain_shell_decoder_rejects_incomplete_numeric_population() -> None:
    with pytest.raises(
        EtabsOAPIError,
        match=r"AreaStrainShell\[7\].*at least 2",
    ):
        decode_area_strain_shell_response(
            _raw(
                count=2,
                identity="unavailable",
                truncate_numeric=0,
            ),
            area_name="A1",
            case_name="EQX",
        )
