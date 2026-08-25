#!/usr/bin/env python
"""Thin CLI for the package-level live VS5 column axial execution authority."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tbdy_engine.engine.vs5_column_axial_execution import (
    build_vs5_column_axial_execution_request,
    execute_live_vs5_column_axial,
)
from tbdy_engine.json_safe import to_jsonable


def _csv_items(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Capture read-only ETABS RC-column factual evidence and execute the bounded "
            "TBDY 7.3.1.2 + TS500 7.4.1 dual-code VS5 path."
        )
    )
    p.add_argument("--out", required=True, type=Path)
    p.add_argument("--expected-model-fingerprint", required=True)
    p.add_argument("--outputs", required=True, help="Comma-separated exact output case/combination names")
    p.add_argument("--reviewed-context-json", required=True, type=Path)
    p.add_argument("--reviewed-force-unit", default="kN")
    p.add_argument("--reviewed-length-unit", default="m")
    p.add_argument("--reviewed-concrete-fc-unit", default="kPa")
    p.add_argument("--factual-review-refs", required=True)
    p.add_argument("--factual-provenance-refs", required=True)
    return p


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
    reviewed_context = json.loads(args.reviewed_context_json.read_text(encoding="utf-8"))
    if not isinstance(reviewed_context, dict):
        raise TypeError("reviewed context JSON root must be an object")

    request = build_vs5_column_axial_execution_request(
        expected_model_fingerprint=args.expected_model_fingerprint,
        output_names=_csv_items(args.outputs),
        reviewed_context=reviewed_context,
        reviewed_force_unit=args.reviewed_force_unit,
        reviewed_length_unit=args.reviewed_length_unit,
        reviewed_concrete_fc_unit=args.reviewed_concrete_fc_unit,
        factual_review_refs=_csv_items(args.factual_review_refs),
        factual_provenance_refs=_csv_items(args.factual_provenance_refs),
    )
    result = execute_live_vs5_column_axial(request)

    args.out.mkdir(parents=True, exist_ok=True)
    factual = result.factual_evidence_payload
    if factual is not None:
        _write(args.out / "factual_column_axial_evidence.json", factual)
    product = result.as_product_dict()
    _write(args.out / "vs5_column_axial_product.json", product)
    print(json.dumps(to_jsonable(product), ensure_ascii=False, sort_keys=True))
    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
