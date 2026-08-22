#!/usr/bin/env python
"""CLI for the VS-3 live seismic response regulatory pack."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tbdy_engine.features.etabs_com_attach import EtabsAttachFailure
from tbdy_engine.integration.live_beam_geometry_f0 import MissingLiveEpochIdentityError
from tbdy_engine.integration.live_seismic_response_f0 import (
    LiveSeismicEvidenceConflictError,
    LiveSeismicResponseError,
    ModalSourceSemanticsError,
)
from tbdy_engine.product.live_seismic_response_product import run_live_seismic_response_product


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the VS-3 F0-only live seismic response regulatory pack."
    )
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--modal-case", required=True)
    parser.add_argument(
        "--modal-4812-applies",
        required=True,
        choices=("true", "false", "unknown"),
    )
    parser.add_argument(
        "--modal-case-basis",
        required=True,
        choices=("verified", "unknown"),
    )
    parser.add_argument("--a1-x-cases", required=True)
    parser.add_argument("--a1-y-cases", required=True)
    parser.add_argument(
        "--a1-eccentricity-basis",
        required=True,
        choices=("verified", "unknown"),
    )
    return parser


def _tri_bool(value: str) -> bool | None:
    return {"true": True, "false": False, "unknown": None}[value]


def _cases(value: str) -> tuple[str, ...]:
    items = tuple(item.strip() for item in value.split(",") if item.strip())
    if not items:
        raise ValueError("case list must contain at least one exact ETABS case name")
    return items


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = run_live_seismic_response_product(
            output_dir=args.out,
            modal_case=args.modal_case,
            modal_4812_applies=_tri_bool(args.modal_4812_applies),
            modal_case_basis_verified=args.modal_case_basis,
            a1_x_cases=_cases(args.a1_x_cases),
            a1_y_cases=_cases(args.a1_y_cases),
            a1_eccentricity_basis=args.a1_eccentricity_basis,
        )
    except ModalSourceSemanticsError as exc:
        print(json.dumps({"status": exc.status, "message": str(exc)}, sort_keys=True))
        return 5
    except LiveSeismicEvidenceConflictError as exc:
        print(json.dumps({"status": exc.status, "message": str(exc)}, sort_keys=True))
        return 6
    except MissingLiveEpochIdentityError as exc:
        print(json.dumps({"status": exc.status, "message": str(exc)}, sort_keys=True))
        return 2
    except EtabsAttachFailure as exc:
        print(
            json.dumps(
                {
                    "status": "BLOCKED_BY_LIVE_ETABS_ATTACH",
                    "attempts": [item.as_dict() for item in exc.attach_result.attempts],
                },
                sort_keys=True,
            )
        )
        return 3
    except (LiveSeismicResponseError, ValueError, TypeError) as exc:
        print(json.dumps({"status": "ERROR", "message": str(exc)}, sort_keys=True))
        return 4

    print(
        json.dumps(
            {
                "status": "OK",
                "product": str(result.output_path),
                "capture": str(result.capture_path),
                "modal_factual_row_count": result.modal_factual_row_count,
                "story_drift_factual_row_count": result.story_drift_factual_row_count,
                "story_max_over_avg_factual_row_count": result.story_max_over_avg_factual_row_count,
                "base_reaction_factual_row_count": result.base_reaction_factual_row_count,
                "a1_story_direction_count": result.a1_story_direction_count,
                "rule_instance_count": result.rule_instance_count,
                "check_result_count": result.check_result_count,
                "finding_count": result.finding_count,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
