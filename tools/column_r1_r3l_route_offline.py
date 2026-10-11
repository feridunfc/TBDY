"""Offline evidence adoption and prospective row identity audit; no ETABS access.

This tool never qualifies a global result, performs displacement arithmetic,
or accepts a presentation convention as a DatabaseTables coordinate contract.
Synthetic audits test rejection laws only; they are not native observations.
"""
from __future__ import annotations

import argparse
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
for directory in (REPO_ROOT, REPO_ROOT / "packages" / "etabs_gateway" / "src"):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

from tbdy_engine.etabs.oapi.database_tables import (
    FIELD_METADATA_ABI_REF, FIELD_METADATA_OUTPUT_ORDER, decode_table_field_metadata,
)

P1_NAME = "column-r1-r3k-schema_20261011_130341_474.json"
P1_SHA = "ff0aef659643b6d30954f5c6289efcf896666ba0fe6e6358179fad63c6707eb4"
P1_SIDECAR_SHA = "d9a92ad4d38a36a386869f015250fb6e199a5d9d779901d1692da106b395b801"
R3K_HEAD = "ab16c693c887ca383603ef3c372a098e05272706"
R3K_TREE = "a1f54bf3eb600b6929584fcf8483132b1448a51f"
SOURCE = r"C:\tmp\B-BLOK_Revised.EDB"
SOURCE_SHA = "FC09E5EEB1E195C7141EB992EC501E0004EA733078997C58E1F84D979F70758F"
TABLE = "Joint Displacements"
# These are accepted P1 observations, not guessed native keys or basis semantics.
FIELDS = ("Story", "Label", "UniqueName", "OutputCase", "CaseType", "StepType",
          "StepNumber", "StepLabel", "Ux", "Uy", "Uz", "Rx", "Ry", "Rz")
