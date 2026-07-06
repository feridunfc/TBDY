"""C13.1-like model-level product report assembled from safe source-table evidence.

P2.0 deliberately keeps this layer small and data-oriented.  It consumes the
accepted ``product_report_source_tables.json`` artifact produced by the safe
FeatureResolver/live-smoke evidence path, or the same shape in fixture mode.  It
never calls ETABS, never mutates a model, never runs analysis/design, and never
uses the CheckEngine.

P2.1 keeps the product behavior stable and polishes only deliverables: the full
report remains canonical, the summary is concise, and heavy diagnostics are
moved into a separate evidence file.

P2.2 adds truthful scope/status language and a package manifest. It does not
add engineering checks and it never recasts the product slice as full TBDY
compliance.
"""
from __future__ import annotations

import html
import json
import shutil
from pathlib import Path
from typing import Any, Mapping, Sequence

from tools.render_product_report import TABLE_COLUMNS, TABLE_TITLES, build_product_summary
from tbdy_engine.product_reports.report_package import write_report_package

SPRINT = "P2.2_TRUTHFUL_REPORT_PACKAGE_SCOPE_MANIFEST"
CANONICAL_PRODUCT_SPRINT = "P2.0_C13_1_LIVE_PRODUCT_REPORT_PARITY"

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
    "checked_scope_status",
    "model_scope_status",
    "full_tbdy_compliance_status",
    "unsupported_object_count_total",
    "excluded_frame_object_count_total",
    "frame_assignment_type_counts",
    "source_frame_assignment_row_count",
    "frame_assignment_type_counts_reconciled",
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

HEAVY_SUMMARY_KEYS: tuple[str, ...] = (
    "beam_section_detail_rows",
    "column_section_detail_rows",
    "beam_section_type_results",
    "column_section_type_results",
    "modal_mass_full_table_rows",
    "source_table_rows",
    "sample_beams",
    "sample_columns",
)

_EVIDENCE_KEYS: tuple[str, ...] = (
    "beam_section_type_results",
    "column_section_type_results",
    "beam_section_detail_rows",
    "column_section_detail_rows",
    "unsupported_sections",
    "unsupported_beam_sections",
    "unsupported_column_sections",
    "modal_mass_summary",
    "modal_mass_full_table_rows",
    "modal_mass_final_verdict_rows",
    "source_tables_path",
)

