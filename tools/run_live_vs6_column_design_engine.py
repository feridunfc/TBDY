#!/usr/bin/env python
"""Read-only live acceptance adapter for the integrated VS6 column design engine.

The adapter acquires factual ETABS combo definitions, constituent/observed
P-M2-M3 rows, column geometry/material facts, the factual reinforcing-bar
catalog, and factual column-section rebar design intent. Engineering pattern
classification, response-spectrum design-state promotion and longitudinal-rebar
selection are delegated to production engine modules.

The ETABS section rebar intent supplies layout seed geometry (clear cover and
named tie size resolved through the factual bar catalog) but is never promoted
to provided/final reinforcement. Maximum aggregate size remains an explicit
project input because it is not inferred from ETABS.

No ETABS analysis/design is started, no model property is changed, no present
unit is set and the model is never saved.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tbdy_engine.design.columns.column_design_demand_engine import ColumnComboDefinition
from tbdy_engine.design.columns.column_design_engine import evaluate_column_design
from tbdy_engine.design.columns.column_rebar_design_engine import ColumnRebarDesignInputs
from tbdy_engine.design.columns.combo_pattern_engine import ComboPatternConstituent
from tbdy_engine.design.columns.rebar_layout_seed import resolve_column_rebar_layout_seed
from tbdy_engine.design.columns.rebar_selection import (
    ColumnDemandBasis,
    ColumnRebarSelectionPolicy,
    ETABS_AXIAL_SIGN_NEGATIVE_COMPRESSION,
    normalize_etabs_column_end_demands,
)
from tbdy_engine.design.columns.section_capacity import ColumnSectionMaterial
from tbdy_engine.etabs.safety import read_session_identity
from tbdy_engine.features.column_design_demand_evidence import build_column_design_demand_evidence
from tbdy_engine.features.etabs_com_attach import ATTACH_STATUS_ATTACHED, attach_to_running_etabs
from tbdy_engine.features.etabs_column_axial_evidence import capture_live_column_axial_evidence
from tbdy_engine.integration.live_beam_geometry_f0 import model_fingerprint_from_path
from tbdy_engine.json_safe import to_jsonable
from tbdy_engine.product_reports.vs6_column_design_engine_report import (
    build_vs6_column_design_engine_reports,
)
from tbdy_engine.providers.etabs_column_rebar_intent_provider import (
    capture_etabs_column_rebar_intent,
)
from tbdy_engine.providers.etabs_combo_definition_provider import (
    EtabsComboDefinitionEvidence,
    capture_etabs_combo_definitions,
)
from tbdy_engine.providers.etabs_rebar_catalog_provider import (
    capture_etabs_rebar_catalog_evidence,
    promote_etabs_rebar_catalog,
)


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
        raise argparse.ArgumentTypeError("requires a nonempty unique comma-separated list")
    return items


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(to_jsonable(payload), ensure_ascii=False, allow_nan=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _all_load_case_names(definitions: Iterable[EtabsComboDefinitionEvidence]) -> tuple[str, ...]:
    """Return factual LOAD_CASE names from the recursively captured combo topology."""
    names: list[str] = []

    def visit(item: EtabsComboDefinitionEvidence) -> None:
        for term in item.constituents:
            if term.cname_type == "LOAD_CASE" and term.name not in names:
                names.append(term.name)
        for child in item.nested_combos:
            visit(child)

    for definition in definitions:
        visit(definition)
    return tuple(names)


def _engine_definition(item: EtabsComboDefinitionEvidence) -> ColumnComboDefinition:
    return ColumnComboDefinition(
        name=item.name,
        combo_type=item.combo_type,
        constituents=tuple(
            ComboPatternConstituent(
                name=term.name,
                scale_factor=term.scale_factor,
                cname_type=term.cname_type,
            )
            for term in item.constituents
        ),
    )


def _blocked_payload(status: str, exc: Exception, *, identity: Any, fingerprint: str) -> dict[str, Any]:
    return {
        "status": status,
        "exception_type": type(exc).__name__,
        "message": str(exc),
        "model": {"path": identity.model_full_path, "fingerprint": fingerprint},
        "safety": SAFETY,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--expected-model-fingerprint", required=True)
    parser.add_argument("--combos", type=_csv_strings, required=True)
    parser.add_argument("--column-name", default="236", help="UniqueName; ignored with --all-columns")
    parser.add_argument("--all-columns", action="store_true")

    parser.add_argument("--reviewed-force-unit", choices=("kN",), required=True)
    parser.add_argument("--reviewed-moment-unit", choices=("kN-m",), required=True)
    parser.add_argument("--reviewed-length-unit", choices=("m", "mm"), required=True)
    parser.add_argument("--reviewed-concrete-fc-unit", choices=("kPa",), required=True)

    parser.add_argument("--rebar-name-field", required=True)
    parser.add_argument("--rebar-diameter-field", required=True)
    parser.add_argument("--rebar-diameter-unit", choices=("mm", "m"), required=True)

    parser.add_argument("--reviewed-aggregate-max-mm", type=float, required=True)
    parser.add_argument("--reviewed-fcd-mpa", type=float, required=True)
    parser.add_argument("--reviewed-fyd-mpa", type=float, required=True)
    parser.add_argument("--expected-fck-mpa", type=float, required=True)

    parser.add_argument("--analysis-order-status", choices=("RESOLVED", "BLOCKED"), required=True)
    parser.add_argument("--minimum-eccentricity-status", choices=("RESOLVED", "BLOCKED"), required=True)
    parser.add_argument("--slenderness-status", choices=("RESOLVED", "BLOCKED"), required=True)
    parser.add_argument("--angle-count", type=int, required=True)
    parser.add_argument("--axial-tolerance-kn", type=float, required=True)
    parser.add_argument("--force-verification-tolerance-kn", type=float, default=0.001)
    parser.add_argument("--moment-verification-tolerance-knm", type=float, default=0.001)
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
        factual_combo_defs = capture_etabs_combo_definitions(sap.RespCombo, args.combos)
        load_case_names = _all_load_case_names(factual_combo_defs)
        if not load_case_names:
            raise ValueError("requested combination topology contains no factual LOAD_CASE constituent")
        output_names = tuple(dict.fromkeys((*load_case_names, *args.combos)))

        acquired = capture_live_column_axial_evidence(
            database_tables=sap.DatabaseTables,
            model_fingerprint=fingerprint,
            output_names=output_names,
            reviewed_force_unit=args.reviewed_force_unit,
            reviewed_length_unit=args.reviewed_length_unit,
            reviewed_concrete_fc_unit=args.reviewed_concrete_fc_unit,
            review_refs=("VS6 integrated live engine explicit unit/source contract",),
            provenance_refs=(f"model:{fingerprint}",),
        )
        design_evidence = build_column_design_demand_evidence(
            model_fingerprint=fingerprint,
            rows=acquired.forces.rows,
            output_names=output_names,
            reviewed_force_unit=args.reviewed_force_unit,
            reviewed_moment_unit=args.reviewed_moment_unit,
        )
        rebar_table = capture_etabs_rebar_catalog_evidence(sap.DatabaseTables)
        rebar_catalog = promote_etabs_rebar_catalog(
            rebar_table,
            name_field=args.rebar_name_field,
            diameter_field=args.rebar_diameter_field,
            diameter_unit=args.rebar_diameter_unit,
            source_name=f"ETABS:{fingerprint}:Reinforcing Bar Sizes",
        )
        section_names = tuple(sorted({column.section for column in acquired.columns}))
        rebar_intent_by_section = {
            section_name: capture_etabs_column_rebar_intent(
                sap.PropFrame,
                section_name,
                reviewed_length_unit=args.reviewed_length_unit,
            )
            for section_name in section_names
        }
        layout_seed_by_section = {
            section_name: resolve_column_rebar_layout_seed(
                section_name=section_name,
                clear_cover_mm=intent.cover_mm,
                tie_size_name=intent.tie_size_name,
                longitudinal_size_name=intent.rebar_size_name,
                intent_authority=intent.authority,
                rebar_catalog=rebar_catalog,
                source_ref=f"ETABS:GetRebarColumn:{section_name}",
            )
            for section_name, intent in rebar_intent_by_section.items()
        }
    except Exception as exc:
        payload = _blocked_payload("BLOCKED_FACTUAL_INPUT_ASSEMBLY", exc, identity=identity, fingerprint=fingerprint)
        _write(args.out, payload)
        print(json.dumps(to_jsonable(payload), ensure_ascii=False, sort_keys=True))
        return 5

    engine_definitions = tuple(_engine_definition(item) for item in factual_combo_defs)
    combo_names = frozenset(args.combos)
    constituent_names = frozenset(load_case_names)
    basis = ColumnDemandBasis(
        analysis_order_status=args.analysis_order_status,
        minimum_eccentricity_status=args.minimum_eccentricity_status,
        slenderness_status=args.slenderness_status,
        combination_scope_status="BLOCKED",
        review_refs=(
            "VS6 live engine: analysis/min-eccentricity/slenderness statuses explicitly reviewed",
            "VS6 live engine: combination scope is engine-derived, not caller-authorized",
        ),
    )

    columns = acquired.columns if args.all_columns else (acquired.column(args.column_name),)
    exact_rows = tuple(dict(row) for row in design_evidence.rows)
    results: list[dict[str, Any]] = []

    try:
        for column in columns:
            if abs(column.fck_mpa - args.expected_fck_mpa) > 1e-9:
                raise ValueError(
                    f"fck mismatch for {column.component_id}: observed={column.fck_mpa:g} expected={args.expected_fck_mpa:g}"
                )
            layout_seed = layout_seed_by_section[column.section]
            normalized = normalize_etabs_column_end_demands(
                exact_rows,
                unique_name=column.unique_name,
                component_id=column.component_id,
                reviewed_force_unit=args.reviewed_force_unit,
                reviewed_moment_unit=args.reviewed_moment_unit,
                axial_sign_policy=ETABS_AXIAL_SIGN_NEGATIVE_COMPRESSION,
            )
            constituent_demands = tuple(item for item in normalized if item.output_case in constituent_names)
            observed_combo_demands = tuple(item for item in normalized if item.output_case in combo_names)

            result = evaluate_column_design(
                component_id=column.component_id,
                combo_definitions=engine_definitions,
                constituent_case_demands=constituent_demands,
                observed_combo_demands=observed_combo_demands,
                verify_observed_rows=True,
                force_tolerance_n=args.force_verification_tolerance_kn * 1000.0,
                moment_tolerance_nmm=args.moment_verification_tolerance_knm * 1_000_000.0,
                rebar_catalog=rebar_catalog,
                rebar_inputs=ColumnRebarDesignInputs(
                    component_id=column.component_id,
                    width_mm=column.width_m * 1000.0,
                    depth_mm=column.depth_m * 1000.0,
                    clear_cover_mm=layout_seed.clear_cover_mm,
                    tie_diameter_mm=layout_seed.tie_diameter_mm,
                    aggregate_max_mm=args.reviewed_aggregate_max_mm,
                    material=ColumnSectionMaterial(
                        fck_mpa=column.fck_mpa,
                        fcd_mpa=args.reviewed_fcd_mpa,
                        fyd_mpa=args.reviewed_fyd_mpa,
                    ),
                    demand_basis=basis,
                    selection_policy=ColumnRebarSelectionPolicy(
                        angle_count=args.angle_count,
                        axial_tolerance_n=args.axial_tolerance_kn * 1000.0,
                    ),
                ),
            )
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
                    "layout_seed": asdict(layout_seed),
                    "engine_result": asdict(result),
                    "report_contributions": [
                        report.as_dict()
                        for report in build_vs6_column_design_engine_reports(
                            result,
                            section_name=column.section,
                        )
                    ],
                }
            )
    except Exception as exc:
        payload = _blocked_payload("BLOCKED_ENGINE_EXECUTION", exc, identity=identity, fingerprint=fingerprint)
        _write(args.out, payload)
        print(json.dumps(to_jsonable(payload), ensure_ascii=False, sort_keys=True))
        return 6

    selected_count = sum(
        1
        for item in results
        if item["engine_result"]["rebar_design"]["selection"] is not None
        and item["engine_result"]["rebar_design"]["selection"]["authority"] == "ENGINE_SELECTED_REBAR"
    )
    combo_scope_blocked_count = sum(
        1
        for item in results
        if item["engine_result"]["design_demands"]["status"] != "PROVEN_COLUMN_DESIGN_DEMAND_SCOPE"
    )

    basis_has_blocker = any(
        value == "BLOCKED"
        for value in (
            args.analysis_order_status,
            args.minimum_eccentricity_status,
            args.slenderness_status,
        )
    )
    if combo_scope_blocked_count:
        status, rc = "COMPLETE_BLOCKED_COMBINATION_SCOPE", 8
    elif selected_count == len(results):
        status, rc = "COMPLETE_ENGINE_SELECTED_REBAR", 0
    elif basis_has_blocker:
        status, rc = "COMPLETE_BLOCKED_REBAR_AUTHORITY", 7
    else:
        status, rc = "COMPLETE_WITH_UNSELECTED_COLUMNS", 9

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
        "source": {
            "design_demand_evidence_epoch_id": design_evidence.evidence_epoch_id,
            "requested_combos": list(args.combos),
            "constituent_load_cases": list(load_case_names),
            "captured_outputs": list(output_names),
            "combo_definitions": [item.as_dict() for item in factual_combo_defs],
            "rebar_catalog_table": rebar_table.as_dict(),
            "rebar_catalog": {
                "status": rebar_catalog.status,
                "authority": rebar_catalog.authority,
                "entries": [asdict(item) for item in rebar_catalog.entries],
                "column_longitudinal_diameters_mm": list(rebar_catalog.column_longitudinal_diameters_mm),
                "excluded_below_column_minimum": [asdict(item) for item in rebar_catalog.excluded_below_column_minimum],
            },
            "section_rebar_intents": {
                name: intent.as_dict()
                for name, intent in sorted(rebar_intent_by_section.items())
            },
            "section_layout_seeds": {
                name: asdict(seed)
                for name, seed in sorted(layout_seed_by_section.items())
            },
        },
        "reviewed_inputs": {
            "force_unit": args.reviewed_force_unit,
            "moment_unit": args.reviewed_moment_unit,
            "length_unit": args.reviewed_length_unit,
            "concrete_fc_unit": args.reviewed_concrete_fc_unit,
            "rebar_name_field": args.rebar_name_field,
            "rebar_diameter_field": args.rebar_diameter_field,
            "rebar_diameter_unit": args.rebar_diameter_unit,
            "layout_seed_source": "ETABS_SECTION_REBAR_INTENT",
            "aggregate_max_mm": args.reviewed_aggregate_max_mm,
            "fcd_mpa": args.reviewed_fcd_mpa,
            "fyd_mpa": args.reviewed_fyd_mpa,
            "expected_fck_mpa": args.expected_fck_mpa,
            "angle_count": args.angle_count,
            "axial_tolerance_kn": args.axial_tolerance_kn,
            "analysis_order_status": args.analysis_order_status,
            "minimum_eccentricity_status": args.minimum_eccentricity_status,
            "slenderness_status": args.slenderness_status,
            "combination_scope_status": "ENGINE_DERIVED",
        },
        "summary": {
            "column_count": len(results),
            "section_rebar_intent_count": len(rebar_intent_by_section),
            "engine_selected_rebar_count": selected_count,
            "blocked_combination_scope_count": combo_scope_blocked_count,
            "final_or_provided_rebar_count": 0,
            "transverse_links_selected": False,
            "final_column_shear_compliance_emitted": False,
        },
        "results": results,
    }
    _write(args.out, payload)
    print(json.dumps(to_jsonable({
        "status": status,
        "summary": payload["summary"],
        "safety": SAFETY,
    }), ensure_ascii=False, sort_keys=True))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
