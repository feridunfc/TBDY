"""C13.4-P6 end-to-end geometry product smoke orchestration.

This module orchestrates existing C13.4-P4 and C13.4-P5 APIs only. It does not
execute checks directly and does not call lower-level adapters directly.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import json

from tbdy_engine.checks.geometry_vertical_slice import run_geometry_vertical_slice_from_file
from tbdy_engine.reports.geometry_markdown_report import render_geometry_markdown_report_from_artifact_dir

_RUNNER_NAME = "C13.4-P6 Geometry Product Smoke"
_SCOPE = "GEOMETRY_ONLY_PRODUCT_SMOKE"
_SOURCE_STEPS = (
    "C13.4-P4 Geometry Vertical Slice Runner",
    "C13.4-P5 Geometry Markdown Report Renderer",
)
_ARTIFACT_FILES = (
    "artifacts/coverage_rows.json",
    "artifacts/coverage_execution_trace.json",
    "artifacts/check_results.json",
    "artifacts/adapter_diagnostics.json",
    "artifacts/run_summary.json",
    "artifacts/run_manifest.json",
    "reports/geometry_report.md",
    "product_smoke_summary.json",
    "product_smoke_manifest.json",
)
_TABLE_NAMES = (
    "executive_summary",
    "geometry_check_summary",
    "adapter_diagnostics",
    "beam_geometry_detail",
    "column_geometry_detail",
    "evidence_trace_detail",
    "artifact_manifest",
    "guardrails",
    "boundary_notes",
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
    "modal_mass",
    "ETABS_live_fetching",
    "Excel_production_path",
    "legacy_runtime_execution",
)


@dataclass(frozen=True, slots=True)
class GeometryProductSmokeResult:
    output_dir: Path
    artifact_dir: Path
    report_path: Path
    product_smoke_summary_path: Path
    product_smoke_manifest_path: Path
    status: str
    p4_check_result_count: int
    p4_adapter_diagnostic_count: int
    p4_coverage_execution_trace_count: int
    p5_section_count: int
    p5_table_count: int

    def __post_init__(self) -> None:
        if self.status != "OK":
            raise ValueError("GeometryProductSmokeResult.status must be OK for successful product smoke output")
        object.__setattr__(self, "output_dir", Path(self.output_dir))
        object.__setattr__(self, "artifact_dir", Path(self.artifact_dir))
        object.__setattr__(self, "report_path", Path(self.report_path))
        object.__setattr__(self, "product_smoke_summary_path", Path(self.product_smoke_summary_path))
        object.__setattr__(self, "product_smoke_manifest_path", Path(self.product_smoke_manifest_path))


def run_geometry_product_smoke(
    *,
    feature_snapshot_path: Path,
    output_dir: Path,
    catalog_dir: Path | None = None,
) -> GeometryProductSmokeResult:
    feature_path = Path(feature_snapshot_path)
    root = Path(output_dir)
    artifact_dir = root / "artifacts"
    report_dir = root / "reports"
    report_path = report_dir / "geometry_report.md"
    summary_path = root / "product_smoke_summary.json"
    manifest_path = root / "product_smoke_manifest.json"

    p4_result = run_geometry_vertical_slice_from_file(
        feature_snapshot_path=feature_path,
        output_dir=artifact_dir,
        catalog_dir=catalog_dir,
    )
    p5_result = render_geometry_markdown_report_from_artifact_dir(
        artifact_dir=artifact_dir,
        output_path=report_path,
    )

    summary = _build_summary(
        feature_snapshot_path=feature_path,
        artifact_dir=artifact_dir,
        report_path=report_path,
        summary_path=summary_path,
        manifest_path=manifest_path,
        p4_run_summary=p4_result.run_summary,
        p5_section_count=p5_result.section_count,
        p5_table_names=p5_result.table_names,
    )
    manifest = _build_manifest(
        feature_snapshot_path=feature_path,
        output_dir=root,
        artifact_dir=artifact_dir,
        report_dir=report_dir,
        report_path=report_path,
    )

    root.mkdir(parents=True, exist_ok=True)
    _write_json(summary_path, summary)
    _write_json(manifest_path, manifest)

    return GeometryProductSmokeResult(
        output_dir=root,
        artifact_dir=artifact_dir,
        report_path=report_path,
        product_smoke_summary_path=summary_path,
        product_smoke_manifest_path=manifest_path,
        status="OK",
        p4_check_result_count=_int_value(p4_result.run_summary.get("check_result_count", 0)),
        p4_adapter_diagnostic_count=_int_value(p4_result.run_summary.get("adapter_diagnostic_count", 0)),
        p4_coverage_execution_trace_count=_int_value(
            p4_result.run_summary.get("coverage_execution_trace_count", 0)
        ),
        p5_section_count=p5_result.section_count,
        p5_table_count=len(p5_result.table_names),
    )


def _build_summary(
    *,
    feature_snapshot_path: Path,
    artifact_dir: Path,
    report_path: Path,
    summary_path: Path,
    manifest_path: Path,
    p4_run_summary: Mapping[str, object],
    p5_section_count: int,
    p5_table_names: tuple[str, ...],
) -> dict[str, object]:
    status_counts = _mapping_value(p4_run_summary.get("check_result_status_counts", {}))
    return {
        "artifact_dir": str(artifact_dir),
        "feature_snapshot_path": str(feature_snapshot_path),
        "outputs": {
            "adapter_diagnostics_json": str(artifact_dir / "adapter_diagnostics.json"),
            "check_results_json": str(artifact_dir / "check_results.json"),
            "coverage_rows_json": str(artifact_dir / "coverage_rows.json"),
            "coverage_execution_trace_json": str(artifact_dir / "coverage_execution_trace.json"),
            "geometry_report_md": str(report_path),
            "product_smoke_manifest_json": str(manifest_path),
            "product_smoke_summary_json": str(summary_path),
            "run_manifest_json": str(artifact_dir / "run_manifest.json"),
            "run_summary_json": str(artifact_dir / "run_summary.json"),
        },
        "p4": {
            "adapter_diagnostic_count": _int_value(p4_run_summary.get("adapter_diagnostic_count", 0)),
            "check_result_count": _int_value(p4_run_summary.get("check_result_count", 0)),
            "check_result_status_counts": {str(key): _int_value(value) for key, value in sorted(status_counts.items())},
            "coverage_row_count": _int_value(p4_run_summary.get("coverage_row_count", 0)),
            "coverage_status_counts": {
                str(key): _int_value(value)
                for key, value in sorted(
                    _mapping_value(p4_run_summary.get("coverage_status_counts", {})).items()
                )
            },
            "coverage_execution_trace_count": _int_value(
                p4_run_summary.get("coverage_execution_trace_count", 0)
            ),
            "check_input_emitted_count": _int_value(
                p4_run_summary.get("check_input_emitted_count", 0)
            ),
            "check_input_not_emitted_count": _int_value(
                p4_run_summary.get("check_input_not_emitted_count", 0)
            ),
            "check_result_emitted_count": _int_value(
                p4_run_summary.get("check_result_emitted_count", 0)
            ),
            "check_result_not_emitted_count": _int_value(
                p4_run_summary.get("check_result_not_emitted_count", 0)
            ),
            "trace_adapter_status_counts": {
                str(key): _int_value(value)
                for key, value in sorted(
                    _mapping_value(p4_run_summary.get("trace_adapter_status_counts", {})).items()
                )
            },
            "trace_result_status_counts": {
                str(key): _int_value(value)
                for key, value in sorted(
                    _mapping_value(p4_run_summary.get("trace_result_status_counts", {})).items()
                )
            },
            "executable_input_count": _int_value(p4_run_summary.get("executable_input_count", 0)),
            "snapshot_count": _int_value(p4_run_summary.get("snapshot_count", 0)),
        },
        "p5": {
            "section_count": p5_section_count,
            "table_count": len(p5_table_names),
            "table_names": list(p5_table_names),
        },
        "report_path": str(report_path),
        "scope": _SCOPE,
        "status": "OK",
    }


def _build_manifest(
    *,
    feature_snapshot_path: Path,
    output_dir: Path,
    artifact_dir: Path,
    report_dir: Path,
    report_path: Path,
) -> dict[str, object]:
    return {
        "artifact_dir": str(artifact_dir),
        "artifact_files": list(_ARTIFACT_FILES),
        "feature_snapshot_path": str(feature_snapshot_path),
        "forbidden_scope": list(_FORBIDDEN_SCOPE),
        "guardrails": {
            "etabs_live_fetching_used": False,
            "excel_production_path_used": False,
            "final_building_compliance_verdict_emitted": False,
            "geometry_only": True,
            "legacy_runtime_used": False,
            "modal_mass_unlocked": False,
            "new_engineering_checks_added": False,
            "orchestration_only": True,
            "rebar_flexure_shear_capacity_unlocked": False,
            "streamlit_ui_used": False,
        },
        "output_dir": str(output_dir),
        "report_dir": str(report_dir),
        "report_path": str(report_path),
        "runner": _RUNNER_NAME,
        "scope": _SCOPE,
        "source_steps": list(_SOURCE_STEPS),
    }


def _mapping_value(value: object) -> Mapping[str, object]:
    if isinstance(value, Mapping):
        return value
    return {}


def _int_value(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return 0


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


__all__ = ["GeometryProductSmokeResult", "run_geometry_product_smoke"]