R3D_SHA = "83ce2ff7c3a6170e931d2869e212adde93b7c08b25bbf44e9f0c2c663f156b03"


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
        allow_nan=False, separators=(",", ":")).encode("utf-8")).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate_receipt_structure(receipt):
    """Validate duplicated receipt facts against immutable raw metadata and anchors.

    This pure structural check does not authenticate native origin. Only adoption
    below accepts the supervisor-pinned original byte hash and original sidecar.
    """
    r = receipt
    require(r["repository"] == {"HEAD": R3K_HEAD, "TREE": R3K_TREE,
        "worktree_status": ""}, "HEAD/TREE binding")
    require(r["source_path"] == SOURCE and r["pid"] == 2072, "source/PID binding")
    require(r["table_key"] == TABLE and r["errors"] == [], "table/native errors")
    require(r["status"] == "SCHEMA_DISCOVERY_COMPLETE_SOURCE_SEMANTICS_NOT_QUALIFIED"
        and r["result_rows_acquired"] == 0 and r["engineering_interpretation"] is False,
        "schema-only scope")
    require(r["GETALLFIELDS_ABI"] == {"output_order": list(FIELD_METADATA_OUTPUT_ORDER),
        "authority_ref": FIELD_METADATA_ABI_REF}, "native ABI authority")
    for key in ("source_sha256_expected", "source_sha256_before", "source_sha256_after"):
        require(r[key] == SOURCE_SHA, "protected source drift")
    require(r["source_unchanged"] is True and r["session_units_unchanged"] is True,
        "source/session unchanged flags")
    before, after = r["identity_before"], r["identity_after"]
    require(before == after, "session/unit/lock drift")
    for phase, identity in (("before", before), ("after", after)):
        require(canonical_hash(identity) == r["identity_" + phase + "_sha256"],
            "identity digest")
    require(before["process_id"] == 2072 and before["model_full_path"] == SOURCE
        and before["attach_strategy"] == "comtypes_create_helper_get_object_process"
        and before["program_name"] == "ETABS" and before["program_version"] == "23.2.0"
        and before["program_api_version"] == 2.014 and before["model_locked"] is True,
        "native session identity")
    units = before["units"]
    require(units["present_observation_status"] == units["database_observation_status"]
        == "OBSERVED_CONSISTENT" and units["diagnostics"] == [], "unit observation")
    for prefix in ("present", "database"):
        require(units[prefix + "_units"] == 6 and
            [units[prefix + "_" + name + "_unit"] for name in ("force", "length", "temperature")]
            == [4, 6, 2], "accepted native units")
    require(units["raw_unit_reads"] == {"GetDatabaseUnits": "6",
        "GetDatabaseUnits_2": "[4, 6, 2, 0]", "GetPresentUnits": "6",
        "GetPresentUnits_2": "[4, 6, 2, 0]"}, "native unit ABI/return codes")
    hashes = {}
    for getter in ("GetAvailableTables", "GetAllFieldsInTable"):
        fact = r["facts"][getter]; payload = fact["payload"]
        digest = canonical_hash(payload["raw_response"])
        require(digest == fact["raw_response_sha256"], "raw getter digest")
        require(payload["source_model_ref"] == SOURCE and
            payload["session_ref"] == "etabs-session:pid:2072" and
            payload["capture_ref"] == r["capture_ref"], "getter source/session/capture drift")
        hashes[getter] = digest
    availability = r["facts"]["GetAvailableTables"]["payload"]
    require(availability["status"] == r["NATIVE_TABLE_AVAILABILITY"] ==
        "NOT_OBSERVED:AVAILABLE_TABLES_NATIVE_ABI_UNAVAILABLE" and
        availability["raw_response"] == [] and availability["return_code"] is None and
        availability["number_tables"] is None and availability["table_keys"] == [],
        "unobserved availability cannot be absence")
    payload = r["facts"]["GetAllFieldsInTable"]["payload"]
    require(payload["table_name"] == TABLE, "wrong metadata table")
    metadata = decode_table_field_metadata(payload["raw_response"], table_name=TABLE)
    require(metadata.status == "PARSED_EXACT_FIELD_METADATA" and metadata.return_code == 0,
        "malformed/unsuccessful native metadata")
    require(metadata.table_version == r["table_version"] == 1 and
        metadata.number_fields == 14 and metadata.field_keys == FIELDS, "accepted field identity")
    for name in ("status", "table_version", "number_fields", "field_keys", "field_names",
                 "descriptions", "units_strings", "is_importable", "return_code"):
        expected = getattr(metadata, name)
        if isinstance(expected, tuple):
            expected = list(expected)
        require(payload[name] == expected, "inconsistent decoded metadata: " + name)
    definitions = [dict(metadata.field_metadata(key)) for key in FIELDS]
    require(r["fields"] == definitions, "inconsistent field definitions")
    require(tuple(metadata.units_strings) == ("",) * 8 + ("m",) * 3 + ("rad",) * 3,
        "accepted native field units")
    require(all(metadata.descriptions), "missing field description")
    return {"schema_structure": "VALIDATED_UNAUTHENTICATED", "SCHEMA_FIELD_COUNT": 14,
        "field_keys": list(FIELDS), "table_version": 1, "return_code": 0,
        "native_table_availability": availability["status"],
        "GetAvailableTables_native_call_observed": False,
        "raw_response_hashes": hashes, "identity_sha256": canonical_hash(before),
        "units_sha256": canonical_hash(units),
        "field_definition_sha256": {d["FieldKey"]: canonical_hash(d) for d in definitions},
        "source_sha256_before": r["source_sha256_before"],
        "source_sha256_after": r["source_sha256_after"],
        "repository": r["repository"], "pid": 2072, "capture_ref": r["capture_ref"],
        "source_path": SOURCE, "program_version": "23.2.0", "program_api_version": 2.014,
        "native_translation_unit": "m", "native_rotation_unit": "rad",
        "result_rows_acquired": 0, "global_qualification": "BLOCKED"}


def adopt_original(receipt_path, sidecar_path):
    path, sidecar = Path(receipt_path), Path(sidecar_path)
    require(path.name == P1_NAME and sidecar.name == P1_NAME + ".sha256", "original filenames")
    raw, side_raw = path.read_bytes(), sidecar.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == P1_SHA, "supervisor-pinned whole JSON SHA256")
    require(hashlib.sha256(side_raw).hexdigest() == P1_SIDECAR_SHA, "original sidecar byte identity")
    require(side_raw.decode("utf-8").split() == [P1_SHA, P1_NAME], "original SHA sidecar")
    result = validate_receipt_structure(json.loads(raw))
    require(path.read_bytes() == raw and sidecar.read_bytes() == side_raw, "original file drift")
    return {"receipt_name": P1_NAME, "receipt_sha256": P1_SHA, "NATIVE_SCHEMA": "CLOSED",
        "sidecar_sha256": hashlib.sha256(side_raw).hexdigest(), **result,
        "schema_structure": "VALIDATED_AUTHENTICATED_ORIGINAL"}


