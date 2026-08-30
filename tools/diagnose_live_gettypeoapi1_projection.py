#!/usr/bin/env python
"""Diagnostic-only live ETABS 23.2.0 ABI capture for LoadCases.GetTypeOAPI_1.

This tool does not decode GetTypeOAPI_1 and does not mutate the ETABS model.
It attaches through the verified safety/gateway session, captures the raw Python
COM projection before interpretation, and writes only type/repr/length evidence.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tbdy_engine.etabs.oapi.load_definitions import read_load_case_names_from_session
from tbdy_engine.etabs.safety import (
    EtabsVerifiedSession,
    _execute_verified_read,
    attach_verified_to_running_etabs,
)

EXPECTED_ETABS_VERSION = "23.2.0"

SAFETY = {
    "analysis_run": False,
    "design_run": False,
    "model_save": False,
    "model_or_property_mutation": False,
    "present_units_set": False,
    "database_tables_selection_changed": False,
    "results_setup_selection_changed": False,
}


def _type_repr(value: object) -> str:
    return repr(type(value))


def _capture_raw_projection(load_cases: Any, case_name: str) -> dict[str, object]:
    # HARD RULE: preserve raw evidence before any semantic decode/reorder/coercion.
    raw = load_cases.GetTypeOAPI_1(case_name)
    raw_repr = repr(raw)
    raw_type = _type_repr(raw)

    try:
        raw_len = len(raw)
    except Exception as exc:
        return {
            "case_name": case_name,
            "python_type_raw": raw_type,
            "raw_repr": raw_repr,
            "len_raw": None,
            "len_exception_type": _type_repr(exc),
            "len_exception_repr": repr(exc),
            "elements": [],
        }

    elements: list[dict[str, object]] = []
    for index in range(raw_len):
        value = raw[index]
        elements.append(
            {
                "index": index,
                "python_type": _type_repr(value),
                "repr": repr(value),
            }
        )

    return {
        "case_name": case_name,
        "python_type_raw": raw_type,
        "len_raw": raw_len,
        "raw_repr": raw_repr,
        "elements": elements,
    }


def _capture_from_session(
    session: EtabsVerifiedSession,
    case_name: str,
) -> dict[str, object]:
    return _execute_verified_read(
        session,
        lambda _app, sap: _capture_raw_projection(sap.LoadCases, case_name),
        operation=f"diagnostic_get_type_oapi_1_raw:{case_name}",
    )


def _unique_in_order(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _write(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-model-path", required=True)
    parser.add_argument("--linear-static-case", required=True)
    parser.add_argument("--modal-case", required=True)
    parser.add_argument("--response-spectrum-case", required=True)
    parser.add_argument(
        "--additional-case",
        action="append",
        default=[],
        help="Additional known case name; may be repeated.",
    )
    parser.add_argument(
        "--no-capture-remaining-cases",
        action="store_true",
        help="By default every remaining LoadCases.GetNameList entry is also captured.",
    )
    parser.add_argument("--pid", type=int)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)

    session = attach_verified_to_running_etabs(
        args.expected_model_path,
        pid=args.pid,
    )
    try:
        identity = session.identity
        if identity.program_version != EXPECTED_ETABS_VERSION:
            payload: dict[str, object] = {
                "status": "BLOCKED_ETABS_VERSION_MISMATCH",
                "expected_etabs_version": EXPECTED_ETABS_VERSION,
                "observed_etabs_version": identity.program_version,
                "model_path": identity.model_full_path,
                "safety": SAFETY,
            }
            _write(args.out, payload)
            print(json.dumps(payload, ensure_ascii=False))
            return 4

        all_case_names, name_list_raw = read_load_case_names_from_session(session)
        all_case_name_set = set(all_case_names)

        role_cases = {
            "linear_static": args.linear_static_case,
            "modal": args.modal_case,
            "response_spectrum": args.response_spectrum_case,
        }
        requested = [
            args.linear_static_case,
            args.modal_case,
            args.response_spectrum_case,
            *args.additional_case,
        ]
        missing = [name for name in requested if name not in all_case_name_set]
        if missing:
            payload = {
                "status": "BLOCKED_REQUIRED_CASE_NOT_FOUND",
                "missing_case_names": missing,
                "available_case_names": list(all_case_names),
                "load_cases_get_name_list_raw_repr": repr(name_list_raw),
                "model_path": identity.model_full_path,
                "program_version": identity.program_version,
                "safety": SAFETY,
            }
            _write(args.out, payload)
            print(json.dumps(payload, ensure_ascii=False))
            return 5

        capture_names = list(requested)
        if not args.no_capture_remaining_cases:
            capture_names.extend(all_case_names)
        capture_names = _unique_in_order(capture_names)

        records: list[dict[str, object]] = []
        role_by_name = {value: key for key, value in role_cases.items()}
        for case_name in capture_names:
            record = _capture_from_session(session, case_name)
            # Label comes from operator-supplied known category, never raw tuple inference.
            record["operator_known_role"] = role_by_name.get(case_name)
            records.append(record)

        payload = {
            "status": "COMPLETE_RAW_GETTYPEOAPI1_PROJECTION_CAPTURE",
            "candidate_sha_expected": "1fbbe441dd025bc93da39c3915d3d7be34dc2172",
            "model": {
                "path": identity.model_full_path,
                "program_name": identity.program_name,
                "program_version": identity.program_version,
                "process_id": identity.process_id,
                "attach_strategy": identity.attach_strategy,
            },
            "documented_signature": {
                "method": "SapModel.LoadCases.GetTypeOAPI_1",
                "semantic_ref_outputs": [
                    "CaseType",
                    "SubType",
                    "DesignType",
                    "DesignTypeOption",
                    "Auto",
                ],
                "return": "ret",
            },
            "safety": SAFETY,
            "required_operator_known_cases": role_cases,
            "load_cases_get_name_list_raw_repr": repr(name_list_raw),
            "capture_count": len(records),
            "records": records,
            "decoder_invoked": False,
            "projection_interpreted": False,
        }
        _write(args.out, payload)
        print(json.dumps(payload, ensure_ascii=False))
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
