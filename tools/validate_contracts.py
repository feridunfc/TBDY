from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tbdy_engine.contracts.loader import EngineContractLoader
from tbdy_engine.contracts.validator import EngineContractValidator


def _to_dict(obj):
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if hasattr(obj, "dict"):
        return obj.dict()
    if hasattr(obj, "as_dict"):
        return obj.as_dict()
    if hasattr(obj, "__dict__"):
        return dict(vars(obj))
    return {}


def main() -> int:
    contracts_dir = PROJECT_ROOT / "tbdy_engine" / "contracts"

    loader = EngineContractLoader(contracts_dir, project_root=PROJECT_ROOT)
    bundle = loader.load(include_legacy=True)
    catalog = loader.build_runtime_catalog(include_legacy=True)

    validator = EngineContractValidator(bundle, catalog)
    errors = validator.validate()
    health = validator.health_report()

    generated_dir = contracts_dir / "generated"
    generated_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    history_dir = generated_dir / "history"
    history_dir.mkdir(parents=True, exist_ok=True)

    runtime_catalog_path = generated_dir / "runtime_catalog.json"
    contract_health_path = generated_dir / "contract_health.json"

    runtime_catalog_history_path = history_dir / f"{timestamp}_runtime_catalog.json"
    contract_health_history_path = history_dir / f"{timestamp}_contract_health.json"
    validation_summary_path = history_dir / f"{timestamp}_validation_summary.txt"

    runtime_payload = json.dumps(
        _to_dict(catalog), ensure_ascii=False, indent=2, default=str
    )
    health_payload = json.dumps(
        health, ensure_ascii=False, indent=2, default=str
    )

    runtime_catalog_path.write_text(runtime_payload, encoding="utf-8")
    contract_health_path.write_text(health_payload, encoding="utf-8")

    runtime_catalog_history_path.write_text(runtime_payload, encoding="utf-8")
    contract_health_history_path.write_text(health_payload, encoding="utf-8")

    warnings = health.get("warnings", []) or []

    summary_text = "\n".join([
        f"timestamp: {timestamp}",
        f"runtime checks: {health.get('check_count')}",
        f"evaluations: {health.get('evaluation_count')}",
        f"datasets: {health.get('dataset_count')}",
        f"combo families: {health.get('combo_family_count')}",
        f"warnings: {len(warnings)}",
        f"errors: {len(errors)}",
        "",
        "warnings:",
        *[f"- {w}" for w in warnings],
        "",
        "errors:",
        *[f"- {e}" for e in errors],
    ])
    validation_summary_path.write_text(summary_text, encoding="utf-8")

    print("runtime checks:", health.get("check_count"))
    print("evaluations:", health.get("evaluation_count"))
    print("datasets:", health.get("dataset_count"))
    print("combo families:", health.get("combo_family_count"))
    print("warnings:", len(warnings))
    print("errors:", len(errors))

    for warning in warnings[:30]:
        print("WARN:", warning)

    for error in errors:
        print("ERROR:", error)

    print("wrote:", runtime_catalog_path)
    print("wrote:", contract_health_path)
    print("snapshot:", runtime_catalog_history_path)
    print("snapshot:", contract_health_history_path)
    print("snapshot:", validation_summary_path)

    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
