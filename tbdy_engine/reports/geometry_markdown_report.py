"""C13.4-P5 deterministic Markdown report for P4 geometry artifacts.

This module is report-only. It reads P4 JSON artifacts and renders Markdown
without executing checks or introducing engineering calculations.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import json

_REQUIRED_ARTIFACTS = (
    "check_results.json",
    "adapter_diagnostics.json",
    "run_summary.json",
    "run_manifest.json",
)
_REPORT_TITLE = "# TBDY Geometry Vertical Slice Report — C13.4-P5"
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
_STATUS_KEYS = ("OK", "FAIL", "NO_DATA", "BLOCKED", "WARNING", "OUT_OF_SCOPE")
_DETAIL_COLUMNS = (
    "component",
    "story",
    "section",
    "check_id",
    "value",
    "limit",
    "unit",
    "comparison",
    "status",
    "ratio",
    "evidence_table",
    "evidence_columns",
    "raw_values",
    "normalized_values",
)


@dataclass(frozen=True, slots=True)
class GeometryMarkdownReportResult:
    report_path: Path
    section_count: int
    table_names: tuple[str, ...]
    source_artifacts: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "report_path", Path(self.report_path))
        object.__setattr__(self, "table_names", tuple(str(item) for item in self.table_names))
        object.__setattr__(self, "source_artifacts", tuple(str(item) for item in self.source_artifacts))


def render_geometry_markdown_report_from_artifact_dir(
    *,
    artifact_dir: Path,
    output_path: Path,
) -> GeometryMarkdownReportResult:
    artifact_root = Path(artifact_dir)
    output = Path(output_path)
    artifacts = _load_required_artifacts(artifact_root)

    check_results = _require_list(artifacts["check_results.json"], "check_results.json")
    adapter_diagnostics = _require_list(artifacts["adapter_diagnostics.json"], "adapter_diagnostics.json")
    run_summary = _require_mapping(artifacts["run_summary.json"], "run_summary.json")
    run_manifest = _require_mapping(artifacts["run_manifest.json"], "run_manifest.json")
    _validate_adapter_diagnostics(adapter_diagnostics)

    report = _render_report(
        check_results=check_results,
        adapter_diagnostics=adapter_diagnostics,
        run_summary=run_summary,
        run_manifest=run_manifest,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report, encoding="utf-8")
    return GeometryMarkdownReportResult(
        report_path=output,
        section_count=len(_TABLE_NAMES),
        table_names=_TABLE_NAMES,
        source_artifacts=_REQUIRED_ARTIFACTS,
    )


def _load_required_artifacts(artifact_dir: Path) -> dict[str, object]:
    artifacts: dict[str, object] = {}
    for artifact_name in _REQUIRED_ARTIFACTS:
        artifact_path = artifact_dir / artifact_name
        if not artifact_path.is_file():
            raise FileNotFoundError(f"Required P4 artifact missing: {artifact_path}")
        with artifact_path.open("r", encoding="utf-8") as handle:
            artifacts[artifact_name] = json.load(handle)
    return artifacts


def _render_report(
    *,
    check_results: Sequence[object],
    adapter_diagnostics: Sequence[object],
    run_summary: Mapping[str, object],
    run_manifest: Mapping[str, object],
) -> str:
    sections = [
        _section("1. Executive Summary", "executive_summary", _executive_summary_rows(run_summary, run_manifest), ("metric", "value")),
        _section("2. Geometry Check Summary", "geometry_check_summary", _geometry_check_summary_rows(check_results), ("check_id", "count", "ok_count", "fail_count", "no_data_count", "blocked_count", "warning_count", "out_of_scope_count")),
        _section("3. Adapter Diagnostics", "adapter_diagnostics", _adapter_diagnostic_rows(adapter_diagnostics), ("check_id", "component_id", "component_type", "status", "missing_features", "invalid_features", "reason")),
        _section("4. Beam Geometry Detail", "beam_geometry_detail", _geometry_detail_rows(check_results, component_type="beam"), _DETAIL_COLUMNS),
        _section("5. Column Geometry Detail", "column_geometry_detail", _geometry_detail_rows(check_results, component_type="column"), _DETAIL_COLUMNS),
        _section("6. Evidence Trace Detail", "evidence_trace_detail", _evidence_trace_rows(check_results), ("component", "component_type", "check_id", "evidence_index", "evidence_status", "source_table", "actual_table_name", "source_column", "raw_value", "normalized_value", "unit", "resolver")),
        _section("7. Artifact Manifest", "artifact_manifest", _artifact_manifest_rows(run_manifest), ("item", "value")),
        _section("8. Guardrails", "guardrails", _guardrail_rows(), ("guardrail", "value")),
        _section("9. Boundary Notes", "boundary_notes", _boundary_note_rows(), ("item", "statement")),
    ]
    return _REPORT_TITLE + "\n\n" + "\n\n".join(sections) + "\n"


def _section(title: str, table_name: str, rows: Sequence[Mapping[str, object]], columns: Sequence[str]) -> str:
    return f"## {title}\nTable name: {table_name}\n\n" + _markdown_table(columns, rows)


def _executive_summary_rows(run_summary: Mapping[str, object], run_manifest: Mapping[str, object]) -> tuple[dict[str, object], ...]:
    status_counts = _mapping_value(run_summary, "check_result_status_counts")
    return (
        {"metric": "report_product_passed", "value": True},
        {"metric": "geometry_vertical_slice_status", "value": run_summary.get("status", "")},
        {"metric": "snapshot_count", "value": run_summary.get("snapshot_count", 0)},
        {"metric": "executable_input_count", "value": run_summary.get("executable_input_count", 0)},
        {"metric": "check_result_count", "value": run_summary.get("check_result_count", 0)},
        {"metric": "adapter_diagnostic_count", "value": run_summary.get("adapter_diagnostic_count", 0)},
        {"metric": "total_ok_count", "value": _count_status(status_counts, "OK")},
        {"metric": "total_fail_count", "value": _count_status(status_counts, "FAIL")},
        {"metric": "total_no_data_count", "value": _count_status(status_counts, "NO_DATA")},
        {"metric": "total_blocked_count", "value": _count_status(status_counts, "BLOCKED")},
        {"metric": "total_warning_count", "value": _count_status(status_counts, "WARNING")},
        {"metric": "total_out_of_scope_count", "value": _count_status(status_counts, "OUT_OF_SCOPE")},
        {"metric": "artifact_scope", "value": run_manifest.get("scope", "")},
        {"metric": "source_runner", "value": run_manifest.get("runner", "")},
    )


def _geometry_check_summary_rows(check_results: Sequence[object]) -> tuple[dict[str, object], ...]:
    grouped: dict[str, Counter[str]] = defaultdict(Counter)
    for raw_result in check_results:
        result = _require_mapping(raw_result, "check_results[]")
        check_id = str(result.get("check_id", ""))
        status = str(result.get("status", ""))
        grouped[check_id][status] += 1
    rows: list[dict[str, object]] = []
    for check_id in sorted(grouped):
        counts = grouped[check_id]
        rows.append(
            {
                "check_id": check_id,
                "count": sum(counts.values()),
                "ok_count": counts["OK"],
                "fail_count": counts["FAIL"],
                "no_data_count": counts["NO_DATA"],
                "blocked_count": counts["BLOCKED"],
                "warning_count": counts["WARNING"],
                "out_of_scope_count": counts["OUT_OF_SCOPE"],
            }
        )
    return tuple(rows)


def _adapter_diagnostic_rows(adapter_diagnostics: Sequence[object]) -> tuple[dict[str, object], ...]:
    if not adapter_diagnostics:
        return (
            {
                "check_id": "-",
                "component_id": "-",
                "component_type": "-",
                "status": "NONE",
                "missing_features": "",
                "invalid_features": "",
                "reason": "No adapter diagnostics",
            },
        )
    rows: list[dict[str, object]] = []
    for raw_diagnostic in adapter_diagnostics:
        diagnostic = _require_mapping(raw_diagnostic, "adapter_diagnostics[]")
        rows.append(
            {
                "check_id": diagnostic.get("check_id", ""),
                "component_id": diagnostic.get("component_id", ""),
                "component_type": diagnostic.get("component_type", ""),
                "status": diagnostic.get("status", ""),
                "missing_features": _sequence_value(diagnostic.get("missing_features", ())),
                "invalid_features": _sequence_value(diagnostic.get("invalid_features", ())),
                "reason": diagnostic.get("reason", ""),
            }
        )
    return tuple(sorted(rows, key=lambda item: (str(item["component_id"]), str(item["check_id"]), str(item["status"]))))


def _geometry_detail_rows(check_results: Sequence[object], *, component_type: str) -> tuple[dict[str, object], ...]:
    rows: list[dict[str, object]] = []
    for raw_result in check_results:
        result = _require_mapping(raw_result, "check_results[]")
        if str(result.get("component_type", "")).casefold() != component_type:
            continue
        evidence = _evidence_sequence(result)
        rows.append(
            {
                "component": result.get("component", ""),
                "story": result.get("story", ""),
                "section": result.get("section", ""),
                "check_id": result.get("check_id", ""),
                "value": result.get("value", ""),
                "limit": result.get("limit", ""),
                "unit": result.get("unit", ""),
                "comparison": _comparison_text(result),
                "status": result.get("status", ""),
                "ratio": result.get("ratio", ""),
                "evidence_table": _joined_evidence_field(evidence, "source_table"),
                "evidence_columns": _joined_evidence_field(evidence, "source_column"),
                "raw_values": _joined_evidence_field(evidence, "raw_value"),
                "normalized_values": _joined_evidence_field(evidence, "normalized_value"),
            }
        )
    return tuple(sorted(rows, key=lambda item: (str(item["component"]), str(item["check_id"]))))


def _comparison_text(result: Mapping[str, object]) -> str:
    ratio_type = result.get("ratio_type")
    if ratio_type == "actual_over_minimum":
        return "value >= limit"
    if ratio_type == "value_over_maximum":
        return "value <= limit"
    return "" if ratio_type is None else str(ratio_type)


def _evidence_trace_rows(check_results: Sequence[object]) -> tuple[dict[str, object], ...]:
    rows: list[dict[str, object]] = []
    for raw_result in check_results:
        result = _require_mapping(raw_result, "check_results[]")
        evidence_items = _evidence_sequence(result)
        for evidence_index, evidence in enumerate(evidence_items):
            rows.append(
                {
                    "component": result.get("component", ""),
                    "component_type": result.get("component_type", ""),
                    "check_id": result.get("check_id", ""),
                    "evidence_index": evidence_index,
                    "evidence_status": evidence.get("evidence_status", ""),
                    "source_table": evidence.get("source_table", ""),
                    "actual_table_name": evidence.get("actual_table_name", ""),
                    "source_column": evidence.get("source_column", ""),
                    "raw_value": evidence.get("raw_value", ""),
                    "normalized_value": evidence.get("normalized_value", ""),
                    "unit": evidence.get("unit", ""),
                    "resolver": evidence.get("resolver", ""),
                }
            )
    if not rows:
        return (
            {
                "component": "-",
                "component_type": "-",
                "check_id": "-",
                "evidence_index": "-",
                "evidence_status": "NONE",
                "source_table": "",
                "actual_table_name": "",
                "source_column": "",
                "raw_value": "",
                "normalized_value": "",
                "unit": "",
                "resolver": "",
            },
        )
    return tuple(sorted(rows, key=lambda item: (str(item["component"]), str(item["check_id"]), int(item["evidence_index"]))))


def _artifact_manifest_rows(run_manifest: Mapping[str, object]) -> tuple[dict[str, object], ...]:
    return tuple(
        {"item": item, "value": run_manifest.get(item, "")}
        for item in (
            "runner",
            "scope",
            "input_path",
            "input_sha256",
            "output_dir",
            "catalog_dir",
            "artifact_files",
            "forbidden_scope",
        )
    )


def _guardrail_rows() -> tuple[dict[str, object], ...]:
    return (
        {"guardrail": "json_artifact_input_used", "value": True},
        {"guardrail": "etabs_live_fetching_used", "value": False},
        {"guardrail": "excel_production_path_used", "value": False},
        {"guardrail": "streamlit_ui_used", "value": False},
        {"guardrail": "legacy_runtime_used", "value": False},
        {"guardrail": "rebar_flexure_shear_capacity_unlocked", "value": False},
        {"guardrail": "modal_mass_unlocked", "value": False},
        {"guardrail": "report_only_no_check_execution", "value": True},
        {"guardrail": "no_new_engineering_logic", "value": True},
    )


def _boundary_note_rows() -> tuple[dict[str, str], ...]:
    return (
        {"item": "scope", "statement": "This report summarizes the C13.4 geometry vertical slice artifacts only."},
        {"item": "source", "statement": "Report input is P4 JSON artifacts, not ETABS or Excel."},
        {"item": "unsupported_sections", "statement": "Unsupported or out-of-scope components appear only through adapter diagnostics and are not treated as concrete geometry failures."},
        {"item": "excluded_engineering_checks", "statement": "Rebar, flexure, shear, force envelopes, capacity design, SCWB, PMM, drift, modal mass, and final building compliance are intentionally excluded."},
        {"item": "evidence", "statement": "Evidence is reported from CheckResult payloads and is not recomputed by the report layer."},
    )


def _markdown_table(columns: Sequence[str], rows: Sequence[Mapping[str, object]]) -> str:
    header = "| " + " | ".join(columns) + " |"
    separator = "| " + " | ".join("---" for _ in columns) + " |"
    body = ["| " + " | ".join(_cell(row.get(column, "")) for column in columns) + " |" for row in rows]
    return "\n".join((header, separator, *body))


def _cell(value: object) -> str:
    if value is None:
        text = ""
    elif isinstance(value, bool):
        text = "True" if value else "False"
    elif isinstance(value, Mapping):
        text = json.dumps(value, sort_keys=True)
    elif isinstance(value, (list, tuple)):
        text = ", ".join(_cell(item) for item in value)
    else:
        text = str(value)
    return text.replace("\n", " ").replace("|", "\\|")


def _mapping_value(payload: Mapping[str, object], key: str) -> Mapping[str, object]:
    value = payload.get(key, {})
    if not isinstance(value, Mapping):
        return {}
    return value


def _sequence_value(value: object) -> tuple[object, ...]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return tuple(value)
    if value in (None, ""):
        return ()
    return (value,)


def _count_status(status_counts: Mapping[str, object], status: str) -> int:
    raw_count = status_counts.get(status, 0)
    if isinstance(raw_count, int):
        return raw_count
    if isinstance(raw_count, float) and raw_count.is_integer():
        return int(raw_count)
    return 0


def _evidence_sequence(result: Mapping[str, object]) -> tuple[Mapping[str, object], ...]:
    evidence = result.get("evidence", ())
    if not isinstance(evidence, Sequence) or isinstance(evidence, (str, bytes, bytearray)):
        return ()
    normalized: list[Mapping[str, object]] = []
    for item in evidence:
        if isinstance(item, Mapping):
            normalized.append(item)
    return tuple(normalized)


def _joined_evidence_field(evidence_items: Sequence[Mapping[str, object]], field_name: str) -> tuple[object, ...]:
    return tuple(item.get(field_name, "") for item in evidence_items)


def _validate_adapter_diagnostics(adapter_diagnostics: Sequence[object]) -> None:
    for raw_diagnostic in adapter_diagnostics:
        diagnostic = _require_mapping(raw_diagnostic, "adapter_diagnostics[]")
        status = str(diagnostic.get("status", ""))
        if status in {"OK", "FAIL"}:
            raise ValueError("Adapter diagnostics must not contain OK or FAIL statuses")


def _require_list(value: object, source_name: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"{source_name} must contain a JSON array")
    return value


def _require_mapping(value: object, source_name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{source_name} must contain a JSON object")
    return value


__all__ = ["GeometryMarkdownReportResult", "render_geometry_markdown_report_from_artifact_dir"]