def mode_identity(row, *, output_case, case_type_token):
    """Prospective identity check. CaseType token must be separately source-qualified.

    StepType Mode alone also matches buckling; the output-case/type checks are
    mandatory. A caller-provided token is an audit input, never CSI authority.
    """
    require(type(case_type_token) is str and bool(case_type_token.strip()), "CaseType authority missing")
    require(row["OutputCase"] == output_case and row["CaseType"] == case_type_token,
        "wrong output case/type")
    require(row["StepType"] == "Mode" and row.get("StepLabel") == "", "wrong modal step identity")
    value = row["StepNumber"]
    require(type(value) in (str, int, float), "invalid mode type")
    try:
        number = Decimal(str(value))
        require(number.is_finite() and number == number.to_integral_value() and 1 <= number <= 100,
            "nonintegral/out-of-range mode")
    except InvalidOperation as exc:
        raise ValueError("invalid native mode") from exc
    return int(number)


def audit_endpoint_rows(rows, endpoints, *, output_case, case_type_token):
    """Identity-only offline audit; duplicates block even when values are equal."""
    require(bool(endpoints), "empty endpoint denominator")
    require(len({p["UniqueName"] for p in endpoints}) == len(endpoints), "duplicate endpoint mapping")
    stories = {p["UniqueName"]: p["Story"] for p in endpoints}
    require(all(type(k) is str and k and type(v) is str and v for k, v in stories.items()),
        "missing exact endpoint identity/story")
    seen = set()
    for row in rows:
        uid = row["UniqueName"]
        require(uid in stories and row["Story"] == stories[uid], "wrong endpoint/story")
        mode = mode_identity(row, output_case=output_case, case_type_token=case_type_token)
        key = (row["Story"], uid, row["OutputCase"], row["CaseType"], row["StepType"], mode)
        require(key not in seen, "duplicate endpoint/mode row")
        seen.add(key)
    require(len(seen) == len(endpoints) * 100, "missing endpoint/mode coverage")
    return {"identity_coverage": "COMPLETE_OFFLINE_AUDIT_ONLY",
        "rows_audited": len(seen), "global_qualification": "BLOCKED"}


def audit_panel_binding(evidence):
    """Reject unresolved generated-joint choices; this is no production qualifier."""
    require(evidence.get("assignment_authority_ref") and evidence.get("joint_authority_ref"),
        "panel-zone assignment/analysis-joint authority missing")
    require(evidence.get("assignment_state") in ("ABSENT_PROVEN", "COLUMN_CONNECTED_PROVEN"),
        "panel-zone applicability ambiguous")
    require(type(evidence.get("analysis_elements")) is list and
        len(evidence["analysis_elements"]) == 1 and
        type(evidence["analysis_elements"][0]) is str and bool(evidence["analysis_elements"][0]),
        "analysis-joint mapping ambiguous")
    require(evidence.get("table_row_element") == evidence["analysis_elements"][0],
        "table/column-connected analysis-joint mismatch")
    return "IDENTITY_AUDIT_ONLY_NOT_GLOBAL_QUALIFICATION"


def route_disposition(schema_index, **presentation_or_field_claims):
    """Current authority disposition cannot be promoted by arbitrary caller claims."""
    require(schema_index.get("NATIVE_SCHEMA") == "CLOSED" and
        schema_index.get("receipt_sha256") == P1_SHA, "accepted schema adoption required")
    return {"GLOBAL_COORDINATE_CONTRACT": "BLOCKED",
        "MODAL_FIELD_SEMANTICS": "PROVEN_ACCEPTED_NATIVE_DESCRIPTIONS",
        "MODAL_RESULT_GRAIN_CONTRACT": "BLOCKED",
        "PHYSICAL_POINT_BINDING": "BLOCKED", "PANEL_ZONE_APPLICABILITY": "BLOCKED",
        "P2_CAPTURE_PLAN": "PREPARED_BLOCKED_NOT_AUTHORIZABLE",
        "P2_EXECUTION_AUTHORIZED": False, "GLOBAL_ENDPOINT_MODAL_ROWS": 0,
        "GLOBAL_STORY_DELTA": "NOT_PROVEN"}


