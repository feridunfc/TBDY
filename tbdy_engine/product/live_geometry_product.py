"""C13.5-P7 live ETABS geometry product orchestration.

This module composes the existing live geometry probe and geometry product smoke
without duplicating either implementation.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import json
import shutil

from tbdy_engine.features.etabs_com_attach import EtabsAttachFailure
from tbdy_engine.features.live_etabs_geometry_probe import (
    LiveGeometryProbeResult,
    create_live_etabs_geometry_provider,
    probe_geometry_feature_snapshots,
    write_com_attach_failure_probe_outputs,
)
from tbdy_engine.product.geometry_product_smoke import (
    GeometryProductSmokeResult,
    run_geometry_product_smoke,
)

_SCOPE = "C13_5_P7_LIVE_ETABS_GEOMETRY_PRODUCT_ORCHESTRATION"
_RUNNER = "C13.5-P7 Live ETABS Geometry Product Orchestration"
_ALLOWED_STATUSES = frozenset({"OK", "PARTIAL", "FAIL"})
_TOP_LEVEL_FILES = (
    "live_geometry_product_summary.json",
    "live_geometry_product_manifest.json",
)
_OWNED_DIRECTORIES = (
    "live_probe",
    "product",
)
_REQUIRED_PRODUCT_FILES = (
    "artifacts/check_results.json",
    "artifacts/adapter_diagnostics.json",
    "artifacts/run_summary.json",
    "artifacts/run_manifest.json",
    "reports/geometry_report.md",
    "product_smoke_summary.json",
    "product_smoke_manifest.json",
)

ProviderFactory = Callable[[], object]
ProbeRunner = Callable[..., LiveGeometryProbeResult]
ProductRunner = Callable[..., GeometryProductSmokeResult]


@dataclass(frozen=True, slots=True)
class LiveGeometryProductResult:
    status: str
    output_dir: Path
    live_probe_output_dir: Path
    product_output_dir: Path
    summary_path: Path
    manifest_path: Path
    feature_snapshot_path: Path | None
    snapshot_count: int | None

    def __post_init__(self) -> None:
        if self.status not in _ALLOWED_STATUSES:
            raise ValueError("Unsupported live geometry product status")
        object.__setattr__(self, "output_dir", Path(self.output_dir))
        object.__setattr__(self, "live_probe_output_dir", Path(self.live_probe_output_dir))
        object.__setattr__(self, "product_output_dir", Path(self.product_output_dir))
        object.__setattr__(self, "summary_path", Path(self.summary_path))
        object.__setattr__(self, "manifest_path", Path(self.manifest_path))
        if self.feature_snapshot_path is not None:
            object.__setattr__(self, "feature_snapshot_path", Path(self.feature_snapshot_path))


def run_live_geometry_product(
    *,
    output_dir: Path,
    target_story: str | None = None,
    target_label: str | None = None,
    target_component: str | None = None,
    max_rows: int = 20,
    design_context: Mapping[str, Any] | None = None,
    provider_factory: ProviderFactory | None = None,
    probe_runner: ProbeRunner | None = None,
    product_runner: ProductRunner | None = None,
) -> LiveGeometryProductResult:
    """Run live probe and feed its exact FeatureSnapshot to product smoke."""
    root = Path(output_dir)
    probe_dir = root / "live_probe"
    product_dir = root / "product"
    summary_path = root / _TOP_LEVEL_FILES[0]
    manifest_path = root / _TOP_LEVEL_FILES[1]
    context = {
        str(key): value
        for key, value in sorted(
            (design_context or {}).items(),
            key=lambda item: str(item[0]),
        )
        if value is not None
    }
    selectors = {
        "target_component": target_component,
        "target_label": target_label,
        "target_story": target_story,
        "max_rows": max_rows,
        "design_context": context,
    }
    _prepare_owned_output_paths(root)

    provider_factory = provider_factory or create_live_etabs_geometry_provider
    probe_runner = probe_runner or probe_geometry_feature_snapshots
    product_runner = product_runner or run_geometry_product_smoke

    try:
        provider = provider_factory()
    except EtabsAttachFailure as exc:
        probe_result = write_com_attach_failure_probe_outputs(
            output_dir=probe_dir,
            attach_result=exc.attach_result,
        )
        return _finish(
            root=root,
            probe_dir=probe_dir,
            product_dir=product_dir,
            summary_path=summary_path,
            manifest_path=manifest_path,
            selectors=selectors,
            status="FAIL",
            live_probe_status=probe_result.status,
            product_status=None,
            snapshot_count=probe_result.snapshot_count,
            probe_diagnostic_count=probe_result.diagnostic_count,
            feature_snapshot_path=None,
            feature_snapshot_consumed=False,
            failure_stage="COM_ATTACH",
            error=exc,
        )
    except Exception as exc:
        return _finish(
            root=root,
            probe_dir=probe_dir,
            product_dir=product_dir,
            summary_path=summary_path,
            manifest_path=manifest_path,
            selectors=selectors,
            status="FAIL",
            live_probe_status=None,
            product_status=None,
            snapshot_count=None,
            probe_diagnostic_count=None,
            feature_snapshot_path=None,
            feature_snapshot_consumed=False,
            failure_stage="PROVIDER_CREATION",
            error=exc,
        )

    try:
        probe_kwargs: dict[str, object] = {
            "provider": provider,
            "output_dir": probe_dir,
            "target_story": target_story,
            "target_label": target_label,
            "target_component": target_component,
            "max_rows": max_rows,
        }
        if context:
            probe_kwargs["design_context"] = context
        probe_result = probe_runner(**probe_kwargs)
    except EtabsAttachFailure as exc:
        probe_result = write_com_attach_failure_probe_outputs(
            output_dir=probe_dir,
            attach_result=exc.attach_result,
        )
        return _finish(
            root=root,
            probe_dir=probe_dir,
            product_dir=product_dir,
            summary_path=summary_path,
            manifest_path=manifest_path,
            selectors=selectors,
            status="FAIL",
            live_probe_status=probe_result.status,
            product_status=None,
            snapshot_count=probe_result.snapshot_count,
            probe_diagnostic_count=probe_result.diagnostic_count,
            feature_snapshot_path=None,
            feature_snapshot_consumed=False,
            failure_stage="COM_ATTACH",
            error=exc,
        )
    except Exception as exc:
        return _finish(
            root=root,
            probe_dir=probe_dir,
            product_dir=product_dir,
            summary_path=summary_path,
            manifest_path=manifest_path,
            selectors=selectors,
            status="FAIL",
            live_probe_status="FAIL",
            product_status=None,
            snapshot_count=None,
            probe_diagnostic_count=None,
            feature_snapshot_path=None,
            feature_snapshot_consumed=False,
            failure_stage="LIVE_PROBE",
            error=exc,
        )

    feature_path = Path(probe_result.feature_snapshot_path)
    probe_summary = _read_json_mapping(probe_result.summary_path)
    snapshot_count = probe_result.snapshot_count
    if (
        probe_result.status == "FAIL"
        or not feature_path.is_file()
        or snapshot_count <= 0
    ):
        return _finish(
            root=root,
            probe_dir=probe_dir,
            product_dir=product_dir,
            summary_path=summary_path,
            manifest_path=manifest_path,
            selectors=selectors,
            status="FAIL",
            live_probe_status=probe_result.status,
            product_status=None,
            snapshot_count=snapshot_count,
            probe_diagnostic_count=probe_result.diagnostic_count,
            feature_snapshot_path=feature_path if feature_path.is_file() else None,
            feature_snapshot_consumed=False,
            probe_summary=probe_summary,
            failure_stage="LIVE_PROBE",
        )

    try:
        product_result = product_runner(
            feature_snapshot_path=feature_path,
            output_dir=product_dir,
        )
    except Exception as exc:
        return _finish(
            root=root,
            probe_dir=probe_dir,
            product_dir=product_dir,
            summary_path=summary_path,
            manifest_path=manifest_path,
            selectors=selectors,
            status="FAIL",
            live_probe_status=probe_result.status,
            product_status="FAIL",
            snapshot_count=snapshot_count,
            probe_diagnostic_count=probe_result.diagnostic_count,
            feature_snapshot_path=feature_path,
            feature_snapshot_consumed=True,
            probe_summary=probe_summary,
            failure_stage="PRODUCT_SMOKE",
            error=exc,
        )

    product_summary = _read_json_mapping(
        getattr(product_result, "product_smoke_summary_path", product_dir / "product_smoke_summary.json")
    )
    product_status = str(getattr(product_result, "status", "")) or None
    missing_product_files = tuple(
        relative for relative in _REQUIRED_PRODUCT_FILES if not (product_dir / relative).is_file()
    )
    if product_status != "OK" or missing_product_files:
        return _finish(
            root=root,
            probe_dir=probe_dir,
            product_dir=product_dir,
            summary_path=summary_path,
            manifest_path=manifest_path,
            selectors=selectors,
            status="FAIL",
            live_probe_status=probe_result.status,
            product_status="FAIL",
            snapshot_count=snapshot_count,
            probe_diagnostic_count=probe_result.diagnostic_count,
            feature_snapshot_path=feature_path,
            feature_snapshot_consumed=True,
            probe_summary=probe_summary,
            product_result=product_result,
            product_summary=product_summary,
            failure_stage="PRODUCT_ARTIFACT_VALIDATION",
            missing_product_files=missing_product_files,
        )

    top_status = "PARTIAL" if probe_result.status == "PARTIAL" else "OK"
    return _finish(
        root=root,
        probe_dir=probe_dir,
        product_dir=product_dir,
        summary_path=summary_path,
        manifest_path=manifest_path,
        selectors=selectors,
        status=top_status,
        live_probe_status=probe_result.status,
        product_status=product_status,
        snapshot_count=snapshot_count,
        probe_diagnostic_count=probe_result.diagnostic_count,
        feature_snapshot_path=feature_path,
        feature_snapshot_consumed=True,
        probe_summary=probe_summary,
        product_result=product_result,
        product_summary=product_summary,
    )


def _prepare_owned_output_paths(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    for directory_name in _OWNED_DIRECTORIES:
        _remove_owned_path(root / directory_name)
    for file_name in _TOP_LEVEL_FILES:
        _remove_owned_path(root / file_name)


def _remove_owned_path(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)


def _finish(
    *,
    root: Path,
    probe_dir: Path,
    product_dir: Path,
    summary_path: Path,
    manifest_path: Path,
    selectors: Mapping[str, object],
    status: str,
    live_probe_status: str | None,
    product_status: str | None,
    snapshot_count: int | None,
    probe_diagnostic_count: int | None,
    feature_snapshot_path: Path | None,
    feature_snapshot_consumed: bool,
    probe_summary: Mapping[str, object] | None = None,
    product_result: object | None = None,
    product_summary: Mapping[str, object] | None = None,
    failure_stage: str | None = None,
    error: Exception | None = None,
    missing_product_files: tuple[str, ...] = (),
) -> LiveGeometryProductResult:
    probe_summary = probe_summary or _read_json_mapping(probe_dir / "live_geometry_probe_summary.json")
    product_summary = product_summary or _read_json_mapping(product_dir / "product_smoke_summary.json")
    population_audit_path = probe_dir / "probe_population_audit.json"
    summary = {
        "status": status,
        "live_probe_status": live_probe_status,
        "product_status": product_status,
        "snapshot_count": snapshot_count,
        "probe_diagnostic_count": probe_diagnostic_count,
        "resolved_geometry_row_count": _mapping_value_or_none(probe_summary, "resolved_geometry_row_count"),
        "feature_status_counts": _mapping_value_or_none(probe_summary, "feature_status_counts"),
        "length_unit_source": _mapping_value_or_none(probe_summary, "length_unit_source"),
        "target_report_length_unit": _mapping_value_or_none(probe_summary, "target_report_length_unit"),
        "product_check_result_count": _product_count(
            product_result,
            product_summary,
            attribute="p4_check_result_count",
            summary_key="check_result_count",
        ),
        "product_adapter_diagnostic_count": _product_count(
            product_result,
            product_summary,
            attribute="p4_adapter_diagnostic_count",
            summary_key="adapter_diagnostic_count",
        ),
        "live_probe_output_dir": _relative(root, probe_dir),
        "product_output_dir": _relative(root, product_dir),
        "feature_snapshot_path": _relative(root, feature_snapshot_path),
        "population_audit_path": _relative(root, population_audit_path if population_audit_path.is_file() else None),
        "feature_snapshot_consumed_by_product": feature_snapshot_consumed,
        "failure_stage": failure_stage,
        "error_type": type(error).__name__ if error is not None else None,
        "error_message": str(error) if error is not None else None,
        "missing_product_files": list(missing_product_files),
    }
    _write_json(summary_path, summary)

    probe_manifest = probe_dir / "live_geometry_probe_manifest.json"
    product_manifest = product_dir / "product_smoke_manifest.json"
    manifest = {
        "scope": _SCOPE,
        "runner": _RUNNER,
        "live_etabs_required_for_ci": False,
        "live_etabs_explicit_opt_in_required": True,
        "probe_is_read_only": True,
        "feature_snapshot_consumed_without_rewrite": True,
        "source_probe_manifest": _relative(root, probe_manifest if probe_manifest.is_file() else None),
        "source_population_audit": _relative(root, population_audit_path if population_audit_path.is_file() else None),
        "source_product_manifest": _relative(root, product_manifest if product_manifest.is_file() else None),
        "output_files": _output_files(
            root=root,
            probe_dir=probe_dir,
            product_dir=product_dir,
            summary_path=summary_path,
            manifest_path=manifest_path,
        ),
        "selectors": dict(selectors),
    }
    _write_json(manifest_path, manifest)

    return LiveGeometryProductResult(
        status=status,
        output_dir=root,
        live_probe_output_dir=probe_dir,
        product_output_dir=product_dir,
        summary_path=summary_path,
        manifest_path=manifest_path,
        feature_snapshot_path=feature_snapshot_path,
        snapshot_count=snapshot_count,
    )


def _product_count(
    result: object | None,
    summary: Mapping[str, object],
    *,
    attribute: str,
    summary_key: str,
) -> int | None:
    value = getattr(result, attribute, None) if result is not None else None
    parsed = _optional_int(value)
    if parsed is not None:
        return parsed
    p4 = summary.get("p4")
    if isinstance(p4, Mapping):
        return _optional_int(p4.get(summary_key))
    return None


def _mapping_value_or_none(mapping: Mapping[str, object], key: str) -> object | None:
    return mapping[key] if key in mapping else None


def _optional_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def _read_json_mapping(path: Path | str) -> Mapping[str, object]:
    candidate = Path(path)
    if not candidate.is_file():
        return {}
    try:
        payload = json.loads(candidate.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, Mapping) else {}


def _relative(root: Path, path: Path | None) -> str | None:
    if path is None:
        return None
    try:
        return Path(path).resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(Path(path))


def _output_files(
    *,
    root: Path,
    probe_dir: Path,
    product_dir: Path,
    summary_path: Path,
    manifest_path: Path,
) -> list[str]:
    files = {
        summary_path.relative_to(root).as_posix(),
        manifest_path.relative_to(root).as_posix(),
    }
    for owned_directory in (probe_dir, product_dir):
        if not owned_directory.is_dir():
            continue
        files.update(
            path.relative_to(root).as_posix()
            for path in owned_directory.rglob("*")
            if path.is_file()
        )
    return sorted(files)


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


__all__ = ["LiveGeometryProductResult", "run_live_geometry_product"]