_REPORT_TABLES: tuple[tuple[str, str, str], ...] = (
    ("1. Executive Summary", "executive_summary", "executive_summary_rows"),
    ("2. Concrete Beam Section Geometry Checks", "concrete_beam_section_geometry_checks", "concrete_beam_section_geometry_checks"),
    ("3. Unsupported / Out-of-Scope Beam Sections", "unsupported_beam_sections", "unsupported_beam_sections"),
    ("4. Concrete Column Section Geometry Checks", "concrete_column_section_geometry_checks", "concrete_column_section_geometry_checks"),
    ("5. Unsupported / Out-of-Scope Column Sections", "unsupported_column_sections", "unsupported_column_sections"),
    ("6. Beam Section Detail", "beam_section_detail", "beam_section_detail_rows"),
    ("7. Column Section Detail", "column_section_detail", "column_section_detail_rows"),
    ("8. Modal Mass Full Table", "modal_mass_full_table", "modal_mass_full_table_rows"),
    ("9. Modal Mass Final Verdict", "modal_mass_final_verdict", "modal_mass_final_verdict_rows"),
    ("10. Guardrails", "guardrails", "guardrail_rows"),
    ("11. Boundary Notes", "boundary_notes", "boundary_note_rows"),
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


def _copy_if_exists(src: Path, dst: Path) -> None:
    if not src.is_file():
        return
    try:
        if src.resolve() == dst.resolve():
            return
    except FileNotFoundError:
        pass
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def _source_tables_payload(input_dir: Path) -> Mapping[str, Any]:
    path = Path(input_dir) / "product_report_source_tables.json"
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    return payload if isinstance(payload, Mapping) else {}


def _source_table_rows(source: Mapping[str, Any], table_key: str) -> list[dict[str, Any]]:
    tables = source.get("tables") if isinstance(source, Mapping) else None
    table = tables.get(table_key) if isinstance(tables, Mapping) else None
    if not isinstance(table, Mapping):
        return []
    rows = table.get("rows") or table.get("parsed_rows") or []
    return [dict(row) for row in rows if isinstance(row, Mapping)]


def _first_present_value(row: Mapping[str, Any], aliases: Sequence[str]) -> Any:
    direct = {str(key): key for key in row.keys()}
    folded = {str(key).replace(" ", "").replace("_", "").casefold(): key for key in row.keys()}
    for alias in aliases:
        if alias in direct:
            value = row.get(direct[alias])
            if value not in (None, ""):
                return value
        folded_key = folded.get(alias.replace(" ", "").replace("_", "").casefold())
        if folded_key is not None:
            value = row.get(folded_key)
            if value not in (None, ""):
                return value
    return None


def _frame_type_bucket(row: Mapping[str, Any]) -> str:
    raw = _first_present_value(row, ("Type", "FrameType", "ObjectType"))
    if raw in (None, ""):
        return "Null"
    normalized = str(raw).strip().casefold()
    if normalized == "beam":
        return "Beam"
    if normalized == "column":
        return "Column"
    if normalized == "brace":
        return "Brace"
    if normalized in {"null", "none", "unassigned", ""}:
        return "Null"
    return "Other"


def _frame_assignment_type_counts(source: Mapping[str, Any]) -> tuple[dict[str, int], int, bool]:
    rows = _source_table_rows(source, "frame_assignments")
    counts = {"Beam": 0, "Column": 0, "Brace": 0, "Null": 0, "Other": 0}
    for row in rows:
        counts[_frame_type_bucket(row)] += 1
    row_count = len(rows)
    return counts, row_count, sum(counts.values()) == row_count


def _modal_fail_count(summary: Mapping[str, Any]) -> int:
    count = 0
    for key in ("modal_ux_status", "modal_uy_status"):
        status = summary.get(key)
        if status not in ("OK", None):
            count += 1
    return count


def _truth_status_summary(summary: Mapping[str, Any], source: Mapping[str, Any]) -> dict[str, Any]:
    frame_counts, source_row_count, reconciled = _frame_assignment_type_counts(source)
    unsupported_object_count_total = int(summary.get("unsupported_beam_object_count") or 0) + int(summary.get("unsupported_column_object_count") or 0)
    excluded_frame_object_count_total = (
        unsupported_object_count_total
        + int(frame_counts.get("Brace", 0))
        + int(frame_counts.get("Null", 0))
        + int(frame_counts.get("Other", 0))
    )
    checked_has_data = bool(summary.get("concrete_beam_section_type_count")) and bool(summary.get("concrete_column_section_type_count")) and bool(summary.get("modal_mass_table_rows"))
    checked_fail_count = int(summary.get("beam_fail_count") or 0) + int(summary.get("column_fail_count") or 0) + _modal_fail_count(summary)
    if checked_fail_count:
        checked_scope_status = "FAIL"
    elif not checked_has_data:
        checked_scope_status = "NO_DATA"
    else:
        checked_scope_status = "PASS"

    if checked_scope_status == "FAIL":
        model_scope_status = "FAIL"
    elif checked_scope_status == "NO_DATA":
        model_scope_status = "NO_DATA"
    elif excluded_frame_object_count_total:
        model_scope_status = "PASS_WITH_EXCLUSIONS"
    else:
        model_scope_status = "PASS"

    return {
        "checked_scope_status": checked_scope_status,
        "model_scope_status": model_scope_status,
        "full_tbdy_compliance_status": "NOT_EVALUATED",
        "unsupported_object_count_total": unsupported_object_count_total,
        "excluded_frame_object_count_total": excluded_frame_object_count_total,
        "frame_assignment_type_counts": frame_counts,
        "source_frame_assignment_row_count": source_row_count,
        "frame_assignment_type_counts_reconciled": reconciled,
        "excluded_frame_object_count_basis": (
            "unsupported beam/column section assignments plus Brace, Null, and Other frame assignment types "
            "from product_report_source_tables.json; this is intentionally conservative when source inventory is incomplete"
        ),
    }


def _truth_notice_lines(executive: Mapping[str, Any]) -> list[str]:
    return [
        "This report is NOT full TBDY compliance.",
        f"full_tbdy_compliance_status = {executive.get('full_tbdy_compliance_status', 'NOT_EVALUATED')}",
        f"checked_scope_status = {executive.get('checked_scope_status')}",
        f"model_scope_status = {executive.get('model_scope_status')}",
        "The checked product scope is limited to the implemented live ETABS product slice.",
        "Unsupported/out-of-scope objects are visible and are not silently ignored.",
        "Legacy booleans product_slice_passed and report_product_passed are product-slice compatibility signals only, not full TBDY compliance.",
    ]


def _stable_source_tables_path(summary: Mapping[str, Any]) -> str | None:
    raw = summary.get("source_tables_path")
    if raw in (None, ""):
        return None
    # Keep product JSON deterministic across output directories while preserving
    # the source artifact identity expected by this product command.
    return "product_report_source_tables.json"


def _fmt(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, float):
        return f"{value:.6g}"
    if isinstance(value, list):
        return ", ".join(_fmt(item) for item in value)
    if isinstance(value, Mapping):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def _table_columns(report: Mapping[str, Any], summary: Mapping[str, Any], summary_key: str, report_key: str) -> list[str]:
    if summary_key == "executive_summary_rows":
        return ["metric", "value"]
    if summary_key == "modal_mass_full_table_rows":
        modal_columns = [str(column) for column in (summary.get("modal_mass_summary") or {}).get("columns", [])]
        if modal_columns:
            return modal_columns
        rows = report.get(report_key) or []
        return list(rows[0].keys()) if rows else []
    return list(TABLE_COLUMNS.get(summary_key, []))


def _rows_for_table(report: Mapping[str, Any], summary_key: str, report_key: str) -> list[dict[str, Any]]:
    if summary_key == "executive_summary_rows":
        executive = report.get("executive_summary") if isinstance(report.get("executive_summary"), Mapping) else {}
        return [{"metric": field, "value": executive.get(field)} for field in EXECUTIVE_SUMMARY_FIELDS]
    if report_key == "guardrails":
        guardrails = report.get("guardrails") if isinstance(report.get("guardrails"), Mapping) else {}
        return [{"guardrail": key, "value": guardrails.get(key)} for key in sorted(guardrails)]
    if report_key == "boundary_notes":
        notes = report.get("boundary_notes") if isinstance(report.get("boundary_notes"), Mapping) else {}
        return [{"item": key, "statement": notes.get(key)} for key in sorted(notes)]
    rows = report.get(report_key) or []
    return [dict(row) for row in rows if isinstance(row, Mapping)]


def _md_table(headers: Sequence[str], rows: Sequence[Mapping[str, Any]]) -> str:
    if not headers:
        return "_No rows._"
    out = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    for row in rows:
        out.append("| " + " | ".join(_fmt(row.get(header)).replace("\n", " ") for header in headers) + " |")
    return "\n".join(out)


def render_product_markdown(report: Mapping[str, Any], summary: Mapping[str, Any]) -> str:
    executive = report.get("executive_summary") if isinstance(report.get("executive_summary"), Mapping) else {}
    lines = [
        "# TBDY Minimal Live Product Report - C13.1",
        "",
        "Concrete rectangular assigned beam and column geometry screening + unsupported section classification + full modal mass table.",
        "",
        "## Truth and Scope Notice",
        "",
    ]
    lines.extend(f"- {line}" for line in _truth_notice_lines(executive))
    lines.append("")
    for title, report_key, summary_key in _REPORT_TABLES:
        rows = _rows_for_table(report, summary_key, report_key)
        headers = _table_columns(report, summary, summary_key, report_key)
        lines.extend([
            f"## {title}",
            "",
            f"Table name: `{TABLE_TITLES.get(summary_key, report_key)}`",
            "",
            _md_table(headers, rows),
            "",
        ])
    return "\n".join(lines)


def _html_table(caption: str, headers: Sequence[str], rows: Sequence[Mapping[str, Any]]) -> str:
    if not headers:
        return f"<p><strong>{html.escape(caption)}:</strong> no rows.</p>"
    head = "".join(f"<th>{html.escape(str(header))}</th>" for header in headers)
    body_lines = []
    for row in rows:
        cells = "".join(f"<td>{html.escape(_fmt(row.get(header)))}</td>" for header in headers)
        body_lines.append(f"<tr>{cells}</tr>")
    body = "\n".join(body_lines)
    return f"<table><caption>{html.escape(caption)}</caption><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def render_product_html(report: Mapping[str, Any], summary: Mapping[str, Any]) -> str:
    title = "TBDY Minimal Live Product Report - C13.1"
    executive = report.get("executive_summary") if isinstance(report.get("executive_summary"), Mapping) else {}
    truth_notice = "".join(f"<li>{html.escape(line)}</li>" for line in _truth_notice_lines(executive))
    sections = []
    for title_text, report_key, summary_key in _REPORT_TABLES:
        rows = _rows_for_table(report, summary_key, report_key)
        headers = _table_columns(report, summary, summary_key, report_key)
        table_name = TABLE_TITLES.get(summary_key, report_key)
        sections.append(
            "<section>"
            f"<h2>{html.escape(title_text)}</h2>"
            f"<p><strong>Table name:</strong> <code>{html.escape(table_name)}</code></p>"
            f"{_html_table(table_name, headers, rows)}"
            "</section>"
        )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>{html.escape(title)}</title>
  <style>
    body {{ font-family: Arial, sans-serif; max-width: 1400px; margin: 32px auto; padding: 0 20px; line-height: 1.45; }}
    table {{ border-collapse: collapse; margin: 12px 0 28px; width: 100%; font-size: 13px; }}
    caption {{ text-align: left; font-weight: 700; margin-bottom: 6px; }}
    th, td {{ border: 1px solid #ddd; padding: 6px 8px; vertical-align: top; }}
    th {{ background: #f3f3f3; }}
    code {{ background: #f7f7f7; padding: 2px 4px; border-radius: 4px; }}
    .scope-warning {{ border: 2px solid #555; padding: 12px 16px; background: #fafafa; margin: 18px 0 28px; }}
  </style>
</head>
<body>
  <h1>{html.escape(title)}</h1>
  <section class="scope-warning"><h2>Truth and Scope Notice</h2><ul>{truth_notice}</ul></section>
  {''.join(sections)}
</body>
</html>
"""


def build_c13_1_product_report(input_dir: Path, out_dir: Path) -> dict[str, Any]:
    """Build the frozen C13.1-like product report shape from source tables.

    ``input_dir`` must contain ``product_report_source_tables.json`` and may
    contain ``product_slice_manifest.json``. The returned payload is the product
    report contract for P2.0/P2.1; it is not a CheckResult schema and does not
    emit engineering PASS/FAIL beyond this explicit product-slice screening
    output.
    """
    summary = build_product_summary(Path(input_dir), Path(out_dir))
    source_payload = _source_tables_payload(Path(input_dir))
    truth_summary = _truth_status_summary(summary, source_payload)
    enriched_summary = dict(summary)
    enriched_summary.update(truth_summary)
    executive_summary = {field: enriched_summary.get(field) for field in EXECUTIVE_SUMMARY_FIELDS}
    guardrails = dict(summary.get("guardrails") or _rows_to_mapping(summary.get("guardrail_rows"), "guardrail", "value"))
    boundary_notes = _rows_to_mapping(summary.get("boundary_note_rows"), "item", "statement")

    report = {
        "metadata": {
            "sprint": CANONICAL_PRODUCT_SPRINT,
            "deliverable_sprint": SPRINT,
            "source_tables_path": _stable_source_tables_path(summary),
            "full_tbdy_compliance_status": "NOT_EVALUATED",
            "report_product_passed_semantics": "Legacy product-slice compatibility boolean only; not full TBDY compliance.",
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
        "scope_manifest": truth_summary,
        "compatibility": {
            "p2_0_product_report_shape_preserved": True,
            "report_product_passed_semantics": "Product-slice compatibility boolean; not full-model or full-TBDY compliance.",
            "table_contract_keys": list(PRODUCT_REPORT_KEYS),
        },
    }
    return report


def build_product_summary_deliverable(report: Mapping[str, Any], summary: Mapping[str, Any]) -> dict[str, Any]:
    """Return the concise, stable ``product_summary.json`` payload for P2.1."""
    executive = report.get("executive_summary") if isinstance(report.get("executive_summary"), Mapping) else {}
    payload: dict[str, Any] = {field: executive.get(field) for field in EXECUTIVE_SUMMARY_FIELDS}
    payload["metadata"] = {
        "sprint": SPRINT,
        "canonical_report_file": "product_report.json",
        "evidence_file": "product_evidence.json",
        "source_tables_path": _stable_source_tables_path(summary),
    }
    return payload


def build_product_evidence_deliverable(report: Mapping[str, Any], summary: Mapping[str, Any]) -> dict[str, Any]:
    """Return deterministic diagnostics moved out of ``product_summary.json``."""
    evidence = {
        "metadata": {
            "sprint": SPRINT,
            "canonical_report_file": "product_report.json",
            "summary_file": "product_summary.json",
            "source_tables_path": _stable_source_tables_path(summary),
        },
        "beam_section_type_results": list(summary.get("beam_section_type_results") or []),
        "column_section_type_results": list(summary.get("column_section_type_results") or []),
        "beam_section_detail_rows": list(report.get("beam_section_detail") or []),
        "column_section_detail_rows": list(report.get("column_section_detail") or []),
        "unsupported_sections": list(summary.get("unsupported_sections") or []),
        "unsupported_beam_sections": list(report.get("unsupported_beam_sections") or []),
        "unsupported_column_sections": list(report.get("unsupported_column_sections") or []),
        "modal_mass_summary": dict(summary.get("modal_mass_summary") or {}),
        "modal_mass_selected_rows": list((summary.get("modal_mass_summary") or {}).get("selected_rows") or []),
        "modal_mass_final_verdict_rows": list(report.get("modal_mass_final_verdict") or []),
        "source_references": {
            "source_tables_path": _stable_source_tables_path(summary),
            "product_report_source_tables_file": "product_report_source_tables.json",
        },
        "scope_status_summary": dict(report.get("scope_manifest") or {}),
    }
    # Keep a stable marker list so tests can reject accidental summary bloat.
    evidence["moved_from_product_summary"] = list(_EVIDENCE_KEYS)
    return evidence


def write_c13_1_product_report(input_dir: Path, out_dir: Path) -> dict[str, Any]:
    """Write stable P2.2 deliverables without changing P2.0 product behavior."""
    input_dir = Path(input_dir)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    _copy_if_exists(input_dir / "product_report_source_tables.json", out_dir / "product_report_source_tables.json")
    _copy_if_exists(input_dir / "product_slice_manifest.json", out_dir / "product_slice_manifest.json")

    summary = build_product_summary(input_dir, out_dir)
    report = build_c13_1_product_report(input_dir, out_dir)
    summary_deliverable = build_product_summary_deliverable(report, summary)
    evidence_deliverable = build_product_evidence_deliverable(report, summary)

    _write_json(out_dir / "product_report.json", report)
    _write_json(out_dir / "product_summary.json", summary_deliverable)
    _write_json(out_dir / "product_evidence.json", evidence_deliverable)
    (out_dir / "product_report.md").write_text(render_product_markdown(report, summary), encoding="utf-8")
    (out_dir / "product_report.html").write_text(render_product_html(report, summary), encoding="utf-8")
    write_report_package(out_dir, report, summary_deliverable)
    return report
