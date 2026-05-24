from __future__ import annotations
import json, sys
from collections import Counter
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from tbdy_engine.contracts.loader import EngineContractLoader
def main() -> int:
    catalog = EngineContractLoader.from_project_root(ROOT).build_runtime_catalog(include_legacy=True)
    combos = Counter()
    for check in catalog.checks.values():
        for fam in check.uses_combo: combos[fam] += 1
    disabled = [k for k,v in catalog.evaluations.items() if not v.enabled]
    print("RUNTIME_CATALOG")
    print(f"checks: {len(catalog.checks)}")
    print(f"evaluations: {len(catalog.evaluations)}")
    print(f"datasets: {len(catalog.datasets)}")
    print(f"combo_families: {len(catalog.combo_families)}")
    print(f"disabled_evaluations: {disabled}")
    print("uses_combo_distribution:")
    print(json.dumps(dict(combos), ensure_ascii=False, indent=2))
    print("checks:")
    for cid in sorted(catalog.checks):
        c = catalog.checks[cid]
        print(f" - {cid}: eval={c.evaluation}.{c.evaluation_field} enabled={c.runner_enabled} experimental={c.experimental}")
    if catalog.warnings:
        print("warnings:")
        for w in catalog.warnings: print(f" ! {w}")
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
