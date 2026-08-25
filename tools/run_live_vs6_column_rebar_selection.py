#!/usr/bin/env python
"""Read-only live acceptance runner for VS6 P4-P6 column rebar selection.

The runner never starts ETABS analysis/design, never saves the model, and never
mutates model properties.  ENGINE_SELECTED_REBAR is emitted only when all four
reviewed design-demand basis gates are explicitly RESOLVED on the command line.
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

from tbdy_engine.design.columns.rebar_layout import (
    ColumnRebarLayoutInputs,
    generate_rectangular_column_rebar_candidates,
)
from tbdy_engine.design.columns.rebar_selection import (
    ColumnDemandBasis,
    ColumnRebarSelectionPolicy,
    ETABS_AXIAL_SIGN_NEGATIVE_COMPRESSION,
    normalize_etabs_column_end_demands,
    select_engine_rebar_for_demands,
)
from tbdy_engine.design.columns.section_capacity import ColumnSectionMaterial
from tbdy_engine.etabs.safety import read_session_identity
from tbdy_engine.features.etabs_com_attach import ATTACH_STATUS_ATTACHED, attach_to_running_etabs
from tbdy_engine.features.etabs_column_axial_evidence import (
    ColumnAxialEvidenceError,
    capture_live_column_axial_evidence,
)
from tbdy_engine.integration.live_beam_geometry_f0 import model_fingerprint_from_path
from tbdy_engine.json_safe import to_jsonable
from tbdy_engine.product_reports.vs6_rebar_layout_report import build_vs6_rebar_layout_report
from tbdy_engine.product_reports.vs6_rebar_selection_report import build_vs6_rebar_selection_report


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


def _csv_floats(value: str) -> tuple[float, ...]:
    try:
        items = tuple(float(item.strip()) for item in value.split(",") if item.strip())
    except ValueError as exc:
        raise argparse.ArgumentTypeError("bar diameters must be numeric") from exc
    if not items or len(items) != len(set(items)):
        raise argparse.ArgumentTypeError("bar diameters must be a nonempty unique list")
    return items


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(to_jsonable(payload), ensure_ascii=False, allow_nan=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _selection_dict(result: Any) -> dict[str, Any]:
    selected = result.selected_candidate
    return {
        "component_id": result.component_id,
        "status": result.status,
        "authority": result.authority,
        "required_as_in_candidate_family_mm2": result.required_as_in_candidate_family_mm2,
        "governing_state_id": result.governing_state_id,
        "governing_utilization": result.governing_utilization,
        "selected_candidate": None if selected is None else {
            "candidate_id": selected.candidate_id,
            "bar_count": selected.bar_count,
            "bar_diameter_mm": selected.bar_diameter_mm,
            "as_total_mm2": selected.as_total_mm2,
            "rho_pct": selected.rho_pct,
            "n_bars_dir2": selected.n_bars_dir2,
            "n_bars_dir3": selected.n_bars_dir3,
            "layout_tie_diameter_dependency_mm": None,
        },
        "trials": [asdict(item) for item in result.trials],
        "selected_evaluations": [
            {
                "state": asdict(item.state),
                "radial_capacity_nmm": item.radial_capacity_nmm,
                "utilization": item.utilization,
                "status": item.status,
            }
            for item in result.selected_evaluations
        ],
        "basis": asdict(result.basis),
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
    parser.add_argument("--reviewed-clear-cover-mm", type=float, required=True)
    parser.add_argument("--reviewed-layout-tie-diameter-mm", type=float, required=True)
    parser.add_argument("--reviewed-aggregate-max-mm", type=float, required=True)
    parser.add_argument("--reviewed-bar-diameters-mm", type=_csv_floats, required=True)
    parser.add_argument("--reviewed-fcd-mpa", type=float, required=True)
    parser.add_argument("--reviewed-fyd-mpa", type=float, required=True)
    parser.add_argument("--expected-fck-mpa", type=float, required=True)

    for name in (
        "analysis-order-status",
        "minimum-eccentricity-status",
        "slenderness-status",
        "combination-scope-status",
    ):
        parser.add_argument(f"--{name}", choices=("RESOLVED", "BLOCKED"), required=True)
    parser.add_argument("--angle-count", type=int, required=True)
    parser.add_argument("--axial-tolerance-kn", type=float, required=True)
    args = parser.parse_args(argv)

    attach = attach_to_running_etabs()
    if attach.status != ATTACH_STATUS_ATTACHED:
        payload = {"status": "BLOCKED_ATTACH", "safety": SAFETY, "attempts": [item.as_dict() for item in attach.attempts]}
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

    basis = ColumnDemandBasis(
        analysis_order_status=args.analysis_order_status,
        minimum_eccentricity_status=args.minimum_eccentricity_status,
        slenderness_status=args.slenderness_status,
        combination_scope_status=args.combination_scope_status,
        review_refs=("VS6 live acceptance explicit CLI demand-basis declaration",),
    )

    try:
        evidence = capture_live_column_axial_evidence(
            database_tables=sap.DatabaseTables,
            model_fingerprint=fingerprint,
            output_names=args.outputs,
            reviewed_force_unit=args.reviewed_force_unit,
            reviewed_length_unit=args.reviewed_length_unit,
            reviewed_concrete_fc_unit=args.reviewed_concrete_fc_unit,
            review_refs=("VS6 live acceptance explicit CLI unit/source contract",),
            provenance_refs=(f"model:{fingerprint}",),
        )
    except ColumnAxialEvidenceError as exc:
        payload = {"status": "BLOCKED_FACTUAL_CAPTURE", "message": str(exc), "safety": SAFETY}
        _write(args.out, payload)
        print(json.dumps(to_jsonable(payload), ensure_ascii=False, sort_keys=True))
        return 5

    columns = evidence.columns if args.all_columns else (evidence.column(args.column_name),)
    force_rows = tuple(dict(row) for row in evidence.forces.rows)
    results: list[dict[str, Any]] = []
    reports: list[dict[str, Any]] = []

    try:
        for column in columns:
            if abs(column.fck_mpa - args.expected_fck_mpa) > 1e-9:
                raise ValueError(
                    f"fck mismatch for {column.component_id}: observed={column.fck_mpa:g} expected={args.expected_fck_mpa:g}"
                )
            layout_inputs = ColumnRebarLayoutInputs(
                width_mm=column.width_m * 1000.0,
                depth_mm=column.depth_m * 1000.0,
                clear_cover_mm=args.reviewed_clear_cover_mm,
                tie_diameter_mm=args.reviewed_layout_tie_diameter_mm,
                aggregate_max_mm=args.reviewed_aggregate_max_mm,
                allowed_bar_diameters_mm=args.reviewed_bar_diameters_mm,
            )
            population = generate_rectangular_column_rebar_candidates(layout_inputs)
            demands = normalize_etabs_column_end_demands(
                force_rows,
                unique_name=column.unique_name,
                component_id=column.component_id,
                reviewed_force_unit=args.reviewed_force_unit,
                reviewed_moment_unit=args.reviewed_moment_unit,
                axial_sign_policy=ETABS_AXIAL_SIGN_NEGATIVE_COMPRESSION,
            )
            result = select_engine_rebar_for_demands(
                component_id=column.component_id,
                width_mm=layout_inputs.width_mm,
                depth_mm=layout_inputs.depth_mm,
                population=population,
                material=ColumnSectionMaterial(
                    fck_mpa=column.fck_mpa,
                    fcd_mpa=args.reviewed_fcd_mpa,
                    fyd_mpa=args.reviewed_fyd_mpa,
                ),
                demands=demands,
                basis=basis,
                policy=ColumnRebarSelectionPolicy(
                    angle_count=args.angle_count,
                    axial_tolerance_n=args.axial_tolerance_kn * 1000.0,
                ),
            )
            result_dict = _selection_dict(result)
            if result_dict["selected_candidate"] is not None:
                result_dict["selected_candidate"]["layout_tie_diameter_dependency_mm"] = args.reviewed_layout_tie_diameter_mm
            results.append(result_dict)
            reports.append(
                {
                    "layout": build_vs6_rebar_layout_report(
                        component_id=column.component_id,
                        section_name=column.section,
                        population=population,
                    ).as_dict(),
                    "selection": build_vs6_rebar_selection_report(result).as_dict(),
                }
            )
    except Exception as exc:
        payload = {
            "status": "BLOCKED_SELECTION_EXECUTION",
            "exception_type": type(exc).__name__,
            "message": str(exc),
            "model": {"path": identity.model_full_path, "fingerprint": fingerprint},
            "safety": SAFETY,
        }
        _write(args.out, payload)
        print(json.dumps(to_jsonable(payload), ensure_ascii=False, sort_keys=True))
        return 6

    counts: dict[str, int] = {}
    for result in results:
        counts[result["status"]] = counts.get(result["status"], 0) + 1
    if not basis.is_resolved:
        status = "COMPLETE_BLOCKED_DEMAND_BASIS"
        rc = 7
    elif counts.get("SELECTED", 0) == len(results):
        status = "COMPLETE_ENGINE_SELECTED_REBAR"
        rc = 0
    else:
        status = "COMPLETE_WITH_UNSELECTED_COLUMNS"
        rc = 8

    payload = {
        "status": status,
        "model": {
            "path": identity.model_full_path,
            "fingerprint": fingerprint,
            "program_name": identity.program_name,
            "program_version": identity.program_version,
            "database_units": identity.units.database_units,
            "present_units": identity.units.present_units,
        },
        "safety": SAFETY,
        "evidence_epoch_id": evidence.evidence_epoch_id,
        "reviewed_inputs": {
            "outputs": list(args.outputs),
            "clear_cover_mm": args.reviewed_clear_cover_mm,
            "layout_tie_diameter_mm": args.reviewed_layout_tie_diameter_mm,
            "aggregate_max_mm": args.reviewed_aggregate_max_mm,
            "bar_diameters_mm": list(args.reviewed_bar_diameters_mm),
            "fcd_mpa": args.reviewed_fcd_mpa,
            "fyd_mpa": args.reviewed_fyd_mpa,
            "expected_fck_mpa": args.expected_fck_mpa,
            "angle_count": args.angle_count,
            "axial_tolerance_kn": args.axial_tolerance_kn,
            "demand_basis": asdict(basis),
        },
        "summary": {
            "column_count": len(results),
            "status_counts": counts,
            "engine_selected_rebar_count": counts.get("SELECTED", 0),
            "final_or_provided_rebar_count": 0,
            "transverse_links_selected": False,
            "final_column_shear_compliance_emitted": False,
        },
        "results": results,
        "report_contributions": reports,
    }
    _write(args.out, payload)
    print(json.dumps(to_jsonable({"status": status, "summary": payload["summary"], "safety": SAFETY}), ensure_ascii=False, sort_keys=True))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
