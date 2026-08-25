#!/usr/bin/env python
"""Read-only live acceptance runner for the VS6 strict topology provider.

This proves only factual topology. It does not promote the ETABS end-offset
clear-span candidate to regulatory ``ln``, does not select reinforcement, does
not compute moment/shear capacity, and emits no regulatory PASS/FAIL verdict.
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
from tbdy_engine.features.column_shear_topology import ColumnShearTopologyError
from tbdy_engine.features.etabs_com_attach import ATTACH_STATUS_ATTACHED, attach_to_running_etabs
from tbdy_engine.integration.live_beam_geometry_f0 import model_fingerprint_from_path
from tbdy_engine.json_safe import to_jsonable
from tbdy_engine.providers.etabs_strict_column_topology_provider import (
    capture_etabs_strict_column_topology,
)


def _write(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            to_jsonable(payload),
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
            sort_keys=True,
        ) + "\n",
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--expected-model-fingerprint", required=True)
    parser.add_argument("--reviewed-length-unit", required=True)
    parser.add_argument("--column-name", default="236")
    args = parser.parse_args(argv)

    attach = attach_to_running_etabs()
    if attach.status != ATTACH_STATUS_ATTACHED:
        payload = {
            "status": "BLOCKED_ATTACH",
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
            "observed_model_path": identity.model_full_path,
        }
        _write(args.out, payload)
        print(json.dumps(to_jsonable(payload), ensure_ascii=False, sort_keys=True))
        return 4

    try:
        evidence = capture_etabs_strict_column_topology(
            sap.DatabaseTables,
            reviewed_length_unit=args.reviewed_length_unit,
        )
        topology = evidence.topology
        selected = topology.column(args.column_name)
    except (ColumnShearTopologyError, KeyError) as exc:
        payload = {
            "status": "BLOCKED_STRICT_TOPOLOGY",
            "factual_topology_status": "BLOCKED",
            "message": str(exc),
            "model": {
                "path": identity.model_full_path,
                "fingerprint": fingerprint,
                "program_name": identity.program_name,
                "program_version": identity.program_version,
                "database_units": identity.units.database_units,
                "present_units": identity.units.present_units,
            },
            "safety": {
                "analysis_run": False,
                "design_run": False,
                "model_save": False,
                "model_or_property_mutation": False,
                "present_units_set": False,
            },
        }
        _write(args.out, payload)
        print(json.dumps(to_jsonable(payload), ensure_ascii=False, sort_keys=True))
        return 4

    payload = {
        "status": "COMPLETE",
        "factual_topology_status": "PROVEN",
        "model": {
            "path": identity.model_full_path,
            "fingerprint": fingerprint,
            "program_name": identity.program_name,
            "program_version": identity.program_version,
            "database_units": identity.units.database_units,
            "present_units": identity.units.present_units,
        },
        "safety": {
            "analysis_run": False,
            "design_run": False,
            "model_save": False,
            "model_or_property_mutation": False,
            "present_units_set": False,
        },
        "table_row_counts": evidence.row_count_map(),
        "topology_summary": topology.summary(),
        "selected_column": selected.as_dict(),
        "scope": {
            "regulatory_ln_promoted": False,
            "reinforcement_selected": False,
            "moment_capacity_computed": False,
            "shear_capacity_computed": False,
            "compliance_verdict_emitted": False,
        },
    }
    _write(args.out, payload)
    print(json.dumps(to_jsonable(payload), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
