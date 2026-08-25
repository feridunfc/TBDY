#!/usr/bin/env python
"""Read-only live acceptance adapter for the factual ETABS rebar catalog.

The production provider performs the display-table acquisition. This tool only
attaches to the reviewed model, verifies its fingerprint, serializes the factual
``Reinforcing Bar Sizes`` evidence and exits. No bar-field semantics, design
candidate generation, section capacity or reinforcement selection is performed.
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
from tbdy_engine.providers.etabs_rebar_catalog_provider import capture_etabs_rebar_catalog_evidence


SAFETY = {
    "analysis_run": False,
    "design_run": False,
    "model_save": False,
    "model_or_property_mutation": False,
    "present_units_set": False,
    "result_output_selection_changed": False,
    "reinforcement_selected": False,
    "section_capacity_computed": False,
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
        evidence = capture_etabs_rebar_catalog_evidence(sap.DatabaseTables)
    except Exception as exc:
        payload = {
            "status": "BLOCKED_REBAR_CATALOG_CAPTURE",
            "exception_type": type(exc).__name__,
            "message": str(exc),
            "model": {"path": identity.model_full_path, "fingerprint": fingerprint},
            "safety": SAFETY,
        }
        _write(args.out, payload)
        print(json.dumps(to_jsonable(payload), ensure_ascii=False, sort_keys=True))
        return 5

    payload = {
        "status": "COMPLETE_FACTUAL_REBAR_CATALOG_PROBE",
        "model": {
            "path": identity.model_full_path,
            "fingerprint": fingerprint,
            "program_name": identity.program_name,
            "program_version": identity.program_version,
            "database_units": identity.units.database_units,
            "present_units": identity.units.present_units,
        },
        "safety": SAFETY,
        "catalog_evidence": evidence.as_dict(),
        "scope": {
            "factual_rebar_catalog_table_proven": True,
            "catalog_field_semantics_promoted": False,
            "column_longitudinal_bar_catalog_promoted": False,
            "reinforcement_selected": False,
        },
    }
    _write(args.out, payload)
    print(json.dumps(to_jsonable({
        "status": payload["status"],
        "field_keys": list(evidence.field_keys),
        "row_count": len(evidence.rows),
        "safety": SAFETY,
    }), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
