#!/usr/bin/env python
"""Read-only live acceptance for TS500 7.6.2.1 stiffness-basis assessment.

The adapter attaches to the exact ETABS model, captures strict RC-frame topology,
projects the assigned concrete-frame I2/I3 modifiers, and asks the pure TS500
stiffness-basis assessment whether those factual modifiers are incompatible
with the uncracked-section basis required by Eq. 7.13.

It does not run analysis, mutate modifiers, classify sway, calculate the
stability index or select reinforcement.
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

from tbdy_engine.design.columns.stability_stiffness_basis import (
    assess_ts500_eq713_stiffness_basis,
)
from tbdy_engine.etabs.safety import read_session_identity
from tbdy_engine.features.etabs_com_attach import ATTACH_STATUS_ATTACHED, attach_to_running_etabs
from tbdy_engine.integration.live_beam_geometry_f0 import model_fingerprint_from_path
from tbdy_engine.json_safe import to_jsonable
from tbdy_engine.providers.etabs_strict_column_topology_provider import (
    capture_etabs_strict_column_topology,
)
from tbdy_engine.providers.strict_topology_stiffness_evidence_provider import (
    build_assigned_rc_frame_bending_modifier_evidence,
)


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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--expected-model-fingerprint", required=True)
    parser.add_argument("--reviewed-length-unit", choices=("m",), required=True)
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
        topology = capture_etabs_strict_column_topology(
            sap.DatabaseTables,
            reviewed_length_unit=args.reviewed_length_unit,
        )
        evidences = build_assigned_rc_frame_bending_modifier_evidence(topology.topology)
        resolution = assess_ts500_eq713_stiffness_basis(evidences)
    except Exception as exc:
        payload = {
            "status": "BLOCKED_TS500_STIFFNESS_BASIS_ASSESSMENT",
            "exception_type": type(exc).__name__,
            "message": str(exc),
            "safety": SAFETY,
        }
        _write(args.out, payload)
        print(json.dumps(to_jsonable(payload), ensure_ascii=False, sort_keys=True))
        return 5

    payload = {
        "status": resolution.status,
        "model": {
            "path": identity.model_full_path,
            "fingerprint": fingerprint,
            "program_name": identity.program_name,
            "program_version": identity.program_version,
        },
        "safety": SAFETY,
        "strict_topology": {
            "authority": topology.authority,
            "summary": topology.topology.summary(),
            "table_row_counts": topology.row_count_map(),
        },
        "assigned_rc_frame_modifier_evidence": [
            {
                "section_name": item.section_name,
                "member_kind": item.member_kind,
                "i2_modifier": item.i2_modifier,
                "i3_modifier": item.i3_modifier,
                "source_refs": list(item.source_refs),
                "authority": item.authority,
            }
            for item in evidences
        ],
        "stiffness_basis_resolution": {
            "status": resolution.status,
            "reanalysis_required": resolution.reanalysis_required,
            "inspected_section_count": resolution.inspected_section_count,
            "inspected_member_kinds": list(resolution.inspected_member_kinds),
            "nonunit_sections": [
                {
                    "section_name": item.section_name,
                    "member_kind": item.member_kind,
                    "i2_modifier": item.i2_modifier,
                    "i3_modifier": item.i3_modifier,
                }
                for item in resolution.nonunit_sections
            ],
            "source_refs": list(resolution.source_refs),
            "authority": resolution.authority,
        },
        "closure_boundary": {
            "assigned_rc_frame_modifiers_bound": True,
            "global_uncracked_basis_promoted": resolution.proves_uncracked,
            "reanalysis_required_emitted": resolution.reanalysis_required,
            "stability_index_calculated": False,
            "sway_classification_promoted": False,
            "engine_selected_rebar_emitted": False,
        },
    }
    _write(args.out, payload)
    print(json.dumps(to_jsonable({
        "status": payload["status"],
        "reanalysis_required": resolution.reanalysis_required,
        "nonunit_sections": [
            {
                "section": item.section_name,
                "kind": item.member_kind,
                "I2Mod": item.i2_modifier,
                "I3Mod": item.i3_modifier,
            }
            for item in resolution.nonunit_sections
        ],
        "safety": SAFETY,
    }), ensure_ascii=False, sort_keys=True))
    # REANALYSIS_REQUIRED is a truthful engineering closure state, not adapter failure.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