def derive_physical_plan(receipt_path):
    """Reuse original R3D object topology; expose no displacement components."""
    from tbdy_engine.features.column_shear_topology import (
        PointTopologyEvidence, resolve_column_physical_endpoints,
    )
    raw = Path(receipt_path).read_bytes()
    require(hashlib.sha256(raw).hexdigest() == R3D_SHA, "accepted R3D original hash")
    receipt = json.loads(raw)
    require(receipt["source_sha256_before"] == receipt["source_sha256_after"] == SOURCE_SHA,
        "R3D protected source binding")
    facts = receipt["facts"]
    def topology_table(key):
        parsed = facts[key]["payload"]["parsed"]
        require(parsed["return_code"] == 0 and parsed["fetch_status"] == "FETCHED",
            "native topology table")
        return parsed["rows"], facts[key]["capture_payload_ref"]
    column_rows, column_ref = topology_table("Column Object Connectivity")
    point_rows, point_ref = topology_table("Point Object Connectivity")
    columns = [c for c in column_rows if c["Story"] == "+0.00"]
    require(columns == receipt["story_columns"] and len(columns) == 86 and
        len({c["UniqueName"] for c in columns}) == 86, "accepted 86 physical Columns")
    needed = {c[k] for c in columns for k in ("UniquePtI", "UniquePtJ")}
    require(len(needed) == 172, "accepted 172 distinct endpoint objects")
    points = {}
    for p in point_rows:
        uid = p["UniqueName"]
        if uid not in needed:
            continue
        require(uid not in points, "duplicate endpoint topology mapping")
        points[uid] = PointTopologyEvidence(uid, p["Story"], p["X"], p["Y"], p["Z"], p)
    require(set(points) == needed, "missing endpoint topology mapping")
    plan, local_count = [], 0
    for c in sorted(columns, key=lambda row: row["UniqueName"]):
        geometry = resolve_column_physical_endpoints(c, points=points,
            source_refs=(column_ref, point_ref), reviewed_length_unit="m")
        endpoints = {}
        for side, point in (("bottom", geometry.bottom), ("top", geometry.top)):
            rows = facts["Modal:JointDispl:" + point.unique_name]["payload"]["rows"]
            require(len(rows) == 100 and {r["step_number"] for r in rows} == set(range(1, 101))
                and all(r["point_object"] == point.unique_name and r["load_case"] == "Modal"
                    and r["step_type"] == "Mode" for r in rows), "accepted local modal identities")
            elements = sorted({r["element_name"] for r in rows})
            require(len(elements) == 1, "accepted local analysis-point identity ambiguity")
            local_count += len(rows)
            endpoints[side] = {"UniqueName": point.unique_name, "object_story": point.story,
                "retained_local_Elm": elements[0]}
        plan.append({"column_unique_name": c["UniqueName"], "column_story": c["Story"], **endpoints})
    require(local_count == 17200, "accepted local modal denominator")
    return {"R3D_original_sha256": R3D_SHA, "columns": plan,
        "column_count": 86, "endpoint_count": 172, "modes": [1, 100],
        "existing_local_modal_rows": local_count, "expected_endpoint_pairs": 8600,
        "physical_plan_sha256": canonical_hash(plan),
        "point_topology_ref": point_ref, "column_topology_ref": column_ref,
        "table_result_element_binding": "BLOCKED_NOT_OBSERVED",
        "global_endpoint_modal_rows": 0, "PHYSICAL_POINT_BINDING": "BLOCKED",
        "PANEL_ZONE_APPLICABILITY": "BLOCKED"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", required=True, type=Path)
    parser.add_argument("--sidecar", required=True, type=Path)
    parser.add_argument("--physical-receipt", type=Path)
    args = parser.parse_args(argv)
    adopted = adopt_original(args.receipt, args.sidecar)
    result = {**adopted, "route": route_disposition(adopted)}
    if args.physical_receipt is not None:
        result["physical_plan"] = derive_physical_plan(args.physical_receipt)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
