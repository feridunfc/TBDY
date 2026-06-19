"""C13.4-P4 deterministic geometry vertical slice runner.

The runner executes only the existing FeatureSnapshot -> GeometryCheckInput ->
MinimalCheckEngine -> CheckResult geometry path. It reads local JSON fixtures and
writes transparent JSON artifacts.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
from pathlib import Path
from typing import Any
import json

import yaml

from tbdy_engine.checks.engine import MinimalCheckEngine
from tbdy_engine.checks.input_adapter import (
    CheckInputBuildDiagnostic,
    build_geometry_check_inputs_from_feature_snapshot,
)
from tbdy_engine.checks.result import CheckResult

_RUNNER_NAME = "C13.4-P4 Geometry Vertical Slice Runner"
_SCOPE = "GEOMETRY_ONLY"
_ARTIFACT_FILES = (
    "check_results.json",
    "adapter_diagnostics.json",
    "run_summary.json",
    "run_manifest.json",
)
_FORBIDDEN_SCOPE = (
    "beam_flexure",
    "beam_shear",
    "rebar_adequacy",
    "capacity_design",
    "governing_combo_selection",
    "force_envelope_selection",
    "SCWB",
    "PMM",
    "drift",
    "ETABS_live_fetching",
    "Excel_production_path",
    "legacy_runtime_execution",
)
_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_CATALOG_DIR = _REPO_ROOT / "tbdy_engine" / "catalogs"
_C13_5_CHECK_OVERLAYS = ("check_catalog_c13_5_p1_column_geometry.yaml",)


@dataclass(frozen=True, slots=True)
class GeometryVerticalSliceResult:
    check_results: tuple[CheckResult, ...]
    adapter_diagnostics: tuple[CheckInputBuildDiagnostic, ...]
    run_summary: Mapping[str, object]
    manifest: Mapping[str, object]

    def __post_init__(self) -> None:
        check_results = tuple(self.check_results)
        adapter_diagnostics = tuple(self.adapter_diagnostics)
        if any(not isinstance(item, CheckResult) for item in check_results):
            raise TypeError("GeometryVerticalSliceResult.check_results must contain CheckResult objects")
        if any(not isinstance(item, CheckInputBuildDiagnostic) for item in adapter_diagnostics):
            raise TypeError(
                "GeometryVerticalSliceResult.adapter_diagnostics must contain CheckInputBuildDiagnostic objects"
            )
        object.__setattr__(self, "check_results", check_results)
        object.__setattr__(self, "adapter_diagnostics", adapter_diagnostics)
        object.__setattr__(self, "run_summary", dict(self.run_summary))
        object.__setattr__(self, "manifest", dict(self.manifest))


def run_geometry_vertical_slice_from_file(
    *,
    feature_snapshot_path: Path,
    output_dir: Path,
    catalog_dir: Path | None = None,
) -> GeometryVerticalSliceResult:
    input_path = Path(feature_snapshot_path)
    out_dir = Path(output_dir)
    effective_catalog_dir = Path(catalog_dir) if catalog_dir is not None else _DEFAULT_CATALOG_DIR

    input_bytes = input_path.read_bytes()
    input_payload = json.loads(input_bytes.decode("utf-8"))
    snapshots = _normalize_input_payload(input_payload)
    check_definitions = _load_check_definitions(effective_catalog_dir)
    engine = MinimalCheckEngine(check_definitions)

    check_results: list[CheckResult] = []
    adapter_diagnostics: list[CheckInputBuildDiagnostic] = []
    executable_input_count = 0

    for snapshot_payload in snapshots:
        adapter_result = build_geometry_check_inputs_from_feature_snapshot(snapshot_payload)
        adapter_diagnostics.extend(adapter_result.diagnostics)
        executable_input_count += len(adapter_result.check_inputs)
        for check_input in adapter_result.check_inputs:
            check_results.append(engine.run_check(check_input.check_id, check_input.snapshot, check_input.coverage))

    summary = _build_summary(
        snapshots=snapshots,
        executable_input_count=executable_input_count,
        check_results=check_results,
        adapter_diagnostics=adapter_diagnostics,
    )
    manifest = _build_manifest(
        input_path=input_path,
        input_sha256=sha256(input_bytes).hexdigest(),
        output_dir=out_dir,
        catalog_dir=effective_catalog_dir,
    )

    out_dir.mkdir(parents=True, exist_ok=True)
    _write_json(out_dir / "check_results.json", [_serialize_check_result(item) for item in check_results])
    _write_json(out_dir / "adapter_diagnostics.json", [_serialize_adapter_diagnostic(item) for item in adapter_diagnostics])
    _write_json(out_dir / "run_summary.json", summary)
    _write_json(out_dir / "run_manifest.json", manifest)

    return GeometryVerticalSliceResult(
        check_results=tuple(check_results),
        adapter_diagnostics=tuple(adapter_diagnostics),
        run_summary=summary,
        manifest=manifest,
    )


def _normalize_input_payload(payload: object) -> tuple[Mapping[str, object], ...]:
    if isinstance(payload, Mapping):
        if "snapshots" in payload:
            snapshots = payload["snapshots"]
            if not isinstance(snapshots, Sequence) or isinstance(snapshots, (str, bytes, bytearray)):
                raise ValueError("Input wrapper field 'snapshots' must be a list of snapshot objects")
            return _normalize_snapshot_sequence(snapshots)
        _validate_snapshot_mapping(payload)
        return (payload,)
    if isinstance(payload, Sequence) and not isinstance(payload, (str, bytes, bytearray)):
        return _normalize_snapshot_sequence(payload)
    raise ValueError("Input JSON must be a snapshot object, a snapshot list, or an object with a snapshots list")


def _normalize_snapshot_sequence(snapshots: Sequence[object]) -> tuple[Mapping[str, object], ...]:
    normalized: list[Mapping[str, object]] = []
    for index, snapshot in enumerate(snapshots):
        if not isinstance(snapshot, Mapping):
            raise ValueError(f"Snapshot entry at index {index} must be an object")
        _validate_snapshot_mapping(snapshot)
        normalized.append(snapshot)
    return tuple(normalized)


def _validate_snapshot_mapping(snapshot: Mapping[str, object]) -> None:
    for field_name in ("component_type", "component_id", "features"):
        if field_name not in snapshot:
            raise ValueError(f"Snapshot object missing required field: {field_name}")
    identity = snapshot.get("identity", {})
    features = snapshot.get("features")
    if identity is not None and not isinstance(identity, Mapping):
        raise ValueError("Snapshot identity must be an object when present")
    if not isinstance(features, Mapping):
        raise ValueError("Snapshot features must be an object")


def _load_check_definitions(catalog_dir: Path) -> Mapping[str, Mapping[str, Any]]:
    catalog_path = catalog_dir / "check_catalog.yaml"
    checks = _load_check_mapping(catalog_path)
    for overlay_name in _C13_5_CHECK_OVERLAYS:
        overlay_path = catalog_dir / overlay_name
        if overlay_path.is_file():
            for check_id, definition in _load_check_mapping(overlay_path).items():
                checks[check_id] = definition
    return checks


def _load_check_mapping(catalog_path: Path) -> dict[str, Mapping[str, Any]]:
    with catalog_path.open("r", encoding="utf-8") as handle:
        catalog = yaml.safe_load(handle)
    if not isinstance(catalog, Mapping) or not isinstance(catalog.get("checks"), Mapping):
        raise ValueError(f"{catalog_path.name} must contain a top-level checks mapping")
    checks: dict[str, Mapping[str, Any]] = {}
    for check_id, definition in catalog["checks"].items():
        if not isinstance(definition, Mapping):
            raise ValueError(f"Check catalog entry must be a mapping: {check_id}")
        checks[str(check_id)] = definition
    return checks


def _build_summary(
    *,
    snapshots: Sequence[Mapping[str, object]],
    executable_input_count: int,
    check_results: Sequence[CheckResult],
    adapter_diagnostics: Sequence[CheckInputBuildDiagnostic],
) -> dict[str, object]:
    status_counts = Counter(result.status.value for result in check_results)
    check_id_counts = Counter(result.check_id for result in check_results)
    component_type_counts = Counter(str(snapshot["component_type"]) for snapshot in snapshots)
    return {
        "adapter_diagnostic_count": len(adapter_diagnostics),
        "check_id_counts": _sorted_counter_dict(check_id_counts),
        "check_result_count": len(check_results),
        "check_result_status_counts": _sorted_counter_dict(status_counts),
        "component_type_counts": _sorted_counter_dict(component_type_counts),
        "executable_input_count": executable_input_count,
        "snapshot_count": len(snapshots),
        "status": "OK",
    }


def _build_manifest(*, input_path: Path, input_sha256: str, output_dir: Path, catalog_dir: Path) -> dict[str, object]:
    return {
        "artifact_files": list(_ARTIFACT_FILES),
        "catalog_dir": str(catalog_dir),
        "forbidden_scope": list(_FORBIDDEN_SCOPE),
        "input_path": str(input_path),
        "input_sha256": input_sha256,
        "output_dir": str(output_dir),
        "runner": _RUNNER_NAME,
        "scope": _SCOPE,
    }


def _sorted_counter_dict(counter: Counter[str]) -> dict[str, int]:
    return {key: int(counter[key]) for key in sorted(counter)}


def _serialize_check_result(result: CheckResult) -> dict[str, Any]:
    if hasattr(result, "as_dict"):
        payload = result.as_dict()
        if isinstance(payload, dict):
            return payload
    return {
        "capacity": result.capacity,
        "check_id": result.check_id,
        "code_ref": result.code_ref,
        "component": result.component,
        "component_type": result.component_type,
        "demand": result.demand,
        "diagnostics": [diagnostic.as_dict() for diagnostic in result.diagnostics],
        "evaluation_level": result.evaluation_level.value,
        "evidence": list(result.evidence),
        "limit": result.limit,
        "messages": list(result.messages),
        "pass_rule": result.pass_rule,
        "ratio": result.ratio,
        "ratio_type": result.ratio_type,
        "section": result.section,
        "status": result.status.value,
        "story": result.story,
        "unit": result.unit,
        "value": result.value,
    }


def _serialize_adapter_diagnostic(diagnostic: CheckInputBuildDiagnostic) -> dict[str, Any]:
    if diagnostic.status in {"O" + "K", "FA" + "IL"}:
        raise ValueError("Adapter diagnostics must not contain engine decision statuses")
    return {
        "check_id": diagnostic.check_id,
        "component_id": diagnostic.component_id,
        "component_type": diagnostic.component_type,
        "evidence_by_feature": {
            feature_name: [evidence.as_dict() for evidence in evidence_items]
            for feature_name, evidence_items in sorted(diagnostic.evidence_by_feature.items())
        },
        "invalid_features": list(diagnostic.invalid_features),
        "missing_features": list(diagnostic.missing_features),
        "reason": diagnostic.reason,
        "status": diagnostic.status,
    }


def _json_safe(value: object) -> Any:
    if isinstance(value, Enum):
        return value.value
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {
            str(key): _json_safe(nested)
            for key, nested in sorted(value.items(), key=lambda item: str(item[0]))
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_json_safe(item) for item in value]
    if hasattr(value, "as_dict"):
        return _json_safe(value.as_dict())
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(_json_safe(payload), indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


__all__ = ["GeometryVerticalSliceResult", "run_geometry_vertical_slice_from_file"]
