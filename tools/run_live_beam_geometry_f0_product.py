"""CLI for the VS-1 live beam geometry -> F0 deterministic product."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from tbdy_engine.features.etabs_com_attach import EtabsAttachFailure
from tbdy_engine.integration.live_beam_geometry_f0 import (
    MissingLiveEpochIdentityError,
    VS1LiveBeamIntegrationError,
)
from tbdy_engine.product.live_beam_geometry_f0_product import (
    PRODUCT_FILENAME,
    build_live_beam_geometry_f0_product_from_capture,
    run_live_beam_geometry_f0_product,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the VS-1 F0-only live beam geometry product slice."
    )
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--target-story")
    parser.add_argument("--target-label")
    parser.add_argument("--target-component")
    parser.add_argument("--max-rows", type=int, default=20)
    parser.add_argument(
        "--feature-snapshot",
        type=Path,
        help="Replay an already-captured canonical FeatureSnapshot artifact.",
    )
    parser.add_argument(
        "--model-path",
        help="Observed ETABS model path paired with --feature-snapshot.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    replay = args.feature_snapshot is not None or args.model_path is not None
    try:
        if replay:
            if args.feature_snapshot is None or args.model_path is None:
                raise VS1LiveBeamIntegrationError(
                    "--feature-snapshot and --model-path must be supplied together"
                )
            result = build_live_beam_geometry_f0_product_from_capture(
                model_path=args.model_path,
                feature_snapshot_path=args.feature_snapshot,
                output_path=args.out / PRODUCT_FILENAME,
            )
        else:
            result = run_live_beam_geometry_f0_product(
                output_dir=args.out,
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
