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

from tbdy_engine.checks.coverage_artifact import canonicalize_coverage_rows
from tbdy_engine.checks.coverage_execution_trace import (
    CoverageExecutionTraceRow,
    canonicalize_coverage_execution_trace,
    coverage_row_identity,
)
from tbdy_engine.checks.engine import MinimalCheckEngine
from tbdy_engine.checks.geometry_coverage_orchestration import (
    assemble_geometry_check_inputs,
    load_geometry_contract_bundle,
)
from tbdy_engine.checks.input_adapter import (
    CheckInputBuildDiagnostic,
    GeometryCheckInput,
    normalize_geometry_feature_snapshot_input,
)
from tbdy_engine.checks.result import CheckResult
from tbdy_engine.coverage.models import CoverageRow

_RUNNER_NAME = "C13.4-P4 Geometry Vertical Slice Runner"
_SCOPE = "GEOMETRY_ONLY"
_ARTIFACT_FILES = (
    "coverage_rows.json",
    "coverage_execution_trace.json",
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
    coverage_rows: tuple[CoverageRow, ...]
    coverage_execution_trace: tuple[CoverageExecutionTraceRow, ...]
    check_results: tuple[CheckResult, ...]
    adapter_diagnostics: tuple[CheckInputBuildDiagnostic, ...]
    run_summary: Mapping[str, object]
    manifest: Mapping[str, object]

    def __post_init__(self) -> None:
        coverage_rows = tuple(self.coverage_rows)
        coverage_execution_trace = tuple(self.coverage_execution_trace)
        check_results = tuple(self.check_results)
        adapter_diagnostics = tuple(self.adapter_diagnostics)
        if any(not isinstance(item, CoverageRow) for item in coverage_rows):
            raise TypeError("GeometryVerticalSliceResult.coverage_rows must contain CoverageRow objects")
        if any(not isinstance(item, CoverageExecutionTraceRow) for item in coverage_execution_trace):
            raise TypeError(
                "GeometryVerticalSliceResult.coverage_execution_trace must contain "
                "CoverageExecutionTraceRow objects"
            )
        if any(not isinstance(item, CheckResult) for item in check_results):
            raise TypeError("GeometryVerticalSliceResult.check_results must contain CheckResult objects")
        if any(not isinstance(item, CheckInputBuildDiagnostic) for item in adapter_diagnostics):
            raise TypeError(
                "GeometryVerticalSliceResult.adapter_diagnostics must contain CheckInputBuildDiagnostic objects"
            )
        object.__setattr__(self, "coverage_rows", coverage_rows)
        object.__setattr__(self, "coverage_execution_trace", coverage_execution_trace)
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
    effective_catalog_dir = (
        Path(catalog_dir)
        if catalog_dir is not None
        else _DEFAULT_CATALOG_DIR
    )

    input_bytes = input_path.read_bytes()
    input_payload = json.loads(input_bytes.decode("utf-8"))
    snapshots = _normalize_input_payload(input_payload)
    check_definitions = _load_check_definitions(
        effective_catalog_dir
    )
    contract_bundle = load_geometry_contract_bundle(
        effective_catalog_dir
    )
    engine = MinimalCheckEngine(check_definitions)

    coverage_rows: list[CoverageRow] = []
    coverage_execution_trace: list[CoverageExecutionTraceRow] = []
    check_results: list[CheckResult] = []
    adapter_diagnostics: list[CheckInputBuildDiagnostic] = []
    seen_coverage_keys: set[tuple[str, str, str]] = set()
    executable_input_count = 0

    for snapshot_payload in snapshots:
        snapshot = normalize_geometry_feature_snapshot_input(
            snapshot_payload
        )
        assembly = assemble_geometry_check_inputs(
            snapshot=snapshot,
            contract_bundle=contract_bundle,
        )
        adapter_result = assembly.build_result
        assembly_rows = tuple(assembly.coverage_rows)
        for coverage_row in assembly_rows:
            key = coverage_row_identity(coverage_row)
            if key in seen_coverage_keys:
                raise ValueError(
                    "Duplicate authoritative CoverageRow canonical key: "
                    f"component_type={key[0]!r}, component_id={key[1]!r}, check_id={key[2]!r}"
                )
            seen_coverage_keys.add(key)
        coverage_rows.extend(assembly_rows)
        executable_input_count += len(adapter_result.check_inputs)
        coverage_execution_trace.extend(
            _execute_coverage_assembly(
                coverage_rows=assembly_rows,
                check_inputs=adapter_result.check_inputs,
                diagnostics=adapter_result.diagnostics,
                engine=engine,
                check_results=check_results,
                adapter_diagnostics=adapter_diagnostics,
            )
        )

    canonical_coverage_rows = canonicalize_coverage_rows(coverage_rows)
    canonical_execution_trace = canonicalize_coverage_execution_trace(
        coverage_execution_trace,
        coverage_rows=canonical_coverage_rows,
        check_results=check_results,
        adapter_diagnostics=adapter_diagnostics,
    )
    summary = _build_summary(
        snapshots=snapshots,
        executable_input_count=executable_input_count,
        coverage_rows=canonical_coverage_rows,
        coverage_execution_trace=canonical_execution_trace,
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
    _write_json(
        out_dir / "coverage_rows.json",
        [row.as_dict() for row in canonical_coverage_rows],
    )
    _write_json(
        out_dir / "coverage_execution_trace.json",
        [row.as_dict() for row in canonical_execution_trace],
    )
    _write_json(
        out_dir / "check_results.json",
        [_serialize_check_result(item) for item in check_results],
    )
    _write_json(
        out_dir / "adapter_diagnostics.json",
        [
            _serialize_adapter_diagnostic(item)
            for item in adapter_diagnostics
        ],
    )
    _write_json(out_dir / "run_summary.json", summary)
    _write_json(out_dir / "run_manifest.json", manifest)

    return GeometryVerticalSliceResult(
        coverage_rows=canonical_coverage_rows,
        coverage_execution_trace=canonical_execution_trace,
        check_results=tuple(check_results),
        adapter_diagnostics=tuple(adapter_diagnostics),
        run_summary=summary,
        manifest=manifest,
    )


def _execute_coverage_assembly(
    *,
    coverage_rows: Sequence[CoverageRow],
    check_inputs: Sequence[GeometryCheckInput],
    diagnostics: Sequence[CheckInputBuildDiagnostic],
    engine: MinimalCheckEngine,
    check_results: list[CheckResult],
    adapter_diagnostics: list[CheckInputBuildDiagnostic],
) -> tuple[CoverageExecutionTraceRow, ...]:
    authoritative_by_key = {
        coverage_row_identity(row): row
        for row in coverage_rows
    }
    if len(authoritative_by_key) != len(coverage_rows):
        raise ValueError("Duplicate authoritative CoverageRow canonical key within assembly")

    input_by_key: dict[tuple[str, str, str], GeometryCheckInput] = {}
    for check_input in check_inputs:
        if not isinstance(check_input, GeometryCheckInput):
            raise TypeError("check_inputs must contain GeometryCheckInput objects")
        key = (
            check_input.component_type,
            check_input.component_id,
            check_input.check_id,
        )
        coverage_row = authoritative_by_key.get(key)
        if coverage_row is None:
            raise ValueError(f"GeometryCheckInput identity has no authoritative CoverageRow: {key!r}")
        if check_input.coverage is not coverage_row:
            raise ValueError(
                "GeometryCheckInput must retain the exact authoritative CoverageRow object"
            )
        if (
            check_input.check_id != coverage_row.check_id
            or check_input.component_type != coverage_row.component_type
            or check_input.component_id != coverage_row.component_id
        ):
            raise ValueError("GeometryCheckInput identity does not match authoritative CoverageRow")
        if key in input_by_key:
            raise ValueError(f"More than one GeometryCheckInput matched CoverageRow: {key!r}")
        input_by_key[key] = check_input

    diagnostic_base_index = len(adapter_diagnostics)
    diagnostic_link_by_key: dict[tuple[str, str, str], tuple[int, CheckInputBuildDiagnostic]] = {}
    for local_index, diagnostic in enumerate(diagnostics):
        if not isinstance(diagnostic, CheckInputBuildDiagnostic):
            raise TypeError("diagnostics must contain CheckInputBuildDiagnostic objects")
        if diagnostic.check_id == "geometry_check_input_adapter":
            if coverage_rows:
                raise ValueError(
                    "Adapter-level geometry diagnostic is only valid when no CoverageRows exist"
                )
            continue
        if diagnostic.component_id is None:
            raise ValueError("Coverage-specific adapter diagnostic requires component_id")
        key = (
            diagnostic.component_type,
            diagnostic.component_id,
            diagnostic.check_id,
        )
        if key not in authoritative_by_key:
            raise ValueError(f"Adapter diagnostic identity has no authoritative CoverageRow: {key!r}")
        if key in diagnostic_link_by_key:
            raise ValueError(f"More than one adapter diagnostic matched CoverageRow: {key!r}")
        diagnostic_link_by_key[key] = (diagnostic_base_index + local_index, diagnostic)

    for coverage_row in coverage_rows:
        key = coverage_row_identity(coverage_row)
        has_input = key in input_by_key
        has_diagnostic = key in diagnostic_link_by_key
        if has_input and has_diagnostic:
            raise ValueError(f"CoverageRow matched both a CheckInput and adapter diagnostic: {key!r}")
        if not has_input and not has_diagnostic:
            raise ValueError(f"CoverageRow has no terminal adapter outcome: {key!r}")

    adapter_diagnostics.extend(diagnostics)
    result_link_by_key: dict[tuple[str, str, str], tuple[int, CheckResult]] = {}
    for check_input in check_inputs:
        key = (
            check_input.component_type,
            check_input.component_id,
            check_input.check_id,
        )
        coverage_row = authoritative_by_key[key]
        result_index = len(check_results)
        result = engine.run_check(
            check_input.check_id,
            check_input.snapshot,
            check_input.coverage,
        )
        if not isinstance(result, CheckResult):
            raise TypeError("MinimalCheckEngine.run_check must return CheckResult")
        if (
            result.check_id != coverage_row.check_id
            or result.component_type != coverage_row.component_type
            or result.component != coverage_row.component_id
        ):
            raise ValueError("CheckResult identity does not match authoritative CoverageRow")
        check_results.append(result)
        result_link_by_key[key] = (result_index, result)

    trace_rows: list[CoverageExecutionTraceRow] = []
    for coverage_row in coverage_rows:
        key = coverage_row_identity(coverage_row)
        result_link = result_link_by_key.get(key)
        if result_link is not None:
            result_index, result = result_link
            trace_rows.append(
                CoverageExecutionTraceRow(
                    component_type=coverage_row.component_type,
                    component_id=coverage_row.component_id,
                    check_id=coverage_row.check_id,
                    coverage_status=coverage_row.coverage_status.value,
                    check_input_emitted=True,
                    adapter_status="READY",
                    adapter_reason=None,
                    adapter_diagnostic_index=None,
                    check_result_emitted=True,
                    check_result_index=result_index,
                    check_result_status=result.status.value,
                )
            )
        else:
            diagnostic_index, diagnostic = diagnostic_link_by_key[key]
            trace_rows.append(
                CoverageExecutionTraceRow(
                    component_type=coverage_row.component_type,
                    component_id=coverage_row.component_id,
                    check_id=coverage_row.check_id,
                    coverage_status=coverage_row.coverage_status.value,
                    check_input_emitted=False,
                    adapter_status=diagnostic.status,
                    adapter_reason=diagnostic.reason,
                    adapter_diagnostic_index=diagnostic_index,
                    check_result_emitted=False,
                    check_result_index=None,
                    check_result_status=None,
                )
            )
    return tuple(trace_rows)

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
    coverage_rows: Sequence[CoverageRow],
    coverage_execution_trace: Sequence[CoverageExecutionTraceRow],
    check_results: Sequence[CheckResult],
    adapter_diagnostics: Sequence[CheckInputBuildDiagnostic],
) -> dict[str, object]:
    status_counts = Counter(result.status.value for result in check_results)
    coverage_status_counts = Counter(row.coverage_status.value for row in coverage_rows)
    trace_adapter_status_counts = Counter(row.adapter_status for row in coverage_execution_trace)
    trace_result_status_counts = Counter(
        row.check_result_status
        for row in coverage_execution_trace
        if row.check_result_status is not None
    )
    check_input_emitted_count = sum(row.check_input_emitted for row in coverage_execution_trace)
    check_result_emitted_count = sum(row.check_result_emitted for row in coverage_execution_trace)
    check_id_counts = Counter(result.check_id for result in check_results)
    component_type_counts = Counter(str(snapshot["component_type"]) for snapshot in snapshots)
    return {
        "adapter_diagnostic_count": len(adapter_diagnostics),
        "check_id_counts": _sorted_counter_dict(check_id_counts),
        "check_result_count": len(check_results),
        "check_result_status_counts": _sorted_counter_dict(status_counts),
        "component_type_counts": _sorted_counter_dict(component_type_counts),
        "coverage_execution_trace_count": len(coverage_execution_trace),
        "coverage_row_count": len(coverage_rows),
        "coverage_status_counts": _sorted_counter_dict(coverage_status_counts),
        "check_input_emitted_count": check_input_emitted_count,
        "check_input_not_emitted_count": len(coverage_execution_trace) - check_input_emitted_count,
        "check_result_emitted_count": check_result_emitted_count,
        "check_result_not_emitted_count": len(coverage_execution_trace) - check_result_emitted_count,
        "executable_input_count": executable_input_count,
        "trace_adapter_status_counts": _sorted_counter_dict(trace_adapter_status_counts),
        "trace_result_status_counts": _sorted_counter_dict(trace_result_status_counts),
        "snapshot_count": len(snapshots),
        "status": "OK",
    }


def _build_manifest(*, input_path: Path, input_sha256: str, output_dir: Path, catalog_dir: Path) -> dict[str, object]:
    return {
        "artifact_files": list(_ARTIFACT_FILES),
        "catalog_dir": str(catalog_dir),
        "coverage_artifact_source": "authoritative_runtime_objects",
        "coverage_authority": "CoverageBuilder",
        "coverage_reconstructed_from_check_results": False,
        "execution_trace_authority": "runtime_coverage_adapter_engine_chain",
        "execution_trace_artifact_source": "authoritative_runtime_objects",
        "execution_trace_reconstructed_from_serialized_artifacts": False,
        "execution_trace_covers_every_coverage_row": True,
        "check_input_coverage_object_identity_required": True,
        "forbidden_scope": list(_FORBIDDEN_SCOPE),
        "input_path": str(input_path),
        "input_sha256": input_sha256,
        "output_dir": str(output_dir),
        "runner": _RUNNER_NAME,
        "scope": _SCOPE,
        "synthetic_coverage_path_used": False,
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
