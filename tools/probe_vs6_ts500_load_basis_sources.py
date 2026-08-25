#!/usr/bin/env python
"""Read-only ETABS source discovery for TS500 7.6.2.1 stability load bases.

The probe captures every analysis case whose factual ETABS summary type is
``Linear Static``, then reads its exact ``StaticLinear.GetLoads`` terms and the
factual ETABS load-pattern type of each ``Load`` term.

It does NOT map cases to TS500 G/Q/E/W actions, construct TS500 load
combinations, interpret story-result quantities, run analysis, or classify
sway.  The purpose is to freeze the factual source graph before regulatory
promotion.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tbdy_engine.etabs.safety import read_session_identity
from tbdy_engine.features.etabs_com_attach import ATTACH_STATUS_ATTACHED, attach_to_running_etabs
from tbdy_engine.integration.live_beam_geometry_f0 import model_fingerprint_from_path
from tbdy_engine.json_safe import to_jsonable
from tbdy_engine.providers.etabs_display_table_fetcher import fetch_display_table
from tbdy_engine.providers.etabs_static_linear_case_provider import (
    capture_etabs_static_linear_cases,
)


CASE_SUMMARY_TABLE = "Load Case Definitions - Summary"
SAFETY = {
    "analysis_run": False,
    "design_run": False,
    "model_save": False,
    "model_or_property_mutation": False,
    "present_units_set": False,
    "result_output_selection_changed": False,
}


def _write(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(to_jsonable(payload), ensure_ascii=False, allow_nan=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _linear_static_case_names(database_tables: Any) -> tuple[tuple[str, ...], dict[str, Any]]:
    fetched = fetch_display_table(database_tables, CASE_SUMMARY_TABLE, max_rows=None)
    if fetched.capture_status.value != "FULL":
        raise RuntimeError(
            f"{CASE_SUMMARY_TABLE} requires FULL capture, got {fetched.capture_status.value}"
        )
    if fetched.parsed.return_code not in (0, None):
        raise RuntimeError(
            f"{CASE_SUMMARY_TABLE} nonzero return code {fetched.parsed.return_code}"
        )
    fields = tuple(fetched.parsed.field_keys)
    if "Name" not in fields or "Type" not in fields:
        raise RuntimeError(
            f"{CASE_SUMMARY_TABLE} missing Name/Type fields: {fields!r}"
        )
    rows = tuple(dict(row) for row in fetched.parsed.rows)
    names = tuple(
        str(row["Name"])
        for row in rows
        if row.get("Type") == "Linear Static"
    )
    if not names or len(names) != len(set(names)):
        raise RuntimeError("linear-static case population must be nonempty and unique")
    return names, {
        "table": CASE_SUMMARY_TABLE,
        "capture_status": fetched.capture_status.value,
        "return_code": fetched.parsed.return_code,
        "field_keys": list(fields),
        "row_count_reported": fetched.parsed.row_count_reported,
        "row_count_captured": len(rows),
        "rows": list(rows),
        "selected_signature": dict(fetched.selected_signature),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--expected-model-fingerprint", required=True)
    args = parser.parse_args(argv)

    attach = attach_to_running_etabs()
    if attach.status != ATTACH_STATUS_ATTACHED:
        payload = {
            "status": "BLOCKED_ATTACH",
            "safety": SAFETY,
            "attempts": [item.as_dict() for item in attach.attempts],
        }
        _write(args.out, payload)
        print(json.dumps(to_jsonable(payload), ensure_ascii=False, sort_keys=True))
        return 3

    sap = attach.sap_model
    identity = read_session_identity(attach.etabs_object, sap, attach_strategy=attach.strategy)
    fingerprint = model_fingerprint_from_path(identity.model_full_path)
    if fingerprint != args.expected_model_fingerprint:
        payload = {
            "status": "BLOCKED_MODEL_IDENTITY_MISMATCH",
            "expected_model_fingerprint": args.expected_model_fingerprint,
            "observed_model_fingerprint": fingerprint,
            "model_path": identity.model_full_path,
            "safety": SAFETY,
        }
        _write(args.out, payload)
        print(json.dumps(to_jsonable(payload), ensure_ascii=False, sort_keys=True))
        return 4

    try:
        case_names, case_summary = _linear_static_case_names(sap.DatabaseTables)
        cases = capture_etabs_static_linear_cases(
            sap.LoadCases.StaticLinear,
            sap.LoadPatterns,
            case_names,
        )
    except Exception as exc:
        payload = {
            "status": "BLOCKED_FACTUAL_LOAD_BASIS_SOURCE_DISCOVERY",
            "exception_type": type(exc).__name__,
            "message": str(exc),
            "model": {"path": identity.model_full_path, "fingerprint": fingerprint},
            "safety": SAFETY,
        }
        _write(args.out, payload)
        print(json.dumps(to_jsonable(payload), ensure_ascii=False, sort_keys=True))
        return 5

    payload = {
        "status": "COMPLETE_FACTUAL_LOAD_BASIS_SOURCE_DISCOVERY",
        "model": {
            "path": identity.model_full_path,
            "fingerprint": fingerprint,
            "program_name": identity.program_name,
            "program_version": identity.program_version,
            "database_units": identity.units.database_units,
            "present_units": identity.units.present_units,
        },
        "safety": SAFETY,
        "case_summary": case_summary,
        "linear_static_cases": [item.as_dict() for item in cases],
        "promotion_boundary": {
            "ts500_action_roles_promoted": False,
            "ts500_stability_load_combinations_constructed": False,
            "uncracked_stiffness_basis_promoted": False,
            "sway_classification_promoted": False,
            "engineering_calculation_performed": False,
            "compliance_verdict_emitted": False,
        },
        "next_evidence_questions": (
            "Which factual ETABS load-pattern types participate in each linear-static case?",
            "Can TS500 permanent/live/quake/wind action roles be assigned without case-name inference?",
            "Are both TS500 stability load bases constructible from exact linear-static constituents?",
            "Is a separate uncracked analysis result basis available or is reanalysis required?",
        ),
    }
    _write(args.out, payload)
    print(json.dumps(to_jsonable({
        "status": payload["status"],
        "linear_static_case_count": len(cases),
        "cases": [
            {
                "name": item.name,
                "loads": [
                    {
                        "load_type": term.load_type,
                        "load_name": term.load_name,
                        "scale_factor": term.scale_factor,
                        "pattern_type": None if term.load_pattern is None else term.load_pattern.type_name,
                        "pattern_type_code": None if term.load_pattern is None else term.load_pattern.type_code,
                    }
                    for term in item.loads
                ],
            }
            for item in cases
        ],
        "safety": SAFETY,
    }), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
