"""Review the accepted R3D bytes offline; no live session or result issuer.

The output binds native amplitudes only. Physical R/Delta/V, CQC, a qualified
B5 epoch and the joint engineering statistic remain independent open gates.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
for path in (REPO_ROOT, REPO_ROOT / "packages" / "etabs_gateway" / "src"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from tbdy_engine.analysis_basis.eq713_response_mechanics import (
    CSI_DATABASE_NORMALIZED_MODAL_AMPLITUDE_CONTRACT as CONTRACT,
    CSI_NATIVE_MODAL_AMPLITUDE_SOURCE, CSI_NATIVE_MODAL_NORMALIZATION_SOURCE,
    NativeModalNormalizationBinding, bind_database_normalized_native_modal_amplitude,
)
from tbdy_engine.etabs.oapi.database_tables import decode_table_field_metadata
from tbdy_engine.etabs.source_units import decode_csi_force_unit, decode_csi_length_unit

ACCEPTED_RECEIPT_SHA256 = "83ce2ff7c3a6170e931d2869e212adde93b7c08b25bbf44e9f0c2c663f156b03"
FC09_SHA256 = "FC09E5EEB1E195C7141EB992EC501E0004EA733078997C58E1F84D979F70758F"
TABLE = "Response Spectrum Modal Info"
MODES = set(range(1, 101))


def _payload_ref(payload):
    raw = json.dumps(payload, sort_keys=True, allow_nan=False, separators=(",", ":")).encode()
    return "modal-read:sha256:" + hashlib.sha256(raw).hexdigest()


def bind_receipt_amplitudes(receipt):
    """Pure factual review of an R3D receipt; never a source/B5 authority issuer."""
    if (receipt["errors"] or receipt["source_unchanged"] is not True
            or receipt["output_state_restored"] is not True
            or receipt["source_sha256_before"] != FC09_SHA256
            or receipt["source_sha256_after"] != FC09_SHA256
            or receipt["identity_before"] != receipt["identity_after"]):
        raise ValueError("successful unchanged FC09 source/session/output state required")
    if receipt["status"] != "FACTUAL_100_MODE_CAPTURE_COMPLETE_PENDING_NORMALIZATION_B5_AND_JOINT_RULE":
        raise ValueError("accepted complete R3D capture status required")
    capture = receipt["factual_capture_binding"]
    if (capture["is_analysis_result_epoch"] is not False
            or receipt["current_b5_qualified"] is not False
            or receipt["stability_promotion"] is not False
            or receipt["R2_RERUN_READY"] is not False):
        raise ValueError("factual read must not claim qualified B5/stability lineage")
    identity = receipt["identity_before"]
    if (identity["program_version"], identity["program_api_version"]) != ("23.2.0", 2.014):
        raise ValueError("accepted native ETABS/API version required")
    units = identity["units"]
    if any(units[k] != "OBSERVED_CONSISTENT" for k in (
            "present_observation_status", "database_observation_status")):
        raise ValueError("independent present/database unit observations required")
    force = decode_csi_force_unit(units["database_force_unit"])
    length = decode_csi_length_unit(units["database_length_unit"])
    present_force = decode_csi_force_unit(units["present_force_unit"])
    present_length = decode_csi_length_unit(units["present_length_unit"])
    native_units = receipt["native_result_units"]
    if (native_units["FrameForce"], native_units["JointDispl"],
            native_units["database_force"], native_units["database_length"]) != (
            present_force, present_length, force, length):
        raise ValueError("native response unit binding mismatch")
    facts = receipt["facts"]
    for key, fact in facts.items():
        if fact["capture_payload_ref"] != _payload_ref(fact["payload"]):
            raise ValueError(f"changed raw capture payload: {key}")
    metadata_fact = facts[TABLE + ":metadata"]
    metadata = decode_table_field_metadata(metadata_fact["payload"]["raw_response"], table_name=TABLE)
    # The capture retained the last identical native header, not both capture
    # UUIDs. Keep the header actually available; do not manufacture RSX's older
    # overwritten metadata payload or its capture identity.
    result = {}
    for case in ("RSX", "RSY"):
        settings = {s["method"]: s for s in facts[case + ":settings"]["payload"]["settings"]}
        for method in ("GetModalCase", "GetLoads"):
            if settings[method]["return_code"] != 0:
                raise ValueError("successful native case dependency/load settings required")
        modal_case = dict(settings["GetModalCase"]["outputs"])["ModalCase"]
        loads = dict(settings["GetLoads"]["outputs"])
        if modal_case != "Modal" or loads["NumberLoads"] != 1:
            raise ValueError("exact single native direction/modal dependency required")
        direction = loads["LoadName"][0]
        if direction != {"RSX": "U1", "RSY": "U2"}[case]:
            raise ValueError("current FC09 direction changed; no case-name inference")
        binding = NativeModalNormalizationBinding(capture["source_model_ref"], capture["session_ref"],
            capture["capture_ref"], modal_case, case, direction, force, length, CONTRACT)
        fact = facts[TABLE + "@" + case]
        parsed = fact["payload"]["parsed"]
        if parsed["fetch_status"] != "FETCHED" or parsed["return_code"] != 0:
            raise ValueError("successful native amplitude table required")
        amplitudes = {}
        for row in parsed["rows"]:
            if row["SpecCase"] != case or row["ModalCase"] != modal_case:
                raise ValueError("amplitude spectrum/modal case mismatch")
            mode_number = Decimal(row["Mode"])
            if not mode_number.is_finite() or mode_number != mode_number.to_integral_value():
                raise ValueError("exact native mode index required")
            mode = int(mode_number)
            if mode in amplitudes:
                raise ValueError("duplicate native amplitude mode")
            amplitudes[mode] = bind_database_normalized_native_modal_amplitude(
                mode=mode, period_s=float(row["Period"]), native_value=float(row[direction + "Amp"]),
                binding=binding, metadata=metadata, raw_response_ref=fact["capture_payload_ref"],
                observed_present_force_unit=present_force, observed_present_length_unit=present_length)
        if set(amplitudes) != MODES:
            raise ValueError("native amplitude mode population is incomplete/extra")
        result[case] = tuple(amplitudes[n] for n in sorted(amplitudes))
    return result


def review_exact_receipt(source: Path):
    data = Path(source).read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != ACCEPTED_RECEIPT_SHA256:
        raise ValueError("reviewed receipt bytes differ from accepted SHA256")
    receipt = json.loads(data)
    bound = bind_receipt_amplitudes(receipt)
    return {
        "status": "NATIVE_AMPLITUDES_BOUND_OFFLINE_PENDING_PHYSICAL_AGGREGATES_CQC_B5_AND_JOINT_RULE",
        "input_receipt_sha256": digest, "contract": CONTRACT,
        "source_references": [CSI_NATIVE_MODAL_NORMALIZATION_SOURCE, CSI_NATIVE_MODAL_AMPLITUDE_SOURCE],
        "native_metadata_capture_payload_ref": receipt["facts"][TABLE + ":metadata"]["capture_payload_ref"],
        "normalization_scope": "native database-unit unit-modal-mass numerical responses; present=database",
        "additional_scale_factor_applied": False, "mode_amplitudes": {
            case: [asdict(a) for a in amplitudes] for case, amplitudes in bound.items()},
        "current_b5_qualified": False, "stability_promotion": False, "R2_RERUN_READY": False,
        "joint_delta_r_v_statistic": "PROJECT_DECISION_REQUIRED", "ETABS_EXECUTED": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.is_relative_to(REPO_ROOT) or not output.parent.is_dir():
        raise ValueError("new review output must be outside repository in an existing directory")
    review = review_exact_receipt(args.receipt)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(review, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"status": review["status"], "bound_amplitudes": 200, "R2_RERUN_READY": False}))


if __name__ == "__main__":
    raise SystemExit(main())
