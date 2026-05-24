from __future__ import annotations
import argparse
import asyncio
import inspect
import json
from typing import Any

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

def _find_context_builder():
    import tbdy_engine.runner as legacy_runner
    for name in ["_build_context_async", "build_context_async", "_build_context", "build_context", "build_model_context"]:
        fn = getattr(legacy_runner, name, None)
        if fn is not None:
            return name, fn
    raise RuntimeError("No context builder found in tbdy_engine.runner.")

def _build_ctx() -> Any:
    name, fn = _find_context_builder()
    print(f"CTX_BUILDER: tbdy_engine.runner.{name}")
    result = fn()
    if inspect.isawaitable(result):
        return asyncio.run(result)
    return result

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report-dir", default="reports_out")
    parser.add_argument("--contracts-dir", default=None)
    parser.add_argument("--no-legacy", action="store_true")
    args = parser.parse_args()

    from tbdy_engine.runner_v2 import run_engine_v2
    ctx = _build_ctx()
    result = run_engine_v2(ctx, contracts_dir=args.contracts_dir, report_dir=args.report_dir, include_legacy=not args.no_legacy)

    print("RUNNER_V2_RESULT")
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0 if result.get("status") in {"OK", "PARTIAL"} else 1

if __name__ == "__main__":
    raise SystemExit(main())
