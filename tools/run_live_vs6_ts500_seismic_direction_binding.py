#!/usr/bin/env python
"""Read-only live acceptance for source-bound TS500 seismic direction binding.

The adapter identifies factual linear-static cases from ETABS case metadata,
promotes atomic QUAKE-pattern cases to TS500 E action sources, captures the
live-proven TSC-2018 auto-seismic direction table, and binds X/Y from exact
ETABS direction flags.  Case names are never parsed for direction.

No analysis/design run, model mutation, load-combination construction, story
result reconstruction, stability-index calculation, sway classification or
reinforcement selection is performed.
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
from tbdy_engine.providers.etabs_auto_seismic_direction_provider import (
    bind_etabs_seismic_action_directions,
    capture_etabs_auto_seismic_direction_evidence,
)
from tbdy_engine.providers.etabs_display_table_fetcher import fetch_display_table
from tbdy_engine.providers.etabs_static_linear_case_provider import capture_etabs_static_linear_cases
from tbdy_engine.providers.etabs_ts500_stability_action_provider import (
    promote_etabs_static_cases_to_ts500_stability_actions,
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


def _linear_static_case_names(database_tables: Any) -> tuple[str, ...]:
    fetched = fetch_display_table(database_tables, CASE_SUMMARY_TABLE, max_rows=None)
    if fetched.capture_status.value != "FULL" or fetched.parsed.return_code not in (0, None):
        raise RuntimeError(f"{CASE_SUMMARY_TABLE} requires successful FULL capture")
    fields = tuple(fetched.parsed.field_keys)
    if "Name" not in fields or "Type" not in fields:
        raise RuntimeError(f"{CASE_SUMMARY_TABLE} missing Name/Type fields: {fields!r}")
    rows = tuple(dict(row) for row in fetched.parsed.rows)
    names = tuple(str(row["Name"]) for row in rows if row.get("Type") == "Linear Static")
    if not names or len(names) != len(set(names)):
        raise RuntimeError("linear-static case population must be nonempty and unique")
    return names


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--expected-model-fingerprint", required=True)
    args = parser.parse_args(argv)

    attach = attach_to_running_etabs()
    if attach.status != ATTACH_STATUS_ATTACHED:
        payload = {"status": "BLOCKED_ATTACH", "safety": SAFETY}
        _write(args.out, payload)
        return 3

    sap = attach.sap_model
    identity = read_session_identity(attach.etabs_object, sap, attach_strategy=attach.strategy)
    fingerprint = model_fingerprint_from_path(identity.model_full_path)
    if fingerprint != args.expected_model_fingerprint:
        payload = {
            "status": "BLOCKED_MODEL_IDENTITY_MISMATCH",
            "expected_model_fingerprint": args.expected_model_fingerprint,
            "observed_model_fingerprint": fingerprint,
            "safety": SAFETY,
        }
        _write(args.out, payload)
        return 4

    try:
        names = _linear_static_case_names(sap.DatabaseTables)
        cases = capture_etabs_static_linear_cases(sap.LoadCases.StaticLinear, sap.LoadPatterns, names)
        action_promotion = promote_etabs_static_cases_to_ts500_stability_actions(cases)
        direction_evidence = capture_etabs_auto_seismic_direction_evidence(sap.DatabaseTables)
        direction_binding = bind_etabs_seismic_action_directions(
            action_promotion.promoted_sources,
            direction_evidence,
        )
    except Exception as exc:
        payload = {
            "status": "BLOCKED_ETABS_SEISMIC_DIRECTION_BINDING",
            "exception_type": type(exc).__name__,
            "message": str(exc),
            "safety": SAFETY,
        }
        _write(args.out, payload)
        print(json.dumps(to_jsonable(payload), ensure_ascii=False, sort_keys=True))
        return 5

    payload = {
        "status": direction_binding.status,
        "model": {
            "path": identity.model_full_path,
            "fingerprint": fingerprint,
            "program_name": identity.program_name,
            "program_version": identity.program_version,
        },
        "safety": SAFETY,
        "action_promotion": action_promotion.as_dict(),
        "direction_evidence": direction_evidence.as_dict(),
        "direction_binding": direction_binding.as_dict(),
        "closure_boundary": {
            "case_names_used_for_direction_inference": False,
            "seismic_direction_bound": direction_binding.complete,
            "wind_direction_bound": False,
            "ts500_stability_load_combinations_constructed": False,
            "story_results_reconstructed": False,
            "uncracked_stiffness_basis_promoted": False,
            "stability_index_calculated": False,
            "sway_classification_promoted": False,
            "engineering_calculation_performed": False,
            "compliance_verdict_emitted": False,
        },
    }
    _write(args.out, payload)
    print(json.dumps(to_jsonable({
        "status": payload["status"],
        "bindings": [item.as_dict() for item in direction_binding.bindings],
        "missing_pattern_names": list(direction_binding.missing_pattern_names),
        "ambiguous_pattern_names": list(direction_binding.ambiguous_pattern_names),
        "safety": SAFETY,
    }), ensure_ascii=False, sort_keys=True))
    # Truthful blocked direction evidence is an engineering closure state, not adapter failure.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
