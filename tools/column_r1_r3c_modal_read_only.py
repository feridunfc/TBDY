"""Bounded protected-FC09 modal evidence read. Never a B5/product run.

No result epoch is issued here. Missing/stale modal rows are factual blockers,
not a request to regenerate analysis. Raw table metadata is retained without
inventing a modal-normalization unit or interpreting method integer codes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import ntpath
from pathlib import Path
import sys
from datetime import datetime, timezone

REPO_ROOT = Path(__file__).resolve().parents[1]
for path in (REPO_ROOT, REPO_ROOT / "packages" / "etabs_gateway" / "src"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
from tools.column_r1_r2_live_preflight import FC09_SHA256, git_anchor, json_value, sha256
from tbdy_engine.etabs.safety import (
    attach_verified_to_running_etabs, reread_verified_session_identity, RuntimeCaptureStatus,
)
from tbdy_engine.etabs.oapi import fetch_display_table_from_session, fetch_display_table_for_output_from_session
from tbdy_engine.etabs.oapi.database_tables import fetch_table_field_metadata_from_session
from tbdy_engine.etabs.oapi.analysis_execution import get_response_spectrum_settings_from_session
from tbdy_engine.etabs.oapi.eq713_response_results import read_frame_force_response_from_session
from tbdy_engine.etabs.oapi.joint_displacement_results import read_joint_displ_from_session
from tbdy_engine.integration.live_etabs_acquisition_context import create_trusted_live_acquisition_context


def raw_ref(value):
    payload = json.dumps(json_value(value), sort_keys=True, allow_nan=False, separators=(",", ":"))
    return "modal-read:sha256:" + hashlib.sha256(payload.encode()).hexdigest()


def run_capture(*, source: Path, pid: int, story: str, receipt_path: Path,
                modal_info_table: str = "Response Spectrum Modal Info"):
    source, receipt_path = Path(source).resolve(), Path(receipt_path).resolve()
    if type(pid) is not int or pid <= 0 or not story or story != story.strip():
        raise ValueError("exact positive PID and canonical representative story are required")
    if not source.is_file() or receipt_path == source or receipt_path.is_relative_to(REPO_ROOT):
        raise ValueError("existing protected EDB and receipt outside repository required")
    if receipt_path.exists() or not receipt_path.parent.is_dir():
        raise ValueError("receipt must be a new file in an existing outside-repository directory")
    receipt = {"mode": "R3C_READ_ONLY_MODAL_FACTS_NOT_B5", "repository": git_anchor(),
               "source_path": str(source), "pid": pid, "representative_story": story,
               "source_sha256_expected": FC09_SHA256, "started_utc": datetime.now(timezone.utc).isoformat(),
               "facts": {}, "errors": [], "current_b5_qualified": False,
               "stability_promotion": False, "R2_RERUN_READY": False,
               "gate_1": "PENDING_NATIVE_FIELD_NORMALIZATION_AND_B5_BINDING",
               "gate_2": "PROJECT_DECISION_REQUIRED",
               "missing_b5_evidence": "Matching qualified uncracked B5 AnalysisExecutionResult, owned-scratch bridge and exact active epoch are not supplied by a protected-source read",
               "selection_policy": "Existing safety-owned reversible output-selection reads; engineering model unchanged"}
    receipt["physical_hash_scope"] = "Protected disk bytes only; no in-memory result freshness or B5 epoch claim"
    session = None
    before = None
    def observe():
        observed = reread_verified_session_identity(session)
        if observed != before or session.identity != before:
            raise ValueError("active source/session/present/database-unit drift")
        return observed
    def capture(key, getter):
        observe()
        fact = getter()
        observe()
        receipt["facts"][key] = {"capture_payload_ref": raw_ref(fact), "payload": json_value(fact)}
        return fact
    def table(key, *, output=None):
        metadata = capture(key + ":metadata", lambda: fetch_table_field_metadata_from_session(session, key))
        fetch = capture(key + ("@" + output if output else ""), lambda:
            fetch_display_table_for_output_from_session(session, key, preferred_output_case=output)
            if output else fetch_display_table_from_session(session, key))
        if metadata.status != "PARSED_EXACT_FIELD_METADATA":
            # Keep exact metadata status; no borrowing or inferred units.
            raise ValueError(f"{key}: native field metadata not decoded: {metadata.status}")
        if fetch.capture_status is not RuntimeCaptureStatus.FULL or fetch.parsed.return_code != 0:
            raise ValueError(f"{key}: exact FULL successful source capture unavailable")
        if len(fetch.parsed.rows) != fetch.parsed.row_count_reported:
            raise ValueError(f"{key}: FULL row-count mismatch")
        if not fetch.parsed.rows:
            raise ValueError(f"{key}: native source table returned no rows")
        if output and not any(x.get("phase") == "restore_verify" and x.get("success") is True for x in fetch.state_diagnostics):
            raise ValueError(f"{key}: output selection restoration not verified")
        return fetch
    try:
        receipt["source_sha256_before"] = sha256(source)
        if receipt["source_sha256_before"] != FC09_SHA256:
            raise ValueError("source must match exact protected FC09 SHA256")
        session = attach_verified_to_running_etabs(str(source), pid=pid, allow_pid_fallback=False)
        before = reread_verified_session_identity(session)
        if before != session.identity or before.process_id != pid:
            raise ValueError("fresh verified identity/PID mismatch")
        if ntpath.normcase(ntpath.normpath(before.model_full_path)) != ntpath.normcase(ntpath.normpath(str(source))):
            raise ValueError("active model path differs from protected source")
        if before.program_version != "23.2.0" or before.program_api_version != 2.014:
            raise ValueError("unsupported exact program/API version")
        if before.units.present_observation_status != "OBSERVED_CONSISTENT" or before.units.database_observation_status != "OBSERVED_CONSISTENT":
            raise ValueError("independent present/database-unit observations missing")
        receipt["identity_before"] = before.as_dict()
        context = create_trusted_live_acquisition_context(session)
        receipt["factual_capture_binding"] = {"source_model_ref": context.source_model_identity.source_model_ref,
            "session_ref": context.session_provenance_ref, "capture_ref": context.acquisition_context_ref,
            "evidence_epoch_id": context.evidence_epoch_id, "is_analysis_result_epoch": False}
        modal_cases = set()
        for case in ("RSX", "RSY"):
            settings = capture(case + ":settings", lambda c=case: get_response_spectrum_settings_from_session(session, case_name=c))
            for required in ("GetModalCase", "GetLoads", "GetModalComb_1", "GetDirComb", "GetDampType", "GetEccentricity", "GetDiaphragmEccentricityOverride", "GetDampOverrides"):
                if not next(x for x in settings.settings if x.method == required).success:
                    raise ValueError(f"{case}: required native {required} signature is unqualified")
            modal = next(x for x in settings.settings if x.method == "GetModalCase")
            if not modal.success:
                raise ValueError(f"{case}: native modal dependency unavailable")
            modal_cases.add(dict(modal.outputs)["ModalCase"])
            table(modal_info_table, output=case)
            table("Load Case Definitions - Response Spectrum") if case == "RSX" else None
        connectivity = table("Column Object Connectivity")
        table("Point Object Connectivity")
        columns = tuple(row for row in connectivity.parsed.rows if row.get("Story") == story)
        if not columns:
            raise ValueError(f"complete factual Column population absent for story {story!r}")
        names = tuple(row.get("UniqueName") for row in columns)
        if any(not isinstance(x, str) or not x for x in names) or len(set(names)) != len(names):
            raise ValueError("representative story has missing/duplicate factual Column identity")
        endpoints = {row.get(key) for row in columns for key in ("UniquePtI", "UniquePtJ")}
        if any(not isinstance(x, str) or not x for x in endpoints):
            raise ValueError("exact physical endpoint identities unavailable")
        points = sorted(endpoints)
        receipt["story_columns"] = columns
        receipt["complete_factual_story_column_count"] = len(columns)
        for modal_case in sorted(modal_cases):
            table("Modal Periods And Frequencies", output=modal_case)
            table("Modal Participating Mass Ratios", output=modal_case)
            table("Story Forces", output=modal_case)
            for name in sorted(names):
                force = capture(f"{modal_case}:FrameForce:{name}", lambda n=name, c=modal_case:
                    read_frame_force_response_from_session(session, frame_name=n, case_name=c))
                if force.return_code != 0 or not force.rows or any(r.step_type != "Mode" for r in force.rows):
                    raise ValueError(f"{modal_case}:FrameForce:{name}: signed per-mode source population unavailable")
            for point in points:
                displacement = capture(f"{modal_case}:JointDispl:{point}", lambda p=point, c=modal_case:
                    read_joint_displ_from_session(session, point_object=p, output_name=c, output_kind="case"))
                if displacement.return_code != 0 or not displacement.rows or any(r.step_type != "Mode" for r in displacement.rows):
                    raise ValueError(f"{modal_case}:JointDispl:{point}: signed per-mode endpoint population unavailable")
        receipt["status"] = "FACTUAL_CAPTURE_COMPLETE_PENDING_NORMALIZATION_B5_AND_JOINT_RULE"
    except Exception as exc:
        receipt["status"] = "BLOCKED_READ_ONLY_CAPTURE"
        receipt["errors"].append({"type": type(exc).__name__, "message": str(exc)})
    finally:
        if session is not None:
            try:
                after = reread_verified_session_identity(session)
                receipt["identity_after"] = after.as_dict()
                if after != before:
                    raise ValueError("final active identity/unit drift")
            except Exception as exc:
                receipt["errors"].append({"type": type(exc).__name__, "message": str(exc)})
            finally:
                try:
                    session._gateway_session.close()
                except Exception as exc:
                    receipt["errors"].append({"type": type(exc).__name__, "message": "gateway close: " + str(exc)})
        try:
            receipt["source_sha256_after"] = sha256(source)
        except Exception as exc:
            receipt["source_sha256_after"] = None
            receipt["errors"].append({"type": type(exc).__name__, "message": "protected hash after: " + str(exc)})
        receipt["source_unchanged"] = receipt["source_sha256_before"] == receipt["source_sha256_after"] == FC09_SHA256 if "source_sha256_before" in receipt else False
        if not receipt["source_unchanged"]:
            receipt["errors"].append({"type": "SourceIntegrityError", "message": "exact FC09 protected pre/post hash guard failed"})
        if not receipt["source_unchanged"] or receipt["errors"]:
            receipt["status"] = "BLOCKED_READ_ONLY_CAPTURE"
        receipt["finished_utc"] = datetime.now(timezone.utc).isoformat()
        with receipt_path.open("x", encoding="utf-8") as stream:
            json.dump(json_value(receipt), stream, ensure_ascii=False, indent=2, allow_nan=False)
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--story", required=True)
    parser.add_argument("--receipt", required=True)
    parser.add_argument("--modal-info-table", default="Response Spectrum Modal Info",
                        help="Exact native table key; no guessed aliases")
    args = parser.parse_args()
    receipt = run_capture(source=Path(args.source), pid=args.pid, story=args.story,
        receipt_path=Path(args.receipt), modal_info_table=args.modal_info_table)
    print(json.dumps({k: receipt[k] for k in ("status", "source_unchanged", "errors", "gate_1", "gate_2", "R2_RERUN_READY")}, indent=2))
    return 0 if not receipt["errors"] and receipt["source_unchanged"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
