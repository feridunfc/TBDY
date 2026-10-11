"""Synthetic offline rejection laws; no manufactured original native receipt."""
import ast
from copy import deepcopy
import inspect
import json

import pytest

from tools import column_r1_r3l_route_offline as tool


def synthetic_receipt():
    """Untrusted synthetic structure deliberately lacking original P1 byte identity."""
    units = {"present_units": 6, "database_units": 6,
        "present_observation_status": "OBSERVED_CONSISTENT",
        "database_observation_status": "OBSERVED_CONSISTENT", "diagnostics": [],
        "raw_unit_reads": {"GetPresentUnits": "6", "GetDatabaseUnits": "6",
            "GetPresentUnits_2": "[4, 6, 2, 0]", "GetDatabaseUnits_2": "[4, 6, 2, 0]"}}
    for prefix in ("present", "database"):
        for name, value in zip(("force", "length", "temperature"), (4, 6, 2)):
            units[prefix + "_" + name + "_unit"] = value
    identity = {"process_id": 2072, "model_full_path": tool.SOURCE,
        "attach_strategy": "comtypes_create_helper_get_object_process", "program_name": "ETABS",
        "program_version": "23.2.0", "program_api_version": 2.014,
        "model_locked": True, "units": units}
    raw = [1, 14, list(tool.FIELDS), list(tool.FIELDS),
        ["SYNTHETIC description " + key for key in tool.FIELDS],
        [""] * 8 + ["m"] * 3 + ["rad"] * 3, [False] * 14, 0]
    fields = [dict(zip(("FieldKey", "FieldName", "Description", "UnitsString", "IsImportable"),
        (raw[2][i], raw[3][i], raw[4][i], raw[5][i], raw[6][i]))) for i in range(14)]
    meta = dict(zip(("table_version", "number_fields", "field_keys", "field_names",
        "descriptions", "units_strings", "is_importable", "return_code"), raw))
    meta.update(table_name=tool.TABLE, status="PARSED_EXACT_FIELD_METADATA", raw_response=raw)
    available = {"status": "NOT_OBSERVED:AVAILABLE_TABLES_NATIVE_ABI_UNAVAILABLE",
        "raw_response": [], "return_code": None, "number_tables": None, "table_keys": []}
    facts = {}
    for getter, payload in (("GetAllFieldsInTable", meta), ("GetAvailableTables", available)):
        payload.update(source_model_ref=tool.SOURCE, session_ref="etabs-session:pid:2072",
            capture_ref="SYNTHETIC-ONLY")
        facts[getter] = {"payload": payload, "raw_response_sha256": tool.canonical_hash(payload["raw_response"])}
    return {"repository": {"HEAD": tool.R3K_HEAD, "TREE": tool.R3K_TREE, "worktree_status": ""},
        "source_path": tool.SOURCE, "pid": 2072, "table_key": tool.TABLE, "errors": [],
        "status": "SCHEMA_DISCOVERY_COMPLETE_SOURCE_SEMANTICS_NOT_QUALIFIED",
        "result_rows_acquired": 0, "engineering_interpretation": False,
        "GETALLFIELDS_ABI": {"output_order": list(tool.FIELD_METADATA_OUTPUT_ORDER),
            "authority_ref": tool.FIELD_METADATA_ABI_REF},
        "source_sha256_expected": tool.SOURCE_SHA, "source_sha256_before": tool.SOURCE_SHA,
        "source_sha256_after": tool.SOURCE_SHA, "source_unchanged": True,
        "session_units_unchanged": True, "identity_before": identity,
        "identity_after": deepcopy(identity), "identity_before_sha256": tool.canonical_hash(identity),
        "identity_after_sha256": tool.canonical_hash(identity), "capture_ref": "SYNTHETIC-ONLY",
        "NATIVE_TABLE_AVAILABILITY": available["status"], "facts": facts,
        "fields": fields, "table_version": 1}


def test_structural_schema_audit_has_14_unique_keys_and_no_global_qualification():
    result = tool.validate_receipt_structure(synthetic_receipt())
    assert len(set(result["field_keys"])) == result["SCHEMA_FIELD_COUNT"] == 14
    assert result["global_qualification"] == "BLOCKED"
    assert result["GetAvailableTables_native_call_observed"] is False
    assert result["native_table_availability"].startswith("NOT_OBSERVED")
    assert "NATIVE_SCHEMA" not in result


def test_unauthenticated_schema_structure_cannot_be_adopted_or_promoted():
    result = tool.validate_receipt_structure(synthetic_receipt())
    with pytest.raises(ValueError, match="adoption required"):
        tool.route_disposition(result)


