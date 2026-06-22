"""Compact deterministic C14.1-P1 tabular report writer."""
from __future__ import annotations
from collections.abc import Mapping, Sequence
from pathlib import Path
import csv
_TABLE_COLUMNS: Mapping[str, tuple[str, ...]] = {
    "executive_summary": ("metric", "value"),
    "beam_section_checks": (
        "section", "material", "assigned_beam_count", "stories",
        "width_mm", "width_limit_mm", "width_status",
        "absolute_depth_value_mm", "absolute_depth_limit_mm", "absolute_depth_status",
        "slab_thickness_mm", "three_times_slab_thickness_mm", "depth_vs_slab_status",
        "depth_width_ratio", "depth_width_limit", "depth_width_status",
        "centerline_length_min_mm", "centerline_length_max_mm", "clear_span_mm",
        "clear_span_candidate_min_mm", "clear_span_candidate_max_mm",
        "web_detailing_trigger_status", "web_detailing_trigger_reason", "span_depth_status",
        "fck_mpa", "fck_limit_mpa", "material_status", "overall_status", "evidence_tables",
    ),
    "unsupported_beam_sections": (
        "section", "section_family", "assigned_beam_count", "stories",
        "sample_labels", "sample_unique_names", "reason", "coverage_impact",
    ),
    "column_section_checks": (
        "section", "material", "assigned_column_count", "stories", "width_mm", "depth_mm",
        "minimum_dimension_mm", "minimum_dimension_limit_mm", "minimum_dimension_status",
        "area_mm2", "area_limit_mm2", "area_status", "aspect_ratio", "aspect_ratio_limit",
        "aspect_ratio_status", "fck_mpa", "fck_limit_mpa", "material_status",
        "overall_status", "evidence_tables",
    ),
    "unsupported_column_sections": (
        "section", "section_family", "assigned_column_count", "stories",
        "sample_labels", "sample_unique_names", "reason", "coverage_impact",
    ),
    "check_detail": (
        "element_type", "section", "material", "check_id", "check_title", "value", "limit",
        "unit", "comparison", "status", "ratio", "ratio_type", "evaluation_level", "tbdy_ref",
        "evidence_table", "evidence_columns", "raw_values", "normalized_values",
    ),
    "diagnostic_summary": (
        "status", "code", "count", "affected_element_type", "sample_component_ids", "sample_sections",
    ),
    "guardrails": ("metric", "value"),
    "boundary_notes": ("topic", "note"),
}
def write_minimum_compliance_tabular_report(*, output_dir: Path, tables: Mapping[str, Sequence[Mapping[str, object]]]) -> Mapping[str, str]:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    paths: dict[str, str] = {}
    markdown: list[str] = ["# Beam + Column Minimum Compliance Report", ""]
    for name, columns in _TABLE_COLUMNS.items():
        rows = tuple(tables.get(name, ()))
        path = root / f"{name}.csv"
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(columns), extrasaction="ignore")
            writer.writeheader()
            for row in rows:
                writer.writerow({column: _cell(row.get(column)) for column in columns})
        paths[f"{name}_csv"] = str(path)
        markdown.extend(_markdown_table(name, columns, rows))
    markdown_path = root / "minimum_compliance_report.md"
    markdown_path.write_text("\n".join(markdown).rstrip() + "\n", encoding="utf-8")
    paths["minimum_compliance_report_md"] = str(markdown_path)
    return paths
def table_columns() -> Mapping[str, tuple[str, ...]]:
    return dict(_TABLE_COLUMNS)
def _markdown_table(name: str, columns: Sequence[str], rows: Sequence[Mapping[str, object]]) -> list[str]:
    lines = [f"## {name}", "", "| " + " | ".join(columns) + " |", "| " + " | ".join("---" for _ in columns) + " |"]
    lines.extend("| " + " | ".join(_markdown_cell(row.get(column)) for column in columns) + " |" for row in rows)
    if not rows:
        lines.append("| " + " | ".join("" for _ in columns) + " |")
    return [*lines, ""]
def _cell(value: object) -> object:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, tuple, set, frozenset)):
        return "; ".join(str(item) for item in value)
    if isinstance(value, Mapping):
        return "; ".join(f"{key}={value[key]}" for key in sorted(value, key=str))
    return value
def _markdown_cell(value: object) -> str:
    return str(_cell(value)).replace("|", "\\|").replace("\n", "<br>")
__all__ = ["table_columns", "write_minimum_compliance_tabular_report"]
