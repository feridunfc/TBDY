#!/usr/bin/env python
"""CLI for the VS-2 live RC component compliance pack."""
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
from tbdy_engine.integration.live_rc_component_f0 import (
    MissingLiveMaterialEvidenceError,
    RealComponentPackConflictError,
    VS2RcComponentIntegrationError,
)
from tbdy_engine.product.live_rc_component_f0_product import (
    run_live_rc_component_f0_product,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the VS-2 F0-only live RC component compliance pack."
    )
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument(
        "--tbdy-7411-applies",
        required=True,
        choices=("true", "false", "unknown"),
        help="Explicit reviewed compile-time TBDY 7.4.1.1 beam applicability context.",
    )
    return parser


def _tbdy_7411_cli_value(value: str) -> bool | None:
    return {"true": True, "false": False, "unknown": None}[value]


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = run_live_rc_component_f0_product(
            output_dir=args.out,
            tbdy_7411_applies=_tbdy_7411_cli_value(args.tbdy_7411_applies),
        )
    except MissingLiveEpochIdentityError as exc:
        print(json.dumps({"status": exc.status, "message": str(exc)}, sort_keys=True))
        return 2
    except MissingLiveMaterialEvidenceError as exc:
        print(json.dumps({"status": exc.status, "message": str(exc)}, sort_keys=True))
        return 5
    except RealComponentPackConflictError as exc:
        print(json.dumps({"status": exc.status, "message": str(exc)}, sort_keys=True))
        return 6
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
    except VS2RcComponentIntegrationError as exc:
        print(json.dumps({"status": "ERROR", "message": str(exc)}, sort_keys=True))
        return 4

    print(
        json.dumps(
            {
                "status": "OK",
                "product": str(result.output_path),
                "beam_count": result.beam_count,
                "column_count": result.column_count,
                "used_concrete_material_count": result.used_concrete_material_count,
                "finding_count": result.finding_count,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
