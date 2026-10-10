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
from decimal import Decimal, InvalidOperation

REPO_ROOT = Path(__file__).resolve().parents[1]
for path in (REPO_ROOT, REPO_ROOT / "packages" / "etabs_gateway" / "src"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
from tools.column_r1_r2_live_preflight import FC09_SHA256, git_anchor, json_value, sha256
from tbdy_engine.etabs.safety import (
    attach_verified_to_running_etabs, reread_verified_session_identity, RuntimeCaptureStatus,
)
from tbdy_engine.etabs.oapi import fetch_display_table_from_session, fetch_display_table_for_output_from_session
from tbdy_engine.etabs.oapi.database_tables import fetch_table_field_metadata_from_session, decode_table_field_metadata
from tbdy_engine.etabs.oapi.analysis_execution import get_response_spectrum_settings_from_session
from tbdy_engine.etabs.oapi.eq713_response_results import read_frame_force_response_from_session
from tbdy_engine.etabs.oapi.joint_displacement_results import read_joint_displ_from_session
from tbdy_engine.integration.live_etabs_acquisition_context import create_trusted_live_acquisition_context
from tbdy_engine.etabs.source_units import decode_csi_force_unit, decode_csi_length_unit

# Exact accepted FC09 scope; neither an inferred modal count nor a B5 issuer.
FC09_MODES = tuple(range(1, 101))
FC09_STORY_POPULATION = {"+0.00": (86, 172)}


def _number(value, label):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{label}: exact finite native number required") from None
    if isinstance(value, bool) or not result.is_finite():
        raise ValueError(f"{label}: exact finite native number required")
    return result


def _mode(value, label):
    number = _number(value, label)
    if number != number.to_integral_value() or number <= 0:
        raise ValueError(f"{label}: positive integer mode required")
    return int(number)


def _unique_modes(rows, field, label, expected=FC09_MODES):
    by_mode = {}
    for row in rows:
        mode = _mode(row.get(field), label)
        if mode in by_mode:
            raise ValueError(f"{label}: duplicate mode {mode}")
        by_mode[mode] = row
    if set(by_mode) != set(expected):
        raise ValueError(f"{label}: mode population differs; missing={sorted(set(expected)-set(by_mode))}; "
                         f"extra={sorted(set(by_mode)-set(expected))}")
    return by_mode


def _metadata_units(metadata, expected):
    if len(set(metadata.field_keys)) != len(metadata.field_keys):
        raise ValueError(f"{metadata.table_name}: duplicate native metadata field")
    for field, unit in expected.items():
        fact = metadata.field_metadata(field)
        if fact["UnitsString"] != unit or not fact["Description"]:
            raise ValueError(f"{metadata.table_name}:{field}: native field unit/definition mismatch")


def _restored(diagnostics, *, modal=False):
    phases = ("restore_verify", "modal_output_restore_verify") if modal else ("restore_verify",)
    if any(not any(x.get("phase") == phase and x.get("success") is True for x in diagnostics)
           or any(x.get("phase") == phase and x.get("success") is not True for x in diagnostics)
           for phase in phases):
        raise ValueError("native output state restoration not verified")
    if modal and not any(x.get("phase") == "temporary_modal_modes" and x.get("success") is True
                         for x in diagnostics):
        raise ValueError("native temporary modal range not verified")


def _physical_modes(fact, *, name, case, frame):
    if fact.return_code != 0 or not fact.rows:
        raise ValueError(f"{case}:{name}: signed per-mode source population unavailable")
    grains = {}
    for row in fact.rows:
        identity = row.object_name if frame else row.point_object
        if identity != name or row.load_case != case or row.step_type != "Mode":
            raise ValueError(f"{case}:{name}: physical object/case/Mode identity mismatch")
        grain = ((row.element_name, row.object_station, row.element_station) if frame else
                 (row.element_name,))
        grains.setdefault(grain, []).append({"Mode": row.step_number})
    for grain, rows in grains.items():
        _unique_modes(rows, "Mode", f"{case}:{name}:{grain}")
    _restored(fact.state_diagnostics, modal=True)
    return {"modes": list(FC09_MODES), "physical_grain_count": len(grains)}


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
    receipt = {"mode": "R3D_READ_ONLY_MODAL_FACTS_NOT_B5", "repository": git_anchor(),
               "source_path": str(source), "pid": pid, "representative_story": story,
               "source_sha256_expected": FC09_SHA256, "started_utc": datetime.now(timezone.utc).isoformat(),
               "facts": {}, "errors": [], "current_b5_qualified": False,
               "stability_promotion": False, "R2_RERUN_READY": False,
               "gate_1": "PENDING_NATIVE_FIELD_NORMALIZATION_AND_B5_BINDING",
               "gate_2": "PROJECT_DECISION_REQUIRED",
               "missing_b5_evidence": "Matching qualified uncracked B5 AnalysisExecutionResult, owned-scratch bridge and exact active epoch are not supplied by a protected-source read",
               "selection_policy": "Existing safety-owned snapshot/verified 1..100 read/verified restoration; engineering model unchanged",
               "mode_population_authority": list(FC09_MODES), "modal_coverage": {},
               "output_state_restored": None}
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
    def table(key, *, output=None, modes=False):
        metadata = capture(key + ":metadata", lambda: fetch_table_field_metadata_from_session(session, key))
        fetch = capture(key + ("@" + output if output else ""), lambda:
            fetch_display_table_for_output_from_session(session, key, preferred_output_case=output,
                **({"modal_mode_range": (1, 100)} if modes else {}))
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
        if output:
            _restored(fetch.state_diagnostics, modal=modes)
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
        length_unit = decode_csi_length_unit(before.units.present_length_unit).value
        force_unit = decode_csi_force_unit(before.units.present_force_unit).value
        receipt["native_result_units"] = {"FrameForce": force_unit, "JointDispl": length_unit,
            "basis": "independently observed present units; no modal multiplier/normalization inferred",
            "database_length": decode_csi_length_unit(before.units.database_length_unit).value,
            "database_force": decode_csi_force_unit(before.units.database_force_unit).value}
        context = create_trusted_live_acquisition_context(session)
        receipt["factual_capture_binding"] = {"source_model_ref": context.source_model_identity.source_model_ref,
            "session_ref": context.session_provenance_ref, "capture_ref": context.acquisition_context_ref,
            "evidence_epoch_id": context.evidence_epoch_id, "is_analysis_result_epoch": False}
        modal_cases = set()
        amplitudes = {}
        for case in ("RSX", "RSY"):
            settings = capture(case + ":settings", lambda c=case: get_response_spectrum_settings_from_session(session, case_name=c))
            for required in ("GetModalCase", "GetLoads", "GetModalComb_1", "GetDirComb", "GetDampType", "GetEccentricity", "GetDiaphragmEccentricityOverride", "GetDampOverrides"):
                if not next(x for x in settings.settings if x.method == required).success:
                    raise ValueError(f"{case}: required native {required} signature is unqualified")
            modal = next(x for x in settings.settings if x.method == "GetModalCase")
            if not modal.success:
                raise ValueError(f"{case}: native modal dependency unavailable")
            modal_cases.add(dict(modal.outputs)["ModalCase"])
            loads = dict(next(x for x in settings.settings if x.method == "GetLoads").outputs)
            if loads["NumberLoads"] != 1 or loads["LoadName"][0] != {"RSX":"U1", "RSY":"U2"}[case]:
                raise ValueError(f"{case}: exact accepted one-direction FC09 source signature required")
            direction = loads["LoadName"][0]
            amplitude = table(modal_info_table, output=case, modes=True)
            metadata = receipt["facts"][modal_info_table + ":metadata"]["payload"]
            # Use the original typed metadata owner, not positional display headers.
            typed = decode_table_field_metadata(metadata["raw_response"], table_name=modal_info_table)
            _metadata_units(typed, {"Mode":"", "Period":"sec", **{u+"Amp":length_unit for u in ("U1","U2","U3")}})
            rows = tuple(r for r in amplitude.parsed.rows if r.get("SpecCase") == case
                         and r.get("ModalCase") == dict(modal.outputs)["ModalCase"])
            modes = _unique_modes(rows, "Mode", f"{case}:native amplitude")
            for row in modes.values():
                for key in ("Period", "U1Amp", "U2Amp", "U3Amp"):
                    _number(row.get(key), f"{case}:{key}")
            amplitudes[case] = (dict(modal.outputs)["ModalCase"], modes)
            receipt.setdefault("native_amplitude_alignment", {})[case] = {
                "source_direction": direction, "source_field": direction + "Amp", "source_unit": length_unit,
                "metadata_ref": raw_ref(metadata), "table_ref": raw_ref(amplitude),
                "modes": list(sorted(modes)), "applied_scaling_factor": None,
                "normalization": "NOT_QUALIFIED_FOR_MODAL_MECHANICS; dimensional native amplitudes retained unchanged"}
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
        if story not in FC09_STORY_POPULATION or (len(columns), len(points)) != FC09_STORY_POPULATION[story]:
            raise ValueError("exact accepted FC09 representative-story Column/endpoint population mismatch")
        point_rows = receipt["facts"]["Point Object Connectivity"]["payload"]["parsed"]["rows"]
        for point in points:
            matched = [row for row in point_rows if row.get("UniqueName") == point]
            if len(matched) != 1:
                raise ValueError(f"physical endpoint {point}: missing/duplicate native connectivity")
        receipt["story_columns"] = columns
        receipt["complete_factual_story_column_count"] = len(columns)
        receipt["complete_factual_endpoint_count"] = len(points)
        for key, fields in (("Column Object Connectivity", {"Length":length_unit}),
                            ("Point Object Connectivity", {"X":length_unit,"Y":length_unit,"Z":length_unit})):
            typed = decode_table_field_metadata(receipt["facts"][key+":metadata"]["payload"]["raw_response"], table_name=key)
            _metadata_units(typed, fields)
        for modal_case in sorted(modal_cases):
            periods = table("Modal Periods And Frequencies", output=modal_case, modes=True)
            reference = _unique_modes(tuple(r for r in periods.parsed.rows if r.get("Case") == modal_case),
                                      "Mode", f"{modal_case}:period authority")
            masses = table("Modal Participating Mass Ratios", output=modal_case, modes=True)
            _unique_modes(tuple(r for r in masses.parsed.rows if r.get("Case") == modal_case),
                          "Mode", f"{modal_case}:mass authority")
            for case, (dependency, modes) in amplitudes.items():
                if dependency == modal_case:
                    for mode, row in modes.items():
                        if _number(row["Period"], f"{case}:period") != _number(reference[mode]["Period"], "Modal:period"):
                            raise ValueError(f"{case}:mode {mode}: native period mismatch")
            for key in ("Modal Periods And Frequencies", "Modal Participating Mass Ratios"):
                typed = decode_table_field_metadata(receipt["facts"][key+":metadata"]["payload"]["raw_response"], table_name=key)
                _metadata_units(typed, {"Mode":"", "Period":"sec"})
            story_forces = table("Story Forces", output=modal_case, modes=True)
            typed = decode_table_field_metadata(receipt["facts"]["Story Forces:metadata"]["payload"]["raw_response"], table_name="Story Forces")
            _metadata_units(typed, {"StepNumber":"", "Location":"", "VX":force_unit, "VY":force_unit})
            # The existing safety selection preserves opposite-domain combos.
            # Retain raw superset rows, but calculation candidates are exact.
            bottom = tuple(r for r in story_forces.parsed.rows if r.get("OutputCase") == modal_case
                and r.get("StepType") == "Mode" and r.get("Story") == story and r.get("Location") == "Bottom")
            _unique_modes(bottom, "StepNumber", f"{modal_case}:{story}:Bottom Story Forces")
            for row in bottom:
                for key in ("VX", "VY"):
                    _number(row.get(key), f"Story Forces:{key}")
            receipt.setdefault("filtered_modal_story_forces", {})[modal_case] = {
                "rows": bottom, "raw_superset_ref": raw_ref(story_forces),
                "field_metadata_ref": raw_ref(typed), "physical_location": "native Location=Bottom",
                "modes": list(FC09_MODES), "source_units": {"VX":force_unit, "VY":force_unit}}
            coverage = {"FrameForce": {}, "JointDispl": {}, "StoryForces": list(FC09_MODES)}
            receipt["modal_coverage"][modal_case] = coverage
            for name in sorted(names):
                force = capture(f"{modal_case}:FrameForce:{name}", lambda n=name, c=modal_case:
                    read_frame_force_response_from_session(session, frame_name=n, case_name=c, modal_mode_range=(1, 100)))
                coverage["FrameForce"][name] = _physical_modes(force, name=name, case=modal_case, frame=True)
            for point in points:
                displacement = capture(f"{modal_case}:JointDispl:{point}", lambda p=point, c=modal_case:
                    read_joint_displ_from_session(session, point_object=p, output_name=c, output_kind="case", modal_mode_range=(1, 100)))
                coverage["JointDispl"][point] = _physical_modes(displacement, name=point, case=modal_case, frame=False)
            if set(coverage["FrameForce"]) != set(names) or set(coverage["JointDispl"]) != set(points):
                raise ValueError("incomplete physical result object population")
        receipt["output_state_restored"] = True
        receipt["gate_1"] = "MODE_POPULATIONS_COMPLETE_NORMALIZATION_AND_B5_BINDING_PENDING"
        receipt["status"] = "FACTUAL_100_MODE_CAPTURE_COMPLETE_PENDING_NORMALIZATION_B5_AND_JOINT_RULE"
    except Exception as exc:
        receipt["status"] = "BLOCKED_READ_ONLY_CAPTURE"
        receipt["errors"].append({"type": type(exc).__name__, "message": str(exc)})
        if getattr(exc, "details", None):
            receipt["errors"][-1]["details"] = json_value(exc.details)
        if any("restore" in x.get("phase", "") and x.get("success") is False
               for x in getattr(exc, "details", {}).get("state_diagnostics", ())):
            receipt["output_state_restored"] = False
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
