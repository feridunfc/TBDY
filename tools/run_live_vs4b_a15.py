#!/usr/bin/env python
"""Thin CLI for the package-level VS-4B-A production execution authority."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tbdy_engine.engine.project_execution import (
    ReviewedAnalysisMethod,
    build_vs4b_a15_execution_request,
    execute_live_vs4b_a15,
)
from tbdy_engine.json_safe import to_jsonable


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Capture one directional read-only ETABS MDEV/Mo factual population and "
            "evaluate the bounded VS-4B-A production path."
        )
    )
    p.add_argument("--out", required=True, type=Path)
    p.add_argument("--expected-model-fingerprint", required=True)
    p.add_argument("--direction", required=True, choices=("X", "Y"))
    p.add_argument("--declared-row", required=True)
    p.add_argument("--regulatory-base-elevation-m", required=True, type=float)
    p.add_argument("--rigid-basement-above-base", required=True, choices=("true", "false"))
    p.add_argument("--piers", required=True)
    p.add_argument("--cases", required=True)
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
    p.add_argument("--assumed-row", required=True)
    p.add_argument("--assumed-r", required=True, type=float)
    p.add_argument("--assumed-d", required=True, type=float)
    p.add_argument("--base-review-refs", required=True)
    p.add_argument("--base-provenance-refs", required=True)
    p.add_argument("--wall-review-refs", required=True)
    p.add_argument("--wall-provenance-refs", required=True)
    p.add_argument("--result-review-refs", required=True)
    p.add_argument("--result-provenance-refs", required=True)
    p.add_argument("--declaration-review-refs", required=True)
    p.add_argument("--declaration-provenance-refs", required=True)
    p.add_argument("--seismic-review-refs", required=True)
    p.add_argument("--seismic-provenance-refs", required=True)
    p.add_argument("--analysis-evidence-refs", required=True)
    p.add_argument("--analysis-provenance-refs", required=True)
    return p


def _csv_items(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _write(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            to_jsonable(payload),
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)

    request = build_vs4b_a15_execution_request(
        expected_model_fingerprint=args.expected_model_fingerprint,
        direction=args.direction,
        declared_row=args.declared_row,
        regulatory_base_elevation_m=args.regulatory_base_elevation_m,
        rigid_basement_above_base=args.rigid_basement_above_base == "true",
        piers=_csv_items(args.piers),
        case_names=_csv_items(args.cases),
        reviewed_analysis_method=args.reviewed_analysis_method,
        scaling_state_id=args.scaling_state_id,
        result_operator_id=args.result_operator_id,
        wall_to_total_sign_factor=args.wall_to_total_sign_factor,
        population_mapping_review_refs=_csv_items(args.population_mapping_review_refs),
        dts=args.dts,
        bys=args.bys,
        assumed_row=args.assumed_row,
        assumed_r=args.assumed_r,
        assumed_d=args.assumed_d,
        base_review_refs=_csv_items(args.base_review_refs),
        base_provenance_refs=_csv_items(args.base_provenance_refs),
        wall_review_refs=_csv_items(args.wall_review_refs),
        wall_provenance_refs=_csv_items(args.wall_provenance_refs),
        result_review_refs=_csv_items(args.result_review_refs),
        result_provenance_refs=_csv_items(args.result_provenance_refs),
        declaration_review_refs=_csv_items(args.declaration_review_refs),
        declaration_provenance_refs=_csv_items(args.declaration_provenance_refs),
        seismic_review_refs=_csv_items(args.seismic_review_refs),
        seismic_provenance_refs=_csv_items(args.seismic_provenance_refs),
        analysis_evidence_refs=_csv_items(args.analysis_evidence_refs),
        analysis_provenance_refs=_csv_items(args.analysis_provenance_refs),
    )
    result = execute_live_vs4b_a15(request)

    factual = result.factual_evidence_payload
    if factual is not None:
        _write(args.out / "factual_mdev_mo_evidence.json", factual)

    product = result.as_product_dict()
    _write(args.out / "vs4b_a15_product.json", product)
    print(json.dumps(to_jsonable(product), ensure_ascii=False, sort_keys=True))
    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
