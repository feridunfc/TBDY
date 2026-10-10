from copy import deepcopy
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path

import pytest

from tbdy_engine.analysis_basis.eq713_response_mechanics import (
    CSI_DATABASE_NORMALIZED_MODAL_AMPLITUDE_CONTRACT as CONTRACT,
    NativeModalNormalizationBinding as Binding, NativeModalColumnAxial as Column,
    bind_database_normalized_native_modal_amplitude as bind,
    aggregate_native_modal_column_axial as aggregate,
)
from tbdy_engine.etabs.oapi.database_tables import decode_table_field_metadata
from tools import column_r1_r3e_modal_normalization_offline as review


def metadata(unit="m"):
    keys = ["Period", "U1Amp", "U2Amp", "U3Amp"]
    return decode_table_field_metadata([1, 4, keys, keys, ["native period", *["native amplitude"]*3],
        ["sec", unit, unit, unit], [False]*4, 0], table_name=review.TABLE)


def binding(length="m", force="kN", direction="U1"):
    return Binding("FC09", "session:2072", "factual-capture", "Modal", "RSX", direction,
        force, length, CONTRACT)


def amplitude(value=-.353072, **kwargs):
    arguments = dict(mode=2, period_s=.553, native_value=value, binding=binding(),
        metadata=metadata(), raw_response_ref="amplitude:raw", observed_present_force_unit="kN",
        observed_present_length_unit="m")
    arguments.update(kwargs)
    return bind(**arguments)


@pytest.mark.parametrize("length,force", [("m", "kN"), ("mm", "N")])
@pytest.mark.parametrize("direction", ["U1", "U2", "U3"])
def test_native_numeric_amplitude_and_dimensional_header_retained(length, force, direction):
    a = amplitude(binding=binding(length, force, direction), metadata=metadata(length),
        observed_present_force_unit=force, observed_present_length_unit=length)
    assert a.multiplier == -.353072  # No additional SF, Gamma, omega or length rescale.
    assert a.native_field_unit == length and a.source_field == direction + "Amp"
    assert a.native_metadata_ref == metadata(length).raw_response_ref
    assert a.normalization_contract == CONTRACT


@pytest.mark.parametrize("value", [0., .762376, -.353072])
def test_signed_native_scaling_and_modal_orientation_invariance(value):
    a = amplitude(value)
    row = Column("C1", 2, -30., 3., a.binding, "kN", "m", "Mode", "PHYSICAL_BOTTOM", "force", "length")
    r = aggregate(amplitude=a, columns=(row,), expected_complete_story_columns=("C1",))
    assert r.r_force_per_length == pytest.approx(10*value)
    reversed_r = aggregate(amplitude=amplitude(-value), columns=(replace(row, signed_p=30.),),
        expected_complete_story_columns=("C1",))
    assert reversed_r.r_force_per_length == r.r_force_per_length
    assert r.qualified_for_stability is False


@pytest.mark.parametrize("changes", [
    {"observed_present_force_unit": "N"}, {"observed_present_length_unit": "mm"},
    {"metadata": metadata("mm")}, {"binding": replace(binding(), normalization_ref="inferred")},
    {"metadata": replace(metadata(), table_name="Other")},
    {"metadata": replace(metadata(), return_code=1)},
    {"metadata": replace(metadata(), field_keys=("Period", "U1Acc", "U2Amp", "U3Amp"))},
    {"metadata": replace(metadata(), units_strings=("s", "m", "m", "m"))},
    {"metadata": replace(metadata(), field_keys=("Period", "U1Amp", "U1Amp", "U3Amp"))},
    {"native_value": float("nan")}, {"native_value": float("inf")},
    {"mode": True}, {"period_s": 0.},
])
def test_unqualified_units_metadata_normalization_or_nonfinite_amplitude_fail(changes):
    with pytest.raises((ValueError, RuntimeError)):
        amplitude(**changes)


