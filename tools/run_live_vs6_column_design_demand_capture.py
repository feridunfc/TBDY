#!/usr/bin/env python
"""Read-only live factual P-M2-M3 acceptance runner for VS6 column design demand.

This runner deliberately stops before reviewed demand-basis resolution,
reinforcement candidate generation, section capacity, or ENGINE_SELECTED_REBAR.
It exists so ETABS result acquisition and exact end-demand normalization can be
accepted independently of project-specific design assumptions.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tbdy_engine.design.columns.rebar_selection import (
    ETABS_AXIAL_SIGN_NEGATIVE_COMPRESSION,
    normalize_etabs_column_end_demands,
)
from tbdy_engine.etabs.safety import read_session_identity
from tbdy_engine.features.column_design_demand_evidence import (
    ColumnDesignDemandEvidenceError,
    build_column_design_demand_evidence,
)
from tbdy_engine.features.etabs_com_attach import ATTACH_STATUS_ATTACHED, attach_to_running_etabs
from tbdy_engine.features.etabs_column_axial_evidence import (
    ColumnAxialEvidenceError,
    capture_live_column_axial_evidence,
)
from tbdy_engine.integration.live_beam_geometry_f0 import model_fingerprint_from_path
from tbdy_engine.json_safe import to_jsonable


SAFETY = {
    "analysis_run": False,
    "design_run": False,
    "model_save": False,
    "model_or_property_mutation": False,
    "present_units_set": False,
    "result_output_selection": "REVERSIBLE_TRANSACTION_ONLY",
}


def _csv_strings(value: str) -> tuple[str, ...]:
    items = tuple(item.strip() for item in value.split(",") if item.strip())
    if not items or len(items) != len(set(items)):
        raise argparse.ArgumentTypeError("value must contain a nonempty unique comma-separated list")
    return items


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(to_jsonable(payload), ensure_ascii=False, allow_nan=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _demand_dict(item: Any) -> dict[str, Any]:
    return {
        "state_id": item.state_id,
        "component_id": item.component_id,
        "output_case": item.output_case,
        "case_type": item.case_type,
        "step_type": item.step_type,
        "step_number": item.step_number,
        "station_m": item.station_m,
        "end_tag": item.end_tag,
        "nd_compression_kn": item.nd_compression_n / 1000.0,
        "m2_knm": item.m2_nmm / 1_000_000.0,
        "m3_knm": item.m3_nmm / 1_000_000.0,
        "moment_magnitude_knm": item.moment_magnitude_nmm / 1_000_000.0,
        "source_identity": item.source_identity,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--expected-model-fingerprint", required=True)
    parser.add_argument("--outputs", type=_csv_strings, required=True)
    parser.add_argument("--column-name", default="236", help="UniqueName; ignored with --all-columns")
    parser.add_argument("--all-columns", action="store_true")
    parser.add_argument("--reviewed-force-unit", choices=("kN",), required=True)
    parser.add_argument("--reviewed-moment-unit", choices=("kN-m",), required=True)
    parser.add_argument("--reviewed-length-unit", choices=("m",), required=True)
    parser.add_argument("--reviewed-concrete-fc-unit", choices=("kPa",), required=True)
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
        acquired = capture_live_column_axial_evidence(
            database_tables=sap.DatabaseTables,
            model_fingerprint=fingerprint,
            output_names=args.outputs,
            reviewed_force_unit=args.reviewed_force_unit,
            reviewed_length_unit=args.reviewed_length_unit,
            reviewed_concrete_fc_unit=args.reviewed_concrete_fc_unit,
            review_refs=("VS6 factual P-M2-M3 live capture explicit CLI unit/source contract",),
            provenance_refs=(f"model:{fingerprint}",),
        )
        design_evidence = build_column_design_demand_evidence(
            model_fingerprint=fingerprint,
            rows=acquired.forces.rows,
            output_names=args.outputs,
            reviewed_force_unit=args.reviewed_force_unit,
            reviewed_moment_unit=args.reviewed_moment_unit,
        )
    except (ColumnAxialEvidenceError, ColumnDesignDemandEvidenceError) as exc:
        payload = {
            "status": "BLOCKED_FACTUAL_CAPTURE",
            "exception_type": type(exc).__name__,
            "message": str(exc),
            "safety": SAFETY,
        }
        _write(args.out, payload)
        print(json.dumps(to_jsonable(payload), ensure_ascii=False, sort_keys=True))
        return 5

    columns = acquired.columns if args.all_columns else (acquired.column(args.column_name),)
    rows = tuple(dict(row) for row in design_evidence.rows)
    results: list[dict[str, Any]] = []
    try:
        for column in columns:
            demands = normalize_etabs_column_end_demands(
                rows,
                unique_name=column.unique_name,
                component_id=column.component_id,
                reviewed_force_unit=args.reviewed_force_unit,
                reviewed_moment_unit=args.reviewed_moment_unit,
                axial_sign_policy=ETABS_AXIAL_SIGN_NEGATIVE_COMPRESSION,
            )
            demand_dicts = [_demand_dict(item) for item in demands]
            max_moment = max(demand_dicts, key=lambda item: item["moment_magnitude_knm"])
            max_compression = max(demand_dicts, key=lambda item: item["nd_compression_kn"])
            min_compression = min(demand_dicts, key=lambda item: item["nd_compression_kn"])
            results.append(
                {
                    "component_id": column.component_id,
                    "UniqueName": column.unique_name,
                    "Story": column.story,
                    "Column": column.column_label,
                    "Section": column.section,
                    "Material": column.material,
                    "width_m": column.width_m,
                    "depth_m": column.depth_m,
                    "fck_mpa": column.fck_mpa,
                    "demand_state_count": len(demand_dicts),
                    "max_moment_state": max_moment,
                    "max_compression_state": max_compression,
                    "min_compression_state": min_compression,
                    "demands": demand_dicts,
                }
            )
    except Exception as exc:
        payload = {
            "status": "BLOCKED_DEMAND_NORMALIZATION",
            "exception_type": type(exc).__name__,
            "message": str(exc),
            "model": {"path": identity.model_full_path, "fingerprint": fingerprint},
            "safety": SAFETY,
        }
        _write(args.out, payload)
        print(json.dumps(to_jsonable(payload), ensure_ascii=False, sort_keys=True))
        return 6

    payload = {
        "status": "COMPLETE_FACTUAL_COLUMN_DESIGN_DEMAND",
        "factual_design_demand_status": "PROVEN",
        "model": {
            "path": identity.model_full_path,
            "fingerprint": fingerprint,
            "program_name": identity.program_name,
            "program_version": identity.program_version,
            "database_units": identity.units.database_units,
            "present_units": identity.units.present_units,
        },
        "safety": SAFETY,
        "source": {
            "table": design_evidence.source_table,
            "output_names": list(design_evidence.output_names),
            "force_unit": design_evidence.force_unit,
            "moment_unit": design_evidence.moment_unit,
            "raw_exact_row_count": len(design_evidence.rows),
            "evidence_epoch_id": design_evidence.evidence_epoch_id,
        },
        "column_count": len(results),
        "columns": results,
        "scope": {
            "combination_scope_resolved": False,
            "analysis_order_resolved": False,
            "minimum_eccentricity_resolved": False,
            "slenderness_resolved": False,
            "reinforcement_candidate_generated": False,
            "reinforcement_selected": False,
            "section_capacity_computed": False,
            "compliance_verdict_emitted": False,
        },
    }
    _write(args.out, payload)
    print(json.dumps(to_jsonable(payload), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
