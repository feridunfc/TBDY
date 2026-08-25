#!/usr/bin/env python
"""Offline acceptance adapter for the VS6 column design-demand engine.

Consumes previously captured read-only artifacts and delegates all combination
classification and design-state promotion to the production engine.  This tool
contains file/CLI serialization only: no engineering pattern logic, no ETABS
connection, no capacity calculation and no reinforcement selection.
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

from tbdy_engine.design.columns.column_design_demand_engine import (
    ColumnComboDefinition,
    evaluate_column_design_demands,
)
from tbdy_engine.design.columns.design_demand_states import LinearComboConstituent
from tbdy_engine.design.columns.rebar_selection import ColumnDemandState
from tbdy_engine.json_safe import to_jsonable
from tbdy_engine.product_reports.vs6_design_demand_report import build_vs6_design_demand_report


SAFETY = {
    "etabs_connection_opened": False,
    "analysis_run": False,
    "design_run": False,
    "model_save": False,
    "model_or_property_mutation": False,
    "reinforcement_selected": False,
    "section_capacity_computed": False,
    "compliance_verdict_emitted": False,
}


def _csv(value: str) -> tuple[str, ...]:
    items = tuple(item.strip() for item in value.split(",") if item.strip())
    if not items or len(items) != len(set(items)):
        raise argparse.ArgumentTypeError("requires a nonempty unique comma-separated list")
    return items


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(to_jsonable(payload), ensure_ascii=False, allow_nan=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _to_state(row: dict[str, Any]) -> ColumnDemandState:
    return ColumnDemandState(
        state_id=str(row["state_id"]),
        component_id=str(row["component_id"]),
        output_case=str(row["output_case"]),
        case_type=str(row["case_type"]),
        step_type=row.get("step_type"),
        step_number=row.get("step_number"),
        station_m=float(row["station_m"]),
        end_tag=str(row["end_tag"]),
        nd_compression_n=float(row["nd_compression_kn"]) * 1000.0,
        m2_nmm=float(row["m2_knm"]) * 1_000_000.0,
        m3_nmm=float(row["m3_knm"]) * 1_000_000.0,
        source_identity=str(row["source_identity"]),
    )


def _column(payload: dict[str, Any], unique_name: str) -> dict[str, Any]:
    matches = [item for item in payload.get("columns", []) if str(item.get("UniqueName")) == unique_name]
    if len(matches) != 1:
        raise ValueError(f"expected one column UniqueName={unique_name}; got {len(matches)}")
    return matches[0]


def _combo_definition(payload: dict[str, Any], name: str) -> dict[str, Any]:
    matches = [item for item in payload.get("combos", []) if item.get("name") == name]
    if len(matches) != 1:
        raise ValueError(f"expected one combo definition {name}; got {len(matches)}")
    return matches[0]


def _definition_from_payload(payload: dict[str, Any], combo_name: str) -> ColumnComboDefinition:
    definition = _combo_definition(payload, combo_name)
    return ColumnComboDefinition(
        name=combo_name,
        combo_type=str(definition["combo_type"]),
        constituents=tuple(
            LinearComboConstituent(
                name=str(item["name"]),
                scale_factor=float(item["scale_factor"]),
                cname_type=str(item["cname_type"]),
            )
            for item in definition.get("constituents", [])
        ),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--constituent-demand", type=Path, required=True)
    parser.add_argument("--observed-combo-demand", type=Path, required=True)
    parser.add_argument("--combo-definitions", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--column-name", required=True)
    parser.add_argument("--combos", type=_csv, required=True)
    parser.add_argument("--force-tolerance-kn", type=float, default=0.001)
    parser.add_argument("--moment-tolerance-knm", type=float, default=0.001)
    args = parser.parse_args(argv)

    try:
        constituent_payload = _load(args.constituent_demand)
        observed_payload = _load(args.observed_combo_demand)
        combo_payload = _load(args.combo_definitions)
        constituent_column = _column(constituent_payload, args.column_name)
        observed_column = _column(observed_payload, args.column_name)

        if constituent_column.get("component_id") != observed_column.get("component_id"):
            raise ValueError("constituent and observed artifacts disagree on component_id")
        component_id = str(constituent_column["component_id"])
        constituent_states = tuple(_to_state(item) for item in constituent_column.get("demands", []))
        observed_states = tuple(_to_state(item) for item in observed_column.get("demands", []))
        definitions = tuple(_definition_from_payload(combo_payload, name) for name in args.combos)

        engine = evaluate_column_design_demands(
            component_id=component_id,
            definitions=definitions,
            case_demands=constituent_states,
            observed_combo_demands=observed_states,
            verify_observed_rows=True,
            force_tolerance_n=args.force_tolerance_kn * 1000.0,
            moment_tolerance_nmm=args.moment_tolerance_knm * 1_000_000.0,
        )

        results: list[dict[str, Any]] = []
        reports: list[dict[str, Any]] = []
        for combo_result in engine.combo_results:
            build = combo_result.build
            verification = combo_result.verification
            result: dict[str, Any] = {
                "combo_name": combo_result.definition.name,
                "classification": asdict(combo_result.classification),
                "status": combo_result.status,
                "generated_state_count": len(build.states) if build is not None else 0,
                "authority": build.authority if build is not None else "NOT_PROMOTED",
                "verification": asdict(verification) if verification is not None else None,
                "end_summaries": [asdict(item) for item in build.end_summaries] if build is not None else [],
                "states": [asdict(item) for item in build.states] if build is not None else [],
            }
            results.append(result)
            if build is not None:
                reports.append(build_vs6_design_demand_report(build, verification=verification).as_dict())

        all_proven = engine.combination_scope_resolved
        status = "PROVEN_VS6_DESIGN_DEMAND_RECONSTRUCTION" if all_proven else "REVIEW_REQUIRED_DESIGN_DEMAND_RECONSTRUCTION"
        payload = {
            "status": status,
            "engine_status": engine.status,
            "component_id": component_id,
            "column_unique_name": args.column_name,
            "requested_combos": list(args.combos),
            "blocked_combo_names": list(engine.blocked_combo_names),
            "source_artifacts": {
                "constituent_demand": str(args.constituent_demand),
                "observed_combo_demand": str(args.observed_combo_demand),
                "combo_definitions": str(args.combo_definitions),
            },
            "safety": SAFETY,
            "scope": {
                "response_spectrum_sign_permutation_semantics": "PROVEN" if all_proven else "REVIEW_REQUIRED",
                "raw_combo_rows_promoted_to_concurrent_states": False,
                "full_regulatory_combination_scope_resolved": False,
                "minimum_eccentricity_resolved": False,
                "slenderness_resolved": False,
                "reinforcement_selected": False,
            },
            "results": results,
            "report_contributions": reports,
        }
        _write(args.out, payload)
        print(
            json.dumps(
                to_jsonable(
                    {
                        "status": status,
                        "engine_status": engine.status,
                        "component_id": component_id,
                        "results": [
                            {
                                "combo_name": item["combo_name"],
                                "pattern": item["classification"]["pattern"],
                                "generated_state_count": item["generated_state_count"],
                                "verification": item["verification"]["status"] if item["verification"] else None,
                            }
                            for item in results
                        ],
                        "safety": SAFETY,
                    }
                ),
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 0 if all_proven else 8
    except Exception as exc:
        payload = {
            "status": "BLOCKED_DESIGN_DEMAND_RECONSTRUCTION",
            "exception_type": type(exc).__name__,
            "message": str(exc),
            "safety": SAFETY,
        }
        _write(args.out, payload)
        print(json.dumps(to_jsonable(payload), ensure_ascii=False, sort_keys=True))
        return 5


if __name__ == "__main__":
    raise SystemExit(main())
