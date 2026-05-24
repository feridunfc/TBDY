
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tbdy_engine.runner import _build_context_async, run_all_checks
from tbdy_engine.checks.registry import registry


async def main() -> None:
    ctx = await _build_context_async()

    registry.load_from_matrix()
    result = run_all_checks(ctx)

    print("\n" + "=" * 80)
    print("SPRINT 3 RUNNER FULL TEST")
    print("=" * 80)

    print("SUMMARY:", result.get("summary", {}))

    for check_id, data in result.get("checks", {}).items():
        print(
            f"{check_id}: status={data.get('status')} "
            f"total={data.get('total_checked')} "
            f"OK={data.get('pass_count')} "
            f"FAIL={data.get('fail_count')} "
            f"WARN={data.get('warning_count')} "
            f"ND={data.get('no_data_count')}"
        )

    missing = [
        x for x in [
            "beam_geometry", "beam_flexure", "beam_shear",
            "beam_ductility", "beam_capacity_hierarchy", "beam_design_full",
        ]
        if x not in result.get("checks", {})
    ]

    if missing:
        raise SystemExit(f"Missing beam checks: {missing}")

    if result.get("summary", {}).get("error", 0) != 0:
        raise SystemExit("Runner has ERROR checks")

    print("\nDONE")


if __name__ == "__main__":
    asyncio.run(main())