@pytest.mark.parametrize("section,key,value", [
    (None, "source_sha256_before", "0" * 64), (None, "source_sha256_after", "0" * 64),
    (None, "source_path", "other.edb"), (None, "pid", 2073),
    (None, "source_unchanged", False), (None, "session_units_unchanged", False),
    (None, "result_rows_acquired", 1), (None, "engineering_interpretation", True),
    (None, "table_key", "Joint Displacements - Absolute"), (None, "errors", ["native error"]),
    ("repository", "HEAD", "0" * 40), ("repository", "TREE", "0" * 40),
    ("repository", "worktree_status", "M file.py"),
    ("identity_after", "process_id", 2073), ("identity_after", "model_locked", False),
])
def test_source_session_scope_and_repository_drift_rejected(section, key, value):
    r = synthetic_receipt(); (r if section is None else r[section])[key] = value
    with pytest.raises(ValueError):
        tool.validate_receipt_structure(r)


@pytest.mark.parametrize("defect", ["hash", "return", "shape", "count", "duplicate",
    "units", "description", "decoded", "source", "session", "capture", "ABI"])
def test_native_schema_hash_shape_ambiguity_and_binding_rejected(defect):
    r = synthetic_receipt(); fact = r["facts"]["GetAllFieldsInTable"]; p = fact["payload"]
    if defect == "hash": fact["raw_response_sha256"] = "0" * 64
    elif defect == "return": p["raw_response"][-1] = 1
    elif defect == "shape": p["raw_response"].pop()
    elif defect == "count": p["raw_response"][1] = 13
    elif defect == "duplicate": p["raw_response"][2][1] = "Story"
    elif defect == "units": p["raw_response"][5][8] = "mm"
    elif defect == "description": p["raw_response"][4][0] = ""
    elif defect == "decoded": p["field_names"] = ["wrong"] * 14
    elif defect == "source": p["source_model_ref"] = "other.edb"
    elif defect == "session": p["session_ref"] = "etabs-session:pid:other"
    elif defect == "capture": p["capture_ref"] = "other"
    elif defect == "ABI": r["GETALLFIELDS_ABI"]["output_order"].reverse()
    if defect != "hash": fact["raw_response_sha256"] = tool.canonical_hash(p["raw_response"])
    with pytest.raises(ValueError): tool.validate_receipt_structure(r)


def test_native_unit_drift_even_with_rehashed_identity_rejected():
    r = synthetic_receipt()
    for phase in ("before", "after"):
        r["identity_" + phase]["units"]["present_length_unit"] = 4
        r["identity_" + phase + "_sha256"] = tool.canonical_hash(r["identity_" + phase])
    with pytest.raises(ValueError, match="native units"): tool.validate_receipt_structure(r)


def test_synthetic_receipt_cannot_be_adopted_as_original(tmp_path):
    p = tmp_path / tool.P1_NAME; p.write_text(json.dumps(synthetic_receipt()))
    side = tmp_path / (tool.P1_NAME + ".sha256"); side.write_text(tool.P1_SHA + " " + tool.P1_NAME)
    with pytest.raises(ValueError, match="whole JSON"): tool.adopt_original(p, side)
    assert p.read_text() == json.dumps(synthetic_receipt())


def row(mode=1):
    return {"Story": "upper-story", "UniqueName": "endpoint-top", "OutputCase": "Modal",
        "CaseType": "SYNTHETIC-Modal-token", "StepType": "Mode", "StepNumber": mode, "StepLabel": ""}


@pytest.mark.parametrize("value", [0, 101, -1, 1.5, "NaN", "Infinity", "abc", True, None, ""])
def test_incorrect_mode_number_rejected(value):
    with pytest.raises(ValueError):
        tool.mode_identity(row(value), output_case="Modal", case_type_token="SYNTHETIC-Modal-token")


@pytest.mark.parametrize("key,value", [("StepType", "Max"), ("StepType", "Time"),
    ("StepLabel", "stage-1"), ("OutputCase", "RSX"), ("CaseType", "SYNTHETIC-Buckling")])
def test_mode_label_alone_cannot_admit_wrong_case_grain(key, value):
    r = row(); r[key] = value
    with pytest.raises(ValueError):
        tool.mode_identity(r, output_case="Modal", case_type_token="SYNTHETIC-Modal-token")


def test_integral_native_step_number_is_exact_mode_identity():
    assert tool.mode_identity(row("100.0"), output_case="Modal",
        case_type_token="SYNTHETIC-Modal-token") == 100


