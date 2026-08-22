"""CLI for the VS-1 live beam geometry -> F0 deterministic product."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tbdy_engine.features.etabs_com_attach import EtabsAttachFailure
from tbdy_engine.integration.live_beam_geometry_f0 import (
    MissingLiveEpochIdentityError,
    VS1LiveBeamIntegrationError,
)
from tbdy_engine.product.live_beam_geometry_f0_product import (
    run_live_beam_geometry_f0_product,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the VS-1 F0-only live beam geometry product slice."
    )
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument(
        "--tbdy-7411-applies",
        required=True,
        choices=("true", "false", "unknown"),
        help="Explicit reviewed compile-time TBDY 7.4.1.1 applicability context.",
    )
    parser.add_argument("--target-story")
    parser.add_argument("--target-label")
    parser.add_argument("--target-component")
    parser.add_argument("--max-rows", type=int, default=20)
    return parser


def _tbdy_7411_cli_value(value: str) -> bool | None:
    mapping = {"true": True, "false": False, "unknown": None}
    try:
        return mapping[value]
    except KeyError as exc:
        raise ValueError("unsupported --tbdy-7411-applies value") from exc


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = run_live_beam_geometry_f0_product(
            output_dir=args.out,
            tbdy_7411_applies=_tbdy_7411_cli_value(args.tbdy_7411_applies),
            target_story=args.target_story,
            target_label=args.target_label,
            target_component=args.target_component,
            max_rows=args.max_rows,
        )
    except MissingLiveEpochIdentityError as exc:
        print(json.dumps({"status": exc.status, "message": str(exc)}, sort_keys=True))
        return 2
    except EtabsAttachFailure as exc:
        print(
            json.dumps(
                {
                    "status": "BLOCKED_BY_LIVE_ETABS_ATTACH",
                    "attempts": [
                        attempt.as_dict() for attempt in exc.attach_result.attempts
                    ],
                },
                sort_keys=True,
            )
        )
        return 3
    except VS1LiveBeamIntegrationError as exc:
        print(json.dumps({"status": "ERROR", "message": str(exc)}, sort_keys=True))
        return 4

    print(
        json.dumps(
            {
                "status": "OK",
                "product": str(result.output_path),
                "beam_count": result.beam_count,
                "finding_count": result.finding_count,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
