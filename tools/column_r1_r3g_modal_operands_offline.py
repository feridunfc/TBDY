"""Accepted FC09 bytes -> factual modal operands; no ETABS or design issuer.

The receipt lacks total modal damping and point local-to-global axes. Retain
those blockers rather than inventing current CQC magnitudes or story Delta.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
for path in (REPO_ROOT, REPO_ROOT / "packages" / "etabs_gateway" / "src"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from tools.column_r1_r3e_modal_normalization_offline import ACCEPTED_RECEIPT_SHA256, bind_receipt_amplitudes
from tools.column_r1_r3f_physical_modal_aggregate_offline import reconcile_receipt_modal_axial
from tbdy_engine.etabs.oapi.database_tables import decode_table_field_metadata
from tbdy_engine.etabs.oapi.joint_displacement_results import JointDisplacementResultFact, JointDisplacementResultRow
from tbdy_engine.providers.etabs_story_stability_result_provider import (
    qualify_native_modal_endpoint_rows, qualify_native_modal_story_shear,
)
from tbdy_engine.analysis_basis.eq713_response_mechanics import (
    native_modal_scalar_contribution, CSI_PERIODIC_CQC_SOURCE, WILSON_PERIODIC_CQC_SOURCE,
)

MODES = tuple(range(1, 101))


def reconcile_receipt_modal_operands(receipt):
    """Offline representative facts, never qualified current B5 results."""
    physical = reconcile_receipt_modal_axial(receipt)
    amplitudes = bind_receipt_amplitudes(receipt)
    facts = receipt["facts"]

    def table(name, suffix=""):
        fact = facts[name + suffix]
        p = fact["payload"]["parsed"]
        if p["actual_table_name"] != name or p["fetch_status"] != "FETCHED" or p["return_code"] != 0:
            raise ValueError(f"successful exact {name} native table required")
        return p["rows"], fact["capture_payload_ref"]

    def metadata(name, fields):
        source = facts[name + ":metadata"]
        m = decode_table_field_metadata(source["payload"]["raw_response"], table_name=name)
        if m.return_code != 0 or len(set(m.field_keys)) != len(m.field_keys):
            raise ValueError("successful unique native metadata required")
        for key, unit in fields.items():
            if m.field_metadata(key)["UnitsString"] != unit:
                raise ValueError(f"{name}:{key}: source field unit mismatch")
        return m, source["capture_payload_ref"]

    periods, period_ref = table("Modal Periods And Frequencies", "@Modal")
    _, period_metadata_ref = metadata("Modal Periods And Frequencies", {
        "Period": "sec", "Frequency": "cyc/sec", "CircFreq": "rad/sec", "Eigenvalue": "rad2/sec2"})
    by_mode = {}
    for row in periods:
        number = float(row["Mode"])
        if row["Case"] != "Modal" or not math.isfinite(number) or int(number) != number or int(number) not in MODES:
            raise ValueError("exact native Modal period mode required")
        n = int(number)
        if n in by_mode:
            raise ValueError("duplicate native period mode")
        if any(not math.isfinite(float(row[f])) or float(row[f]) <= 0 for f in ("Period", "Frequency", "CircFreq", "Eigenvalue")):
            raise ValueError("positive finite source period/frequency/eigenvalue required")
        by_mode[n] = row
    if set(by_mode) != set(MODES):
        raise ValueError("complete native 100-mode period population required")

    case_rows, case_ref = table("Load Case Definitions - Response Spectrum")
    case_metadata, case_metadata_ref = metadata("Load Case Definitions - Response Spectrum", {
        "ModalCombo": "", "DirCombo": "", "RigidResp": ""})
    for field in ("ModalCombo", "DirCombo", "RigidResp"):
        if not case_metadata.field_metadata(field)["Description"]:
            raise ValueError("native named case-setting definitions required")
    signatures = {}
    shear_rows, shear_ref = table("Story Forces", "@Modal")
    shear_metadata, shear_metadata_ref = metadata("Story Forces", {"VX": "kN", "VY": "kN"})
    operands = {}
    for case, amps in amplitudes.items():
        matches = [row for row in case_rows if row["Name"] == case]
        if len(matches) != 1:
            raise ValueError("exact unique native response-spectrum case row required")
        definition = matches[0]
        source = facts[case + ":settings"]
        native = source["payload"]["settings"]
        settings = {s["method"]: s for s in native}
        if len(settings) != len(native):
            raise ValueError("duplicate native getter setting")
        required = ("GetLoads", "GetModalCase", "GetModalComb_1", "GetDampConstant", "GetDampOverrides")
        if any(settings[m]["return_code"] != 0 for m in required):
            raise ValueError("successful exact native case and damping getters required")
        loads = dict(settings["GetLoads"]["outputs"])
        if (loads["CSys"] != ["Global"] or loads["Ang"] != [0.0]
                or loads["LoadName"] != [amps[0].binding.source_direction]
                or definition["CoordSys"] != "Global" or float(definition["Angle"]) != 0
                or definition["LoadName"] != amps[0].binding.source_direction
                or definition["ModalCase"] != amps[0].binding.modal_case
                or definition["ModalCombo"] != "CQC" or definition["DirCombo"] != "SRSS"
                or definition["RigidResp"] != "No"):
            raise ValueError("source-exact single Global/zero-angle CQC/SRSS/all-periodic case required")
        comb = dict(settings["GetModalComb_1"]["outputs"])
        if comb["F2"] != 0.0:
            raise ValueError("unsupported rigid response; exact native F2=0 required")
        damp = dict(settings["GetDampConstant"]["outputs"])["Damp"]
        overrides = dict(settings["GetDampOverrides"]["outputs"])
        if (damp != 0.05 or overrides != {"NumberItems": 0, "Mode": [], "Damp": []}):
            raise ValueError("accepted case-damping observation changed")
        # Named native table labels establish methods. Retain getter codes
        # untouched; no undocumented MyType/DampType integer mapping.
        signatures[case] = {"native_case_row": definition, "native_getters": native,
            "case_damping_observation": damp, "total_modal_damping": "NOT_CAPTURED",
            "periodic_branch": "SOURCE_PROVEN_F2_ZERO_AND_NATIVE_RIGIDRESP_NO",
            "source_refs": [case_ref, case_metadata_ref, source["capture_payload_ref"]]}
        shears = qualify_native_modal_story_shear(shear_rows, story="+0.00", amplitudes=amps,
            expected_modes=MODES, metadata=shear_metadata, raw_response_ref=shear_ref)
        rows = []
        for a, shear, r in zip(amps, shears, physical["signed_modal_r"][case]):
            period = by_mode[a.mode]
            if float(period["Period"]) != a.period_s or r["mode"] != a.mode:
                raise ValueError("same mode/native period required for every physical operand")
            rows.append({"mode": a.mode, "R_kN_per_m": r["r_force_per_length"],
                "Delta_global_m": None, "V_kN": native_modal_scalar_contribution(amplitude=a, response=shear),
                "period_s": a.period_s, "frequency_hz": float(period["Frequency"]),
                "native_period_frequency_row": period, "total_damping_ratio": None,
                "case_damping_observation": damp, "native_amplitude": asdict(a),
                "physical_grain_refs": [shear.physical_grain_ref, "COMPLETE_86_PHYSICAL_COLUMN_BOTTOMS_AXIS_TO_AXIS"],
                "source_refs": [*r["source_refs"], *shear.raw_response_refs, shear_metadata_ref,
                    period_ref, period_metadata_ref, *signatures[case]["source_refs"]]})
        operands[case] = rows

    points = {g[k] for g in physical["physical_columns"].values() for k in ("joint_bottom", "joint_top")}
    observed = {k.removeprefix("Modal:JointDispl:") for k in facts if k.startswith("Modal:JointDispl:")}
    if points != observed or len(points) != 172:
        raise ValueError("complete exact 172 physical endpoint identities required")
    endpoints = {}
    for point in sorted(points):
        source = facts["Modal:JointDispl:" + point]
        p = source["payload"]
        fact = JointDisplacementResultFact(p["point_object"], p["output_name"], p["output_kind"],
            tuple(JointDisplacementResultRow(**row) for row in p["rows"]), p["return_code"],
            p["source_api"], p["item_type_elm"], tuple(p["state_diagnostics"]))
        endpoints[point] = qualify_native_modal_endpoint_rows(point, fact, modal_case="Modal",
            expected_modes=MODES, length_unit=receipt["native_result_units"]["JointDispl"],
            raw_response_ref=source["capture_payload_ref"])
    pairs = {}
    for uid, g in physical["physical_columns"].items():
        bottom, top = g["joint_bottom"], g["joint_top"]
        pairs[uid] = [{"mode": n, "bottom_point": bottom, "top_point": top,
            "bottom_point_local_u_m": [row.u1, row.u2, row.u3],
            "top_point_local_u_m": [endpoints[top][n-1].u1, endpoints[top][n-1].u2, endpoints[top][n-1].u3],
            "source_refs": [facts["Modal:JointDispl:" + bottom]["capture_payload_ref"],
                facts["Modal:JointDispl:" + top]["capture_payload_ref"], *g["source_refs"]]}
            for n, row in enumerate(endpoints[bottom], 1)]
    return {"status": "R3G_PARTIAL_SOURCE_PERIODIC_CQC_IMPLEMENTED_V_BOUND_DELTA_AND_TOTAL_DAMPING_BLOCKED",
        "input_receipt_sha256": ACCEPTED_RECEIPT_SHA256, "case_signatures": signatures,
        "modal_operands": operands, "native_endpoint_pairs": pairs,
        "physical_endpoint_rows": 17200, "physical_column_mode_pairs": 8600,
        "V_physical_binding": "PROVEN_EXACT_NATIVE_GLOBAL_BOTTOM_CUT", "V_modes_per_case": 100,
        "Delta_physical_binding": "BLOCKED_POINT_LOCAL_TO_GLOBAL_AXES_NOT_CAPTURED",
        "Delta_story_operator": "EXISTING_COMPLETE_POPULATION_COMMON_TRANSLATION_ONLY; NO MAXIMUM_OR_AVERAGE",
        "Delta_modes_formed": 0,
        "CQC": "BLOCKED_TOTAL_PER_MODE_MATERIAL_AND_LINK_SUPPORT_DAMPING_NOT_CAPTURED",
        "CQC_source_authorities": [CSI_PERIODIC_CQC_SOURCE, WILSON_PERIODIC_CQC_SOURCE],
        "CQC_matrix_issued": False, "RSX_R_CQC": None, "RSY_R_CQC": None,
        "frequency_precision": "Native reported decimals retained; no unrounded ETABS internal frequency claim",
        "additional_spectrum_scale_factor_applied": False,
        "factual_capture_binding": receipt["factual_capture_binding"],
        "current_b5_qualified": False, "stability_promotion": False,
        "joint_delta_r_v_statistic": "PROJECT_DECISION_REQUIRED", "R2_RERUN_READY": False,
        "ETABS_EXECUTED": False, "source_model_mutated": False}


def reconcile_exact_receipt(path):
    data = Path(path).read_bytes()
    if hashlib.sha256(data).hexdigest() != ACCEPTED_RECEIPT_SHA256:
        raise ValueError("exact accepted R3D receipt SHA256 required")
    return reconcile_receipt_modal_operands(json.loads(data))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.is_relative_to(REPO_ROOT) or not output.parent.is_dir():
        raise ValueError("new output outside repository required")
    result = reconcile_exact_receipt(args.receipt)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({k: result[k] for k in ("status", "V_modes_per_case", "Delta_modes_formed", "CQC", "R2_RERUN_READY")}))


if __name__ == "__main__":
    raise SystemExit(main())