@pytest.mark.parametrize("token", [None, "", " "])
def test_missing_case_type_token_cannot_admit_modal_rows(token):
    with pytest.raises(ValueError):
        tool.mode_identity(row(), output_case="Modal", case_type_token=token)


def test_empty_endpoint_denominator_cannot_claim_coverage():
    with pytest.raises(ValueError, match="empty endpoint"):
        tool.audit_endpoint_rows([], [], output_case="Modal", case_type_token="SYNTHETIC-Modal-token")


def two_story_rows():
    endpoints = [{"UniqueName": "endpoint-top", "Story": "upper-story"},
        {"UniqueName": "endpoint-bottom", "Story": "lower-story"}]
    rows = [{**row(mode), **endpoint} for endpoint in endpoints for mode in range(1, 101)]
    return rows, endpoints


def test_two_endpoint_stories_preserved_and_complete_identity_audit_stays_blocked():
    rows, endpoints = two_story_rows()
    result = tool.audit_endpoint_rows(rows, endpoints, output_case="Modal",
        case_type_token="SYNTHETIC-Modal-token")
    assert result["rows_audited"] == 200 and result["global_qualification"] == "BLOCKED"


@pytest.mark.parametrize("defect", ["duplicate-row", "duplicate-endpoint", "wrong-story",
    "nearest-name", "missing-mode", "same-story-filter"])
def test_duplicate_endpoint_mapping_and_coverage_ambiguity_rejected(defect):
    rows, endpoints = two_story_rows()
    if defect == "duplicate-row": rows.append(deepcopy(rows[0]))
    elif defect == "duplicate-endpoint": endpoints.append(deepcopy(endpoints[0]))
    elif defect == "wrong-story": rows[100]["Story"] = "upper-story"
    elif defect == "nearest-name": rows[0]["UniqueName"] = "coincident-unmapped-point"
    elif defect == "missing-mode": rows.pop()
    elif defect == "same-story-filter": rows = rows[:100]
    with pytest.raises(ValueError): tool.audit_endpoint_rows(rows, endpoints, output_case="Modal",
        case_type_token="SYNTHETIC-Modal-token")


def panel_evidence():
    return {"assignment_authority_ref": "SYNTHETIC-assignment", "joint_authority_ref": "SYNTHETIC-joint",
        "assignment_state": "COLUMN_CONNECTED_PROVEN", "analysis_elements": ["column-point"],
        "table_row_element": "column-point"}


@pytest.mark.parametrize("key,value", [("assignment_authority_ref", None),
    ("joint_authority_ref", None), ("assignment_state", "UNKNOWN"),
    ("assignment_state", "BEAM_BRACE"), ("analysis_elements", []),
    ("analysis_elements", ["column-point", "beam-point"]), ("table_row_element", "beam-point")])
def test_panel_zone_and_analysis_joint_ambiguity_rejected(key, value):
    e = panel_evidence(); e[key] = value
    with pytest.raises(ValueError): tool.audit_panel_binding(e)


@pytest.mark.parametrize("claims", [{"presentation_global": True}, {"field_names_global": True},
    {"coordinates": "global", "schema_success": True}, {"panel_zone_global_convention": True},
    {"all_gates": "PROVEN"}])
def test_false_global_qualification_never_promotes_presentation_schema_or_caller_claims(claims):
    # A derived-index anchor describes the already accepted P1 schema, not these
    # synthetic rows. It still cannot supply missing coordinate/result authority.
    disposition = tool.route_disposition({"NATIVE_SCHEMA": "CLOSED", "receipt_sha256": tool.P1_SHA}, **claims)
    assert disposition["GLOBAL_COORDINATE_CONTRACT"] == "BLOCKED"
    assert disposition["MODAL_RESULT_GRAIN_CONTRACT"] == "BLOCKED"
    assert disposition["P2_EXECUTION_AUTHORIZED"] is False
    assert disposition["GLOBAL_ENDPOINT_MODAL_ROWS"] == 0


def test_offline_tool_has_no_native_access_selection_or_state_mutation_calls():
    tree = ast.parse(inspect.getsource(tool))
    forbidden = {"RunAnalysis", "StartDesign", "Save", "SaveAs", "GetTableForDisplayArray",
        "JointDispl", "attach_verified_to_running_etabs", "get_sap", "GetObjectProcess"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
            assert name not in forbidden and not name.startswith("Set")
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            assert node.module not in {"etabs_gateway", "comtypes", "tbdy_engine.etabs.safety"}
