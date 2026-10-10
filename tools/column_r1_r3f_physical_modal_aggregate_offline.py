"""Exact accepted FC09 receipt -> signed physical modal R, offline only.

No CQC, result issuer, concurrent state, stability decision or live session.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
for path in (REPO_ROOT, REPO_ROOT / "packages" / "etabs_gateway" / "src"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from tools.column_r1_r3e_modal_normalization_offline import (
    ACCEPTED_RECEIPT_SHA256, TABLE as AMPLITUDE_TABLE, bind_receipt_amplitudes,
)
from tbdy_engine.features.column_shear_topology import (
    PointTopologyEvidence, resolve_column_physical_endpoints,
)
from tbdy_engine.etabs.oapi.database_tables import decode_table_field_metadata
from tbdy_engine.etabs.oapi.eq713_response_results import FrameForceResponseFact, FrameForceResponseRow
from tbdy_engine.providers.etabs_story_stability_result_provider import qualify_native_modal_physical_bottom_rows
from tbdy_engine.analysis_basis.eq713_response_mechanics import (
    NativeModalColumnAxial, aggregate_native_modal_column_axial,
    qualify_ts500_eq713_axis_to_axis_length, TS500_EQ713_AXIS_TO_AXIS_LENGTH_SOURCE,
)


def reconcile_receipt_modal_axial(receipt):
    amplitudes = bind_receipt_amplitudes(receipt)
    facts = receipt["facts"]
    def table(key, fields):
        f = facts[key]
        m = facts[key + ":metadata"]
        metadata = decode_table_field_metadata(m["payload"]["raw_response"], table_name=key)
        for name, unit in fields.items():
            definition = metadata.field_metadata(name)
            if definition["UnitsString"] != unit or not definition["Description"]:
                raise ValueError(f"{key}:{name}: exact native geometry metadata required")
        parsed = f["payload"]["parsed"]
        if parsed["fetch_status"] != "FETCHED" or parsed["return_code"] != 0:
            raise ValueError(f"{key}: successful native source table required")
        return parsed["rows"], (f["capture_payload_ref"], m["capture_payload_ref"])
    column_rows, column_refs = table("Column Object Connectivity", {"Length": "m"})
    point_rows, point_refs = table("Point Object Connectivity", {"X": "m", "Y": "m", "Z": "m"})
    if receipt["representative_story"] != "+0.00":
        raise ValueError("accepted +0.00 representative scope required")
    columns = [c for c in column_rows if c["Story"] == "+0.00"]
    names = [c["UniqueName"] for c in columns]
    force_names = {k.removeprefix("Modal:FrameForce:") for k in facts if k.startswith("Modal:FrameForce:")}
    if len(names) != 86 or len(set(names)) != 86 or set(names) != force_names:
        raise ValueError("exact complete 86-Column force/connectivity denominator required")
    needed_points = {c[k] for c in columns for k in ("UniquePtI", "UniquePtJ")}
    if len(needed_points) != 172:
        raise ValueError("exact 172 physical endpoint denominator required")
    points = {}
    for row in point_rows:
        uid = row["UniqueName"]
        if uid not in needed_points:
            continue
        if uid in points:
            raise ValueError("duplicate physical endpoint identity")
        points[uid] = PointTopologyEvidence(uid, row["Story"], row["X"], row["Y"], row["Z"], row)
    if set(points) != needed_points:
        raise ValueError("missing physical endpoint source")
    physical, bottom_rows, raw_refs, lengths = {}, {}, {}, {}
    expected_modes = tuple(range(1, 101))
    for c in columns:
        uid = c["UniqueName"]
        geometry = resolve_column_physical_endpoints(c, points=points,
            source_refs=(*column_refs, *point_refs), reviewed_length_unit="m")
        length = qualify_ts500_eq713_axis_to_axis_length(geometry, source_length_unit="m")
        source = facts["Modal:FrameForce:" + uid]
        p = source["payload"]
        fact = FrameForceResponseFact(p["frame_name"], p["case_name"],
            tuple(FrameForceResponseRow(**r) for r in p["rows"]), p["return_code"],
            p["source_api"], tuple(p["state_diagnostics"]))
        bottom_rows[uid] = qualify_native_modal_physical_bottom_rows(geometry, fact,
            modal_case="Modal", expected_modes=expected_modes, raw_response_ref=source["capture_payload_ref"],
            force_unit=receipt["native_result_units"]["FrameForce"],
            length_unit=receipt["native_result_units"]["JointDispl"])
        physical[uid], lengths[uid], raw_refs[uid] = geometry, length, source["capture_payload_ref"]
    result = {}
    for case, modes in amplitudes.items():
        aggregates = []
        for a in modes:
            rows = tuple(NativeModalColumnAxial(uid, a.mode, bottom_rows[uid][a.mode-1].p,
                lengths[uid], a.binding, "kN", "m", "Mode", "PHYSICAL_BOTTOM", raw_refs[uid],
                TS500_EQ713_AXIS_TO_AXIS_LENGTH_SOURCE + "|" + "|".join(physical[uid].source_refs))
                for uid in sorted(names))
            aggregates.append(asdict(aggregate_native_modal_column_axial(amplitude=a, columns=rows,
                expected_complete_story_columns=sorted(names))))
        result[case] = aggregates
    return {
        "status": "FACTUAL_SIGNED_MODAL_R_COMPLETE_PENDING_CQC_CURRENT_B5_AND_JOINT_RULE",
        "physical_bottom_binding": "PROVEN_EXACT_NATIVE_OBJECT_ENDPOINT",
        "column_denominator": 86, "mode_denominator": 100,
        "native_physical_bottom_rows": sum(len(v) for v in bottom_rows.values()),
        "length_authority": TS500_EQ713_AXIS_TO_AXIS_LENGTH_SOURCE,
        "length_basis": "AXIS_TO_AXIS; end offsets not assumed zero or subtracted",
        "lengths_m": lengths,
        "physical_columns": {uid: {"joint_bottom": g.bottom.unique_name, "joint_top": g.top.unique_name,
            "bottom_coord_m": g.bottom.coord_m, "top_coord_m": g.top.coord_m,
            "object_length_m": g.object_length_m, "coordinate_length_m": g.coordinate_length_m,
            "element_name": bottom_rows[uid][0].element_name,
            "object_station": bottom_rows[uid][0].object_station,
            "element_station": bottom_rows[uid][0].element_station,
            "source_refs": [*g.source_refs, raw_refs[uid]]} for uid,g in physical.items()},
        "signed_modal_r": result, "r_response_unit": "kN/m",
        "native_amplitudes": {case: [asdict(a) for a in modes] for case, modes in amplitudes.items()},
        "native_amplitude_metadata_capture_payload_ref": facts[AMPLITUDE_TABLE + ":metadata"]["capture_payload_ref"],
        "normalization": "CSI native coordinate-to-physical-response map; native Amp metadata=m retained",
        "additional_scale_factor_applied": False,
        "factual_capture_binding": receipt["factual_capture_binding"],
        "current_b5_qualified": False, "stability_promotion": False, "CQC": "NOT_PERFORMED",
        "joint_delta_r_v_statistic": "PROJECT_DECISION_REQUIRED", "R2_RERUN_READY": False,
        "ETABS_EXECUTED": False, "source_model_mutated": False,
    }


def reconcile_exact_receipt(path):
    data = Path(path).read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != ACCEPTED_RECEIPT_SHA256:
        raise ValueError("exact accepted R3D receipt SHA256 required")
    result = reconcile_receipt_modal_axial(json.loads(data))
    result["input_receipt_sha256"] = digest
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.is_relative_to(REPO_ROOT) or not output.parent.is_dir():
        raise ValueError("new reconciliation output outside repository required")
    result = reconcile_exact_receipt(args.receipt)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({k:result[k] for k in ("status", "native_physical_bottom_rows", "R2_RERUN_READY")}))


if __name__ == "__main__":
    raise SystemExit(main())
