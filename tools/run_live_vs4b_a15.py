#!/usr/bin/env python
"""Read-only live runner for the bounded VS-4B-A A15 MDEV/Mo slice."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tbdy_engine.etabs.safety import read_session_identity
from tbdy_engine.features.etabs_com_attach import (
    ATTACH_STATUS_ATTACHED,
    attach_to_running_etabs,
)
from tbdy_engine.features.etabs_mdev_mo_evidence import (
    MdevMoEvidenceError,
    ReviewedAnalysisMethod,
    ReviewedDirectionalWallPopulation,
    ReviewedRegulatoryBaseContext,
    ReviewedResultPopulationContext,
    capture_live_mdev_mo_evidence,
)
from tbdy_engine.integration.live_beam_geometry_f0 import model_fingerprint_from_path
from tbdy_engine.json_safe import to_jsonable
from tbdy_engine.regulatory.structural_system import (
    DirectionalAnalysisSystemAssumption,
    ReviewedDirectionalRcSystemDeclaration,
    ReviewedSeismicClassificationContext,
)
from tbdy_engine.regulatory.vs4b_program import run_vs4b_a15_direction


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Capture read-only ETABS MDEV/Mo facts and, only when the analysis-method/result-population "
            "gate is resolved, evaluate TBDY 2018 4.3.4.5 A15."
        )
    )
    p.add_argument("--out", required=True, type=Path)
    p.add_argument("--expected-model-fingerprint", required=True)
    p.add_argument("--regulatory-base-elevation-m", required=True, type=float)
    p.add_argument("--rigid-basement-above-base", required=True, choices=("true", "false"))
    p.add_argument("--x-piers", required=True)
    p.add_argument("--y-piers", required=True)
    p.add_argument("--x-cases", required=True)
    p.add_argument("--y-cases", required=True)
    p.add_argument(
        "--reviewed-analysis-method",
        required=True,
        choices=(ReviewedAnalysisMethod.MODAL_COMBINATION.value,),
    )
    p.add_argument("--scaling-state-id", required=True)
    p.add_argument("--result-operator-id", required=True)
    p.add_argument("--wall-to-total-sign-factor", required=True, type=int, choices=(-1, 1))
    p.add_argument("--population-mapping-review-refs", default="")
    p.add_argument("--dts", required=True)
    p.add_argument("--bys", required=True, type=int)
    p.add_argument("--x-assumed-row", required=True)
    p.add_argument("--x-assumed-r", required=True, type=float)
    p.add_argument("--x-assumed-d", required=True, type=float)
    p.add_argument("--y-assumed-row", required=True)
    p.add_argument("--y-assumed-r", required=True, type=float)
    p.add_argument("--y-assumed-d", required=True, type=float)
    p.add_argument("--base-review-refs", required=True)
    p.add_argument("--base-provenance-refs", required=True)
    p.add_argument("--x-wall-review-refs", required=True)
    p.add_argument("--x-wall-provenance-refs", required=True)
    p.add_argument("--y-wall-review-refs", required=True)
    p.add_argument("--y-wall-provenance-refs", required=True)
    p.add_argument("--result-review-refs", required=True)
    p.add_argument("--result-provenance-refs", required=True)
    p.add_argument("--declaration-review-refs", required=True)
    p.add_argument("--declaration-provenance-refs", required=True)
    p.add_argument("--seismic-review-refs", required=True)
    p.add_argument("--seismic-provenance-refs", required=True)
    p.add_argument("--analysis-evidence-refs", required=True)
    p.add_argument("--analysis-provenance-refs", required=True)
    return p


def _items(value: str, label: str) -> tuple[str, ...]:
    items = tuple(item.strip() for item in value.split(",") if item.strip())
    if not items:
        raise ValueError(f"{label} requires at least one exact value")
    if len(items) != len(set(items)):
        raise ValueError(f"{label} contains duplicates")
    return items


def _optional_items(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _write(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(to_jsonable(payload), ensure_ascii=False, allow_nan=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)

    attach = attach_to_running_etabs()
    if attach.status != ATTACH_STATUS_ATTACHED:
        payload = {
            "status": "BLOCKED_BY_LIVE_ETABS_ATTACH",
            "attempts": [item.as_dict() for item in attach.attempts],
        }
        _write(args.out / "vs4b_a15_product.json", payload)
        print(json.dumps(payload, sort_keys=True))
        return 3

    identity = read_session_identity(
        attach.etabs_object,
        attach.sap_model,
        attach_strategy=attach.strategy,
    )
    model_fingerprint = model_fingerprint_from_path(identity.model_full_path)
    if model_fingerprint != args.expected_model_fingerprint:
        payload = {
            "status": "BLOCKED_MODEL_IDENTITY_MISMATCH",
            "expected_model_fingerprint": args.expected_model_fingerprint,
            "observed_model_fingerprint": model_fingerprint,
            "observed_model_path": identity.model_full_path,
        }
        _write(args.out / "vs4b_a15_product.json", payload)
        print(json.dumps(payload, sort_keys=True))
        return 2

    try:
        base = ReviewedRegulatoryBaseContext(
            elevation_m=args.regulatory_base_elevation_m,
            rigid_basement_above_base=args.rigid_basement_above_base == "true",
            review_refs=_items(args.base_review_refs, "base review refs"),
            provenance_refs=_items(args.base_provenance_refs, "base provenance refs"),
        )
        walls = (
            ReviewedDirectionalWallPopulation(
                "X",
                _items(args.x_piers, "X piers"),
                _items(args.x_wall_review_refs, "X wall review refs"),
                _items(args.x_wall_provenance_refs, "X wall provenance refs"),
            ),
            ReviewedDirectionalWallPopulation(
                "Y",
                _items(args.y_piers, "Y piers"),
                _items(args.y_wall_review_refs, "Y wall review refs"),
                _items(args.y_wall_provenance_refs, "Y wall provenance refs"),
            ),
        )
        result_context = ReviewedResultPopulationContext(
            analysis_method=ReviewedAnalysisMethod(args.reviewed_analysis_method),
            scaling_state_id=args.scaling_state_id,
            result_operator_id=args.result_operator_id,
            wall_to_total_sign_factor=args.wall_to_total_sign_factor,
            review_refs=_items(args.result_review_refs, "result review refs"),
            provenance_refs=_items(args.result_provenance_refs, "result provenance refs"),
            population_mapping_review_refs=_optional_items(args.population_mapping_review_refs),
        )
        bundle = capture_live_mdev_mo_evidence(
            database_tables=attach.sap_model.DatabaseTables,
            model_fingerprint=model_fingerprint,
            base_context=base,
            wall_populations=walls,
            result_context=result_context,
            x_cases=_items(args.x_cases, "X cases"),
            y_cases=_items(args.y_cases, "Y cases"),
        )
    except (MdevMoEvidenceError, ValueError, TypeError) as exc:
        payload = {
            "status": getattr(exc, "status", "BLOCKED_MDEV_MO_FACTUAL_ACQUISITION"),
            "message": str(exc),
            "model_fingerprint": model_fingerprint,
            "observed_model_path": identity.model_full_path,
        }
        _write(args.out / "vs4b_a15_product.json", payload)
        print(json.dumps(payload, sort_keys=True))
        return 4

    _write(args.out / "factual_mdev_mo_evidence.json", bundle.as_dict())

    declaration_refs = _items(args.declaration_review_refs, "declaration review refs")
    declaration_prov = _items(args.declaration_provenance_refs, "declaration provenance refs")
    seismic = ReviewedSeismicClassificationContext(
        dts=args.dts,
        bys=args.bys,
        review_refs=_items(args.seismic_review_refs, "seismic review refs"),
        provenance_refs=_items(args.seismic_provenance_refs, "seismic provenance refs"),
    )
    analysis_refs = _items(args.analysis_evidence_refs, "analysis evidence refs")
    analysis_prov = _items(args.analysis_provenance_refs, "analysis provenance refs")

    runs = []
    for direction in ("X", "Y"):
        declaration = ReviewedDirectionalRcSystemDeclaration(
            direction=direction,
            table_4_1_row="A15",
            review_refs=declaration_refs,
            provenance_refs=declaration_prov,
        )
        if direction == "X":
            assumption = DirectionalAnalysisSystemAssumption(
                direction="X",
                assumed_table_4_1_row=args.x_assumed_row,
                assumed_r=args.x_assumed_r,
                assumed_d=args.x_assumed_d,
                analysis_evidence_refs=analysis_refs,
                provenance_refs=analysis_prov,
            )
        else:
            assumption = DirectionalAnalysisSystemAssumption(
                direction="Y",
                assumed_table_4_1_row=args.y_assumed_row,
                assumed_r=args.y_assumed_r,
                assumed_d=args.y_assumed_d,
                analysis_evidence_refs=analysis_refs,
                provenance_refs=analysis_prov,
            )
        runs.append(
            run_vs4b_a15_direction(
                declaration=declaration,
                seismic=seismic,
                analysis_assumption=assumption,
                evidence=bundle.direction(direction),
            )
        )

    product = {
        "status": (
            "OK" if all(item.regulatory_resolved for item in runs) else "OK_WITH_REGULATORY_BLOCK"
        ),
        "FACTUAL_MDEV_MO_ACQUISITION": "PROVEN",
        "model_identity": {
            "model_fingerprint": model_fingerprint,
            "observed_model_path": identity.model_full_path,
            "program_name": identity.program_name,
            "program_version": identity.program_version,
            "program_api_version": identity.program_api_version,
            "database_units": identity.units.database_units,
            "present_units": identity.units.present_units,
        },
        "reviewed_project_context": {
            "regulatory_base_elevation_m": base.elevation_m,
            "rigid_basement_above_base": base.rigid_basement_above_base,
            "base_review_refs": list(base.review_refs),
            "base_provenance_refs": list(base.provenance_refs),
        },
        "evidence_epoch_id": bundle.evidence_epoch_id,
        "directions": [item.as_dict() for item in runs],
        "safety": {
            "analysis_run": False,
            "design_run": False,
            "model_save": False,
            "model_or_property_mutation": False,
            "present_units_set": False,
            "output_selection_mutation": "REVERSIBLE_TRANSACTION_ONLY",
        },
    }
    _write(args.out / "vs4b_a15_product.json", product)
    print(json.dumps(to_jsonable(product), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
