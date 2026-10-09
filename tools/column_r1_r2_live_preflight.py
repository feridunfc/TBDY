"""Read-only FC09 R0/R1 evidence capture; never an R2 product execution.

Run only with the operator's exact ETABS PID. No scratch is created and no
engineering approval, result freshness or design completion is inferred.
Receipts are written exclusively outside this repository. Current live unit
observer accepts reviewed m enums only; mm4 is supported only if independently
verified mm observations become available through that same observer.
"""
from __future__ import annotations

import argparse
from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
import hashlib
import json
import ntpath
from pathlib import Path
import subprocess
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
for path in (REPO_ROOT, REPO_ROOT / "packages" / "etabs_gateway" / "src"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from tbdy_engine.etabs.safety import (
    RuntimeCaptureStatus,
    attach_verified_to_running_etabs,
    reread_verified_session_identity,
)
from tbdy_engine.etabs.oapi import fetch_display_table_from_session
from tbdy_engine.etabs.oapi.database_tables import fetch_table_field_metadata_from_session
from tbdy_engine.etabs.oapi.frame_section_mechanics import (
    FRAME_SECTION_INERTIA_SOURCE_AUTHORITY_REF,
    get_frame_section_mechanics_from_session,
)
from tbdy_engine.etabs.oapi.object_model import read_frame_names_from_session, read_rebar_column_from_session
from tbdy_engine.etabs.oapi.load_definitions import (
    LINEAR_STATIC_CASE_TYPE_CODE,
    read_load_pattern_names_from_session,
    read_load_pattern_type_from_session,
    read_load_case_names_from_session,
    read_load_case_type_from_session,
    read_static_linear_case_from_session,
)
from tbdy_engine.integration.live_etabs_acquisition_context import (
    create_trusted_live_acquisition_context,
    acquire_actual_concrete_design_combo_selection_from_context,
)
from tbdy_engine.providers.etabs_combo_definition_provider import capture_all_etabs_combo_definitions_from_session
from tbdy_engine.providers.etabs_frame_flexural_base_provider import (
    TABLE_FRAME_ASSIGNMENTS, TABLE_RECTANGULAR, TABLE_FRAME_SECTION_SUMMARY,
    TABLE_BASIC_MATERIAL, TABLE_CONCRETE,
)

FC09_SHA256 = "FC09E5EEB1E195C7141EB992EC501E0004EA733078997C58E1F84D979F70758F"
FACT_TABLES = (TABLE_FRAME_ASSIGNMENTS, TABLE_RECTANGULAR,
               TABLE_FRAME_SECTION_SUMMARY, TABLE_BASIC_MATERIAL, TABLE_CONCRETE)
NOT_CAPTURED = (
    "A17 engineering tolerance approval for FC09",
    "reviewed aggregate/ductility/design-basis applicability approval",
    "expected combo policy approval and accepted-input/harness rebind",
    "VS5 Nd/Ndm current-result epoch, sign/superposition/NO_REDUCTION review",
    "W project applicability approval; absence of a wind pattern is not approval",
    "new analysis/design outputs or READY/B6 proof",
)


def json_value(value):
    """Lossless factual serialization for typed owner payloads, not COM objects."""
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return {f.name: json_value(getattr(value, f.name)) for f in fields(value)}
    if isinstance(value, Mapping):
        return {str(k): json_value(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [json_value(v) for v in value]
    if isinstance(value, Decimal):
        return str(value)
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    raise TypeError(f"Unsupported factual receipt value: {type(value).__name__}")


def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024*1024), b""):
            h.update(block)
    return h.hexdigest().upper()


def git_anchor():
    result = {}
    for key, expression in (("HEAD", "HEAD"), ("TREE", "HEAD^{tree}")):
        result[key] = subprocess.check_output(
            ["git", "rev-parse", expression], cwd=REPO_ROOT, text=True).strip()
    result["worktree_status"] = subprocess.check_output(
        ["git", "status", "--porcelain"], cwd=REPO_ROOT, text=True).strip()
    return result


def exact_sections(assignments, frame_names):
    """Discover factual assigned section names; do not classify engineering routes."""
    if assignments.capture_status is not RuntimeCaptureStatus.FULL:
        raise ValueError("Frame assignment capture is not FULL")
    if assignments.parsed.return_code != 0:
        raise ValueError("Frame assignment return is not successful")
    seen = set()
    sections = set()
    unassigned = []
    for row in assignments.parsed.rows:
        name = row.get("UniqueName")
        if not isinstance(name, str) or not name or name in seen:
            raise ValueError("Missing/duplicate exact Frame UniqueName")
        seen.add(name)
        keys = [k for k in ("SectProp", "Section Property") if k in row]
        if len(keys) != 1:
            raise ValueError("Missing/ambiguous factual assigned-section field")
        section = row[keys[0]]
        if section in (None, "", "None"):
            unassigned.append(name)
        elif not isinstance(section, str) or section != section.strip():
            raise ValueError("Invalid factual section identity")
        else:
            sections.add(section)
    if seen != set(frame_names) or len(frame_names) != len(set(frame_names)):
        raise ValueError("Frame assignments do not cover exact FrameObj population")
    return tuple(sorted(sections)), tuple(sorted(unassigned))


def capture_r0(session, context, receipt, assignments, sections):
    """Continue independent factual leaves; record missing facts without substitution."""
    facts = receipt["r0_facts"]
    def capture(key, callback):
        try:
            value = callback()
            payload = json_value(value)
            facts[key] = {"status": "CAPTURED", "value": payload,
                          "context_refs": receipt["r0_context_refs"],
                          "payload_ref": "preflight-fact:sha256:" + hashlib.sha256(
                              json.dumps(payload, sort_keys=True, allow_nan=False).encode()).hexdigest()}
            return value
        except Exception as exc:
            facts[key] = {"status": "NOT_CAPTURED", "error": f"{type(exc).__name__}: {exc}"}
            return None

    facts[TABLE_FRAME_ASSIGNMENTS] = {"status": "CAPTURED", "value": json_value(assignments)}
    for table in FACT_TABLES[1:]:
        value = capture(table, lambda t=table: fetch_display_table_from_session(session, t, max_rows=None))
        if value is not None and (value.capture_status is not RuntimeCaptureStatus.FULL or value.parsed.return_code != 0):
            facts[table]["status"] = "INCOMPLETE_FACTUAL_CAPTURE"
        capture(table+":field_metadata", lambda t=table: fetch_table_field_metadata_from_session(session, t))
    for section in sections:
        capture("rebar_column:"+section, lambda n=section: read_rebar_column_from_session(session, n))
    capture("selected_concrete_design_combos", lambda: acquire_actual_concrete_design_combo_selection_from_context(context=context))
    capture("all_combo_definitions", lambda: capture_all_etabs_combo_definitions_from_session(session))
    pattern_population = capture("load_pattern_population", lambda: read_load_pattern_names_from_session(session))
    if pattern_population is not None:
        for name in pattern_population[0]:
            capture("load_pattern:"+name, lambda n=name: read_load_pattern_type_from_session(session, n))
    case_population = capture("load_case_population", lambda: read_load_case_names_from_session(session))
    if case_population is not None:
        for name in case_population[0]:
            fact = capture("load_case:"+name, lambda n=name: read_load_case_type_from_session(session, n))
            if fact is not None and fact.case_type_code == LINEAR_STATIC_CASE_TYPE_CODE:
                capture("static_linear_loads:"+name, lambda n=name: read_static_linear_case_from_session(session, n))


def run_preflight(*, source, pid, receipt_path):
    if type(pid) is not int or pid <= 0:
        raise ValueError("Exact positive ETABS PID is required")
    source, output = Path(source).resolve(), Path(receipt_path).resolve()
    if output.is_relative_to(REPO_ROOT) or output == source:
        raise ValueError("Receipt must be outside repository and protected source")
    if output.exists() or not output.parent.is_dir():
        raise ValueError("Receipt must be a new file in an existing outside-repo directory")
    receipt = {
        "schema": "COLUMN_R1_R0_R1_READ_ONLY_PREFLIGHT_V1",
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "mode": "READ_ONLY_PREFLIGHT_NOT_R2", "status": "FAIL",
        "source_path": str(source), "expected_source_sha256": FC09_SHA256,
        "exact_pid": pid, "authority": FRAME_SECTION_INERTIA_SOURCE_AUTHORITY_REF,
        "repository": git_anchor(), "section_facts": [], "r0_facts": {},
        "not_captured_by_this_tool": NOT_CAPTURED,
        "R2_READY": False,
        "r2_gate": "NO — until preflight/rebind is reviewed",
        "unit_scope": "Current verified observer m-only; no unit mutation or enum expansion",
        "physical_hash_scope": "Protected disk bytes; no claim of analysis/design freshness or engineering approval",
    }
    session = None
    before = None
    failures = []
    try:
        receipt["source_sha256_before"] = sha256(source)
        if receipt["source_sha256_before"] != FC09_SHA256:
            raise ValueError("Protected source is not the exact FC09 bytes")
        session = attach_verified_to_running_etabs(str(source), pid=pid, allow_pid_fallback=False)
        before = reread_verified_session_identity(session)
        if before != session.identity or before.process_id != pid:
            raise ValueError("Fresh attach identity does not match exact verified session/PID")
        if ntpath.normcase(ntpath.normpath(before.model_full_path)) != ntpath.normcase(ntpath.normpath(str(source))):
            raise ValueError("Active source does not match protected EDB")
        receipt["identity_before"] = before.as_dict()
        print(json.dumps({"program_version": before.program_version,
                          "API_version": before.program_api_version,
                          "present_unit_state": before.units.as_dict()}, sort_keys=True))
        if before.program_version != "23.2.0" or before.program_api_version != 2.014:
            raise ValueError("Unsupported ETABS/API version")
        context = create_trusted_live_acquisition_context(session)
        receipt["r0_context_refs"] = {
            "source_model_ref": context.source_model_identity.source_model_ref,
            "session_ref": context.session_provenance_ref,
            "capture_ref": context.acquisition_context_ref,
            "evidence_epoch_id": context.evidence_epoch_id,
        }
        frame_names, frame_raw = read_frame_names_from_session(session)
        receipt["frame_population"] = {"names": frame_names, "raw": json_value(frame_raw)}
        assignments = fetch_display_table_from_session(session, TABLE_FRAME_ASSIGNMENTS, max_rows=None)
        sections, unassigned = exact_sections(assignments, frame_names)
        receipt["unassigned_frame_names"] = unassigned
        receipt["native_section_scope"] = sections
        if not sections:
            raise ValueError("No factual assigned sections for native proof")
        for section in sections:
            fact = get_frame_section_mechanics_from_session(session, section_name=section)
            entry = json_value(fact)
            entry["raw_response_ref"] = fact.raw_response_ref
            entry["qualified_L4"] = False
            receipt["section_facts"].append(entry)
            if fact.success:
                bindings = [fact.source_unit_for(key, "L4") for key in ("I22", "I33")]
                if any(p.authority_ref != FRAME_SECTION_INERTIA_SOURCE_AUTHORITY_REF or
                       p.authority_kind != "REVIEWED_PROPERTY_SOURCE_SEMANTICS" for p in bindings):
                    raise ValueError("Successful native output lacks exact reviewed L4 authority")
                entry["qualified_L4"] = True
                print(json.dumps({"section": section, "source_model_ref": fact.source_model_ref,
                                  "session_ref": fact.session_ref, "capture_ref": fact.capture_ref,
                                  "raw_response_ref": fact.raw_response_ref,
                                  "bindings": [{"output_key": p.output_key, "source_unit": p.source_unit,
                                                "qualification": p.qualification, "evidence_ref": p.evidence_ref}
                                               for p in bindings]}, sort_keys=True))
            else:
                if fact.unit_provenance:
                    raise ValueError("Nonzero native result must remain unqualified")
                failures.append(f"GetSectProps nonzero for {section}: {fact.return_code}")
        capture_r0(session, context, receipt, assignments, sections)
        receipt["successful_native_count"] = sum(f["qualified_L4"] for f in receipt["section_facts"])
        if not receipt["successful_native_count"]:
            failures.append("No successful qualified native section")
    except Exception as exc:
        failures.append(f"{type(exc).__name__}: {exc}")
    finally:
        if session is not None:
            try:
                after = reread_verified_session_identity(session)
                receipt["identity_after"] = after.as_dict()
                if before is None or after != before or session.identity != before:
                    failures.append("Source/session/present-unit state drift during preflight")
            except Exception as exc:
                failures.append(f"Final identity read failed: {exc}")
            try:
                receipt["gateway_closed"] = session.close()
                if not receipt["gateway_closed"]:
                    failures.append("Gateway did not close cleanly")
            except Exception as exc:
                failures.append(f"Gateway close failed: {exc}")
        try:
            receipt["source_sha256_after"] = sha256(source)
            if receipt["source_sha256_after"] != receipt.get("source_sha256_before"):
                failures.append("Protected EDB hash changed")
        except Exception as exc:
            failures.append(f"Final protected hash failed: {exc}")
        receipt["errors"] = failures
        receipt["status"] = "FAIL" if failures else "PASS_NATIVE_PENDING_R0_REVIEW"
        receipt["finished_utc"] = datetime.now(timezone.utc).isoformat()
        # Exclusive creation prevents accidental receipt replacement.
        with output.open("x", encoding="utf-8") as stream:
            json.dump(json_value(receipt), stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
        print(json.dumps({"status": receipt["status"], "receipt": str(output), "R2_READY": False}))
    return 1 if failures else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--source", required=True, help="Protected exact FC09 EDB path")
    parser.add_argument("--receipt", required=True, help="New JSON file outside repository")
    args = parser.parse_args(argv)
    return run_preflight(source=args.source, pid=args.pid, receipt_path=args.receipt)


if __name__ == "__main__":
    raise SystemExit(main())
