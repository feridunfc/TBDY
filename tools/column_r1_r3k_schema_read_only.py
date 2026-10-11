"""Protected-FC09 getter-only schema discovery; operator authorization required.

No results are acquired and no coordinate/engineering meaning is assigned.
Receipts are exclusive, read-only files outside the repository. The SHA sidecar
hashes the exact UTF-8 receipt bytes; native response hashes use the explicitly
recorded canonical JSON serialization, not an unavailable COM wire encoding.
"""
from __future__ import annotations

import argparse
import ast
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
import ntpath
from pathlib import Path
import re
import subprocess
import sys
import uuid

REPO_ROOT = Path(__file__).resolve().parents[1]
for path in (REPO_ROOT, REPO_ROOT / "packages" / "etabs_gateway" / "src"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from tbdy_engine.etabs.safety import CapabilityState, attach_verified_to_running_etabs, reread_verified_session_identity
from tbdy_engine.etabs.oapi.database_tables import (
    FIELD_METADATA_ABI_REF, FIELD_METADATA_OUTPUT_ORDER,
    fetch_available_table_metadata_from_session, fetch_table_field_metadata_from_session,
)

FC09_SOURCE_PATH = r"C:\tmp\B-BLOK_Revised.EDB"
FC09_SHA256 = "FC09E5EEB1E195C7141EB992EC501E0004EA733078997C58E1F84D979F70758F"
TABLE_KEY = "Joint Displacements"


def _json_value(value):
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return _json_value(asdict(value))
    if isinstance(value, dict):
        return {str(k): _json_value(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_value(v) for v in value]
    if value is None or type(value) in (str, bool, int, float):
        return value
    raise TypeError(f"Unsupported native receipt value: {type(value).__name__}")


def _raw_sha256(value):
    encoded = json.dumps(_json_value(value), sort_keys=True, ensure_ascii=False,
                         allow_nan=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _file_sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def _git_anchor():
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=REPO_ROOT, text=True).strip()
    return {"HEAD": git("rev-parse", "HEAD"), "TREE": git("rev-parse", "HEAD^{tree}"),
            "worktree_status": git("status", "--porcelain")}


def _windows_path(path):
    return ntpath.normcase(ntpath.normpath(str(path)))


def _validate_identity(identity, *, source, pid):
    if identity.process_id != pid or _windows_path(identity.model_full_path) != _windows_path(source):
        raise ValueError("exact existing PID / loaded model path mismatch")
    if identity.attach_strategy != "comtypes_create_helper_get_object_process":
        raise ValueError("exact PID-specific native attachment strategy required; no fallback")
    if identity.program_name != "ETABS" or identity.program_version != "23.2.0" or identity.program_api_version != 2.014:
        raise ValueError("exact ETABS 23.2.0 / API 2.014 identity required")
    if identity.model_locked is None:
        raise ValueError("native model-lock observation unavailable")
    units = identity.units
    if units.present_observation_status != "OBSERVED_CONSISTENT" or units.database_observation_status != "OBSERVED_CONSISTENT":
        raise ValueError("independent unchanged present/database unit observations required; no setter permitted")
    raw_units = dict(units.raw_unit_reads)
    for name in ("GetPresentUnits_2", "GetDatabaseUnits_2"):
        raw = ast.literal_eval(raw_units.get(name, "None"))
        if not isinstance(raw, (tuple, list)) or len(raw) != 4 or type(raw[-1]) is not int or raw[-1] != 0:
            raise ValueError("unsuccessful or malformed native unit observation: " + name)
    for name in ("GetPresentUnits", "GetDatabaseUnits"):
        raw = ast.literal_eval(raw_units.get(name, "None"))
        if isinstance(raw, (tuple, list)) and len(raw) == 2 and type(raw[-1]) is int and raw[-1] == 0:
            raw = raw[0]
        if type(raw) is not int:
            raise ValueError("unsuccessful or malformed native scalar unit observation: " + name)


def run_probe(*, source: Path, pid: int, receipt_path: Path, expected_head: str):
    source, output = Path(source).resolve(), Path(receipt_path).resolve()
    sidecar = output.with_name(output.name + ".sha256")
    if type(pid) is not int or pid <= 0:
        raise ValueError("explicit verified positive ETABS PID required")
    if type(expected_head) is not str or not re.fullmatch(r"[0-9a-f]{40}", expected_head):
        raise ValueError("supervisor-authorized exact repository HEAD required")
    if _windows_path(source) != _windows_path(Path(FC09_SOURCE_PATH).resolve()) or not source.is_file():
        raise ValueError("only the exact existing protected original EDB path is allowed")
    if output.is_relative_to(REPO_ROOT) or sidecar.is_relative_to(REPO_ROOT) or source in (output, sidecar):
        raise ValueError("immutable raw evidence must be outside the repository and protected EDB")
    if output.exists() or sidecar.exists() or not output.parent.is_dir():
        raise ValueError("new exclusive receipt/sidecar in an existing outside-repository directory required")
    anchor = _git_anchor()
    if anchor["HEAD"] != expected_head or anchor["worktree_status"]:
        raise ValueError("exact authorized clean repository checkpoint required before attachment")
    receipt = {
        "mode": "R3K_GETTER_ONLY_SCHEMA_DISCOVERY_NOT_RESULTS_NOT_B5",
        "repository": anchor, "source_path": str(source), "pid": pid,
        "source_sha256_expected": FC09_SHA256, "table_key": TABLE_KEY,
        "started_utc": datetime.now(timezone.utc).isoformat(), "facts": {}, "errors": [],
        "GETALLFIELDS_ABI": {"output_order": FIELD_METADATA_OUTPUT_ORDER, "authority_ref": FIELD_METADATA_ABI_REF},
        "raw_hash_encoding": "UTF-8 canonical JSON: sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(',',':'); immutable typed-owner raw response, no unit conversion",
        "NATIVE_TABLE_AVAILABILITY": "NOT_OBSERVED", "CSI_SUPPORT_REQUEST": "DRAFT_NOT_SENT",
        "CSI_CONTRACT_AUTHORITY": "BLOCKED", "GLOBAL_MODAL_DELTA": "NOT_PROVEN",
        "CURRENT_B5": "NOT_PROVIDED", "JOINT_DELTA_R_V": "PROJECT_DECISION_REQUIRED",
        "R2_RERUN_READY": False, "M6_B": "OPEN", "result_rows_acquired": 0,
        "engineering_interpretation": False,
    }
    session = None
    before = None
    capture_ref = "r3k-schema-capture:" + uuid.uuid4().hex
    def observe():
        observed = reread_verified_session_identity(session)
        _validate_identity(observed, source=source, pid=pid)
        if observed.as_dict() != before.as_dict() or session.identity.as_dict() != before.as_dict():
            raise ValueError("active source/session/lock/present/database-unit drift")
        return observed
    def capture(name, getter):
        observe()
        fact = getter()
        receipt["facts"][name] = {"payload": _json_value(fact),
            "raw_response_sha256": _raw_sha256(fact.raw_response)}
        observe()
        if (_windows_path(fact.source_model_ref) != _windows_path(source)
                or fact.session_ref != f"etabs-session:pid:{pid}" or fact.capture_ref != capture_ref):
            raise ValueError("native metadata source/session/capture binding mismatch")
        return fact
    try:
        receipt["source_sha256_before"] = _file_sha256(source)
        if receipt["source_sha256_before"] != FC09_SHA256:
            raise ValueError("exact protected FC09 pre-read SHA256 mismatch")
        session = attach_verified_to_running_etabs(str(source), pid=pid, allow_pid_fallback=False)
        if session.capabilities.pid_attach is not CapabilityState.SUPPORTED:
            raise ValueError("PID-specific attachment capability not proven")
        before = reread_verified_session_identity(session)
        _validate_identity(before, source=source, pid=pid)
        if before.as_dict() != session.identity.as_dict():
            raise ValueError("fresh attachment identity mismatch")
        receipt["identity_before"] = before.as_dict()
        receipt["identity_before_sha256"] = _raw_sha256(before.as_dict())
        receipt["capture_ref"] = capture_ref
        availability = capture("GetAvailableTables", lambda: fetch_available_table_metadata_from_session(session, capture_ref=capture_ref))
        if availability.status.startswith("BLOCKED:"):
            raise ValueError(availability.status)
        if availability.status == "PARSED_NATIVE_AVAILABLE_TABLES":
            if TABLE_KEY in availability.table_keys:
                i = availability.table_keys.index(TABLE_KEY)
                receipt["NATIVE_TABLE_AVAILABILITY"] = {
                    "TableKey": availability.table_keys[i], "TableName": availability.table_names[i],
                    "ImportType": availability.import_types[i], "IsEmpty": availability.is_empty[i],
                    "meaning": "native availability fact only; no result population or coordinate qualification",
                }
            else:
                receipt["NATIVE_TABLE_AVAILABILITY"] = "NOT_LISTED_BY_NATIVE_GETAVAILABLETABLES"
        else:
            receipt["NATIVE_TABLE_AVAILABILITY"] = availability.status
        metadata = capture("GetAllFieldsInTable", lambda: fetch_table_field_metadata_from_session(session, TABLE_KEY, capture_ref=capture_ref))
        if metadata.status != "PARSED_EXACT_FIELD_METADATA" or metadata.return_code != 0 or not metadata.number_fields:
            raise ValueError("successful nonempty exact native field metadata required: " + metadata.status)
        if metadata.table_name != TABLE_KEY:
            raise ValueError("exact native table-key binding mismatch")
        receipt["fields"] = [metadata.field_metadata(key) for key in metadata.field_keys]
        receipt["table_version"] = metadata.table_version
        receipt["status"] = "SCHEMA_DISCOVERY_COMPLETE_SOURCE_SEMANTICS_NOT_QUALIFIED"
    except Exception as exc:
        receipt["errors"].append({"type": type(exc).__name__, "message": str(exc)})
    finally:
        if session is not None:
            try:
                after = observe() if before is not None else reread_verified_session_identity(session)
                receipt["identity_after"] = after.as_dict()
                receipt["identity_after_sha256"] = _raw_sha256(after.as_dict())
                receipt["session_units_unchanged"] = before is not None and after.as_dict() == before.as_dict()
            except Exception as exc:
                receipt["session_units_unchanged"] = False
                receipt["errors"].append({"type": type(exc).__name__, "message": "final identity: " + str(exc)})
            finally:
                try:
                    if session.close() is not True:
                        raise ValueError("gateway close not confirmed")
                except Exception as exc:
                    receipt["errors"].append({"type": type(exc).__name__, "message": "gateway close: " + str(exc)})
        try:
            receipt["source_sha256_after"] = _file_sha256(source)
        except Exception as exc:
            receipt["source_sha256_after"] = None
            receipt["errors"].append({"type": type(exc).__name__, "message": "protected hash after: " + str(exc)})
        receipt["source_unchanged"] = receipt.get("source_sha256_before") == receipt["source_sha256_after"] == FC09_SHA256
        if not receipt["source_unchanged"]:
            receipt["errors"].append({"type": "SourceIntegrityError", "message": "exact FC09 pre/post hash guard failed"})
        if receipt["errors"]:
            receipt["status"] = "BLOCKED_SCHEMA_DISCOVERY"
        receipt["finished_utc"] = datetime.now(timezone.utc).isoformat()
        payload = (json.dumps(_json_value(receipt), ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
        with output.open("xb") as stream:
            stream.write(payload)
        output.chmod(0o444)
        with sidecar.open("x", encoding="ascii", newline="\n") as stream:
            stream.write(hashlib.sha256(payload).hexdigest() + "  " + output.name + "\n")
        sidecar.chmod(0o444)
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--receipt", required=True)
    parser.add_argument("--expected-head", required=True)
    args = parser.parse_args(argv)
    receipt = run_probe(source=Path(args.source), pid=args.pid,
                        receipt_path=Path(args.receipt), expected_head=args.expected_head)
    print(json.dumps({key: receipt[key] for key in ("status", "NATIVE_TABLE_AVAILABILITY",
        "source_unchanged", "errors", "GLOBAL_MODAL_DELTA", "R2_RERUN_READY")}, indent=2))
    return 0 if not receipt["errors"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
