from __future__ import annotations

import inspect

import pytest

import tbdy_engine.application.column_public_a5 as public_a5
from tbdy_engine.application.column_execution import (
    ColumnExecutionContractError,
    _decode_canonical_a23_demand_states,
)


COMPONENT = "Story1:C1:1"


def _state_payload(*, state_id: str, end_tag: str) -> dict[str, object]:
    return {
        "state_id": state_id,
        "component_id": COMPONENT,
        "output_case": "ULS",
        "case_type": "DesignStaticLinearExact",
        "step_type": None,
        "step_number": None,
        "station_m": 0.0 if end_tag == "I_END" else 3.0,
        "end_tag": end_tag,
        "nd_compression_n": 500000.0,
        "m2_nmm": 20000000.0,
        "m3_nmm": 30000000.0,
        "source_identity": f"A23:{state_id}",
    }


def _canonical_payload() -> dict[str, object]:
    return {
        "component_id": COMPONENT,
        "canonical_second_order": {
            "blockers": (),
            "reanalysis_items": (),
            "state_slenderness_bases": (),
            "moment_magnification_bases": (),
            "expected_final_states": (
                _state_payload(state_id="ULS:I", end_tag="I_END"),
                _state_payload(state_id="ULS:J", end_tag="J_END"),
            ),
        },
        "source_refs": (
            "COLUMN_R1_A21_A23_TYPED_FND2_PAYLOAD",
        ),
    }


def test_a37_restores_current_a23_states_without_recalculation():
    states = _decode_canonical_a23_demand_states(
        _canonical_payload(),
        component_id=COMPONENT,
    )

    assert tuple(item.state_id for item in states) == (
        "ULS:I",
        "ULS:J",
    )
    assert {item.end_tag for item in states} == {"I_END", "J_END"}
    assert all(item.component_id == COMPONENT for item in states)


def test_a37_a23_decoder_fails_closed_on_blocked_payload():
    payload = _canonical_payload()
    payload["canonical_second_order"]["blockers"] = (
        "A23:EXPLICIT_UNRESOLVED",
    )

    with pytest.raises(
        ColumnExecutionContractError,
        match="population is blocked",
    ):
        _decode_canonical_a23_demand_states(
            payload,
            component_id=COMPONENT,
        )


def test_a37_a23_decoder_fails_closed_on_component_mismatch():
    payload = _canonical_payload()
    payload["canonical_second_order"]["expected_final_states"][0][
        "component_id"
    ] = "OTHER:COLUMN"

    with pytest.raises(
        ColumnExecutionContractError,
        match="component identity mismatch",
    ):
        _decode_canonical_a23_demand_states(
            payload,
            component_id=COMPONENT,
        )


def test_public_a5_forwards_same_generation_a23_and_free_length_to_completion():
    materializer_source = inspect.getsource(
        public_a5._materialize_public_a5_column
    )
    public_source = inspect.getsource(
        public_a5.execute_public_a5_column
    )

    assert (
        "inputs, free_length, canonical_second_order = "
        "_materialize_fnd2_inputs("
    ) in materializer_source
    assert "fnd_col_2_inputs=inputs" in materializer_source
    assert "free_length=free_length" in materializer_source
    assert (
        "canonical_second_order=canonical_second_order"
        in materializer_source
    )

    assert "_materialize_public_a5_column(" in public_source
    assert "free_length=materialized.free_length" in public_source
    assert (
        "canonical_second_order=materialized.canonical_second_order"
        in public_source
    )
