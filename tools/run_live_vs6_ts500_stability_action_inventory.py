#!/usr/bin/env python
"""Read-only live acceptance for TS500 7.6.2.1 stability action inventory.

The adapter acquires factual ETABS linear-static case loads and the complete
load-pattern catalog, promotes the narrow source-bound ETABS pattern-type to
TS500 G/Q/E/W mapping, and resolves the two symbolic TS500 Eq.7.13 load-basis
inventories.

It does not bind E/W directions, read story result quantities, run analysis,
claim an uncracked stiffness basis, calculate phi, or classify sway.
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

from tbdy_engine.design.columns.stability_action_basis import (
    resolve_ts500_stability_load_inventory,
)
from tbdy_engine.etabs.safety import read_session_identity
from tbdy_engine.features.etabs_com_attach import ATTACH_STATUS_ATTACHED, attach_to_running_etabs
from tbdy_engine.integration.live_beam_geometry_f0 import model_fingerprint_from_path
from tbdy_engine.json_safe import to_jsonable
from tbdy_engine.providers.etabs_display_table_fetcher import fetch_display_table
from tbdy_engine.providers.etabs_load_pattern_catalog_provider import (
    capture_etabs_load_pattern_catalog,
)
from tbdy_engine.providers.etabs_static_linear_case_provider import (
    capture_etabs_static_linear_cases,
)
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


def _template_dict(template: Any) -> dict[str, Any]:
    return {
        "load_basis": template.load_basis,
        "status": template.status,
        "coefficients": dict(template.coefficients),
        "candidate_case_names_by_role": {
            role: list(names) for role, names in template.candidate_case_names_by_role.items()
        },
        "missing_roles": list(template.missing_roles),
        "direction_binding_required_roles": list(template.direction_binding_required_roles),
        "action_inventory_complete": template.action_inventory_complete,
        "direction_binding_complete": template.direction_binding_complete,
        "source_refs": list(template.source_refs),
        "authority": template.authority,
    }


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
        pattern_catalog = capture_etabs_load_pattern_catalog(sap.LoadPatterns)
        promotion = promote_etabs_static_cases_to_ts500_stability_actions(cases)
        inventory = resolve_ts500_stability_load_inventory(promotion.promoted_sources)
    except Exception as exc:
        payload = {
            "status": "BLOCKED_TS500_STABILITY_ACTION_INVENTORY",
            "exception_type": type(exc).__name__,
            "message": str(exc),
            "safety": SAFETY,
        }
        _write(args.out, payload)
        print(json.dumps(to_jsonable(payload), ensure_ascii=False, sort_keys=True))
        return 5

    payload = {
        "status": inventory.status,
        "model": {
            "path": identity.model_full_path,
            "fingerprint": fingerprint,
            "program_name": identity.program_name,
            "program_version": identity.program_version,
        },
        "safety": SAFETY,
        "factual_load_pattern_catalog": pattern_catalog.as_dict(),
        "factual_linear_static_cases": [item.as_dict() for item in cases],
        "action_promotion": promotion.as_dict(),
        "inventory": {
            "status": inventory.status,
            "gqe": _template_dict(inventory.gqe),
            "gqw": _template_dict(inventory.gqw),
            "authority": inventory.authority,
        },
        "closure_boundary": {
            "case_names_used_for_role_inference": False,
            "seismic_direction_bound": False,
            "wind_direction_bound": False,
            "story_results_reconstructed": False,
            "uncracked_stiffness_basis_promoted": False,
            "stability_index_calculated": False,
            "sway_classification_promoted": False,
        },
    }
    _write(args.out, payload)
    print(json.dumps(to_jsonable({
        "status": payload["status"],
        "patterns": [
            {"name": item.name, "type": item.type_name, "code": item.type_code}
            for item in pattern_catalog.patterns
        ],
        "promoted_actions": [
            {"case": item.case_name, "pattern": item.pattern_name, "role": item.action_role}
            for item in promotion.promoted_sources
        ],
        "gqe": _template_dict(inventory.gqe),
        "gqw": _template_dict(inventory.gqw),
        "safety": SAFETY,
    }), ensure_ascii=False, sort_keys=True))
    # A blocked inventory is a truthful engineering closure state, not adapter failure.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
