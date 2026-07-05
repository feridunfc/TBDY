"""C13.1-like model-level product report assembled from safe source-table evidence.

P2.0 deliberately keeps this layer small and data-oriented.  It consumes the
accepted ``product_report_source_tables.json`` artifact produced by the safe
FeatureResolver/live-smoke evidence path, or the same shape in fixture mode.  It
never calls ETABS, never mutates a model, never runs analysis/design, and never
uses the CheckEngine.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from tools.render_product_report import build_product_summary, render_markdown

SPRINT = "P2.0_C13_1_LIVE_PRODUCT_REPORT_PARITY"

PRODUCT_REPORT_KEYS: tuple[str, ...] = (
    "executive_summary",
    "concrete_beam_section_geometry_checks",
    "unsupported_beam_sections",
    "concrete_column_section_geometry_checks",
    "unsupported_column_sections",
    "beam_section_detail",
    "column_section_detail",
    "modal_mass_full_table",
    "modal_mass_final_verdict",
    "guardrails",
    "boundary_notes",
)

EXECUTIVE_SUMMARY_FIELDS: tuple[str, ...] = (
    "product_slice_passed",
    "report_product_passed",
    "concrete_beam_section_type_count",
    "concrete_beam_object_count",
    "unsupported_beam_section_type_count",
    "unsupported_beam_object_count",
    "concrete_column_section_type_count",
    "concrete_column_object_count",
    "unsupported_column_section_type_count",
    "unsupported_column_object_count",
    "beam_fail_count",
    "column_fail_count",
    "modal_mass_table_rows",
    "modal_threshold",
    "modal_ux_status",
    "modal_uy_status",
    "total_fail_count",
)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _rows_to_mapping(rows: Any, key_name: str, value_name: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if not isinstance(rows, list):
        return out
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        key = row.get(key_name)
        if key in (None, ""):
            continue
        out[str(key)] = row.get(value_name)
    return out


def build_c13_1_product_report(input_dir: Path, out_dir: Path) -> dict[str, Any]:
    """Build the frozen C13.1-like product report shape from source tables.

    ``input_dir`` must contain ``product_report_source_tables.json`` and may
    contain ``product_slice_manifest.json``. The returned payload is the product
    report contract for P2.0; it is not a CheckResult schema and does not emit
    engineering PASS/FAIL beyond this explicit product-slice screening output.
    """
    summary = build_product_summary(Path(input_dir), Path(out_dir))
    executive_summary = {field: summary.get(field) for field in EXECUTIVE_SUMMARY_FIELDS}
    guardrails = dict(summary.get("guardrails") or _rows_to_mapping(summary.get("guardrail_rows"), "guardrail", "value"))
    boundary_notes = _rows_to_mapping(summary.get("boundary_note_rows"), "item", "statement")

    report = {
        "metadata": {
            "sprint": SPRINT,
            "source_tables_path": summary.get("source_tables_path"),
            "excel_production_path_used": False,
            "streamlit_ui_used": False,
            "legacy_runtime_used": False,
            "check_engine_executed": False,
            "check_result_emitted": False,
            "etabs_model_mutated": False,
            "analysis_run": False,
            "design_run": False,
        },
        "executive_summary": executive_summary,
        "concrete_beam_section_geometry_checks": list(summary.get("concrete_beam_section_geometry_checks") or []),
        "unsupported_beam_sections": list(summary.get("unsupported_beam_sections") or []),
        "concrete_column_section_geometry_checks": list(summary.get("concrete_column_section_geometry_checks") or []),
        "unsupported_column_sections": list(summary.get("unsupported_column_sections") or []),
        "beam_section_detail": list(summary.get("beam_section_detail_rows") or []),
        "column_section_detail": list(summary.get("column_section_detail_rows") or []),
        "modal_mass_full_table": list(summary.get("modal_mass_full_table_rows") or []),
        "modal_mass_final_verdict": list(summary.get("modal_mass_final_verdict_rows") or []),
        "guardrails": guardrails,
        "boundary_notes": boundary_notes,
        "compatibility": {
            "legacy_summary_keys_retained_in_product_summary_json": True,
            "table_contract_keys": list(PRODUCT_REPORT_KEYS),
        },
    }
    return report


def write_c13_1_product_report(input_dir: Path, out_dir: Path) -> dict[str, Any]:
    """Write ``product_report.json``, ``product_report.md`` and compatibility JSON.

    ``product_report.json`` is the P2.0 contract output. ``product_summary.json``
    remains available for C13.0/C13.1 compatibility and debugging.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = build_product_summary(Path(input_dir), out_dir)
    report = build_c13_1_product_report(Path(input_dir), out_dir)
    _write_json(out_dir / "product_report.json", report)
    _write_json(out_dir / "product_summary.json", summary)
    (out_dir / "product_report.md").write_text(render_markdown(summary), encoding="utf-8")
    return report