def synthetic_receipt():
    r = dict(errors=[], source_unchanged=True, output_state_restored=True,
        source_sha256_before=review.FC09_SHA256, source_sha256_after=review.FC09_SHA256,
        identity_before=dict(program_version="23.2.0", program_api_version=2.014,
            units=dict(database_force_unit=4, database_length_unit=6, present_force_unit=4,
                present_length_unit=6, present_observation_status="OBSERVED_CONSISTENT",
                database_observation_status="OBSERVED_CONSISTENT")),
        factual_capture_binding=dict(source_model_ref="FC09", session_ref="session:2072",
            capture_ref="factual-capture", is_analysis_result_epoch=False), current_b5_qualified=False,
        stability_promotion=False, R2_RERUN_READY=False,
        status="FACTUAL_100_MODE_CAPTURE_COMPLETE_PENDING_NORMALIZATION_B5_AND_JOINT_RULE",
        native_result_units=dict(FrameForce="kN", JointDispl="m", database_force="kN", database_length="m"), facts={})
    r["identity_after"] = deepcopy(r["identity_before"])
    def fact(key, payload):
        r["facts"][key] = dict(payload=payload, capture_payload_ref=review._payload_ref(payload))
    fact(review.TABLE + ":metadata", dict(raw_response=list(metadata().raw_response)))
    for case, direction in (("RSX", "U1"), ("RSY", "U2")):
        fact(case + ":settings", dict(settings=[
            dict(method="GetModalCase", return_code=0, outputs=[["ModalCase", "Modal"]]),
            dict(method="GetLoads", return_code=0, outputs=[["NumberLoads", 1], ["LoadName", [direction]], ["SF", [10.]]])]))
        fact(review.TABLE + "@" + case, dict(parsed=dict(fetch_status="FETCHED", return_code=0,
            rows=[dict(SpecCase=case, ModalCase="Modal", Mode=str(n), Period=".553",
                **{direction + "Amp": "-.353072"}) for n in range(1, 101)])))
    return r


def test_complete_native_population_binds_two_cases_without_case_sf_reapplication():
    result = review.bind_receipt_amplitudes(synthetic_receipt())
    assert len(result["RSX"]) == len(result["RSY"]) == 100
    assert all(a.multiplier == -.353072 for rows in result.values() for a in rows)


@pytest.mark.parametrize("defect", ["source", "session", "units", "version", "restore", "b5", "epoch",
    "promotion", "raw", "truncated", "duplicate", "wrong_case", "wrong_direction", "noninteger"])
def test_offline_adapter_rejects_drift_incomplete_modes_and_false_lineage(defect):
    r = synthetic_receipt()
    if defect == "source": r["source_sha256_after"] = "5AA"
    elif defect == "session": r["identity_after"]["process_id"] = 9
    elif defect == "units":
        r["identity_before"]["units"]["present_observation_status"] = "UNAVAILABLE"
        r["identity_after"] = deepcopy(r["identity_before"])
    elif defect == "version":
        r["identity_before"]["program_version"] = "other"
        r["identity_after"] = deepcopy(r["identity_before"])
    elif defect == "restore": r["output_state_restored"] = False
    elif defect == "b5": r["current_b5_qualified"] = True
    elif defect == "epoch": r["factual_capture_binding"]["is_analysis_result_epoch"] = True
    elif defect == "promotion": r["stability_promotion"] = True
    else:
        fact = r["facts"][review.TABLE + "@RSX"]
        rows = fact["payload"]["parsed"]["rows"]
        if defect in ("raw", "truncated"): rows.pop()
        elif defect == "duplicate": rows.append(rows[0])
        elif defect == "wrong_case": rows[0]["ModalCase"] = "Other"
        elif defect == "wrong_direction":
            fact = r["facts"]["RSX:settings"]
            fact["payload"]["settings"][1]["outputs"][1][1] = ["U2"]
        elif defect == "noninteger": rows[0]["Mode"] = "1.1"
        if defect != "raw": fact["capture_payload_ref"] = review._payload_ref(fact["payload"])
    with pytest.raises(ValueError): review.bind_receipt_amplitudes(r)


def test_changed_reviewed_receipt_bytes_fail_before_interpretation(tmp_path):
    path = tmp_path / "changed.json"
    path.write_text(json.dumps(synthetic_receipt()))
    with pytest.raises(ValueError, match="SHA256"): review.review_exact_receipt(path)


def test_actual_fc09_receipt_200_amplitudes_and_open_engineering_gates():
    value = os.getenv("COLUMN_R1_R3E_CAPTURE_TEST_PATH")
    if not value:
        pytest.skip("complete raw FC09 receipt is external source evidence")
    report = review.review_exact_receipt(Path(value))
    assert report["input_receipt_sha256"] == review.ACCEPTED_RECEIPT_SHA256
    assert len(report["mode_amplitudes"]["RSX"]) == len(report["mode_amplitudes"]["RSY"]) == 100
    assert report["mode_amplitudes"]["RSX"][0]["multiplier"] == .762376
    assert report["mode_amplitudes"]["RSX"][1]["multiplier"] == -.353072
    assert report["mode_amplitudes"]["RSY"][0]["multiplier"] == .361023
    assert report["current_b5_qualified"] is report["stability_promotion"] is report["R2_RERUN_READY"] is False
    assert report["joint_delta_r_v_statistic"] == "PROJECT_DECISION_REQUIRED"
