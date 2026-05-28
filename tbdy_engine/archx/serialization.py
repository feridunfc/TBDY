from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any


ARTIFACT_TYPE = "ARCH-X_RUN_RESULT"
ARTIFACT_VERSION = "ARCH-X-VS-1"


def archx_run_result_to_dict(result: Any) -> dict[str, Any]:
    return {
        "artifact_type": ARTIFACT_TYPE,
        "artifact_version": ARTIFACT_VERSION,
        "run_id": result.run_id,
        "summary": _json_safe(result.summary),
        "diagnostics": list(result.diagnostics),
        "evaluation_packages": [_json_safe(package) for package in result.evaluation_packages],
        "check_results": [_json_safe(check_result) for check_result in result.check_results],
        "workbench_bundle": _json_safe(result.workbench_bundle),
    }


def write_archx_run_json(result: Any, output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = archx_run_result_to_dict(result)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return path


def _json_safe(value: Any) -> Any:
    if is_dataclass(value):
        return _json_safe(asdict(value))
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value
