#!/usr/bin/env python
"""Read-only acceptance adapter for ETABS column reinforcement design intent.

The production provider owns ``GetRebarColumn`` decoding and authority labeling.
This tool only attaches to the exact reviewed model, captures one section's
factual rebar intent, serializes it and exits. It performs no capacity,
reinforcement selection, compliance check, ETABS design or model mutation.
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

from tbdy_engine.etabs.safety import read_session_identity
from tbdy_engine.features.etabs_com_attach import ATTACH_STATUS_ATTACHED, attach_to_running_etabs
from tbdy_engine.integration.live_beam_geometry_f0 import model_fingerprint_from_path
from tbdy_engine.json_safe import to_jsonable
from tbdy_engine.providers.etabs_column_rebar_intent_provider import (
    capture_etabs_column_rebar_intent,
)


SAFETY = {
    "analysis_run": False,
    "design_run": False,
    "model_save": False,
    "model_or_property_mutation": False,
    "present_units_set": False,
    "result_output_selection_changed": False,
    "reinforcement_selected": False,
    "section_capacity_computed": False,
    "compliance_verdict_emitted": False,
}


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(to_jsonable(payload), ensure_ascii=False, allow_nan=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--expected-model-fingerprint", required=True)
    parser.add_argument("--section-name", required=True)
    parser.add_argument("--reviewed-length-unit", choices=("m", "mm"), required=True)
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
        intent = capture_etabs_column_rebar_intent(
            sap.PropFrame,
            args.section_name,
            reviewed_length_unit=args.reviewed_length_unit,
        )
    except Exception as exc:
        payload = {
            "status": "BLOCKED_COLUMN_REBAR_INTENT_CAPTURE",
            "exception_type": type(exc).__name__,
            "message": str(exc),
            "model": {"path": identity.model_full_path, "fingerprint": fingerprint},
            "safety": SAFETY,
        }
        _write(args.out, payload)
        print(json.dumps(to_jsonable(payload), ensure_ascii=False, sort_keys=True))
        return 5

    payload = {
        "status": "COMPLETE_FACTUAL_COLUMN_REBAR_INTENT_PROBE",
        "model": {
            "path": identity.model_full_path,
            "fingerprint": fingerprint,
            "program_name": identity.program_name,
            "program_version": identity.program_version,
            "database_units": identity.units.database_units,
            "present_units": identity.units.present_units,
        },
        "safety": SAFETY,
        "rebar_intent": intent.as_dict(),
        "scope": {
            "etabs_section_rebar_intent_proven": True,
            "intent_promoted_to_provided_rebar": False,
            "intent_promoted_to_engine_selected_rebar": False,
            "reinforcement_selected": False,
        },
    }
    _write(args.out, payload)
    print(json.dumps(to_jsonable({
        "status": payload["status"],
        "section_name": intent.section_name,
        "authority": intent.authority,
        "cover_mm": intent.cover_mm,
        "rebar_size_name": intent.rebar_size_name,
        "tie_size_name": intent.tie_size_name,
        "to_be_designed": intent.to_be_designed,
        "safety": SAFETY,
    }), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
